# 09 · Secondary Analytics (M13)

*Companion to [05-DELIVERY-PLAN.md](./05-DELIVERY-PLAN.md)'s M13 milestone:
"Vehicle class/colour/coarse-make; zone rules (intrusion, loitering,
wrong-way, stopped vehicle); camera tamper detection." Exit bar: "reliable
analytics beyond ANPR" — an explicit bonus criterion. Face recognition was
excluded by decision (see
[00-SOLUTION-PLAN §9](./00-SOLUTION-PLAN.md)); the freed time went into
vehicle attributes and zone rules instead, kept honest below against what's
actually implemented.*

---

## 1. Vehicle colour classification

**Decision: an HSV heuristic, not a trained classifier.** Colour
classification from a bounding-box crop is a genuinely simpler problem than
plate OCR — a small, fixed palette (white/black/silver/grey/red/blue/
green/yellow/other) is separable by saturation/value thresholds and hue
ranges without training data or an extra model in the inference budget.

**What's real:**

- `edge_agent/analytics/colour.py`: `classify_vehicle_colour()` takes the
  vehicle's cropped BGR pixels, converts to HSV, and buckets by
  saturation/value (achromatic: white/grey/black by value; chromatic: hue
  range lookup for red/orange/yellow/green/blue/violet, folded into the
  fixed palette).
- Wired into `AnprPipeline._classify_colour()`, called once per confirmed
  vehicle track alongside plate OCR, so it costs nothing extra beyond a
  crop + `cv2.cvtColor`.
- `Detection.vehicle_colour` column (migration `08e724ff6b3a`), surfaced
  through `DetectionIn`/`DetectionOut` schemas and `ingest_detection`.
- 11 unit tests over the colour buckets (`test_colour.py`) plus one
  pipeline-integration test confirming the field actually reaches the
  emitted detection event.

**Honest gap:** this is colour only. "Coarse-make" (vehicle manufacturer/
model, e.g. "Maruti Swift" vs "Hyundai i20") is explicitly **out of scope**
— it requires a genuinely different trained classifier (fine-grained
visual categorisation, not a heuristic), which is a real model-training
exercise this session did not undertake. Listed here rather than silently
dropped or falsely claimed.

---

## 2. Camera tamper detection

**Decision: frame statistics, not a trained model.** The three tamper
modes worth detecting in practice — a lens covered, a lens smeared/
defocused, a camera physically knocked or re-aimed — all show up as gross,
easily-computed shifts in the raw frame, not subtle patterns needing a
classifier.

**What's real:**

- `edge_agent/analytics/tamper.py`'s `TamperDetector` flags:
  - **covered** — near-uniform pixel intensity (low overall variance)
    sustained across consecutive frames.
  - **blurred** — sustained low Laplacian variance (the standard
    focus-measure operator; a sharp frame has high-frequency edges, a
    defocused one doesn't).
  - Each mode requires *sustained* evidence across several frames before
    flagging, so a single dark frame or a momentary glare does not count.
- Runs inside the existing per-camera health-reporting loop in
  `worker.py`'s `_report_health`/`_run_camera` — no separate polling path,
  no extra model download.
- `Camera.tamper_status` column (migration `3a9af9c7bca1`), surfaced
  through `CameraHealthUpdate`/`CameraOut` schemas and
  `update_camera_health`/`camera_to_out`.
- Frontend: `Cameras.tsx` has a **Tamper** column;
  `SeverityBadge.tsx`'s `tamperToSeverity()` maps `ok` → neutral,
  `covered`/`blurred`/`moved` → warning, `view_lost` → high.
- **Verified live in-browser**: a styled "covered" badge rendered in the
  Cameras table against a real camera reporting real tamper state.

### 2a. Camera angle changed — an alert, not just a badge

A camera that is knocked by wind, turned by a miscreant, or loosened on its
mount still streams, so health checks stay green while the camera watches
the wrong road. The original "moved" check compared frame histograms; on
real footage it flickered with traffic and lighting and never raised an
alert. It is replaced by a view monitor that compares *where things are*.

- `edge_agent/analytics/view_monitor.py`'s `ViewMonitor` keeps a reference
  view per camera and every 2 s matches ORB features (480-px greyscale,
  contrast-equalised) against it, then fits a rotation + shift + scale with
  RANSAC. Moving vehicles and people are outliers; the fixed scene decides.
- States `learning → ok → moved | view_lost`. It learns from three
  agreeing checks, raises **view shifted** after three consecutive
  checks (≈6 s) with the measured shift and rotation, and **view not
  recognised** after ≈60 s with no match (turned to face somewhere else,
  or sprayed). Three aligned checks close the alert as **restored**.
- It re-anchors every 2 min while aligned, so day-to-night light changes
  do not drift into false alarms, and after 15 min in a new position the
  new view is adopted (someone re-aimed it on purpose and nobody reset it).
- Frames with too little texture (night, fog, covered lens) are skipped,
  so the covered/blurred checks own those cases.
- The worker posts `/api/v1/camera-events` with **before/after snapshots**
  and the camera's burned-in clock time; the server keeps one open alert
  per camera and kind (`camera_events` table, migration `b7d2e4f6a8c0`,
  department RLS), pushes an SSE `camera_event`, and closes it
  automatically when the view comes back (`resolved_by = "system: view
  restored"`). Acknowledge/resolve/false-alarm are audited.
- Console: a **"Camera view changed"** banner, and **Alerts → Camera
  views** shows the before and after frames side by side with triage
  actions. The Cameras **Tamper** column shows *Moved* / *View lost*.
- PTZ cameras that are meant to move opt out with the camera attribute
  `view_monitoring: off`.

**Measured on the mirrored government footage (cam01, cam24, cam30):** no
false alarm on untouched footage, rain and haze, a bus filling the frame,
or ±1% wind shake; a 12% knock detected ≈4 s after it happened; a 6°
rotation measured to within a degree; a camera turned to another scene
reported as not recognised at ≈58 s. Cost is 35–60 ms of CPU per check,
i.e. under 3% of one core per camera at one check every 2 s. cam06's
corrupted stream gives neither detections nor false alarms.

**Demo:** `make angle-demo` replays mirrored cam01 as camera `angle-demo`
from 300 s into the recording (before that the stitched clip's burned-in
clock jumps backwards), knocks it 12% at 60 s and puts it back at 180 s. The
burned-in clock stays fixed, as it would on a real camera, and reads ≈21:06:3x
at the knock and ≈21:08:3x at the restore. Run `make angle-demo-worker`
alongside it (2 fps; at 8 fps a second worker on a laptop falls behind live
and the alert arrives a minute late); `make angle-demo-stop` ends it.
Measured live: alert 6 s after the knock, closed 6 s after the restore.

Tests: `test_tamper.py`, `test_view_monitor.py` (13),
`test_worker_view_change.py` (10), `test_camera_events_api.py` (8),
`apps/web/tests/camera-view.spec.ts` (2).

---

## 3. Zone rules engine

**Decision: hand-rolled polygon geometry over normalised coordinates, no
new geometry dependency.** Zones are simple, mostly-convex regions (a
lane, a gate, a loading bay); ray-casting point-in-polygon is a dozen lines
and avoids pulling in `shapely` for a problem this small. Coordinates are
normalised to `[0, 1]` per axis so a zone definition is resolution-
independent — the same zone works whether the camera streams at 640×480
or 1920×1080.

**What's real:**

- `edge_agent/analytics/zone_rules.py`: `Zone` (polygon + rule type +
  thresholds), `ZoneEvent` (fired violation), `ZoneRuleEngine` (stateful,
  keyed per tracked-vehicle-id):
  - **intrusion** — fires once when a track's position enters the
    polygon; resets when it exits, so re-entry fires again.
  - **loitering** / **stopped_vehicle** — fire once a track's dwell time
    inside the zone (loitering: any movement; stopped_vehicle: near-zero
    speed specifically) exceeds a configurable threshold, tracked via a
    per-track `fired_rules` set so a single continuous dwell fires once,
    not once per frame; cleared on exit or resumed movement.
  - **wrong_way** — fires once a track's heading sustains a deviation
    beyond tolerance from the zone's configured expected direction;
    cleared when heading returns within tolerance.
  - A `_TrackState.positions` rolling window (default 5 s) backs both the
    `speed()` and `heading_deg()` computations used by the above.
- Backend: `Zone`/`ZoneEvent` ORM models with `FORCE ROW LEVEL SECURITY`
  policies matching M12's department-tenancy pattern (migration
  `6943898d1be1`); `core_api/zones/` (schemas + service) and
  `core_api/routers/zones.py`, registered in `app.py`.
- Edge wiring: `worker.py`'s `_load_zone_engine()` fetches a camera's
  configured zones over a real HTTP call at startup — the same "build it
  like a real integration, default to nothing configured" pattern used
  for M11's government-registry providers, rather than hardcoding zones
  into the worker. `_evaluate_zones()` runs the engine against
  `AnprPipeline.last_tracked_vehicles` each frame and POSTs any fired
  events back to core.
- Frontend: `CameraDetailModal.tsx`'s new `ZoneRulesSection` — a
  preset-region picker (full frame / left / right / top / bottom / centre
  third, since free-hand polygon drawing was out of scope for the time
  available), a rule-type selector, a zone list, and a recent-events
  list. `types.ts`/`api.ts` gained the corresponding `Zone`/`ZoneCreate`/
  `ZoneEvent` types and `zonesApi` client.
- 12 unit tests (`test_zone_rules.py`, covering all four rule types plus
  fire/reset semantics) and 7 `test_zones_service.py` tests.
- **Verified live in-browser, end to end**: opened a real camera's detail
  modal against the running dev stack, created a "Highway Shoulder" /
  `stopped_vehicle` zone through the UI, and confirmed it rendered
  correctly in the zone list — against a live synthetic camera feed
  actually running through the edge worker.

**Honest gap:** zone *shape* is limited to six coarse presets, not
free-hand polygon drawing on the video canvas — the underlying engine
supports arbitrary polygons (it's just point-in-polygon over a coordinate
list), but a drag-to-draw canvas editor was descoped as a UI investment
not justified by the time remaining relative to its marginal value over
the presets.

---

## 3a. People: counting and zone intrusion, never identity

The official evaluation lists person detection next to vehicle detection. The
vehicle detector's COCO model already finds people, so the same single inference
now reports them (`DETECTED_CLASSES` in `vehicle_detector.py`):

- **Counting.** Each heartbeat carries the most people and vehicles seen in one
  analysed frame since the last (`people_in_view`, `vehicles_in_view`). The
  Cameras screen shows them under the ANPR rate: crowd and queue counting with
  no extra model.
- **Zones.** People are tracked on their own tracker and held to intrusion and
  loitering zones (a person standing still is not a stopped vehicle, and has no
  wrong way). Their zone events are labelled `person` in the queue.
- **No identity.** People are never read, matched or followed across cameras.
  Faces in evidence stay blurred. This keeps the no-face-recognition position.
- **Vehicles are unaffected.** People get their own non-maximum suppression, so
  a rider's box can never suppress the motorcycle under them. On 120 real
  government-grid frames: 185 people found in 90 frames, and zero vehicle boxes
  lost against vehicle-only detection.

---

## 4. Verification summary

- Full backend suite at the time of this milestone: **353 tests passing**
  (up from 298 at the end of M12; 359 after the M14/M15 work), `mypy` and `ruff` clean across `packages`, `services`, `tests`.
- Frontend: `npm run build` (the authoritative `tsc -b` + Vite build)
  clean.
- All three features additionally verified against the *live* dev stack
  (real Postgres, a real edge worker driving 8 synthetic cameras, real
  browser interaction) — not unit tests alone standing in for integration
  proof.
