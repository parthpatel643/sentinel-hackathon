# 05 — Delivery Plan
### Sentinel · Build sequence for a solo full-time developer

> Assumption: ~6 hours/day, ~40 hours/week, single developer, deadline extended. Sequence is ordered by **risk retirement first**, then by scored value. Every milestone ends in something demo-able — if you stopped at any milestone, you would still have a coherent story.

---

## 1. Sequencing principle

The two things that can kill this project are not features. They are:

1. **Can one M4 sustain ~50 concurrent streams with ANPR?** — unknown until measured.
2. **Is open-source ANPR accurate enough on Indian plates at CCTV angles?** — unknown until measured.

Both are answered in **week 1**, before a single screen is designed. Everything after that is execution against known constraints. Building features on top of an unmeasured assumption is how hackathon projects die at 2 a.m. the night before submission.

---

## 2. Milestones

### M0 · Foundations — days 1–2
- Monorepo scaffold (`apps/`, `services/`, `packages/`, `infra/`), `uv` workspace, ruff + mypy + pytest, pre-commit hooks
- `docker compose up` brings up Postgres/PostGIS/TimescaleDB, Valkey, NATS, MinIO, MediaMTX
- `sentinel_core`: event schemas (Pydantic v2), config, structured logging, OpenTelemetry bootstrap
- CI: lint + type + test on push
- **Exit:** `docker compose up` works from a clean clone; `pytest` green

### M1 · Capacity truth — days 3–5 ⚠️ *highest-risk milestone, do it first*
- Catalogue client for `GET /api/ingest`; per-camera property mapping
- Capture harness: RTSP-over-TCP, VideoToolbox hardware decode, `StreamClock` (PTS-only), backoff supervisor, loop-cut detector
- **Local synthetic RTSP grid** (MediaMTX looping mixed-codec, mixed-resolution samples) so you can develop and chaos-test without touching the government gateway
- Benchmark script: N cameras × M fps until degradation, on M4 and M2
- **Exit:** a published capacity curve — "M4 sustains X cameras at tier A, Y at tier B" — and a tiering configuration derived from it. This number shapes every later decision and belongs in the HLD.

### M2 · ANPR accuracy truth — days 6–10 ⚠️ *second-highest risk*
- Implement the full chain: vehicle detect → track → plate detect → rectify → OCR → temporal vote → format validation
- Export models to ONNX; CoreML EP on Mac, CUDA/TensorRT path documented
- Build a labelled evaluation set (300–500 plate instances captured from the test grid, hand-labelled)
- Measure plate-level and character-level accuracy; publish a benchmark table per pipeline variant
- **Decision gate:** public research shows **no credible pretrained Indian ANPR weights exist**, and the global OCR model's region list does not include India — so treat fine-tuning as *probable, not contingent* and budget 1–2 Colab days here. If plate-level accuracy on legible plates is ≥ 85% off-the-shelf, defer the fine-tune and revisit after M9.
- **Exit:** accuracy report committed to the repo, with failure-mode examples. This table goes straight into the PPT — very few entrants will have one.

### M3 · Registry + GIS (Model 1, mandatory) — days 11–14
- Schema: departments, sites, cameras (PostGIS point + FOV polygon), stream profiles, health
- Onboarding: catalogue auto-onboard, bulk CSV with column mapping and dry-run, manual entry, REST API
- Reconciliation job (catalogue diff → auto-update)
- Coverage gap analysis query + exportable report
- **Exit:** all ~50 test cameras onboarded automatically and visible on a map with live status

### M4 · Detection pipeline end-to-end — days 15–19
- Edge agent: tiered frame scheduler, motion gating, ragged batching, backpressure
- Events published to NATS → persisted to TimescaleDB with snapshots in MinIO
- Health telemetry stream; Prometheus metrics; ops endpoints
- **Compliance test suite** mirroring the official checklist, one test per line
- **Exit:** run the whole test grid for an hour and produce a plate/timestamp CSV — this is already 80% of submission deliverable (4)

### M5 · Watchlist, correlation, alerts — days 20–24
- Watchlist schema + matching ladder (exact → ambiguity class → edit distance → partial → attribute → ReID)
- Continuous correlation against a hot in-memory index; retro-scan on new entry
- Alert orchestrator: priority scoring, dedupe windows, lifecycle, escalation
- WebSocket alert stream
- **Exit:** add a plate to the watchlist → alert appears in a CLI/WS consumer within 2 s of the detection PTS, with a retro-scan of history

### M6 · Design system + Operator Console core — days 25–32
- Tokens, primitives, component gallery at `/dev/gallery`
- Shell, navigation, auth, ⌘K palette
- **Home** (map + alert rail + health pill) and **Find a Vehicle** — the two screens that carry the demo, built to a higher standard than everything else
- **Exit:** type a plate → see the route on a map. The product becomes real at this milestone.

### M7 · Live wall + playback — days 33–38
- WHEP player with HLS fallback, visible-tile-only streaming, transport/latency badge
- Adaptive grid, saved layouts, detection overlays
- Event-clip recording, sealed + hashed; timeline scrubber playback for recorded cameras
- **Exit:** 16 tiles live without dropped frames; click an alert → watch the sealed clip

### M8 · Route reconstruction + cross-camera ReID — days 39–43
- Sighting → route assembly, spatio-temporal feasibility gate, appearance-embedding bridges
- Route replay animation, evidence strip, Movement Report export (PDF + CSV + hash manifest)
- **Exit:** the full BOLO moment, end to end, rehearsable in 90 seconds

### M9 · Alerts screen, Cameras screen, Health/Ops — days 44–48
- Alert inbox and detail panel with the full triage workflow and "Not this vehicle" feedback loop
- Camera onboarding wizard with live preview; gap-analysis heat layer
- Health board + **Integrator Compliance panel**
- **Exit:** every Must-have feature is reachable through the UI

### M10 · Admin Portal + Field PWA — days 49–54
- Admin: users/roles with permission preview, watchlist management, retention policies, audit log with "Verify integrity", integration cards
- PWA: alerts, plate lookup, report-a-sighting with offline outbox, nearby cameras; Web Push; installable
- **Exit:** three surfaces, one design system

### M11 · Federation adapters + government integration stubs — days 55–59
- ONVIF driver (discovery, media profiles, PTZ, events); driver conformance suite
- Vendor shims (Milestone/Genetec/Hikvision/Dahua) against mock servers, with the plugin SDK documented
- `ExternalRegistry` providers for VAHAN/SARTHI/eGujCop/AFIS with conformant mocks and published contracts
- **Exit:** "onboarding department 27 is a driver, not a release" — demonstrated, not asserted

### M12 · Security, privacy, hardening — days 60–63
- OIDC/RBAC/ABAC, Postgres RLS department tenancy, mTLS between edge and core
- Edge-side default face blurring; reveal-on-authorisation with reason capture
- Hash-chained audit log + verification CLI; retention policy engine
- `pip-audit`/`npm audit`, SBOM, secret scanning, signed media URLs
- **Exit:** a security section in the HLD backed by running code

### M13 · Secondary analytics — days 64–67
- Vehicle class/colour/coarse-make; zone rules (intrusion, loitering, wrong-way, stopped vehicle); camera tamper detection
- *(No face recognition — excluded by decision; see [00-SOLUTION-PLAN §9](./00-SOLUTION-PLAN.md). The freed time goes into vehicle attributes, which is also what cross-camera ReID needs.)*
- **Exit:** "reliable analytics beyond ANPR" — an explicit bonus criterion

### M14 · Evidence run + deliverables — days 68–74
- Overnight multi-hour run across the full grid; auto-generated evidence report
- Record demo video (1): own feed, 2–3 min, scripted
- Record demo video (2): government feed + output report
- Write the PPT; export the HLD to PDF; polish README with screenshots and a 5-minute quickstart
- **Exit:** every submission artefact exists

### M15 · Rehearsal, hardening, buffer — days 75–80
- Chaos drills: kill feeds, block 8554, force loop cuts, throttle the network — during a rehearsed demo
- Fresh-clone test on the M2 (proves the quickstart actually works on a machine that is not yours)
- Link verification in incognito; consistency pass across PPT/HLD/videos/repo
- Rehearse the three winning moments until they are muscle memory
- **Exit:** submitted, with days to spare

---

## 3. Weekly rhythm

| Day | Practice |
|---|---|
| Every day | End with a working build. Commit early, commit often, meaningful messages — the repo is a scored artefact and its history is read. |
| Every Friday | Record a 2-minute progress video. By submission you will have a highlight reel and you will have rehearsed the narration a dozen times. |
| Every Sunday | Re-read the seven evaluation criteria. Score yourself out of 10 on each. Work next week on the lowest number. |
| Continuously | Keep an `evidence/` folder: benchmark CSVs, accuracy tables, screenshots, capacity curves. Claims backed by artefacts win; adjectives do not. |

---

## 4. Where to use AI assistance aggressively

You are backend/AI-heavy and solo. Spend your own hours on the parts where judgement matters and delegate the rest:

| Delegate heavily | Do yourself |
|---|---|
| React screen scaffolding from the specs in [03-UX-DESIGN](./03-UX-DESIGN.md) | The ANPR pipeline and its accuracy tuning |
| CRUD endpoints, Pydantic schemas, migrations | The PTS/clock design and stream resilience behaviours |
| Test scaffolding, fixtures, mock servers | The matching ladder and route feasibility logic |
| PDF/CSV report generators | The scale model and the numbers you will defend live |
| Documentation formatting, diagram boilerplate | The demo narrative and the three winning moments |

---

## 5. Definition of done (per feature)

A feature is done when: it works against the live test grid (not only the synthetic one) · it has tests · it degrades sensibly when its dependency is down · it appears in the UI with plain-language copy · it is covered by an evidence artefact (screenshot, CSV or metric) · and it is documented in one paragraph in the README.

---

*Next: [06-SUBMISSION-PLAYBOOK](./06-SUBMISSION-PLAYBOOK.md) — demo scripts and the evaluation-day checklist.*
