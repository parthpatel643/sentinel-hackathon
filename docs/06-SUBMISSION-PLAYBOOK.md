# 06 — Submission & Evaluation Playbook
### Sentinel · Demo scripts, artefacts and the day-of checklist

---

## 1. The four required submissions

| # | Requirement | Artefact | Owner milestone |
|---|---|---|---|
| 1 | Solution Presentation (PPT/PDF) | `deliverables/presentation/sentinel-solution.pdf` | M14 |
| 2 | Technical Proposal / HLD | `docs/01-ARCHITECTURE.md` + `docs/04-SCALE-PLAN.md` → `deliverables/hld/sentinel-hld.pdf` | M14 |
| 3 | Demo on your own feed (2–3 min) | Unlisted YouTube + Drive mirror | M14 |
| 4 | Demo on government feed + output report | Unlisted YouTube + Drive mirror + `deliverables/reports/govt-feed-evidence.pdf`/`.csv` | M14 |

Plus: a **source archive** (the repository stays private — see [00-SOLUTION-PLAN §9](./00-SOLUTION-PLAN.md)) containing a README a stranger can run in five minutes, and a `SOURCE-TOUR.md` guided reading path.

---

## 2. Presentation outline (14 slides, no more)

1. **The problem in one picture** — 26 islands, 80,000 cameras, a getaway car that requires phone calls to trace
2. **What we built** — one sentence and one screenshot of the route-replay screen
3. **Model choice and justification** — Hybrid 1+2+3+selective-4, and *why each*
4. **The rejected option, with numbers** — 160 Gbps, 12.1 PB/week, ₹400 cr+. The honesty moment.
5. **Architecture** — the one diagram, layered, readable from the back of the room
6. **Ingest & federation** — heterogeneous sources, adapter framework, zero change to department systems
7. **ANPR pipeline** — stages, and the accuracy table on live government feeds
8. **Watchlist correlation** — the matching ladder, with the explainability screenshot
9. **Alerting & triage** — priority, dedupe, escalation, false-positive feedback loop
10. **Cross-camera tracking** — the GIS route with confirmed vs probable hops
11. **Scale to 80,000** — the tiering table, GPU/bandwidth/storage math, phased rollout
12. **Security & privacy** — default blur, reveal-on-authorisation, hash-chained audit, DPDP alignment
13. **Operational impact** — minutes-to-trace before vs after; what a constable can now do unaided
14. **PoC readiness** — what is running today, what we need from departments, the 90-day pilot plan

Design rules: one idea per slide · every number sourced · no clip-art · screenshots of the real product, never mock-ups · dark slides matching the product's visual identity, so the deck and the demo feel like one thing.

---

## 3. Demo video 1 — own feed (target 2:45)

*Rewritten in M15 against the system as built. Every command below was run;
every number is one this platform actually produced. The earlier draft of this
section was written before implementation and referenced things that do not
exist — see §4's note on the catalogue endpoint for the sharpest example.*

**Before recording.** Clean desktop, notifications off, 1080p60. Start the
stack and let the worker settle for a minute so the map is populated:

```bash
make up && make api          # :18000
make web                     # :5173
uv run python scripts/synthetic_grid.py all
make worker                  # synthetic grid
```

Sign in as `admin@sentinel-platform.com` / `sentinel-admin-2026`.

| Time | Beat | On screen |
|---|---|---|
| 0:00–0:15 | "This is Sentinel, running on my machine. Nothing here is a mock-up." | Terminal: `make ps` → every service healthy. Cut to the console. |
| 0:15–0:35 | The fleet is real | Overview: cameras on the map, the status strip reading *N live · 0 down*. Hover a marker — it names the camera and its state. |
| 0:35–1:05 | Live ANPR | Live Wall, 2×2. Tiles are playing. Cut to the terminal running the worker: plate reads scrolling with confidence values. "Every timestamp comes from the stream's own clock, not when the packet arrived." |
| 1:05–1:25 | Arm the watchlist | Find a Vehicle → search a plate the worker has just read → *Watch for this vehicle* → mark it **Stolen**, add a case reference. |
| 1:25–1:55 | **The ambiguity moment** | Ingest a read of the same plate with OCR confusions (`8→B`, `0→O`, `5→S`). The alert still fires, tagged `ambiguity_class`. "An operator typed one plate. The camera read a different string. We still caught it." |
| 1:55–2:25 | Trace it | Alerts → the hit → Find a Vehicle → timeline with per-sighting confidence, map framed on the sightings, *Replay route*. |
| 2:25–2:45 | Close on evidence | *Export report* → the generated Movement Report PDF with its hash manifest. |

**The ambiguity beat is the one to rehearse.** It is the single clearest
demonstration that this is a real matching system rather than a string compare,
and it takes one command:

```bash
uv run python - <<'EOF'
import httpx, uuid
from datetime import datetime, UTC
from sentinel_core.config import Settings
from sentinel_core.plates import normalise_plate, ambiguity_key
s = Settings(); variant = 'GJ1B67OS'          # watchlist holds GJ186705
httpx.post('http://localhost:18000/api/v1/detections',
    json={'event_id': str(uuid.uuid4()), 'camera_id': 'dev-cam-01',
          'observed_at': datetime.now(UTC).isoformat(), 'plate_text': variant,
          'plate_normalised': normalise_plate(variant),
          'plate_ambiguity_key': ambiguity_key(variant),
          'plate_confidence': 0.68, 'frames_voted': 4, 'vehicle_class': 'truck',
          'vehicle_colour': 'blue', 'pts_ms': 5678.0, 'node_id': 'demo',
          'model_versions': {'demo': '1'}},
    headers={'X-Service-Token': s.edge_service_token.get_secret_value()})
EOF
```

Production notes: narrate calmly, no music, subtitles burned in (juries often
watch muted). Show a terminal at least twice — it is the cheapest proof that a
backend exists.

---

## 4. Demo video 2 — government feed + report (target 3:30)

> **Correction worth knowing before you record.** The integrator guide's generic
> `GET /api/ingest` path **404s on our assigned deployment** — that guide is a
> shared template with `<host>` placeholders, and this deployment only
> implements `GET /cameras.json`, behind a session-cookie login. Saying
> "/api/ingest" on camera would be saying something untrue about our own
> integration. See `evidence/M4-GOV-CAMERA-GRID-INTEGRATION.md`.

> **Pace the run.** The sandbox enforces an account-level viewing-time quota and
> returns `403 watch time limit reached`, cutting every feed. Do not leave a
> large run going before recording. Six cameras is a comfortable number.

| Time | Beat | On screen |
|---|---|---|
| 0:00–0:25 | Discovery is not hard-coded | Terminal: authenticate, `GET cameras.json` → 30 cameras with real Gujarat names. Then one call to `POST /api/v1/cameras/discover` → **30 onboarded, 0 failed**. |
| 0:25–0:50 | The grid on a map | Overview: real cameras plotted across Ahmedabad, Junagadh, Rajkot, Navsari. Note openly that 21 of 30 geocode from their names and the rest are deliberately left unplotted rather than guessed. |
| 0:50–1:25 | Live government video, no credentials in the browser | Live Wall playing real traffic. Open devtools: the video URL is our own `localhost` relay path. "The camera's credentialed URL never reaches the browser." |
| 1:25–2:00 | ANPR on real traffic | Worker terminal: reads scrolling from `cam01…cam06`. Detections table filling. Cite the measured run: **172 detections, 124 distinct plates in ~10 minutes across 6 cameras**. |
| 2:00–2:25 | Beyond plates | Cameras table showing a camera flagged **`moved`** by tamper detection, and zone events — **186 intrusion + 22 wrong-way** on real footage. |
| 2:25–2:50 | It survives the network | Run `uv run python scripts/chaos_drill.py --drill feed-loss` live. The camera drops, the platform notices, reconnects and recovers unattended. |
| 2:50–3:10 | Compliance, checked not claimed | Admin → Integrator Compliance: green ticks. "These are assertions in a test suite, not a slide." |
| 3:10–3:30 | The report | `scripts/evidence_report.py` → open `evidence/M14-EVIDENCE-RUN.md` and the CSV. End on the findings document: the quota, the double-connection issue, the accuracy number we do not claim. |

**Ending on the findings document is a deliberate choice.** A jury that has sat
through ten decks of unbroken success will remember the team that showed its
own measured limitations — and it is the honest thing to do.

**Output report** (`evidence/M14-EVIDENCE-RUN.md` + `m14-detections.csv`): run
window, fleet composition, throughput, read-quality distribution, secondary
analytics, resilience counters, ingest latency, and every detection row (plate,
confidence, camera, class, colour). Generated by script, not by hand.

---

## 5. Source archive presentation

The repository is private, so the archive you hand over *is* your code credibility. It will be skimmed, not studied — optimise for the skim.

- `README.md`: one-paragraph pitch, a hero screenshot, a 90-second architecture summary, **a five-minute quickstart that actually works on a clean machine**, a feature list mapped to the seven evaluation criteria, and a link to these docs
- **`SOURCE-TOUR.md`** — a guided five-minute reading path: start at the edge agent's capture loop, then the ANPR pipeline, then the matching ladder, then the alert orchestrator. Name the file and the function for each stop. This is the single highest-leverage page in a private submission.
- `docs/` as published here; `evidence/` with benchmark CSVs, the accuracy table and the capacity curves
- Clean commit history with meaningful messages — evidence of sustained engineering rather than a weekend paste
- No secrets, no model weights committed (download scripts instead), no dead code, no `TODO: fix this` in a path a reviewer will open
- LICENSE file, and a `THIRD-PARTY-LICENCES.md` listing every dependency and its licence — the challenge mandates open-source technologies, and showing you tracked licences (including the AGPL components and why they are acceptable) is exactly the diligence a government buyer looks for
- CI configured and green; include the workflow file even though the badge is not publicly visible

**Consider before you upload:** the challenge mandates open-source technologies. A fully closed submission can read as being in tension with that spirit. If you can make the repository public at submission time without losing anything you actually care about, it is worth doing — it is a one-click change and it converts an explanation into an asset.

---

## 6. Pre-submission checklist

**Organisers' technical checklist** — verified by the automated compliance suite, and screenshotted for the PPT:
- [ ] All clients force RTSP over TCP
- [ ] No logic depends on declared FPS or arrival time
- [ ] Inter-frame gaps do not crash the pipeline
- [ ] Backoff reconnect tested by restarting a feed mid-run
- [ ] Decoder warnings logged, never fatal
- [ ] Camera discovery is catalogue-driven
- [ ] Mixed codec and resolution handled
- [ ] Sane behaviour across the loop cut

**Submission hygiene:**
- [ ] YouTube videos set to *Unlisted* and verified in an incognito window
- [ ] Drive/OneDrive mirrors set to "Anyone with the link — Viewer", verified in incognito
- [ ] Source archive uploaded (or private link with reviewer access granted and verified from a second account)
- [ ] `SOURCE-TOUR.md` and `THIRD-PARTY-LICENCES.md` included in the archive
- [ ] Names, dates and version numbers consistent across PPT, HLD, videos and source archive
- [ ] PDFs open correctly and are under any portal size limits
- [ ] Every claim in the PPT is demonstrable in the videos — no orphan claims
- [ ] Contact details correct; category selected correctly at registration
- [ ] Uploaded with days to spare, not hours

---

## 7. Evaluation-day playbook (Phase 2, live)

**Before you start**
- Two machines, both fully set up. The M2 is the hot spare, tested from a fresh clone.
- Local synthetic grid running as a fallback if the venue network blocks the real feeds.
- Recorded demo videos on local disk — if the network dies entirely, you still have a story.
- Wired network if possible; phone hotspot as backup.
- Pre-warm: services up, models loaded, cameras onboarded, caches hot. Never cold-start in front of a jury.

**When they give you the vehicle number**
1. Say what you are about to do before you do it — juries follow narration better than clicks.
2. Type the plate into the single search field. Do not open a settings panel. The simplicity *is* the demo.
3. Show the retro-search result first (route on the map), then point out that a BOLO is now armed forward in time.
4. Replay the route. Let it run — the animation does the explaining.
5. Open one hop's evidence: snapshot, camera, department, PTS-accurate timestamp, confidence.
6. Export the Movement Report and hand it over. Ending with an artefact in the evaluator's hands is worth more than another screen.

**Questions you will be asked, and the short answers**
| Question | Answer |
|---|---|
| "What if the plate is dirty or partly unreadable?" | Show the fuzzy/partial path and the ambiguity classes, then the appearance-ReID bridge and the feasibility gate |
| "How does this scale to 80,000?" | The tiering table and the three formulas. Offer to re-derive with their numbers. |
| "What about privacy?" | **"We do no face recognition at all — faces are detected only so we can blur them."** Then: default blur at the edge, reveal-on-authorisation with reason capture, hash-chained audit, retention engine, false-match redressal |
| "Will this disturb our existing systems?" | Read-only, pull-based, standards-first; no agent on department infrastructure; the department's VMS keeps running untouched |
| "How long to onboard a new department?" | A driver, not a release — show the conformance suite and the plugin SDK |
| "What do you need from us?" | The data-collection template in [04-SCALE-PLAN §8](./04-SCALE-PLAN.md) — answer with a document, not a wish |
| "What doesn't work yet?" | Name it plainly. The Won't-do list in the master plan exists precisely so you can answer this without flinching. |

**Demeanour:** calm, slow, specific. Say "I measured that" and show the artefact. When something breaks — and something will — narrate the recovery: *"That camera dropped; the supervisor is backing off and will reconnect in about eight seconds."* Then let it reconnect on camera. Handling a failure gracefully in front of a jury is a stronger signal than a flawless run, because it is the thing they cannot fake-check.

---

*Back to [00-SOLUTION-PLAN](./00-SOLUTION-PLAN.md).*
