# 16 — Technical Q&A: how the algorithms actually work
### Sentinel · for the technical jury (NIT Surat, DA-IICT) · 13 October 2026

Every number and parameter below is read from the code or the evidence files,
not the design docs: if a professor asks "what is the threshold", this is the
answer the code gives. File paths are under `services/edge_agent/src/edge_agent/`
(edge) and `services/core_api/src/core_api/` (core) unless stated.

---

## 0. How to answer

Professors are testing whether you understand **why**, and whether you know
your **limits**. Answer every algorithm question in four beats, about thirty
seconds:

1. **What it does**, in one sentence.
2. **The decision and its reason** — what you chose over the obvious
   alternative, and why.
3. **The number** — measured, with its sample size.
4. **The limit** — what it does not do. Say it before they find it.

> *"The tracker is a SORT-style Kalman filter with Hungarian assignment on IoU.
> We stepped the filter by the video's own timestamps instead of per frame,
> because these streams deliver 3 to 25 fps with gaps — a per-frame filter
> turns every gap into a velocity error. It's single-stage association, not
> ByteTrack's two-stage, so a vehicle detected at low confidence through an
> occlusion can get a new id; the vote resets with it."*

If you do not know, say *"I don't know — here's how I'd find out"*. Never
guess a number.

---

## 1. The whole pipeline on one page

```
camera RTSP ──► relay (one pull per camera) ──► decode
   │
   ├─ StreamClock: PTS → time; detects loop cuts (sentinel_core/clock.py)
   ├─ AnalysisScheduler: which frames to analyse, by tier
   │
   ▼  per analysed frame
 YOLO11n (640², vehicles + people) ──► NMS
   ▼
 Kalman + Hungarian IoU tracker (PTS-timed)        ──► people: counted, zones
   ▼  per vehicle track
 ROI crop (≥640 px of real frame) ──► YOLOv9-t plate detector ──► pad 10%/15%
   ▼
 CCT-XS OCR: one character per slot, with per-character confidence
   ▼
 grammar correction (within ambiguity class only) ──► PlateVoter (per track)
   ▼
 ≥6 chars? valid Indian grammar? changed since last emit?   ── no ─► drop
   ▼ yes
 camera clock: PP-OCRv6 reads overlay; accepted only if a second reading agrees
   ▼
 dedupe on (plate, camera's printed second) ──► face-blurred snapshot ──► event (~1 KB)
   ▼
 HTTP to core (durable SQLite outbox if core is down)
   ▼  core
 ingest (DB dedupe index) ──► watchlist match (exact / ambiguity key) ──► alert
                              route search: exact → ambiguity → 1 edit → bridge
                              feasibility: haversine speed > 150 km/h flagged
```

The design rule under all of it: **time is the video's presentation timestamp
(PTS) for ordering and the camera's printed clock for evidence — never the
time a frame arrived.**

---

## 2. Edge, stage by stage

### 2.1 Stream time — `sentinel_core/clock.py`

- Every frame carries its PTS. A backwards jump of more than 250 ms, or a
  forward jump over 10 s, is a **discontinuity** (a loop point or a camera
  reboot); a gap over 1 s is flagged so motion models widen their uncertainty.
- On a discontinuity the tracker, voters and clock readings are all reset —
  otherwise one track id would span two unrelated vehicles.
- **Why not arrival time?** The gateway replays a buffered group of pictures
  on connect, so the first frames arrive faster than real time; arrival-time
  logic computes impossible velocities after every reconnect. Asserted in
  `tests/test_compliance.py`.

### 2.2 Which frames to analyse — `analytics/scheduler.py`

| Tier | Rule | Use |
|---|---|---|
| `a_continuous` | every frame, or every `stride`-th | priority junctions |
| `b_sampled` | `sampled_fps` (default 8), paced by PTS | most cameras |
| `c_motion_gated` | frame difference at 4 fps on a 160-px thumbnail; analyse at `sampled_fps` while > 1% of pixels change by > 25 grey levels, and 3 s after | quiet scenes |
| `d_registry_only` | never opened | view-only |

- **Why 8 fps?** A vehicle is in shot 1–3 s, so 8 fps gives the voter 8–24
  reads, at about a third of a 25 fps camera's cost.
- Today's demo runs cam06 at 4 fps with stride 3.

### 2.3 Vehicle detection — `analytics/vehicle_detector.py`

- **YOLO11n**, exported to ONNX, 640×640 letterboxed input, ONNX Runtime with
  the CoreML provider on Apple silicon (5–8× faster than CPU-only here).
- Anchor-free head; per-box class = argmax of class scores; overlapping boxes
  removed with OpenCV's NMS. Classes kept: car, motorcycle, bus, truck, and
  person (people are tracked separately, never read).
- About **11 ms per frame** on the laptop.
- **Licence:** YOLO11n is AGPL-3.0, the one copyleft part; RF-DETR (Apache-2.0)
  is the identified replacement.

### 2.4 Tracking — `analytics/tracker.py`

- **State:** `[cx, cy, w, h, vx, vy]`, constant-velocity on the centre, size
  tracked directly. Measurement: `[cx, cy, w, h]`.
- **Time-varying transition:** rebuilt on every update from Δt = ΔPTS:
  `x += vx·Δt`; process noise scales with Δt (position 0.08 px²/s, velocity
  5.12 (px/s)²/s — tuned per frame at 8 fps, then expressed per second so the
  filter behaves the same at any frame rate).
- **Association:** predicted boxes vs detections, IoU matrix, **Hungarian
  assignment** (`scipy.optimize.linear_sum_assignment`, O(n³), n ≈ vehicles in
  shot, so trivial). Match only if IoU ≥ 0.3.
- **Lifecycle:** a track survives **3.75 s of footage** unmatched (30 frames at
  8 fps), measured in PTS, not frames.
- **Why not DeepSORT / ByteTrack?** DeepSORT needs a re-identification network
  per box (more compute, another model); the reference ByteTrack code (BoxMOT)
  is AGPL. Ours is ~250 lines, MIT.
- **Limit:** single-stage association. ByteTrack's second pass (low-confidence
  detections against unmatched tracks) is not implemented, so a long occlusion
  can split a track. A split costs a vote reset, never a wrong plate.

### 2.5 Plate detection — `analytics/plate_reader.py`, `pipeline._crop_roi`

- The vehicle's box plus a 10% margin, then **widened to at least 640 px of
  the real frame**. The plate detector resizes its input to 640 anyway; a tight
  140×230 crop would be upscaled ~5× and interpolation cannot invent strokes.
  Taking real pixels instead roughly **tripled valid reads** on wide-angle
  footage.
- **YOLOv9-t** plate detector (end-to-end ONNX, NMS in the graph), confidence
  ≥ 0.4.
- Plate box padded **10% horizontally, 15% vertically**: the detector's box
  clipped the last character of small plates.

### 2.6 OCR — `fast-plate-ocr`, model `cct-xs-v2-global`

- A compact convolutional transformer that classifies a **fixed number of
  character slots**, each with its own confidence (a softmax per slot). The
  per-character confidences are what the voter weighs.
- ~49 ms per plate crop on CPU — the most expensive stage, which is why the
  voter skips reads once a plate is settled (2.8).
- **Model choice was measured, not assumed:** on our holdout `cct-xs-v2` read
  4× more plates exactly than `cct-s-v2` (the larger model) and ran ~6× faster.

### 2.7 Indian grammar correction — `sentinel_core/plates.py`

- Format: `SS DD L{1,3} N{1,4}` (state, district, series, number), plus Bharat
  series `NN BH NNNN L{1,2}`; the state code must be one of 37 RTO codes.
- **Correction:** for each layout (district 1–2 digits × series 1–3 letters,
  four-digit number) that fits the read's length, coerce each position to its
  required type **within its ambiguity class only** (`Q→0`, `0→D`, `5→S`…).
  If no layout fits, or two layouts give different answers, the read is left
  unchanged.
- **Invariant:** a correction never changes the ambiguity key, so it can never
  move a read to a different rung of the matching ladder. It never invents a
  missing character.
- Effect, measured: exact per-crop reads went **35 → 53** (of the 80 crops
  the detector found), and it helped both halves of a vehicle-wise split, so
  it is not overfitting.

### 2.8 Temporal voting — `analytics/voting.py`

Per vehicle track, all reads so far are resolved into one plate:

1. **Choose the length.** Popularity alone is wrong: a distant plate yields
   many truncated reads that agree with each other. So: if any read is a valid
   full registration (four-digit number), vote among those lengths; else any
   valid plate; else all reads. Take the modal length in that pool.
   (Measured: 8-character reads were 1% valid, 9-character 60%.)
2. **Vote per position**, weighted by each read's per-character confidence.
3. A position is **uncertain** if the winner holds < 60% of the weight —
   shown, not hidden.
4. **Settled** after 6 reads with a valid, unanimous result; then only every
   8th frame is read (to catch a tracker id switch). An unreadable track backs
   off to every 3rd frame after 24 attempts.

Effect: **65.4% exact per crop → 80.5% exact per vehicle after the vote.**

### 2.9 What gets reported — `analytics/pipeline.py`

A voted plate is emitted only if: ≥ 6 characters (a one-edit search on "1"
matches everything), valid Indian grammar (93% of raw reads on the grid were
not), and changed since the track's last emission. Unconfirmed plates keep
being read; a later valid read of the same track is still reported.

### 2.10 The camera's clock — `analytics/frame_clock.py`

- **What:** the date and time each camera burns into its frame is the only time
  a sighting is ever reported with.
- **How it reads:** PP-OCRv6 (PaddleOCR's detector and recogniser, ONNX, via
  `rapidocr`). The first read searches the frame's top and bottom bands (132 ms
  median); later reads only recognise the remembered box (~21 ms). It reads at
  most once a second of footage, more often while a vehicle in shot has no
  clock frame yet (max 2/s).
- **Why agreement, not confidence:** the recogniser reads damaged digits with
  full confidence. So a reading `r₁` at PTS `t₁` is accepted only if another
  reading `r₂` at `t₂` satisfies:

  `|(r₁ − r₂) − (t₁ − t₂)| ≤ 2 s`, with `0.9 s ≤ |t₁ − t₂| ≤ 300 s`

  The 0.9 s floor exists because frames 40 ms apart share the same compression
  damage and confirmed each other's misread on the grid.
- **Evidence frame:** the newest frame of that vehicle whose clock is verified
  becomes the snapshot, so the time in the report is the time visible in the
  image. If none verifies: **"time unknown"**, never another time.
- **Measured:** 97.7% exact on 87 hand-labelled frames, **zero wrong**
  (Tesseract: 69.0%, one wrong). 37.4% of stream-seconds across all 30 grid
  cameras get a verified time; most of the rest have no legible clock.

### 2.11 One read per printed second

Key = (plate, camera's printed time), remembered at the edge (last 4,096) and
enforced again by a database index on (camera, plate, camera time). A looped
recording, a reconnect replay or two tracks on one vehicle produce one
sighting, not many. Reads with no camera time are left alone — nothing says two
of them are one moment.

### 2.12 The rest of the edge

| Analytic | Method | Honest limit |
|---|---|---|
| Vehicle colour | HSV histogram on the central 60% of the vehicle box; achromatic (white/grey/black) by saturation and value first | A heuristic, not a trained classifier |
| Camera covered / blurred | Mean brightness < 15, or Laplacian variance < 20, sustained 0.5 s of footage | Thresholds hand-set |
| Camera moved | ORB keypoints on the fixed scene, matched to a remembered view, RANSAC similarity transform; traffic falls out as outliers; CLAHE for lighting | Validated on recorded footage, not a field trial |
| Face blur | YuNet (OpenCV DNN) on every snapshot; Gaussian blur; original kept in a separate, unserved store, revealed only with a stated reason | Misses some small faces |
| People | Counted and held to zones (intrusion, loitering); never identified | No face recognition, by decision |
| Offline | Detections that cannot be delivered go to a SQLite outbox, replayed oldest first, idempotent on event id | 72 h is the design figure for districts; the laptop's outbox is size-bound by disk |

---

## 3. Core: search, alerts, evidence

### 3.1 The matching ladder — `detections/service.py`

Search stops at the first rung that finds anything:

| Rung | Rule | Index / cost | Shown as |
|---|---|---|---|
| 1 Exact | normalised plate equal | B-tree, O(log n) | confirmed |
| 2 Ambiguity | same ambiguity key: `O D Q→0`, `I L→1`, `Z→2`, `S→5`, `B→8`, `G→6`, `A→4` | B-tree on the stored key, O(log n) | confirmed |
| 3 One edit | query ≥ 7 chars; distinct plates in the window within one substitution/insertion/deletion; top 5 by frequency | linear in distinct plates in the window | **probable**, dashed |
| 4–5 Bridge | same last 4 chars, Levenshtein ≤ 3, **same vehicle class and colour** as every confirmed sighting, reachable at ≤ 120 km/h from the hops either side | `LIKE '%tail'` + filters | **probable** |

- **Why fold ambiguity into a key?** A fuzzy scan over every plate is
  O(n · L²); folding the confusable characters makes "is this a misread of
  that?" a single indexed equality.
- **Rung 3 at scale:** linear over distinct plates seen in the window — fine
  for a district, not for a statewide 7-day window. `pg_trgm` trigram indexing
  is in the stack for exactly this; say so.
- Probable hops are never merged silently: the plate *as read* is shown and an
  officer confirms against the frame.

### 3.2 Impossible travel

Haversine distance between consecutive cameras ÷ difference in the cameras'
printed times. Above **150 km/h**, the hop is flagged, not drawn as a route
— a cloned plate, a wrong camera clock, or a misread. Under 50 m, speed is 0
(same junction).

### 3.3 Watchlist and alerts — `watchlist/service.py`

- Every confirmed read is matched against active entries on rungs 1–2 at
  ingest, in the same transaction.
- **Dedup:** same plate, same camera, within 5 minutes → one alert with a
  rising sighting count. A pass replayed by a loop (same printed time within
  1 minute) never re-alerts.
- **Priority score** = priority weight (low .25 … critical 1.0) × read
  confidence × rung weight (exact 1.0, ambiguity .7).
- **Watch for this vehicle** = arm an entry **and** retro-scan every stored
  read, so a vehicle seen before the watch alerts immediately.
- Alerts reach every open console over server-sent events, typically within a
  second of the read being stored.

### 3.4 Evidence integrity

- **Audit log:** append-only hash chain, `row_hash = SHA-256(prev_hash ‖
  canonical(row))`, genesis constant. A Postgres transaction-scoped advisory
  lock serialises appends, so two concurrent writers cannot fork the chain.
  *Verify integrity* recomputes every row; the DR drill proved an edited row
  is caught.
- **Movement Report:** a ZIP of PDF, CSV and frames with a manifest of
  per-file SHA-256s; `report_sha256 = SHA-256(pdf_sha ‖ ":" ‖ csv_sha)`.
- **Access:** department scoping is Postgres row-level security
  (`current_setting('app.current_department_id')`), not just a UI filter.

---

## 4. How the numbers were measured

| Claim | Set | Method | 95% interval |
|---|---|---|---|
| **80.5%** plates exact after voting | 33 of 41 vehicles | 160 plate crops from government-grid snapshots; labelled by a person **blind to the OCR**; 79 unreadable to a person excluded; the vote approximated by voting a vehicle's crops | **66–90%** |
| 65.4% exact per crop | 53 of 81 legible crops | same | 55–75% |
| 88.6% characters correct | 81 crops | same | — |
| **97.7%** clock exact, 0 wrong | 85 of 87 frames with a legible clock | 158 frames hand-labelled; replay over all 30 cameras for coverage | **92–99%** |
| ~16 analysed fps on one laptop | dense synthetic scene, real worker | `scripts/measure_tier_capacity.py`; 4 cams × 4 fps kept up | — |
| 27–40 s median read latency | two evidence runs | footage time → stored row; mostly the vote waiting for agreement | p90 67–87 s |

- **Overfitting guard:** every accuracy change was scored on the full set and
  on two halves split by vehicle; a change was kept only if it helped both.
  It started at **8.6%** with the configured model; the measurement drove the
  fixes.
- **Say the interval** if asked about 41 vehicles: *"80.5%, and with 41
  vehicles the 95% interval is roughly 66 to 90 — the pilot's first job is a
  bigger labelled set from live feeds."*
- **The vote is approximated:** crops of one plate stand in for one track's
  frames; a live track gives the voter 5–15 reads, not 1–3, so live accuracy
  should be at least this, but that is an expectation, not a measurement.

---

## 5. Scale arithmetic — `docs/04-SCALE-PLAN.md`

Five formulas; offer to recompute with their camera mix.

```
events/s    = Σ cameras_tier × events/hour_tier ÷ 3600
            = (9,600×150 + 22,400×20 + 28,000×5) ÷ 3600  ≈ 563/s
backbone    = 563 × (1 KB event + 30 KB snapshot) ≈ 17.5 MB/s ≈ 140 Mbps
            vs 80,000 × 2 Mbps = 160 Gbps to centralise video
GPUs        = Σ cameras_tier × analysed fps ÷ 300 fps per L4
            = (96,000 + 44,800 + 8,400) ÷ 300 ≈ 497 → ≈ 560 with N+1
storage     ≈ 390 TB usable (selective) vs 12.1 PB for one week of all video
```

- **300 fps per L4 is a vendor-benchmark estimate** (≈ 4.7 ms per analysed
  frame, TensorRT FP16, batched). Measured: ~16 fps on a laptop CPU. The
  pilot's first exit criterion is measuring the GPU figure.
- The tier split (12/28/35/25%) is our planning assumption, not a survey.

---

## 6. Questions to expect, and the answer

**"Why not one end-to-end model, or a vision-language model, for the plate?"**
Cost and control. A detect-then-read chain runs ~60 ms per vehicle on a CPU
with no internet; a VLM is orders of magnitude more compute per frame across
80,000 cameras. And each stage gives a measurable, fixable error — we fixed the
crop, the padding and the grammar separately and measured each.

**"Why not train your own OCR on Gujarat plates?"**
That is the next step and the pilot's first work item. We had no labelled
Gujarat set; we built one (160 crops) to *measure*, and the measurement — not
training — took us from 8.6% to 80.5%. Fine-tuning needs thousands of labelled
plates from live feeds.

**"Your accuracy is on 41 vehicles. Is that significant?"**
It is an estimate with a wide interval: 66–90% at 95%. We publish the
interval, and every change was validated on two vehicle-wise halves.

**"How do you handle two-row plates, fancy fonts, non-standard plates?"**
Two-row: 3 in the holdout, all read. Fancy fonts and non-standard plates fail
the grammar check and are not reported — by design, since a wrong plate is
worse than none. A plate that never validates still shows as a vehicle
(class, colour, track) but not as a searchable read.

**"What about night, rain, motion blur?"**
Night is visible today: cam06's night footage gave 3 distinct valid plates in
14 minutes, against dozens in daylight. The vote helps with blur (more frames); nothing fixes a
20-pixel plate. That is why tiers and camera choice matter: analyse cameras
whose plates are legible.

**"Why Kalman + IoU and not optical flow or DeepSORT?"**
Vehicles at junction cameras move smoothly over 1–3 s; constant velocity
fits. IoU association needs no appearance model, so no second network per
box. The cost is identity switches under long occlusion, which the voter
absorbs (a reset, not a wrong plate).

**"How do you know a clock reading is right if the OCR is confident and
wrong?"**
We don't trust confidence. Two readings at least 0.9 s of footage apart must
agree with the footage between them to within 2 s. A single inserted digit
moves a time by minutes or hours, so it cannot agree.

**"What if the same plate is on two vehicles — a cloned plate?"**
The feasibility gate: two sightings implying > 150 km/h are flagged as
impossible, not drawn as a route.

**"What is the latency, and why is it 30 seconds?"**
Median 27–40 s from the moment in the footage to the stored sighting, mostly
deliberate: the vote waits for frames to agree. The alert itself reaches
consoles within a second of storage. Near-real-time for investigation, not
for boom gates.

**"Could you do this without plates — re-identify a vehicle by appearance?"**
Partly today: the bridge rung uses class, colour, partial plate and road-speed
reachability, returned as probable. Full appearance ReID (an embedding per
vehicle) is designed and costed (`docs/14-APPEARANCE-REID-DESIGN.md`), not
built.

**"How does this scale computationally — what's the bottleneck?"**
At the edge, the plate reader (~49 ms/crop on CPU, ~30 reads/s per laptop),
which is why reads are skipped once a vote settles. At the core, events are
563/s statewide — modest; the core is storage and query, not throughput. Rung
3 of search is linear and needs trigram indexing at statewide scale.

**"What did you get wrong?"**
The first OCR model read 8.6%. An early grammar fixer invented characters and
was reverted. The clock reader's first version let frames 40 ms apart confirm
each other's misread. Each is documented in `evidence/`.

---

## 7. Do not say

- That it is real-time, or sub-second. It is near-real-time.
- That it re-identifies vehicles without a plate.
- Any accuracy above 80.5%, or without "measured on 41 vehicles".
- That the GPU figure is measured.
- That the VAHAN / eGujCop connectors are live — they run against mocks.
- That it works at 80,000 cameras — it is sized for 80,000; it ran on 30.

---

*See also [02 — ANPR Pipeline](./02-ANPR-PIPELINE.md),
[evidence/ANPR-ACCURACY.md](../evidence/ANPR-ACCURACY.md),
[evidence/CLOCK-READER-ACCURACY.md](../evidence/CLOCK-READER-ACCURACY.md),
[04 — Scale Plan](./04-SCALE-PLAN.md), [15 — Demo Book](./15-DEMO-BOOK.md).*
