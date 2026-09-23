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
defocused, a camera physically knocked or panned — all show up as gross,
easily-computed statistical shifts in the raw frame, not subtle patterns
needing a classifier.

**What's real:**

- `edge_agent/analytics/tamper.py`'s `TamperDetector`: maintains a rolling
  reference frame and flags:
  - **covered** — near-uniform pixel intensity (low overall variance)
    sustained across consecutive frames.
  - **blurred** — sustained low Laplacian variance (the standard
    focus-measure operator; a sharp frame has high-frequency edges, a
    defocused one doesn't).
  - **moved** — a large frame-to-frame greyscale-histogram shift,
    indicating the field of view itself changed (pan/knock), as opposed
    to normal scene motion within a stable frame.
  - Each mode requires *sustained* evidence across several frames before
    flagging, specifically to avoid false positives on a single dark
    frame, a fast-moving foreground object, or a momentary glare.
- Runs inside the existing per-camera health-reporting loop in
  `worker.py`'s `_report_health`/`_run_camera` — no separate polling path,
  no extra model download.
- `Camera.tamper_status` column (migration `3a9af9c7bca1`), surfaced
  through `CameraHealthUpdate`/`CameraOut` schemas and
  `update_camera_health`/`camera_to_out`.
- Frontend: `Cameras.tsx` gained a **Tamper** column;
  `SeverityBadge.tsx`'s new `tamperToSeverity()` maps `ok` → neutral,
  `covered`/`blurred`/`moved` → warning-styled badges.
- 7 unit tests (`test_tamper.py`) plus 2 new `test_registry_service.py`
  tests covering the health-update wiring.
- **Verified live in-browser**: screenshot-confirmed a styled "covered"
  badge rendering correctly in the Cameras table against a real camera
  reporting real tamper state.

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

## 4. Verification summary

- Full backend suite: **353 tests passing** (up from 298 at the end of
  M12), `mypy` and `ruff` clean across `packages`, `services`, `tests`.
- Frontend: `npm run build` (the authoritative `tsc -b` + Vite build)
  clean.
- All three features additionally verified against the *live* dev stack
  (real Postgres, a real edge worker driving 8 synthetic cameras, real
  browser interaction) — not unit tests alone standing in for integration
  proof.
