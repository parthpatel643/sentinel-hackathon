# Sentinel Platform

Unified CCTV integration and AI video-analytics platform, built for the
**Gujarat Police Innovation Challenge 2026 (Sentinel)**.

Onboards heterogeneous government CCTV feeds into one registry, runs continuous
ANPR with watchlist correlation, raises prioritised real-time alerts, and
reconstructs a vehicle's timestamped route across cameras on a GIS map — with a
documented path to ~80,000 cameras.

![Operations overview](docs/images/01-operations-overview.png)

> **Screenshots** are the current console, a departures-style "gate board"
> (see [DESIGN.md](DESIGN.md)), captured on 12 October 2026 from the recorded
> government footage (`make worker SOURCE=mirror`). Times are each camera's own
> clock; "time unknown" means that frame's clock could not be confirmed.
> Regenerate with `npm run screenshots` from `apps/web`.

> **Status:** M0–M15 complete. Running against the **real government camera
> grid** — 30 cameras onboarded from the live catalogue, continuous ANPR,
> watchlist correlation, zone rules and tamper detection all verified on real
> traffic footage. See [evidence/](evidence) for measured results, including the
> things that did not work.
>
> **Phase 2 (grand finale, 12–13 Oct 2026, i-Hub Gujarat):** real CCTV at scale.
> Cameras onboarded on the day — wizard, bulk CSV, ONVIF/NVR device discovery —
> are analysed by `make worker SOURCE=registry` without a restart. The on-site
> procedure is in [10 — Finale Runbook](docs/10-FINALE-RUNBOOK.md).

---

## Five-minute quickstart

**New to this repository? Read [GETTING-STARTED.md](GETTING-STARTED.md)** — it
covers prerequisites, the real-grid setup, how to pace load against the
organisers' viewing quota, and every failure mode hit while setting this up on a
fresh machine. The summary below assumes the tooling is already in place.

Needs Docker, [uv](https://docs.astral.sh/uv/), Node 20+, and ffmpeg
(`brew install ffmpeg`).

```bash
# 1. dependencies and infrastructure
make install
make up                                          # postgres/postgis, valkey, nats, minio, relay

# 2. database schema and a login
cd services/core_api && uv run --project ../.. alembic upgrade head && cd ../..
make seed                                        # local-only login: admin@sentinel-platform.com / sentinel-admin-2026

# 3. a local camera grid to analyse (mixed codecs and resolutions, on purpose)
uv run python scripts/synthetic_grid.py all

# 4. three processes, one per terminal
make api                                         # http://localhost:18000/api/docs
make web                                         # http://localhost:5173
make worker                                      # capture -> ANPR -> detections
```

Open <http://localhost:5173>, sign in, and the cameras appear on the map as the
worker reports them.

To run against the **real government grid** instead of the synthetic one, copy
`.env.example` to `.env`, fill in your registered email and access password,
then:

```bash
uv run python scripts/verify_gov_catalogue.py    # validate the live catalogue
curl -X POST localhost:18000/api/v1/cameras/discover \
     -H "Authorization: Bearer $TOKEN"           # onboard all 30 cameras

# analyse a couple of them - see the pacing note below before raising this
make worker SOURCE=gov CAMERAS=cam06,cam30 STRIDE=3
```

The government grid is being taken down. A **local copy** of all 30 cameras
(a 6–17 minute recording of each, replayed from the local relay) runs with no
remote at all:

```bash
make mirror-start                                # replay data/gov-mirror under mirror/<id>
make worker SOURCE=mirror CAMERAS=cam06,cam24 STRIDE=3
```

What the copy holds, and how to extend it while the remote still answers, is
in [GETTING-STARTED.md](GETTING-STARTED.md#the-local-copy-when-the-grid-is-gone).

For **any other cameras** — a department's RTSP feeds, an ONVIF camera, an NVR —
onboard them in the console (or `POST /api/v1/cameras/bulk-import`) and run
`make worker SOURCE=registry`. It re-reads the registry every 30 seconds, and
each camera's tier decides how much of it is analysed; see
[GETTING-STARTED.md](GETTING-STARTED.md).

> The government sandbox enforces an account-level viewing-time quota. Four
> cameras exhaust it in under an hour, after which it returns `403 watch time
> limit reached` and cuts every feed until consumption stops entirely for
> 15-20 minutes. Analysing four 1080p streams at full frame rate also
> saturates an 8-core laptop and stalls live preview - `--frame-stride 3`
> cuts that load by roughly four-fifths. See
> [GETTING-STARTED.md](GETTING-STARTED.md) and
> [the evidence-run findings](evidence/M14-EVIDENCE-RUN-FINDINGS.md).

Host ports are deliberately non-default (`15432`, `16379`, `14222`, `19000`) so
the stack never collides with anything else on the machine; override with
`SENTINEL_*_PORT`.

---

## What it does

**Find a vehicle** — a plate goes in; a timestamped, per-camera timeline and a
mapped route come out, with recognition confidence per sighting and route replay
when enough sightings can be placed on the map. Searches reach back 24 hours, 48
hours or 7 days; when nothing matches exactly, reads one character away come
back as clearly-marked *probable* hops. The exported Movement Report (PDF + CSV +
hash manifest) is in IST, with UTC alongside.

![Find a vehicle](docs/images/05-find-a-vehicle.png)

**Live wall** — any camera in the fleet, including credentialed government
feeds, played in the browser without a single credential reaching it: the local
relay pulls the stream and republishes it.

![Live wall](docs/images/02-live-wall.png)

**Watchlist alerts** — prioritised hits from a two-rung matching ladder: exact
first, then an OCR-ambiguity class that still catches a read of `GJ1B67OS` when
the watchlist says `GJ186705`.

![Alerts](docs/images/03-alerts.png)

**Camera registry** — catalogue-driven onboarding, bulk CSV import, ONVIF and
NVR device discovery, a coverage-gap map layer, an infrastructure lifecycle
report (ageing cameras, lapsed AMCs, maintenance, offline) with a CSV work list,
and per-camera health, tamper state and zone rules. Stream credentials never
leave the API: operators see `rtsp://***@host/...`.

![Cameras](docs/images/04-cameras.png)

Also an [Admin Portal](docs/images/07-admin.png) (users, integrations, retention,
hash-chained audit log), a [Health](docs/images/06-health.png) dashboard, and a
[Field PWA](docs/images/10-field-pwa.png) for officers on a phone, with an
offline outbox.

The interface ships in **English, Hindi and Gujarati**, in
[light](docs/images/08-operations-overview-light.png) and dark themes:

![Gujarati](docs/images/09-operations-overview-gujarati.png)

---

## What is real, and what is not

Reviewers should not have to guess which parts are load-bearing.

| Area | Status |
|---|---|
| Capture, reconnect/backoff, PTS timing | Real. Verified against the live government grid and by [chaos drills](evidence/M15-CHAOS-DRILLS.md). |
| ANPR (detect → track → plate → OCR → vote) | Real open-source models, no mocks. Benchmarked on Apple Silicon. |
| **ANPR accuracy number** | **Measured, and below target.** 65% exact per crop, 80.5% after the multi-frame vote (re-measured 12 Oct), on 81 hand-labelled legible plates from one camera. 79 more were unreadable to a person. See [`evidence/ANPR-ACCURACY.md`](evidence/ANPR-ACCURACY.md). |
| **Sighting times (camera's burned-in clock)** | **Measured.** PP-OCRv6 reads the exact timestamp on 97.7% of 87 hand-labelled frames with a legible clock (Tesseract: 69.0%), with no wrong times; replayed across all 30 grid cameras, 37.4% of stream-seconds get a verified time (Tesseract: 12.8%). The rest are *time unknown*, mostly streams with no legible clock. See [`evidence/CLOCK-READER-ACCURACY.md`](evidence/CLOCK-READER-ACCURACY.md). |
| Camera registry, search, alerts, evidence clips | Real, PostGIS-backed, tested against a real database. |
| Watchlist correlation (both rungs) | Real. Exercised end-to-end on live government reads. |
| Route search, rung 3 (one-character misreads) | Real, route search only; returned as *probable* hops. Wildcard search and appearance ReID are designed, not built. |
| Secondary analytics (colour, tamper, zones, people) | Real — 208 zone events on real footage; a camera knocked or re-aimed raises an alert with before/after frames within seconds and closes itself when restored, with no false alarms on rain, traffic or wind shake in the mirrored feeds. People are counted and trip intrusion/loitering zones (185 found in 120 real frames), never identified. Vehicle colour is an HSV heuristic, not a trained classifier. |
| Coarse-make (manufacturer/model) | **Out of scope.** Needs a different trained classifier; not attempted. |
| Face recognition | **Excluded by decision** — see [00-SOLUTION-PLAN](docs/00-SOLUTION-PLAN.md). |
| mTLS, RBAC/ABAC, Postgres RLS, audit chain | Real and verified, including detecting tampering of the audit chain itself. |
| Government registry integrations (VAHAN/SARTHI/eGujCop/AFIS/NAFIS) | Real client, retry, circuit-breaker and audit code against **built-in mock transports** — no real credentials exist to hold. A rejected credential raises; it never reads as "no record". |
| 80,000-camera scale | **Arithmetic, not a deployment.** See [04-SCALE-PLAN](docs/04-SCALE-PLAN.md). |

---

## Layout

| Path | Contents |
|---|---|
| [packages/sentinel_core](packages/sentinel_core) | Shared domain model: event envelope, PTS clock, plate normalisation, camera drivers, government registry clients |
| [services/core_api](services/core_api) | REST + WebSocket API, registry (PostGIS), search, alerts, evidence, zones, admin, audit |
| [services/edge_agent](services/edge_agent) | Capture, decode, reconnect supervisor, ANPR pipeline, secondary analytics |
| [apps/web](apps/web) | Operator console and Field PWA (React, MapLibre, i18n) |
| [infra/compose](infra/compose) | Local infrastructure stack, pull-only relay config, mTLS edge gateway |
| [scripts](scripts) | Synthetic grid, benchmarks, chaos drills, evidence report, audit verification |
| [evidence](evidence) | Measured results and honest findings |
| [tests](tests) | Cross-cutting suites, including automated integrator compliance |
| [docs](docs) | Solution plan, HLD, ANPR pipeline, UX, scale, delivery, security, analytics |

---

## Documents

| Doc | Contents |
|---|---|
| [00 — Solution Plan](docs/00-SOLUTION-PLAN.md) | Strategy, rubric mapping, architecture choice, stack, scope, risks |
| [01 — Architecture (HLD)](docs/01-ARCHITECTURE.md) | ADRs, planes, federation adapters, correlation, data model, security |
| [02 — ANPR Pipeline](docs/02-ANPR-PIPELINE.md) | Model selection, measured Apple Silicon benchmarks, Indian-plate strategy |
| [03 — Experience Design](docs/03-UX-DESIGN.md) | Design tokens, three surfaces, screen-by-screen specifications |
| [04 — Scale Plan](docs/04-SCALE-PLAN.md) | The 80,000-camera arithmetic: bandwidth, GPU, storage, DR, cost |
| [05 — Delivery Plan](docs/05-DELIVERY-PLAN.md) | Risk-first milestone sequence |
| [06 — Submission Playbook](docs/06-SUBMISSION-PLAYBOOK.md) | Demo scripts, deliverables, evaluation-day checklist |
| [07 — Driver SDK](docs/07-DRIVER-SDK.md) | Writing a camera driver; ONVIF and four vendor shims |
| [08 — Security & Hardening](docs/08-SECURITY-HARDENING.md) | mTLS, RLS tenancy, face blurring, audit chain, supply chain, signed URLs |
| [09 — Secondary Analytics](docs/09-SECONDARY-ANALYTICS.md) | Vehicle colour, camera tamper detection, zone rules |
| [10 — Finale Runbook](docs/10-FINALE-RUNBOOK.md) | Phase-2 on-site procedure: what to ask organisers, onboarding real cameras, offline operation, the designated-vehicle drill, fallbacks |
| [13 — Showcase Prep](docs/13-SHOWCASE-PREP.md) | The 20-minute on-site evaluation: run-of-show, pitch script, plate-yield triage, 80K walkthrough, cost impact, Q&A, cheat card |
| [15 — Demo Book](docs/15-DEMO-BOOK.md) | The printed playbook for the live government feed: tonight's setup, warm-up, the trace click by click, the plate and camera, quota, fallbacks (`npm run docs:demo-book` for the PDF) |
| [14 — Appearance ReID](docs/14-APPEARANCE-REID-DESIGN.md) | Matching a vehicle whose plate is not read: design, effort, risk and go/no-go |

### Evidence

| Artefact | Contents |
|---|---|
| [M14 — Evidence run](evidence/M14-EVIDENCE-RUN.md) | Auto-generated from a real run: throughput, read quality, analytics, latency |
| [M14 — Findings](evidence/M14-EVIDENCE-RUN-FINDINGS.md) | What those numbers meant, and the problems the run exposed |
| [M15 — Chaos drills](evidence/M15-CHAOS-DRILLS.md) | Feed kills, blocked RTSP, scene cuts — with what was and was not proven |
| [M15 — Fresh-clone test](evidence/M15-FRESH-CLONE-TEST.md) | Proof the quickstart works from a clean checkout, and the bug that caught |
| [M1 — Capacity findings](evidence/M1-CAPACITY-FINDINGS.md) | How many streams this hardware actually sustains |
| [M2 — Synthetic grid limitation](evidence/M2-SYNTHETIC-GRID-DISCONTINUITY-FINDING.md) | Why the local fixture cannot reproduce a real PTS discontinuity |
| [M4 — Government grid integration](evidence/M4-GOV-CAMERA-GRID-INTEGRATION.md) | First live run against the real grid, and the two real bugs it found |
| [Camera-clock reader accuracy](evidence/CLOCK-READER-ACCURACY.md) | PP-OCRv6 against Tesseract on a hand-labelled holdout and a replay of all 30 grid cameras |

Background research: [sentinel-hackathon-research.md](sentinel-hackathon-research.md)

---

## Design commitments worth knowing

- **Time is PTS, never arrival.** The gateway replays a buffered GOP on connect,
  so arrival-time logic computes impossible velocities after every reconnect.
  Enforced by [`StreamClock`](packages/sentinel_core/src/sentinel_core/clock.py);
  the vehicle and people trackers' Kalman filters step by each frame's PTS
  delta (velocity in px/s, track lifetime in seconds of footage), and both
  are asserted in [`tests/test_compliance.py`](tests/test_compliance.py).
- **Consume only.** The relay grants no publish permission outside our own
  `dev/*` test fixture, and RTMP/SRT are disabled — asserted in the compliance
  suite, not merely documented.
- **Catalogue-driven discovery.** Camera IDs are never hard-coded; every run
  starts from the government catalogue endpoint.
- **Video stays local, meaning travels.** A detection event is ~1 KB; a stream is
  2 Mbps.
- **One upstream connection per camera, whatever is watching.** The edge worker and
  every browser tile read the same local relay path, so a camera that is both
  analysed and previewed still costs the gateway exactly one stream — measured, in
  [the evidence-run findings](evidence/M14-EVIDENCE-RUN-FINDINGS.md).
- **Credentials are assembled at call time**, never stored as one literal string
  — see `Settings.gov_stream_url`. A combined `scheme://user:pass@host` literal
  is exactly the shape credential scanners rewrite, which silently broke an
  earlier draft of this file.
- **Near-real-time, not barrier control.** Temporal voting deliberately withholds
  a read until several frames agree, so end-to-end latency is tens of seconds.
  Right for investigation, wrong for dropping a boom gate — stated plainly rather
  than left for a reviewer to discover.

## Development

```bash
make check        # ruff + mypy + pytest (359 tests)
make audit        # pip-audit + npm audit
make secrets-scan # detect-secrets

cd apps/web
npm run build         # tsc -b + vite build
npm run test:ui       # 16 Playwright UI tests (i18n, themes, contrast, mobile)
npm run screenshots   # regenerate docs/images from a live stack
npm run docs:pdf      # build docs/Sentinel-Platform-HLD.pdf (61pp, gitignored)
```

```bash
make deck             # build docs/Sentinel-Platform-Deck.pptx (15 slides, gitignored)
make pitch            # build docs/Sentinel-Finale-Pitch.pptx (15-slide pitch built around the live trace, a 10-slide appendix, speaker notes included)
```

The submission PDF is deliberately not committed — a checked-in PDF that
silently disagrees with the markdown it came from is worse than none, the same
reasoning applied to SBOMs. Regenerate it as the last step before submitting.
