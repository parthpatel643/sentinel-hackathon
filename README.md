# Sentinel Platform

Unified CCTV integration and AI video-analytics platform, built for the **Gujarat Police Innovation Challenge 2026 (Sentinel)**.

Onboards heterogeneous government CCTV feeds into one registry, runs continuous ANPR with
watchlist correlation, raises prioritised real-time alerts, and reconstructs a vehicle's
timestamped route across cameras on a GIS map — with a documented path to ~80,000 cameras.

> **Status:** M0 + M1 + M2 + M3 complete — infrastructure, capture/reconnect pipeline, a
> real tested ANPR pipeline, and the mandatory Model 1 camera registry (async SQLAlchemy
> + PostGIS, catalogue-driven onboarding, bulk CSV import, coverage gap analysis) are all
> in place and verified against real services. Next: M4 (unified live viewing + alerts).

## Quickstart

```bash
make install     # install workspace dependencies (uv)
make up          # start postgres/postgis/timescale, valkey, nats, minio, mediamtx
uv run python scripts/synthetic_grid.py all   # local mixed-codec test grid
make api         # core API on http://localhost:18080/api/docs
make check       # lint + type-check + tests
```

Host ports are deliberately non-default (`15432`, `16379`, `14222`, `19000`) so the stack
never collides with anything else running on the machine; override them with
`SENTINEL_*_PORT` environment variables.

For the real government test grid, copy `.env.example` to `.env` and fill in your registered
email + access password, then run `uv run python scripts/verify_gov_catalogue.py` to validate
the catalogue schema against the live endpoint.

For ANPR, export the vehicle detector once (in an isolated environment — see the script's
own docstring for why) and run the real-model smoke test:

```bash
uv run --isolated --with ultralytics --with onnx python scripts/export_models.py
uv run python scripts/smoke_test_anpr.py
```

## Layout

| Path | Contents |
|---|---|
| [packages/sentinel_core](packages/sentinel_core) | Shared domain model: event envelope, PTS clock, plate normalisation, event-bus port |
| [services/core_api](services/core_api) | REST + WebSocket API, camera registry (PostGIS), search, alerts |
| [services/edge_agent](services/edge_agent) | Capture, decode, reconnect supervisor, catalogue client, ANPR analytics |
| [infra/compose](infra/compose) | Local infrastructure stack and the pull-only relay config |
| [scripts](scripts) | Synthetic test grid, capacity/ANPR benchmarks, model export, catalogue verification |
| [evidence](evidence) | Benchmark CSVs and honest findings (capacity, synthetic-grid limitations) |
| [tests](tests) | Cross-cutting suites, including automated integrator compliance |
| [docs](docs) | Solution plan, HLD, ANPR pipeline, UX specs, scale plan |

Run the registry migrations against the local stack with:

```bash
cd services/core_api && uv run --project ../.. alembic upgrade head
```

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

Background research on the challenge: [sentinel-hackathon-research.md](sentinel-hackathon-research.md)

## Design commitments worth knowing

- **Time is PTS, never arrival.** The gateway replays a buffered GOP on connect, so
  arrival-time logic computes impossible velocities after every reconnect.
  Enforced by [`StreamClock`](packages/sentinel_core/src/sentinel_core/clock.py) and asserted
  in [`tests/test_compliance.py`](tests/test_compliance.py).
- **Consume only.** The relay grants no publish permission and RTMP/SRT are disabled.
- **Catalogue-driven discovery.** Camera IDs are never hard-coded; every run starts from
  the government catalogue endpoint.
- **Video stays local, meaning travels.** A detection event is ~1 KB; a stream is 2 Mbps.
- **Credential-bearing URLs are always assembled at call time from separate config fields,
  never stored as one literal string** — see `Settings.gov_stream_url` in
  [config.py](packages/sentinel_core/src/sentinel_core/config.py). A combined
  `scheme://user:pass@host` literal is exactly the shape credential-scanning tooling flags
  and rewrites, which silently broke an earlier draft of this file.
