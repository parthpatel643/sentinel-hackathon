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

## The demo in one command

Once the prerequisites below are installed and `.env` holds the government
credentials, one script does everything else — dependencies, models, the
stack, the schema, the admin login, the API and console, catalogue sync, the
watchlist and a worker — and checks each step before the next:

```bash
make demo                                   # government grid, cam06 + cam30 analysed, all 30 onboarded
make demo PHONE=1                           # also: Cloudflare tunnel + console on Vercel for phones
make demo SOURCE=mirror                     # the recorded copy, offline, no quota
make demo RESET=1 WATCH="GJ03MH7800:wanted:critical"
make demo-status                            # cameras live, gateway connections, 403s
make demo-down                              # stops the worker first, releasing the gateway
```

Everything it starts is logged under `var/demo/`. `PHONE=1` puts the API on
the internet, so it runs with `SENTINEL_ENVIRONMENT=prod`: it generates
secrets into `.env`, changes the admin password (printed at the end), and
needs `cloudflared` and `npx vercel login` once. Every option is listed at
the top of [`scripts/demo.sh`](scripts/demo.sh).

## 1. Prerequisites

| Tool | Version | Why | Install (macOS) |
|---|---|---|---|
| **Docker** | any recent | Postgres/PostGIS, Valkey, NATS, MinIO, media relay | [Docker Desktop](https://docker.com) or [OrbStack](https://orbstack.dev) |
| **uv** | 0.5+ | Python toolchain and workspace manager | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| **Python** | **3.13+** | enforced by `pyproject.toml` | handled by `uv` — see below |
| **Node** | 20+ | operator console (Vite + React) | `brew install node` |
| **ffmpeg** | 6+ | RTSP capture and evidence clips | `brew install ffmpeg` |

You do **not** need a GPU. The ANPR models run on CPU — CoreML on Apple
silicon, ONNX elsewhere.

You also do not need to install Python 3.13 yourself. `uv` reads the version
from `pyproject.toml` and downloads a matching interpreter into the project's
own environment, so a machine whose system `python3` is much older is fine —
verified here on a host still running 3.9.

> **On sighting times.** The clock a camera burns into its frames is the
> only time a sighting is ever reported with — not the stream's PTS, not when
> we processed the frame. It is read by PP-OCRv6 models that ship inside the
> `rapidocr` Python package (installed by `make install`; nothing to download
> at runtime, no system package). A reading is used only when a second
> reading of the same camera's clock agrees with it, so a misread digit is
> never shown. If the models cannot load, every sighting is recorded as
> *time unknown — camera clock unreadable*: searchable, but kept off the
> timed route. The worker still runs, with a single warning.

Check everything at once:

```bash
docker info > /dev/null && echo "docker ok"
uv --version && node --version && ffmpeg -version | head -1
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
`admin@sentinel-platform.com` / `sentinel-admin-2026` — a **local development
login only**: with `SENTINEL_ENVIRONMENT` set to anything but `local`, the API
refuses that password and `make seed` will not set it.

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

> **Expect zero plate reads from the synthetic grid.** The streams are ffmpeg
> `testsrc` patterns — a moving gradient with a scrolling timestamp, and no
> vehicles in them at all. Cameras will go `live` at 25fps and health will
> report normally, but the detections table stays empty, and that is correct
> rather than broken. The synthetic grid exists to exercise capture,
> reconnection, PTS handling and mixed codecs without touching the
> organisers' gateway. For actual plate reads you need the real grid, below.

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
make doctor                                               # walks the whole chain
curl -s localhost:18000/api/v1/health                     # {"status":"ok",...}
```

In the console: **Live Wall** shows the cameras, and **Find a Vehicle** finds a
plate once the worker has read one.

### Analysing any camera you onboard (the registry source)

The synthetic and government sources each bring their own camera list. A real
deployment — and the Phase-2 finale — starts from whatever you onboard: the
**Add camera** wizard, a **bulk CSV**, **device discovery** (an ONVIF camera or
a Hikvision/Dahua NVR by address and account), or a catalogue sync. Point the
worker at the registry instead:

```bash
make worker SOURCE=registry                       # every onboarded camera
make worker SOURCE=registry DEPARTMENT=Police     # one shard per department
```

How much of each camera is analysed is set by its **tier** (the CSV `tier`
column, or the wizard), not by the worker:

| Tier | Analyses | Worker setting |
|---|---|---|
| `a_continuous` | Every frame, or every `STRIDE`-th | `STRIDE=3` analyses one frame in three |
| `b_sampled` (default) | A fixed rate, paced by the stream's own timestamps | `SAMPLED_FPS=8` |
| `c_motion_gated` | `SAMPLED_FPS`, only while something moves | `SAMPLED_FPS` |
| `d_registry_only` | Nothing: map and live wall only | none |

A base M2 reaches about 16 analysed frames a second of dense traffic in total
before it starts to fall behind
([tier capacity](evidence/TIER-CAPACITY.md)). The Cameras screen shows each
camera's analysed rate and, in red, how far analysis trails live when it
falls behind.

It re-reads the registry every 30 seconds (`--resync-interval`), so a camera
onboarded while it runs starts being analysed within one interval, a corrected
stream URL replaces the old one, and a camera moved to the `d_registry_only`
tier is stopped and its relay connection released. The worker reads the
registry through a service-token-only endpoint; operators never see stream
credentials — the console and API show them as `rtsp://***@host/...`.

A minimal CSV (see the wizard's help for every column, including
`installed_on`, `amc_expires_on`, `maintenance_status`, `vendor` and `model`
for the lifecycle report, and `ownership`, `consent_ref` and
`consent_expires_on` for private cameras):

```csv
camera_id,name,department_name,lat,lon,protocol,url
pol-cg-road-01,CG Road junction,Police,23.0300,72.5600,rtsp,rtsp://viewer:p%40ss@10.20.1.15:554/Streaming/Channels/101
```

Percent-encode `@`, `:`, `/`, `#` and `?` inside a password (`@` is `%40`).

A private camera (a society, mall or shop sharing its view) is onboarded with
`ownership=private` and the consent it was shared under: `consent_ref` (the
station's consent or MoU number) and `consent_expires_on`. Without both, or
once the date passes, the camera stays in the registry but is not viewed or
analysed, and **Coverage & lifecycle** lists it for renewal.

Before going onto a network without internet, run `make prefetch` once while
online: the plate detector, plate OCR and face-blur models are otherwise
downloaded on first use. `make doctor` warns if any are missing.

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

The quota belongs to the **account, not the machine**. Two laptops running
workers against the same credentials draw from one budget and will exhaust it
twice as fast, each looking as though the other is not there. Stop the worker
on the old machine before starting one somewhere else.

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

### The local copy (when the grid is gone)

The government grid is being taken down, so a copy of it lives in
`data/gov-mirror/` (gitignored): one clip per camera, recorded as the grid
sent it (stream copy, never re-encoded), with the same camera ids, names and
map positions. Nothing in this path contacts the remote.

```bash
make up                         # the relay must be running
make mirror-start               # replay all 30 clips under rtsp://localhost:8554/mirror/<id>
make worker SOURCE=mirror CAMERAS=cam06,cam24 STRIDE=3
make mirror-stop
```

To register them in the console instead, onboard the RTSP URLs from
`data/gov-mirror/catalogue.json` and run `make worker SOURCE=registry`.
`uv run python scripts/gov_mirror.py register` puts all 30 on the map and the
live wall in one step (a worker registers only the cameras it runs).

While the remote is still reachable, the copy can be extended — `make
mirror-capture` records every camera to `data/gov-mirror/raw/` (resumable;
it pauses itself through quota cooldowns), and `make mirror` stitches the
recording into clips and rewrites the catalogue. Pass `--max-minutes N` to
`scripts/gov_mirror.py capture` for longer clips.

What the copy is, and is not:

- **6–17 minutes per camera**, not the grid's full recordings — the viewing
  quota caps what one account can record. `data/gov-mirror/manifest.json`
  lists each clip's length, codec, resolution and frame rate.
- **A few continuous stretches of each clip, back to back.** The grid drops
  connections every minute or two and its timeline moves on during a quota
  cooldown, so footage is stitched by matching what it shows; stretches that
  match nothing are kept as separate sections, with a scene cut between them.
- **As patchy as the grid sent it.** Many cameras delivered only a few
  frames a second of a nominal 25; the manifest's `delivery.missing_pct`
  says how much of each clip is gaps.
- **Seamless at the loop point.** It is replayed with ffmpeg's
  `-stream_loop`, which does not reset timestamps the way the real grid did
  (see [the M2 finding](evidence/M2-SYNTHETIC-GRID-DISCONTINUITY-FINDING.md)).

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
| `SENTINEL_ENVIRONMENT` + `SENTINEL_JWT_SECRET`, `_EDGE_SERVICE_TOKEN`, `_MTLS_GATEWAY_SHARED_SECRET`, `_MEDIA_URL_SIGNING_SECRET` | the API is reachable from another machine. Any environment other than `local` refuses to start while a secret still has its published `dev-only-*` default; workers need the same `SENTINEL_EDGE_SERVICE_TOKEN` |
| `SENTINEL_CORE_API_URL` | an edge worker on a different machine from the API |
| `VITE_MAP_TILE_URL` (in `apps/web/.env`) | basemap tiles from a local or departmental tile server instead of openstreetmap.org |

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

**Start here: `make doctor`.** Live preview depends on a chain — Docker,
Postgres, the relay, the API, credentials, an onboarded camera, the model, a
running worker, a registered relay path, then HLS. A break anywhere shows up in
the browser as the same thing: a tile that says "Connecting…". `make doctor`
walks that chain in order, stops at the first break, and prints the remedy.
Add `GOV=1` to include the government credentials and quota.

```bash
make doctor           # local stack
make doctor GOV=1     # also check the government grid
```

**`make up` fails to pull an image.** The compose stack starts only what is
needed; the object store is opt-in precisely because `docker compose up` aborts
the entire command when any single image cannot be pulled, and an optional
service would otherwise take Postgres and the relay down with it. If some other
image fails, the stack genuinely cannot start — check network access, and note
that a registry being down is not something this repository can work around.

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

**A camera stays `down` and the relay logs `path 'ext/…' is not configured`.**
The relay was restarted (`make up` is enough) and lost its paths, which live in
memory rather than its config file. The worker re-asserts them on its next
reconnect, so this repairs itself within a retry cycle — under a minute. If it
persists beyond that, the worker is not running.

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
