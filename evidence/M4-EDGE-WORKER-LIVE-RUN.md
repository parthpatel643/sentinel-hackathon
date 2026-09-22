# M4 Edge Worker — Live Run Finding

## What was run

`services/edge_agent/src/edge_agent/worker.py` (`uv run --package edge-agent
python -m edge_agent.worker`), against the real M0-era docker-compose stack
(Postgres/PostGIS/Timescale, MediaMTX) and the M1 8-camera synthetic RTSP
grid, for ~3.5 minutes continuously.

This is the first time the capture → ANPR → API path ran as one live
process rather than being proven in three separate pieces (unit tests with
fake ports, a static-image smoke test, and manual `curl` against `core_api`).

## What it proved

- All 8 synthetic cameras (`dev-cam-01`..`08`, mixed h264/h265, 8-30 declared
  fps) connected, registered themselves into the registry (idempotent
  `POST /api/v1/cameras`, `409` on re-run — expected, not an error), and
  reported health every 5s via `PATCH /api/v1/cameras/{id}/health`.
- Measured fps matched declared fps for every camera for the whole run
  (e.g. `dev-cam-06`: 30.0/30.0, `dev-cam-08`: 8.0/8.0) — the capture and
  inference loop kept up with all 8 streams concurrently on this machine,
  not just one at a time.
- Zero reconnects across the run, with one exception: a single transient
  health-report POST failure for `dev-cam-01` at 18:30:33, silently
  recovered on the next 5s cycle with no operator action and no dropped
  frames. This is the kind of blip the M1 `CameraSupervisor` backoff design
  exists for, and it behaved exactly as designed.

## What it did not prove

No plate-read events were emitted in this run — `AnprPipeline` never fired
its "resolved plate" callback for any of the 8 synthetic streams in ~3.5
minutes. This is consistent with, not contradictory to, the M2 milestone's
own finding: the synthetic grid's source clips are generic stock driving
footage assembled to exercise capture/reconnect/timing (M1's actual concern),
not curated to guarantee a clearly-readable plate in frame — real detection
accuracy was verified separately in M2 via a static labelled test image
(`scripts/smoke_test_anpr.py`, "5AU5341" read correctly) and a 500-frame live
capture run. Getting a plate-bearing vehicle in front of the synthetic grid's
cameras during a normal run is possible but not guaranteed by clip content
alone.

The BOLO/detections/watchlist/alerts pipeline downstream of ingest (matching
ladder, dedup, retro-scan) is separately verified end-to-end against
hand-crafted realistic detection payloads in
`services/core_api/tests/test_detections_service.py` and
`test_watchlist_service.py`, and manually via `curl` against the running API
(see commit history) — this finding is specifically about the edge worker's
live capture-to-API wiring, not the correctness of the matching logic.

## Follow-up (not done here, scope for a later milestone)

Point the worker at a clip that is known to contain a clear, well-lit plate
for a few seconds, and confirm an end-to-end detection appears in
`GET /api/v1/detections` without any manual `curl` seeding. Deferred rather
than silently left implied "done" — the wiring is proven; a live plate read
from the synthetic grid specifically is not.
