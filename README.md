# Sentinel Platform

Unified CCTV integration and AI video-analytics platform, built for the
**Gujarat Police Innovation Challenge 2026 (Sentinel)**.

Onboards heterogeneous government CCTV feeds into one registry, runs continuous
ANPR with watchlist correlation, raises prioritised real-time alerts, and
reconstructs a vehicle's timestamped route across cameras on a GIS map — with a
documented path to ~80,000 cameras.

![Operations overview](docs/images/01-operations-overview.png)

> **UI update:** the current console has been structurally redesigned with a
> compact navigation rail, interactive network workbench, selectable surveillance
> wall, three-panel vehicle investigation, and master-detail alert triage. Admin,
> health and field workflows have also been rebuilt. The screenshots in this README
> document the earlier live-data run; see the
> [implemented workspace specification](docs/03-UX-DESIGN.md#implemented-workspace)
> for the current interaction design. Regenerate live-data screenshots with
> `npm run screenshots` from `apps/web` using a working operator account.

> **Status:** M0–M13 complete. Running against the **real government camera
> grid** — 30 cameras onboarded from the live catalogue, continuous ANPR,
> watchlist correlation, zone rules and tamper detection all verified on real
> traffic footage. See [evidence/](evidence) for measured results, including the
> things that did not work.

---

## Five-minute quickstart

Needs Docker, [uv](https://docs.astral.sh/uv/), Node 20+, and ffmpeg
(`brew install ffmpeg`).

```bash
# 1. dependencies and infrastructure
make install
make up                                          # postgres/postgis, valkey, nats, minio, relay

# 2. database schema and a login
cd services/core_api && uv run --project ../.. alembic upgrade head && cd ../..
make seed                                        # admin@sentinel-platform.com / sentinel-admin-2026

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
make worker SOURCE=gov                           # analyse them
```

> The government sandbox enforces an account-level viewing-time quota. Pace the
> camera count and run length, or it returns `403 watch time limit reached` and
> cuts the feeds. See
> [the evidence-run findings](evidence/M14-EVIDENCE-RUN-FINDINGS.md).

Host ports are deliberately non-default (`15432`, `16379`, `14222`, `19000`) so
the stack never collides with anything else on the machine; override with
`SENTINEL_*_PORT`.

---

## What it does

**Find a vehicle** — a plate goes in; a timestamped, per-camera timeline and a
mapped route come out, with recognition confidence per sighting and route replay
when enough sightings can be placed on the map.

![Find a vehicle](docs/images/05-find-a-vehicle.png)

**Live wall** — any camera in the fleet, including credentialed government
feeds, played in the browser without a single credential reaching it: the local
relay pulls the stream and republishes it.

![Live wall](docs/images/02-live-wall.png)

**Watchlist alerts** — prioritised hits from a two-rung matching ladder: exact
first, then an OCR-ambiguity class that still catches a read of `GJ1B67OS` when
the watchlist says `GJ186705`.

![Alerts](docs/images/03-alerts.png)

**Camera registry** — catalogue-driven onboarding, bulk CSV import,
coverage-gap analysis, and per-camera health, tamper state and zone rules.

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
| **ANPR accuracy number** | **Not claimed.** Needs a hand-labelled holdout that does not exist yet; `scripts/eval_anpr.py` is built and waiting on it. |
| Camera registry, search, alerts, evidence clips | Real, PostGIS-backed, tested against a real database. |
| Watchlist correlation (both rungs) | Real. Exercised end-to-end on live government reads. |
| Secondary analytics (colour, tamper, zones) | Real — 208 zone events and a `moved` tamper flag on real footage. Vehicle colour is an HSV heuristic, not a trained classifier. |
| Coarse-make (manufacturer/model) | **Out of scope.** Needs a different trained classifier; not attempted. |
| Face recognition | **Excluded by decision** — see [00-SOLUTION-PLAN](docs/00-SOLUTION-PLAN.md). |
| mTLS, RBAC/ABAC, Postgres RLS, audit chain | Real and verified, including detecting tampering of the audit chain itself. |
| Government registry integrations (VAHAN/SARTHI/eGujCop/AFIS) | Real client, retry, circuit-breaker and audit code against **built-in mock transports** — no real credentials exist to hold. |
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

Background research: [sentinel-hackathon-research.md](sentinel-hackathon-research.md)

---

## Design commitments worth knowing

- **Time is PTS, never arrival.** The gateway replays a buffered GOP on connect,
  so arrival-time logic computes impossible velocities after every reconnect.
  Enforced by [`StreamClock`](packages/sentinel_core/src/sentinel_core/clock.py)
  and asserted in [`tests/test_compliance.py`](tests/test_compliance.py).
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
```

The submission PDF is deliberately not committed — a checked-in PDF that
silently disagrees with the markdown it came from is worse than none, the same
reasoning applied to SBOMs. Regenerate it as the last step before submitting.
