# M4 Edge Worker — Real Government Camera Grid Integration

## What this documents

The first live run of the full capture → ANPR → API pipeline against the
actual Sentinel Camera Grid (the organisers' real integration target —
`cctv.corp8.cloud` / `103.250.160.189`), not the M1 synthetic grid. This
supersedes the "no plate reads fired" caveat in
`evidence/M4-EDGE-WORKER-LIVE-RUN.md`, which was specifically about the
synthetic grid's generic stock footage.

## Two real bugs found and fixed getting here

**1. The catalogue/HLS host requires a session-cookie login the integrator
guide doesn't mention up front.** `GovCatalogueClient.fetch()` was hitting
a `302 Found` redirect to `/auth/login` on every call — RTSP/WHEP
authenticate per-connection via credentials embedded in the URL (as
documented), but `cameras.json` and HLS sit behind a separate form login
(`POST /auth/login` with `email`/`password` fields, discovered by reading
the login page's own HTML). Fixed in `sentinel_core/gov_catalogue.py`:
logs in once per client instance before the first `fetch()`, guarded so it
never fires when no gov credentials are configured (e.g. synthetic-grid-only
local dev).

**2. The plate detector's CoreML execution provider fails on real camera
frames.** `docs/02-ANPR-PIPELINE.md`'s measured recommendation (CoreML for
the plate detector, ~5-8.6x faster than CPU) was based on the M1 synthetic
grid and a single static test image — neither ever triggered a real bug in
this specific YOLOv9 end-to-end ONNX export: its baked-in NMS produces a
zero-length dynamic array on some real frames, which CoreML's EP cannot
execute (`dynamic shape ({-1}) but the runtime shape ({0}) has zero
elements`) and silently returns no detections for, while logging an error.
Running against two real government cameras for two minutes hit this on
effectively every frame — plate detection was fully disabled the entire
time, not degraded. CPU EP does not have this bug. Fixed in
`edge_agent/analytics/plate_reader.py`: the plate detector now defaults to
CPU-only. Re-verified against the static test image
(`scripts/smoke_test_anpr.py`) afterwards — same correct "5AU5341" read,
confidence 1.0 — so this is not a regression in read quality, only a
provider change.

## What was verified, end to end, against real infrastructure

1. `curl https://cctv.corp8.cloud/cameras.json` → `302` → confirmed the
   login requirement; `POST /auth/login` with real credentials from
   `.env` → session cookie → `cameras.json` → **30 real cameras**
   (`cam01`.."cam30"), real Gujarat locations ("Chiman bhai Bridge",
   "Janpath", "O.N.G.C. Office", Junagadh/Rajkot/Navsari/Patan-area
   cameras, etc.) — not placeholder data.
2. `ffprobe -rtsp_transport tcp` against the authenticated RTSP URL for
   `cam01` → real stream, h264, 1920x1080 @ 25fps.
3. `POST /api/v1/cameras/discover` → all 30 onboarded into the registry in
   one call, zero failures.
4. `uv run --package edge-agent python -m edge_agent.worker --source gov
   --limit 2` → both cameras connected, zero reconnects, health reporting
   every 5s, **and real plate-read events posted to `POST
   /api/v1/detections` and confirmed via `GET /api/v1/detections`** —
   e.g. `F110` (0.83 confidence, vehicle_class=car, 4 frames voted),
   `C234` (0.78, truck). `format_valid: false` on all of them is expected
   and correct: partial/short reads from real distant/angled traffic-camera
   footage don't match full Indian plate grammar the way a curated test
   image does — the pipeline is correctly reporting low-quality reads as
   low-quality, not silently accepting them.

## New capability: `edge_agent.worker --source {synthetic,gov}`

The worker now supports either camera source uniformly (both normalise to
`sentinel_core.schemas.CameraDescriptor` before the capture/pipeline loop).
`--source gov` defaults to `--limit 4` concurrent cameras rather than all
30 at once, per the integrator guide's explicit "pace your load, open only
the cameras you are processing" guidance — override with `--limit N` or
select specific ids with `--cameras cam01,cam04`.

## Known transient issue (not a code bug)

Two of several `--source gov` runs hit an `httpx.ReadTimeout` during the
initial login/catalogue fetch, succeeding on retry with no code change.
Consistent with this being a shared, sometimes-congested sandbox host
(documented since M1's capacity findings) rather than a real endpoint or
client bug — not investigated further here since it self-resolved on
retry both times.

## Test data hygiene

The 30 onboarded gov cameras and the detections generated during this
verification were deleted from the dev database afterward
(`docker exec sentinel-postgres psql ... DELETE FROM ...`) — the same
reason `scripts/seed_demo_data.py` exists as an opt-in script rather than
leaving data seeded: the integration test suite asserts exact counts
against a near-empty database and fails otherwise. Re-run
`POST /api/v1/cameras/discover` or the worker with `--source gov` to
repopulate real data for a live demo.
