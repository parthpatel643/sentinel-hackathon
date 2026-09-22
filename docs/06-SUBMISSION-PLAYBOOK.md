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

| Time | Beat | On screen |
|---|---|---|
| 0:00–0:15 | "This is Sentinel, running live on my machine. Nothing here is a mock-up." | Terminal: `docker compose ps` → all services healthy. Then the console. |
| 0:15–0:40 | Onboard a feed | Camera wizard: pick location on map, paste the stream link, live preview appears, choose "Read number plates". Camera turns green on the map. |
| 0:40–1:10 | Live ANPR | Live wall tile with plate boxes and read text overlaid; detections table filling in real time with PTS-accurate timestamps |
| 1:10–1:35 | Arm the watchlist | Add a plate as "Stolen vehicle" with a case reference. Show it is armed. |
| 1:35–2:05 | The alert | Vehicle reappears → chime, alert card with snapshot, plain-language match reason, confidence. Acknowledge it. |
| 2:05–2:35 | Trace it | Find a Vehicle → route on map with numbered hops → Replay → evidence strip |
| 2:35–2:45 | Close | Export the Movement Report; show the generated PDF |

Production notes: 1080p60 screen recording, clean desktop, no notifications, narrate calmly and slowly, no music, subtitles burned in (juries often watch muted). Show a terminal at least twice — it is the cheapest proof that a backend exists.

---

## 4. Demo video 2 — government feed + report

| Time | Beat |
|---|---|
| 0:00–0:20 | `GET /api/ingest` in the terminal → "we never hard-code camera IDs" → one click auto-onboards the whole catalogue |
| 0:20–0:45 | All ~50 cameras appear on the GIS map with live health; health board shows measured vs declared fps, mixed H.264/H.265, active tiers |
| 0:45–1:30 | Live wall across multiple departments; ANPR overlays on several feeds simultaneously |
| 1:30–2:10 | Detections dashboard: thousands of reads from the overnight run, filterable by camera, time, plate |
| 2:10–2:50 | Pick a plate seen on multiple cameras → route across the grid on the map + timeline |
| 2:50–3:15 | Integrator Compliance panel — green ticks against the organisers' own checklist |
| 3:15–3:30 | Export the evidence report; show the PDF with plates, timestamps, cameras and snapshots |

**Output report** (`govt-feed-evidence.pdf` + `.csv`) contains: run window, cameras processed, total detections, unique plates, per-detection rows (plate, confidence, camera ID, camera name, department, lat/lon, PTS, absolute timestamp, snapshot thumbnail), plus a summary of health events (reconnects, discontinuities) — because showing that you *noticed* the gateway's quirks is itself evidence of engineering quality.

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
