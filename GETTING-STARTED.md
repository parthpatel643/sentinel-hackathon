# Getting started

How to run Sentinel Platform on a machine that has never seen it before.

Everything here was executed on a clean checkout before it was written down.
Where something is a known rough edge, it says so rather than pretending
otherwise — the [Troubleshooting](#troubleshooting) section covers every failure
actually hit while setting this up, including the ones that look alarming and
are not.

**Time to a working console:** about 20 minutes, most of it waiting for model
and container downloads.

---

## 1. Prerequisites

| Tool | Version | Why | Install (macOS) |
|---|---|---|---|
| **Docker** | any recent | Postgres/PostGIS, Valkey, NATS, MinIO, media relay | [Docker Desktop](https://docker.com) or [OrbStack](https://orbstack.dev) |
| **uv** | 0.5+ | Python toolchain and workspace manager | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| **Python** | **3.13+** | enforced by `pyproject.toml` | `uv python install 3.13` |
| **Node** | 20+ | operator console (Vite + React) | `brew install node` |
| **ffmpeg** | 6+ | RTSP capture and evidence clips | `brew install ffmpeg` |
| **tesseract** | 5+ | *optional* — reads the camera's burned-in clock | `brew install tesseract` |

You do **not** need a GPU. The ANPR models run on CPU — CoreML on Apple
silicon, ONNX elsewhere.

> **On tesseract being optional.** Without it, detections fall back to
> stamping the time *we processed* the frame. That is fine for a local demo,
> but note the government feeds replay archived footage, so their burned-in
> clocks read months in the past — with tesseract installed you get the
> scene's real time, which is what belongs in evidence. It degrades with a
> single warning rather than failing.

Check everything at once:

```bash
docker info > /dev/null && echo "docker ok"
uv --version && node --version && ffmpeg -version | head -1
tesseract --version 2>/dev/null | head -1 || echo "tesseract: not installed (optional)"
```

---

## 2. Install and start the stack

```bash
git clone <repository-url> sentinel-platform
cd sentinel-platform
git checkout stg

make install     # uv sync --all-packages, then npm install in apps/web
make up          # postgres/postgis, valkey, nats, minio, media relay
```

`make up` prints the ports it bound. They are deliberately non-default so the
stack never collides with anything already running:

```
postgres :15432  valkey :16379  nats :14222  minio :19000 (console :19001)
relay    rtsp :8554  hls :8888  whep :8889  api :9997
```

Wait for the containers to report healthy — Postgres in particular runs
initialisation on first start:

```bash
make ps
```

### Export the vehicle model

**A fresh clone has no model weights** — `models/weights/` is gitignored, and
the worker refuses to start without the vehicle detector. This is the single
most likely thing to stop you:

```bash
uv run --isolated --with ultralytics --with onnx python scripts/export_models.py
```

That produces `models/weights/yolo11n.onnx` (~10 MB). The remaining three
models — plate detector, OCR, and the face detector used for privacy blurring —
download themselves on first use, so this is the only one you run by hand.

The `--isolated` is not tidiness. Ultralytics pins plain `opencv-python`, which
conflicts with this project's `opencv-python-headless` if both land in the same
environment; the export therefore runs in a throwaway env and only its output is
kept. See [`models/README.md`](models/README.md) for the full picture, including
licences.

---

## 3. Create the schema and a login

```bash
cd services/core_api && uv run --project ../.. alembic upgrade head && cd ../..
make seed
```

`make seed` prints the account it created. The default is
`admin@sentinel-platform.com` / `sentinel-admin-2026`.

**Change it before the machine is reachable by anyone else:**

```bash
uv run --package core_api python scripts/seed_admin_user.py \
  --email admin@sentinel-platform.com --password 'something-else' --reset-password
```

---

## 4. Run it

`make worker` defaults to the **synthetic grid**, so publish that first —
otherwise there is nothing to analyse:

```bash
uv run python scripts/synthetic_grid.py all
```

This publishes a local RTSP grid of mixed codecs and resolutions — deliberately
messy, because a fleet that is uniformly H.264 1080p is not a fleet anyone
actually has.

Then three processes, one per terminal:

```bash
make api       # http://localhost:18000/api/docs
make web       # http://localhost:5173
make worker    # capture -> ANPR -> detections
```

Open <http://localhost:5173> and sign in. The cameras appear on the map as the
worker reports them.

### Verifying it works

```bash
curl -s localhost:18000/api/v1/health                     # {"status":"ok",...}
docker exec sentinel-postgres psql -U sentinel -d sentinel \
  -t -A -c 'SELECT count(*) FROM detections;'             # climbs as the worker runs
```

In the console: **Live Wall** shows the cameras, and **Find a Vehicle** finds a
plate once the worker has read one.

---

## 5. Running against the real government grid

The synthetic grid needs no credentials. The real one does.

```bash
cp .env.example .env
# fill in SENTINEL_GOV_ACCESS_EMAIL and SENTINEL_GOV_ACCESS_PASSWORD
```

Only emails on the organisers' approved access list can connect at all.

```bash
uv run python scripts/verify_gov_catalogue.py    # confirm the credentials work

# onboard all 30 cameras from the live catalogue
TOKEN=$(curl -s -X POST localhost:18000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@sentinel-platform.com","password":"sentinel-admin-2026"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')

curl -X POST localhost:18000/api/v1/cameras/discover -H "Authorization: Bearer $TOKEN"
```

Then analyse a few of them:

```bash
make worker SOURCE=gov CAMERAS=cam06,cam30 STRIDE=3
```

Equivalent to calling the module directly, which is worth knowing for anything
the Makefile does not expose (`--limit`, `--direct`):

```bash
uv run --package edge-agent python -m edge_agent.worker \
  --source gov --cameras cam06,cam30 --frame-stride 3
```

### Pace your load

Two independent limits bite here, and both were hit repeatedly during
development:

**The account viewing quota.** The sandbox meters watch time per account.
Four cameras exhaust it in **under an hour**; it then returns `403 watch time
limit reached` on the catalogue and `401` on RTSP, and every feed dies. It
recovers after roughly 15–20 minutes of *zero* consumption — so stop the
worker, do not just reduce it. Two cameras roughly doubles the window.

**Your own hardware.** Measured on an 8-core laptop: four 1080p cameras at full
frame rate put the worker at ~540% CPU and load average ~46, which starves the
relay's HLS muxer and stalls live preview — the cameras stay healthy and
detections keep flowing, but the video tiles will not play. `--frame-stride 3`
runs ANPR on every third frame and cuts load to ~10. Counter-intuitively this
*increased* detections, because at full rate the machine was dropping frames
before the pipeline ever saw them.

Sensible defaults for a demo: **two cameras, `--frame-stride 3`.**

```bash
# how many gateway connections am I holding?  (should equal camera count)
lsof -nP -iTCP@103.250.160.189:8554 -sTCP:ESTABLISHED | grep -c ESTABLISHED
```

### Stop the worker cleanly

```bash
kill <worker-pid>    # SIGTERM, SIGINT and SIGHUP all release cleanly
```

The worker pins its relay paths open while running and hands them back on the
way out — otherwise the relay keeps dialling the cameras with nothing reading
them, quietly draining the quota. A `kill -9` cannot be caught, so if that
happens the *next* startup sweeps up whatever was left pinned. Either way it
self-corrects; you should never need to clean up by hand.

---

## 6. Development

```bash
make check     # lint + types + tests — everything CI runs
make test      # pytest only
make lint      # ruff
make types     # mypy
```

Frontend:

```bash
cd apps/web
npm run build      # tsc -b && vite build
npm run test:ui    # Playwright
npm run lint       # oxlint
```

`make check` needs the stack running (`make up`) — a good part of the suite runs
against real Postgres with PostGIS geometry and RLS policies rather than mocks,
which is the point.

> **Tests and a running worker.** The suite is safe to run while the worker is
> ingesting; it was made robust to that deliberately. If you see a retention or
> gap-analysis test fail on counts, that is the historical shape of this
> problem — tests asserting absolute totals over a table something else is
> writing to. Report it rather than re-running until it passes.

---

## 7. Configuration

Everything is environment-driven with the `SENTINEL_` prefix, defined in
[`packages/sentinel_core/src/sentinel_core/config.py`](packages/sentinel_core/src/sentinel_core/config.py).
Defaults work for a local run; set these only when they do not.

| Variable | When you need it |
|---|---|
| `SENTINEL_GOV_ACCESS_EMAIL` / `_PASSWORD` | running against the real grid |
| `SENTINEL_CORS_ALLOW_ORIGINS` | console served from anywhere but `localhost:5173` |
| `SENTINEL_RELAY_HLS_URL` | browser reaches the relay on a different host than the API does |
| `SENTINEL_DB_*` | changed the compose ports |
| `SENTINEL_ADMIN_PASSWORD` | scripts that log in on your behalf |

Both CORS variables matter the moment the console is not on the same machine as
the API — a mismatch shows up as the console loading fine and then every request
failing, which reads like an auth problem and is not.

```bash
SENTINEL_CORS_ALLOW_ORIGINS='["https://your-console.example"]' \
SENTINEL_RELAY_HLS_URL='https://your-relay.example' \
uv run --package core_api uvicorn core_api.app:app --port 18000
```

---

## Troubleshooting

**`no vehicle model at .../models/weights/yolo11n.onnx`.** Expected on a fresh
clone — the weights are gitignored. Run the export in
[step 2](#export-the-vehicle-model). The error message itself prints the exact
command.

**`Connect call failed ... 15432` from alembic, or the API 500s on every query.**
Postgres is not up. Usually the Docker engine stopped — a laptop sleeping is
enough. `docker ps` failing with a socket error confirms it. Start the engine
(`orb start` for OrbStack, or open Docker Desktop), then `make up`. Data lives
in a named volume and survives.

**Console loads, every request fails.** CORS. The API only accepts the origins
in `SENTINEL_CORS_ALLOW_ORIGINS`, which defaults to `localhost:5173` only. The
browser console will name the blocked origin explicitly.

**Live Wall tiles stay on "Connecting…".** In order of likelihood:
1. The worker is not running, so no camera is being pulled.
2. The quota is exhausted — check for `403`/`401` in the worker log.
3. The machine is saturated; see the pacing note above.
4. Transient packet loss on the uplink starves the HLS muxer of keyframes. This
   rotates between cameras and self-heals. A wired connection largely clears it.

A camera the worker has marked `down` reports itself unavailable with a reason
rather than serving a URL that will not play, so the tile should tell you which
of these it is.

**`403 watch time limit reached`.** Quota. Stop the worker entirely and wait
15–20 minutes. Reducing the camera count is not enough; consumption must reach
zero.

**Detections stop but the worker looks alive.** Check the log for repeated
reconnects. The supervisor backs off exponentially to 30s and will recover on
its own once upstream returns.

**First run is slow.** Models download on first use (vehicle detector, plate
reader) and Postgres initialises PostGIS and TimescaleDB. Subsequent starts are
quick.

---

## Where to look next

| | |
|---|---|
| [`README.md`](README.md) | what the platform does, with screenshots |
| [`docs/01-ARCHITECTURE.md`](docs/01-ARCHITECTURE.md) | services, data flow, matching ladder |
| [`docs/02-ANPR-PIPELINE.md`](docs/02-ANPR-PIPELINE.md) | detection, tracking, plate voting |
| [`docs/04-SCALE-PLAN.md`](docs/04-SCALE-PLAN.md) | the path from 30 cameras to ~80,000 |
| [`docs/08-SECURITY-HARDENING.md`](docs/08-SECURITY-HARDENING.md) | RLS tenancy, audit chain, retention |
| [`evidence/`](evidence) | measured results — **including what did not work** |

The evidence directory is the honest one. `M1-CAPACITY-FINDINGS.md` records
where decode degrades on real hardware, and `M14-EVIDENCE-RUN-FINDINGS.md`
records how the quota actually behaves. Both are worth reading before planning a
demo around a specific camera count.
