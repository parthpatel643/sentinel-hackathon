# M14 Evidence Run — findings

Companion to the auto-generated `M14-EVIDENCE-RUN.md`. That file is produced
by `scripts/evidence_report.py` and is overwritten on every run; this one is
written by hand and records what the numbers *meant*, including the problems
the run exposed.

Run: 6 cameras from the real government grid (`cctv.corp8.cloud`), ~10
minutes of analysed footage, 172 detections, 208 zone events.

---

## 1. The government sandbox enforces a viewing-time quota

Twice during this session the grid began returning:

```
HTTP 403  watch time limit reached — please wait for your cooldown, then watch again
```

Observed properties:

- It affects **both** the catalogue/HLS host (`cameras.json` → 403) and raw
  **RTSP** (`DESCRIBE` → 401). It is an account-level quota, not a per-protocol
  or per-session limit.
- The response carries no `Retry-After` and no stated duration. One measured
  cooldown cleared in **under 15 minutes**; another had not cleared after
  several minutes of retrying.
- In-flight captures do not fail loudly. Cameras simply stop delivering, the
  supervisor reconnects on its backoff schedule, and the fleet drifts to
  `down` — which is exactly what the platform reported (83 reconnects across
  the fleet by the end of the run).

**Consequence for the demo:** camera count and run duration have to be paced
deliberately. A long unattended "overnight run across the full grid", as the
delivery plan's M14 describes, is **not achievable against this sandbox** —
not because of anything in this platform, but because the upstream grid will
cut it off. The run above is the honest maximum shape: a modest camera count
for a bounded window.

## 2. Live preview doubles our connection count against that quota

This is the most actionable finding of the run, and it is our problem, not
theirs.

The integrator guide is explicit: *"Each connected client receives its own
copy of the stream. Open only the cameras you are actively processing."*

Right now Sentinel opens **two** connections to the gateway for any camera
that is both analysed and previewed:

1. the edge worker dials the camera's RTSP URL directly for analytics, and
2. MediaMTX separately dials the *same* RTSP URL to republish it as
   `ext/<camera_id>` for the browser (added in the live-preview fix).

So watching the six cameras we were already analysing consumed twelve
streams' worth of the quota, and very plausibly accelerated the cooldown
above.

**The fix is architectural and worth doing:** point the edge worker at the
local relay path (`rtsp://localhost:8554/ext/<camera_id>`) instead of at the
gateway. MediaMTX then holds exactly one upstream connection per camera and
fans it out locally to both the analytics pipeline and every browser tile —
which is what a relay is *for*, and which also makes the "pace your load"
guidance structurally true rather than a thing we have to remember.

Not implemented in this commit: it changes the worker's source resolution and
needs verification against a live feed, which the cooldown currently prevents.
Recorded here so it is a known, scoped piece of work rather than a surprise.

## 3. Zone rules and tamper detection are validated on real footage

Both M13 features fired for the first time against real traffic, not fixtures:

- **208 zone events** across three zones on three cameras — 186 `intrusion`
  and 22 `wrong_way`. The `wrong_way` events are the more meaningful of the
  two: they require the engine's rolling-window heading computation to work
  on real vehicle tracks, not just a point-in-polygon test.
- **Tamper detection flagged one camera as `moved`** while the other five
  stayed `ok`. Exactly the kind of result that cannot be produced by a
  synthetic fixture, where every frame is generated and nothing ever shifts.

The `stopped_vehicle` zone on `cam06` fired nothing. That is plausible for a
ten-minute window on a moving carriageway and is not evidence either way.

## 4. Zones are read once, at worker startup

Adding a zone through the UI while a worker is running has no effect until
that worker restarts — `_load_zone_engine` fetches a camera's zones during
pipeline construction and never re-reads them. This was hit directly during
the run (three zones were created, then the worker had to be restarted before
a single event fired).

Not a bug in the sense of being wrong, but a real operational sharp edge: an
operator drawing a zone reasonably expects it to take effect. Worth either
polling for zone changes or invalidating on a push from core.

## 5. Ingest latency is ~40s end to end, and that is mostly by design

Median `observed_at` → row committed was **39.6s**, p90 **67.3s**. That sounds
alarming and mostly is not:

- `observed_at` is derived from the stream's **PTS**, not arrival time
  (ADR-005). When a client attaches, the gateway replays its buffered
  group-of-pictures, so the first frames processed are already seconds old by
  their own timeline.
- Temporal voting deliberately withholds a read until it has agreement across
  multiple frames (mean 4.0, max 20 frames this run). That is latency bought
  on purpose in exchange for far fewer wrong plates.

What it does mean: Sentinel is a **near-real-time investigative** system, not
a sub-second barrier-control ANPR. The watchlist-hit path is fast enough for
"a constable is told to look for this vehicle", not for "drop the boom gate".
The HLD should say so in those words.

## 6. Zero reads passed Indian-plate format validation

All 172 reads had `format_valid: false`, consistent with the earlier finding
in `M4-GOV-CAMERA-GRID-INTEGRATION.md`. On this footage — distant, angled,
often night-time traffic cameras — partial reads are the norm, and the
validator correctly refuses to bless them.

This is reported deliberately rather than hidden, and it is **not** an
accuracy figure. Mean plate confidence was 0.776 with a p90 of 1.000, so the
recogniser is confident about the characters it does read; what it rarely gets
is a *complete, well-formed* Indian plate from this vantage.

The honest position remains the one stated since M2: **this project cannot
quote an ANPR accuracy number**, because that needs a hand-labelled holdout
from real footage and no such holdout exists yet. `scripts/eval_anpr.py` is
built and working and is waiting on that data.

---

## Reproducing

```bash
# 1. onboard the grid and start a paced worker
curl -X POST localhost:18000/api/v1/cameras/discover -H "Authorization: Bearer $TOKEN"
uv run --package edge-agent python -m edge_agent.worker --source gov --limit 6

# 2. let it run, then generate the report
uv run --package core_api python scripts/evidence_report.py \
    --since <ISO-8601 start> \
    --out evidence/M14-EVIDENCE-RUN.md \
    --csv evidence/m14-detections.csv
```
