# 14 — Appearance ReID: design and go/no-go
### Sentinel · Matching a vehicle across cameras when its plate is not read

**Status: designed, not built.** Written 8 October 2026 as an option for the
finale. **Default decision: no-go before 12 October** — present this design and
the plate-ladder bridge that already exists ([13 — Showcase Prep §7](./13-SHOWCASE-PREP.md)).
Build it only if every condition in §6 holds by Friday 9 October, 18:00.

---

## 1. The gap

Every stored sighting today is a **plate read**: a `Detection` row exists only
when the multi-frame vote resolves a plate of six or more characters
([`pipeline.py`](../services/edge_agent/src/edge_agent/analytics/pipeline.py)).
A vehicle whose plate is never read — too small, dirty, at night, angled away —
leaves no trace, so no route can include it.

The existing bridge in
[`_bridge_unread_hops`](../services/core_api/src/core_api/detections/service.py)
only reaches *partially* read plates (same last four characters, ≤ 3 edits,
same class and colour, reachable at road speed). It cannot reach a vehicle with
no read at all.

## 2. Design

```
edge: track ends ──► best crop ──► embedding (512-d) ──► vehicle.detected event
                                                            │  (+ embedding on every plate read)
core: vehicle_sightings hypertable ◄────────────────────────┘
route: confirmed hops A ─(gap)─ B  ──► candidates in the gap:
         reachable from A and to B at ≤ 120 km/h  ∧  same class  ∧  cosine ≥ τ
       ──► probable hop, match_rung = "appearance", similarity shown
```

### 2.1 Edge: emit a sighting per vehicle track

- **Where:** `AnprPipeline`. Keep the best crop per track (largest
  bounding-box area, sharpness above a floor) while it is alive; when
  `_prune_stale_voters` sees the track age out, embed that crop once and emit
  `EventType.VEHICLE_DETECTED` — the enum value already exists and is unused.
- **Plate reads carry an embedding too**, so every confirmed hop can seed a
  search.
- **Embedding model:** a general-purpose image encoder exported to ONNX
  (DINOv2-small, Apache-2.0, or CLIP ViT-B/32 image tower, MIT). One forward
  pass **per track, not per frame**, so ~30–50 ms on CPU is affordable. Avoid
  vehicle-ReID weights trained on VeRi-776 or VehicleID: those datasets are
  licensed for research only.
- **Fallback descriptor** if the model is too slow on the M4: a 128-bin HSV
  histogram of the crop plus class and aspect ratio. Weak, but explainable and
  ~1 ms.
- **Cost guard:** emission is rate-limited per camera, and `d_registry_only`
  and `c_motion_gated` cameras do not emit.

### 2.2 Core: store and search

- New hypertable `vehicle_sightings` (`event_id`, `observed_at`, `camera_id`,
  `vehicle_class`, `vehicle_colour`, `embedding real[512]`, `snapshot_uri`,
  `bbox`, `track_id`), partitioned on `observed_at` like `detections`; a nullable
  `embedding` column on `detections`. Same tenancy (RLS) and retention rules.
- **No new extension at demo scale:** filter by time window, reachable cameras
  and class in SQL, then cosine similarity in Python over a few hundred rows.
  At 80,000 cameras: pgvector or OpenSearch k-NN, partitioned by district and day.
- **Route integration:** after the existing rungs, for each gap between two
  confirmed hops, add at most one `appearance` hop per camera, chosen by
  highest similarity above τ. Always `confirmed=False`, drawn dashed amber,
  similarity shown, and **never** raises a watchlist alert on its own.
- **New endpoint:** `GET /api/v1/sightings/{event_id}/similar?window=` —
  "find this vehicle elsewhere", from any sighting.

### 2.3 Console

The hop panel shows the probable hop's crop beside the nearest confirmed hop's
crop, with the similarity score and the words *"appearance match — confirm on
the frame"*. The Movement Report lists appearance hops in their own section.

### 2.4 Calibration and honesty

- Calibrate τ on the own-car footage ([13 §6.5](./13-SHOWCASE-PREP.md)) plus
  the gov mirror: positive pairs are the same track across cameras, negatives
  are different vehicles of the same class and colour. Pick τ for ≤ 5% false
  matches; record the precision/recall in `evidence/`.
- Same-model, same-colour vehicles (white hatchbacks, autorickshaws) are the
  failure mode. The speed gate and per-gap limit contain it; the "probable"
  label and operator confirmation are the actual safeguard.

## 3. Effort

| Piece | Estimate |
|---|---|
| Model export + edge embedding + emission + tests | 0.5 day |
| Migration, ingest, route rung, `similar` endpoint + tests | 0.5–0.75 day |
| Console hop panel + report section | 0.5 day |
| Calibration on own footage, evidence write-up | 0.5 day |
| **Total** | **≈ 2–2.5 focused days** |

## 4. Risk to the finale

- It touches `pipeline.py` and `worker.py`, the code path the mandatory
  vehicle trace depends on, three days before a live evaluation.
- A new model adds CPU per track on a laptop whose analysis budget is already
  the binding constraint ([13 §6.2](./13-SHOWCASE-PREP.md)).
- An appearance hop shown wrongly in front of the jury damages the credibility
  of every correct hop.

## 5. Mitigations if built

- Behind a setting, **off by default** (`SENTINEL_REID_ENABLED=false`); the
  plate pipeline is untouched when it is off.
- Edge embedding off the capture loop (thread pool), so a slow embed cannot
  stall a camera.
- `make check` and the M4 UAT re-run with it on and with it off.

## 6. Go/no-go (Friday 9 October, 18:00)

Build only if **all** hold:

1. The M4 UAT has passed and the gov mirror is committed.
2. The own-car three-camera drill has produced a plate-confirmed route (the
   positives needed for calibration exist).
3. Two people can spend Saturday on it without taking rehearsal time.

Otherwise: do not build. Present §1–§2 as the next step and show the existing
bridge. A designed-and-costed feature stated plainly scores better than a
fragile one shown live.

---

*Back to [13 — Showcase Prep](./13-SHOWCASE-PREP.md) ·
[01 — Architecture §6.3](./01-ARCHITECTURE.md).*
