# 02 — ANPR Pipeline
### Sentinel · Model selection, accuracy engineering and Apple Silicon execution

> All latency figures marked **(measured)** were benchmarked on a **base M2 (4P+4E, 16 GB)** with `onnxruntime 1.30.0`. The demo machine is an **M4**, which should land roughly 1.5–2× higher — but that multiplier is an *inference, not a measurement*. **Re-run the benchmark scripts on the M4 and quote only measured numbers to the jury.**

> **Planning-figure correction (M15).** Figures of "~50 cameras" and references to a
> `GET /api/ingest` catalogue endpoint in this document date from planning, before the
> grid was accessible. The real grid assigned to us has **30 cameras**, and our host
> serves its catalogue at **`GET /cameras.json`** behind a session-cookie login — the
> integrator guide's `/api/ingest` path 404s there, because that guide is a shared
> template with `<host>` placeholders. The planning text is left as written rather than
> quietly rewritten, so the record of what was assumed stays visible; where this
> document states a present-tense fact, trust the README and `evidence/`.

> **Implementation status (M2, this session):** the pipeline described below is built, tested and verified against real models — not just researched. See [`services/edge_agent/src/edge_agent/analytics/`](../services/edge_agent/src/edge_agent/analytics) (`vehicle_detector.py`, `tracker.py`, `plate_reader.py`, `voting.py`, `pipeline.py`), 35 unit tests covering pre/post-processing and voting with constructed data (no model weights needed for CI), plus three real-model verifications: a static-image smoke test (`scripts/smoke_test_anpr.py`), a 500-frame live-capture integration run against the synthetic grid with zero crashes, and a measured full-chain throughput of **~14.7 fps (67.9 ms/frame)** on this base M2 (one vehicle/frame; CoreML EP for both detectors, CPU EP for OCR, per the execution-provider policy in section 3). The one thing **not yet done**: a real accuracy number on Indian plates — `scripts/eval_anpr.py` is built and works, but needs a hand-labelled holdout from real footage to mean anything (section 7). Tracking is a SORT-style Kalman+IoU tracker (a documented simplification of full ByteTrack — see section 2.1); a keypoint-based rectification stage (section 2, step 4) was deferred as a "Should" enhancement since fast-alpr's built-in crop handling already reads cleanly on frontal test imagery.

---

## 1. Pipeline

```
RTSP (TCP) ─ VideoToolbox decode ─ frame scheduler (PTS-driven, motion-gated)
   │
   ├─[1] Vehicle detection ........ YOLO26n / YOLO11n ONNX @640, ORT CoreML EP
   ├─[2] Multi-object tracking .... SORT-style tracker (Kalman+IoU) → stable vehicle_track_id
   ├─[3] Plate detection .......... yolo-v9-t-640-license-plate-end2end, CoreML EP
   │                                 (run on the vehicle ROI, not the full frame)
   ├─[4] Rectification ............ YOLOv8m-Pose 4-corner keypoints → perspective warp
   ├─[5] OCR ...................... fast-plate-ocr CCT-S, ORT **CPU EP**
   ├─[6] Temporal voting .......... per-slot confidence accumulation over the track
   └─[7] Validation ............... Indian plate grammar + RTO state-code check
   │
   └──→ one high-confidence plate per vehicle → ANPR event → correlation
```

**Why two detection stages rather than one full-frame plate detector.** Detecting the vehicle first gives a track ID, which is what makes temporal voting possible; it shrinks the plate-detection search region (≈2 ms on an ROI versus 7.7 ms full-frame); and it yields vehicle class/colour attributes that the correlation engine uses for re-identification when the plate is unreadable. The extra stage pays for itself three times over.

**Why temporal voting is the single biggest accuracy lever.** A vehicle is in frame for 1–3 seconds. At 5 analytic fps that is 5–15 independent reads of the same plate. Per-character confidence voting across those reads beats *any* single-frame model, including much larger ones — and `fast-plate-ocr` returns per-character confidences natively, so it is cheap to implement.

---

## 2. Model selection

| # | Stage | Choice | Licence | Measured latency (M2) | Notes |
|---|---|---|---|---|---|
| 1 | Vehicle detection | **YOLO26n** ONNX @640 via ORT **CoreML EP** | AGPL-3.0 | **8.70 ms / 114.9 fps** (YOLO11n, measured) | YOLO26n COCO mAP50-95 40.9, 2.4 M params. Apache alternative below. |
| 2 | Tracking | **SORT-style tracker** (Kalman filter + Hungarian IoU assignment), our own ~150-line MIT implementation | MIT (vendored) | negligible | Single-stage association — the honest simplification of full ByteTrack's two-confidence-stage matching, which is a documented, bounded upgrade (not a hidden gap). BoxMOT (AGPL) was avoided entirely; needs no ReID net. Upgrade path: two-stage association, or BoT-SORT (HOTA 69.68) / OccluBoost (HOTA 71.10) via BoxMOT if the AGPL trade is later accepted. |
| 3 | Plate detection | **`ankandrew/open-image-models` `yolo-v9-t-640-license-plate-end2end`**, CoreML EP | **MIT** | **7.69 ms / 130 fps** full-frame (measured) | Repo-reported P 0.966 / R 0.896 / mAP50 0.958. The only *permissively licensed pretrained* plate detector found. |
| 4 | Rectification | **`PrasannaBAImodel/license-plate-keypoint-detection`** (YOLOv8m-Pose, 4 corners) → `cv2.getPerspectiveTransform` | Apache-2.0 | ~10 ms, only on plate crops | Pose mAP50 0.9264 / mAP50-95 0.9137. **Highest-ROI single addition for oblique CCTV angles.** |
| 5 | OCR | **`fast-plate-ocr` `cct-s-v2`**, ORT **CPU EP** | **MIT** | **10.87 ms / 92 plates per second** (measured) | Purpose-built for plates; first-class Keras-3 fine-tuning CLI that runs on a Colab T4. `cct-xs-v2` is **1.65 ms** if you need the speed. |
| 5b | OCR fallback | **PARSeq** on low-confidence crops | Apache-2.0 | ~14.87 ms | IIIT5K 99.00 / combined 95.95. Last commit Apr 2024 — usable, unmaintained. Selective second opinion only. |
| 6 | Attributes / ReID | **FastReID** (VeRi vehicle ReID) | Apache-2.0 | — | Unmaintained since Jul 2024 but the best Apache-licensed option; used for cross-camera bridging. |

**End-to-end `fast-alpr` measured at 30.00 ms/frame (33 fps) on a 1080p frame** with default provider selection. With the execution-provider fix in §3 this should fall to roughly **19 ms/frame (~52 fps)**.

### 2.1 Framework

Build on **`ankandrew/fast-alpr`** (MIT, 805★, actively maintained). It exposes pluggable `BaseOCR` / detector interfaces, so our fine-tuned weights and the PARSeq fallback drop in without forking.

**Steal Frigate's heuristics wholesale** (`blakeblackshear/frigate`, MIT — its LPR is the same architectural shape: YOLOv9 plate detector + OCR): `min_area` ≈ 1000 px so 32×32 noise is discarded · `detection_threshold` 0.7 · `recognition_threshold` 0.9 · a 0–10 `enhancement` knob (contrast/sharpen/denoise) applied before OCR · `min_plate_length` · fuzzy known-plate matching with wildcards · a `debug_save_plates` mode that is invaluable when tuning. These are years of field-tuning available for free.

### 2.2 Rejected

| Rejected | Why |
|---|---|
| **OpenALPR** | **Dead** — last commit 30 Jul 2020, Tesseract-era LBP cascades. Its 11.4k stars are historical. |
| **`parkpow/deep-license-plate-recognition`** | A client for the *paid* Plate Recognizer API. Not open-source, and would fail the mandate. |
| **RF-DETR for vehicle detection** | Apache-2.0 and more accurate (COCO AP 48.4), but **broken on CoreML EP — returns 0 detections** and is slower than CPU (8.7 fps). `open-image-models` already hard-codes its exclusion from CoreML. |
| **TrOCR / VLM-based OCR** | 62 M params minimum for a stage that runs on every tracked vehicle. 30× over budget. |
| **Neural plate super-resolution (Real-ESRGAN)** | Generic SR **hallucinates characters** on 56×34 px crops and produces confident wrong reads. In a police system that is a liability, not a feature. Use rectification + temporal voting + contrast enhancement instead. |
| **NVIDIA DeepStream** | Proprietary EULA. Named in the production scale path only, and flagged as non-open-source. |
| **Janus** | GPLv3, Linux-first, RTSP only via a plugin. MediaMTX (MIT) is strictly better for our use. |

---

## 3. Execution-provider policy ⚠️

This is the highest-value operational finding of the research, and it is counter-intuitive enough that it belongs in the HLD:

| Stage | Provider | Measured effect |
|---|---|---|
| Vehicle detection (YOLO ONNX) | **CoreML EP** | 32.62 ms → **8.70 ms** (3.7× faster) |
| Plate detection (YOLOv9 ONNX) | **CoreML EP** | 38.99 ms → **7.69 ms** (5.1× faster); `yolo-v9-s-608`: 95.62 → 11.13 ms (**8.6×**) |
| **OCR (CCT models)** | **CPU EP — explicitly pinned** | CoreML makes it **2–3× *slower*** (1.65 → 5.46 ms for `cct-xs`; 10.87 → 21.82 ms for `cct-s`) |

The `fast-plate-ocr` documentation claims CoreML gives a 5× speedup — **that claim applies only to the legacy CNN models.** The newer CCT (Compact Convolutional Transformer) models regress on CoreML because attention operators partition badly and ANE dispatch overhead dominates a sub-2 ms model. *Pin the OCR session to `CPUExecutionProvider` explicitly; do not rely on automatic provider selection.*

### 3.1 Known-broken paths — avoid these before they cost a day

1. **CoreML `.mlpackage` export of YOLO11/YOLO26 fails** on `ultralytics 8.4.158` + `coremltools 9.0` (the C2PSA attention block: *"only 0-dimensional arrays can be converted to Python scalars"*). **Workaround: export to ONNX with `opset=17, simplify=True` and use the ORT CoreML EP** — that path works and is fast.
2. **`yolo-v9-t-384` + CoreML throws on zero-detection frames** (*"dynamic shape ({-1}) but runtime shape ({0}) has zero elements"*). `open-image-models` catches it and logs a warning — meaning you **silently lose that frame**. Fix: use the 640 model, and/or set `RequireStaticInputShapes=1`.
3. Official macOS ORT wheels ship the CoreML EP built in — no custom build required.

---

## 4. India-specific work ⚠️ *this changes the plan*

**The finding:** the shipped `cct-s-v2-global-model` config declares `plate_regions` covering 66 countries — **and India is not among them.** Out-of-the-box OCR accuracy on Indian plates is therefore *unvalidated*, and no credible pretrained Indian ANPR weights exist anywhere (GitHub search returns only single-digit-star student projects with self-reported, unverifiable accuracy claims and, mostly, no released weights).

**Consequence for the plan:** your stated preference was "start off-the-shelf, fine-tune only if accuracy is poor". That remains the right *sequence* — but treat fine-tuning as **probable, not contingent**, and budget the 1–2 days for it up front in milestone M2. The global model is a warm start, not a solution.

**And regardless of accuracy: you currently have no honest way to state an accuracy number.** There is no public Indian plate benchmark with real data behind it. Building your own 500–1,000-crop Gujarat holdout set from the test-grid cameras is therefore not optional — it is the only way to put a defensible number on a slide, and almost no competing entry will have one.

### 4.1 Configuration deltas

```yaml
# plate_config.yaml — fast-plate-ocr, India
max_plate_slots: 11        # GJ01AB1234 = 10; BH-series 22BH6517A = 9; margin for stacked truck plates
alphabet: '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_'
img_height: 64
img_width: 128
image_color_mode: rgb      # keep RGB — plate colour encodes vehicle class in India
```

### 4.2 Plate grammar and post-processing

```python
STANDARD = r'^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{4}$'   # GJ01AB1234
BH_SERIES = r'^[0-9]{2}BH[0-9]{4}[A-Z]{1,2}$'          # 22BH6517A
```
Plus: strip the `IND` HSRP prefix and the hologram/chip region before OCR · validate the two-letter prefix against the 36 state/UT RTO codes (a prefix that is not a real RTO code is a misread, and knowing that fixes it) · handle two-line plates (common on motorcycles and commercial vehicles) by detecting the line break and concatenating · use **plate colour as a class signal**: white/black = private, yellow/black = commercial, black/yellow = rentable, green/white = EV. That colour signal is free, uniquely Indian, and it is a genuinely differentiating detail to show a jury.

### 4.3 Confidence and ambiguity

Every read carries per-character confidence. Characters below threshold are marked uncertain rather than guessed, and are surfaced in the UI at reduced opacity (see [03-UX-DESIGN §2.2](./03-UX-DESIGN.md)). The correlation engine then matches on **ambiguity classes** rather than on exact strings:

```
0↔O↔D    1↔I↔L    2↔Z    5↔S    8↔B    6↔G    4↔A
```

The normalised plate key folds these classes, so `GJO1AB1Z34` and `GJ01AB1234` collide on a single index lookup. This is what turns a mediocre OCR read into a successful watchlist hit — and it is the reason the matching ladder in [01-ARCHITECTURE §6.1](./01-ARCHITECTURE.md) is a ladder rather than an equality test.

---

## 5. Datasets for fine-tuning

**Licence-clean and verified to contain data:**

| Dataset | Size | Licence | Use |
|---|---|---|---|
| `ridham2k4/npds-number-plate-detection` (Kaggle) | 16,989 train / 1,535 val / 785 test, 20,597 boxes | **CC0** | ⭐ Primary Indian plate-*detection* set. Source-grouped split, no augmentation leakage. Updated Sep 2026. |
| `paneraghanshyam/gujarat-vehicle-number-plates-yolo-ready` (Kaggle) | 45.9 MB | **Apache-2.0** | ⭐ **Gujarat-specific** formats, fonts and layouts. Directly on-point for SCRB. |
| `abtexp/synthetic-indian-license-plates` (Kaggle) | 18,000 images, all 36 states/UTs | **CC0** | ⭐ OCR pretraining, especially for rare RTO codes |
| `mabo7237/license-plates-700k` (HF) | 99,744 files | **MIT** | Large global OCR pretraining corpus |
| `detectRecog/CCPD` | >300k | **MIT** | Backbone pretraining only (Chinese plates — different aspect ratio and charset) |
| `thundarstrom/traffic-vehicle-detection` (HF) | 23,319 images, 215,109 boxes, UA-DETRAC | **CC BY 4.0** | ⭐ Real fixed-intersection CCTV — exactly our camera geometry |

**Licence traps — do not touch, this is a government deliverable:**
`dataclusterlabs/indian-number-plates-dataset` (Kaggle says CC0, the HuggingFace mirror of the same data says **CC BY-NC-ND** — NoDerivatives forbids fine-tuning; conflicting licences on identical data means avoid entirely) · `saisirishan/indian-vehicle-dataset` (CC BY-NC-ND, popular but unusable) · `unidpro/*` (NC-ND commercial teasers) · any dataset with an *Unknown* licence, including `adityamangal98/HR-LR-images-of-the-Indian-License-plates`.

**A caution worth knowing:** the HuggingFace org `thundarstrom` publishes beautifully specified Indian ANPR datasets (an 18,537-crop OCR corpus, a frozen 3,034-crop "DashCop" benchmark with median 56×34 px crops). **Their file manifests contain only `.gitattributes` and `README.md` — the images were never uploaded.** The cards describe data that does not exist. It is the best-designed Indian ANPR data plan available and would be worth an email to the author, but do not plan around it.

### 5.1 Colab fine-tuning recipe

```
Detector:  CCPD-pretrain the YOLOv9 backbone
           → fine-tune on ridham2k4/npds + paneraghanshyam/gujarat  (~18k Indian images)
OCR:       pretrain cct-s on abtexp synthetic (18k) + mabo7237 (700k)
           → fine-tune on real Indian crops harvested from the test grid
Hardware:  single Colab T4/A100 is sufficient for both
Output:    ONNX export → validate CoreML EP on the M4 → version and pin in the event schema
```

Harvest training crops from your own pipeline: every detection already saves a snapshot, so a half-day of grid running produces thousands of real Gujarat crops at exactly the camera geometry you will be evaluated on. Label a stratified sample (day/night, angle, distance, motion blur) as the holdout; use the rest for fine-tuning.

---

## 6. Capacity model for the demo

**Measured concurrency ceiling on base M2:** a shared ORT session with the plate detector on CoreML EP saturates at **≈220 inferences/second** (1 thread → 128/s, 2 → 210/s, 4 → 222/s, 8 → 221/s). Latency degrades linearly past 2 threads while aggregate throughput stays flat — so the scheduler should use a **small fixed worker pool feeding a shared session**, not a thread per camera.

```
Full chain ≈ 3 inferences per analysed frame (vehicle + plate + OCR)
Base M2 :  220 inf/s ÷ 3 ≈  73 analysed frames/s  →  12–15 streams at 5 fps
M4      : ~350–440 inf/s ÷ 3 ≈ 120–145 frames/s   →  ~20–30 streams at 5 fps  (extrapolated)
```

**Fitting the ~50-camera government grid onto one M4** — this is exactly why the tiering in [01-ARCHITECTURE §4.3](./01-ARCHITECTURE.md) exists:

```
10 cameras × 5 fps  (tier A, traffic-facing)     =  50 frames/s
40 cameras × 1 fps  (tier B/C, motion-gated)     =  40 frames/s
                                          Total  =  90 frames/s   ✓ within the ~120–145 M4 budget
```

All 30 cameras are onboarded, monitored, viewable and health-tracked; analytics intensity is allocated by operational value. That is not a compromise to apologise for — **it is the same tiering logic that makes the 80,000-camera plan work**, demonstrated honestly at demo scale. Say so explicitly: *"This is not a limitation of the demo machine, it is the architecture."*

**Decode is not the bottleneck** — the inference ceiling binds first. Budget one VideoToolbox session per camera at the sub-sampled analytic rate (5 fps), not at the full 25 fps. Note that go2rtc's own testing found M1 **CPU** transcoding beat M1 GPU; measure before assuming hardware paths always win.

---

## 7. Accuracy engineering checklist

Ordered by return on effort:

1. **Temporal voting across the track** — biggest single win, near-zero cost
2. **Keypoint-quad rectification before OCR** — the highest-ROI *model* addition for oblique CCTV
3. **Format/grammar validation + RTO state-code check** — fixes misreads for free
4. **Frigate's enhancement knob** (contrast/sharpen/denoise) tuned per camera — cheap, effective
5. **Per-camera ROI and minimum plate area** — stop wasting inference on sky and pavement
6. **Reject rather than guess** — mark uncertain characters; a flagged partial read is forensically useful, a confident wrong read is a liability
7. **PARSeq second opinion** on low-confidence crops only — accuracy where it matters, cost where it does not
8. **Per-camera calibration** — a mounting angle is fixed, so plate size and skew are predictable per camera; use it

**Evaluation protocol:** a frozen holdout set (never trained on), reporting plate-level exact-match accuracy, character-level accuracy, precision/recall for detection, and a stratified breakdown by day/night, angle and distance. Every result is tagged with model versions (which the event schema already carries) so regressions are attributable. Track this in `evidence/anpr-accuracy.csv` from milestone M2 onward — the trend line itself is a persuasive artefact.

---

## 8. Licensing position

| Permissive — safe for Phase-2 commercialisation | Copyleft — fine for the hackathon, blocks closed-source productisation |
|---|---|
| `fast-alpr` MIT · `open-image-models` MIT · `fast-plate-ocr` MIT · Frigate MIT · MediaMTX MIT · go2rtc MIT · PARSeq Apache-2.0 · PaddleOCR Apache-2.0 · FastReID Apache-2.0 · plate-keypoint model Apache-2.0 · RF-DETR Apache-2.0 | **Ultralytics YOLO26/YOLO11 AGPL-3.0** · **BoxMOT AGPL-3.0** |

**Recommendation:** ship the AGPL components (Ultralytics for vehicle detection, optionally BoxMOT for tracking) and **state it plainly in the submission** — the challenge mandates "open-source technologies", and AGPL-3.0 is OSI-approved. Then show the **Apache-only migration path** on a Phase-2 slide: RF-DETR (Apache-2.0) for vehicle detection plus a vendored MIT ByteTrack. Naming the licence consequence *before the jury asks* is exactly the kind of judgement that separates a procurement-ready submission from a hackathon project.

Practical hedge: vendor a standalone MIT ByteTrack from day one (it is ~200 lines and needs no ReID network). That removes the BoxMOT AGPL dependency immediately at no cost, leaving Ultralytics as the only copyleft component — and therefore a single, cleanly swappable one.

---

## 9. Open gaps — carry these into M2

- **All latency numbers are M2 measurements.** Re-benchmark on the M4 before quoting anything.
- **No verified accuracy for any model on Indian plates exists publicly.** Every figure found (95% detection, 80–99% OCR) is a self-reported claim in a low-star repo with no published evaluation protocol. Build your own holdout set.
- **`fast-plate-ocr` CCT-v2 absolute accuracy is unpublished** — the model zoo gives latency only; the 93.3–94.19% figures belong to the *legacy* models. Do not quote a v2 accuracy number from the repo.
- **`.mlpackage` CoreML export is untested** because it is currently broken; a working export with `MLComputeUnits=CPUAndNeuralEngine` might beat the 8.70 ms ONNX path.
- **Roboflow Universe was unreachable during research** (Cloudflare 403) — check `universe.roboflow.com` manually for additional Indian plate datasets, verifying licences before use.
- **Apple hardware decode-engine counts are unverified** — Apple publishes no authoritative figure. Measure; do not quote.

---

*Back to [00-SOLUTION-PLAN](./00-SOLUTION-PLAN.md) · Next: [03-UX-DESIGN](./03-UX-DESIGN.md).*
