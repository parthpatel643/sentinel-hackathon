# 11 · M4 user-acceptance test
### Run on the MacBook Pro M4 that goes to i-Hub, before 12 October

The M2 is the development machine; this is the test on the machine that will
actually run the finale. Part 1 is automated and leaves its own evidence.
Part 2 is hands-on in the browser, with what you should see at each step. Note
pass or fail in the last column, and fix or escalate anything that fails before
the event.

---

## 0. Set up the M4 (once, online)

```bash
git clone <repo> && cd sentinel-hackathon     # or: git pull
make install
make up
(cd services/core_api && uv run --project ../.. alembic upgrade head)
make prefetch                  # all models, so nothing downloads on site
make seed                      # local admin login for the checks below
```

In three separate terminals, left running for the whole test:

```bash
make api
make web                       # console at http://localhost:5173
uv run python scripts/synthetic_grid.py all     # 8 mixed-codec test cameras on the local relay
```

Install the browser the UI tests use, once: `cd apps/web && npx playwright install chromium-headless-shell`.

**Keep `SENTINEL_ENVIRONMENT=local` until step K.** The checks log in with the
local seed account, which production mode refuses by design.

---

## Part 1 · Automated: `make uat`

```bash
make uat                # about 25 minutes; QUICK=1 skips the capacity curve
```

It runs, and saves each step's full output to `var/uat/<timestamp>/` with a
summary in `report.md`:

| Step | Expected |
|---|---|
| Preflight (`diagnose.py --preflight`) | stack, relay, API and offline models green |
| Lint, format, types | clean |
| Test suite (pytest) | all pass. It shares the dev database: run on a fresh database or after resetting the demo data |
| Web build and Playwright UI tests | all pass |
| DR drill | every row `yes`: counts identical, migration head identical, audit chain intact, tampering detected |
| Capacity curve | per camera count: `keeps up` or `FALLS BEHIND` |

**Record the capacity result.** The largest camera count that keeps up, at 8 fps
and at 4 fps, is the M4's capacity. On the M2, 2 cameras at 8 fps were marginal
and 4 at 4 fps kept up ([tier capacity](../evidence/TIER-CAPACITY.md)). Run the curve
twice: the verdict near the edge varies from run to run. Use the M4's numbers to
plan which finale cameras get which tier (runbook §6). Commit the report:
`cp -r var/uat/<timestamp> evidence/uat-m4` and add a line to this file.

---

## Part 2 · Hands-on

### Plate cameras for the checks

`make uat` (or any capacity run) leaves a 1080p clip of a car with plate
`GJ01AB1234` in `var/load-grid/`. Publish it as two cameras about 1.5 km apart:

```bash
for cam in uat-plate-01 uat-plate-02; do
  ffmpeg -hide_banner -loglevel error -re -stream_loop -1 \
    -i var/load-grid/vehicle-1080p25.mp4 -c copy -f rtsp -rtsp_transport tcp \
    "rtsp://dev-grid:dev-grid-local-only@127.0.0.1:8554/dev/$cam" &
done
cat > /tmp/uat-cameras.csv <<'CSV'
camera_id,name,department_name,lat,lon,tier,protocol,url,codec
uat-plate-01,UAT junction A,Police,23.0300,72.5600,b_sampled,rtsp,rtsp://127.0.0.1:8554/dev/uat-plate-01,h264
uat-plate-02,UAT junction B,Police,23.0400,72.5700,b_sampled,rtsp,rtsp://127.0.0.1:8554/dev/uat-plate-02,h264
CSV
```

### Checks

| # | Do | Expect | Result |
|---|---|---|---|
| A | **Cameras → Import cameras**, choose `/tmp/uat-cameras.csv`; then import `apps/web/public/camera-import-template.csv` as a dry run only | Two cameras added, pins on the map. Template dry run: 5 rows valid, one of them a private camera | |
| B | Terminal: `make worker SOURCE=registry` | Within 30 s both UAT cameras show **live** and `ANPR 8.0 fps` on the Cameras screen; worker log prints `uat-plate-0x: GJ01AB1234`; `make doctor` reports the whole chain healthy | |
| C | **Live Wall**: open both UAT cameras and two synthetic grid cameras, including an H.265 one | Every tile plays. Note whether the H.265 tile plays in Chrome; if not, confirm it plays in Safari (field card, [07 §6a](./07-DRIVER-SDK.md)) | |
| D | Stop one UAT publisher (`kill %1`), wait, start it again | Its tile shows an error, then recovers by itself within about 30 s of the feed returning | |
| E | Open the console in two browser windows. **Watchlist**: add `GJ01AB1234` as stolen | Both windows show the alert banner and play the sound within a second or two of the next `GJ01AB1234` line in the worker log | |
| F | **Find a Vehicle** → `GJ01AB1234` | A route alternating between junction A and B. Hops between them are flagged as infeasible (`needs … km/h`, or `seen here no later than at the previous camera`), because one car cannot be at both junctions seconds apart. This is the cloned-plate check working | |
| G | Download the **movement report** | A ZIP with `report.pdf` (route sketch to scale, an evidence frame per hop, IST times), `report.csv`, `evidence/*.jpg` and `manifest.json`. Check one hash: `shasum -a 256 report.pdf` equals `files["report.pdf"].sha256` in the manifest | |
| H | Stop the worker with Ctrl-C | It exits within a few seconds. `curl -s localhost:9997/v3/paths/list` shows no `ext/` paths left pinned. After 30 s the Cameras screen shows both UAT cameras as **stale**, not live | |
| I | Restart the worker. While it runs, stop the API (Ctrl-C in its terminal) for 40 s, then start it again | Worker log: `queued GJ01AB1234 for replay (n waiting)` while the API is down, then `replayed n queued detection(s)` within 5 s of it returning. No detection lost | |
| J | **Cameras → Coverage & lifecycle** | The tiles and department table render; with the template imported for real, one private camera's consent is counted | |
| K | Security, in `.env`: set `SENTINEL_ENVIRONMENT=prod`, restart the API | The API **refuses to start** and names the secrets still at their defaults. Generate them (runbook §3), restart: it starts. Logging in with the seed password is refused; create a real admin with `scripts/seed_admin_user.py --email … --password …` | |
| L | Create an operator: `uv run --package core_api python scripts/seed_admin_user.py --role operator --email op@… --password …`; log in as them | Cameras screen has no **Import** or **Add camera**; `POST /api/v1/cameras` with their token returns 403 | |
| M | Turn Wi-Fi off and repeat B and F | Everything works except basemap tiles, and the map says so | |
| N | If a real camera or NVR is available: onboard it by RTSP URL (field card) or **Discover a device** | Live, and plates read if the angle allows | |
| O | Optional, if the government grid quota allows: `make doctor GOV=1`, then onboard 2 grid cameras | Live through the relay; people and vehicle counts appear on the Cameras screen | |

Afterwards, put `SENTINEL_ENVIRONMENT` back the way the finale needs it
(runbook §3), stop the publishers (`kill %1 %2`), and remove the UAT cameras by
resetting the dev database (runbook §10).

---

## Results log

| Date | Machine | Part 1 report | Capacity (8 fps / 4 fps) | Part 2 failures | Notes |
|---|---|---|---|---|---|
| 2026-10-08 | M4 | `make uat QUICK=1`: 7/7 pass (preflight, lint, types, pytest, web build, Playwright 16/16, DR drill); logs in the M4's `var/uat/`, not yet copied to `evidence/uat-m4/` | **Not measured** (QUICK skips the curve) | Part 2 not yet run | Still to do: full `make uat` twice for capacity, then Part 2 A–N |
| | M4 | `evidence/uat-m4/report.md` | | | |
