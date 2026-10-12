# 13 — Showcase Prep: the 20-minute on-site evaluation
### Sentinel · 12–13 October 2026, i-Hub Gujarat · pitch, live drill, 80K walkthrough, cost

This is the one document to rehearse from. It does not repeat the on-site
procedure — that is [10 — Finale Runbook](./10-FINALE-RUNBOOK.md) — it decides
**what to say, in what order, in 20 minutes**, and what to fix before Monday.

Written 8 October 2026 after re-reading
[sentinel.gujarat.gov.in/problems](https://sentinel.gujarat.gov.in/problems)
end to end against the repository.

---

## 0. The five things that matter most before Monday

1. **Email the organisers today** (§1 of the runbook): feed format, camera count,
   coordinates, live vs replayed, network — and **whether every feed carries a
   burned-in date/time overlay**: a sighting's time now comes only from that
   clock, so a camera without one cannot contribute to the timed route. The helpdesk is Mon–Sat 10:00–18:00,
   so **Saturday 10 Oct is the last working day to get an answer.**
2. **Prove a real cross-camera route once, end to end, on footage we control.**
   It has never been shown on time-aligned real video
   ([cross-camera finding](../evidence/CROSS-CAMERA-TRACKING-FINDINGS.md)).
   Drive one team car with a known plate past 3 phone/IP cameras at known GPS
   points, analyse live, and get a 3-hop route. This is also the best
   own-feed answer to "is it real?" (§6.5).
3. **Measure the M4's capacity.** `make uat QUICK=1` passed 7/7 on 8 Oct, but
   `QUICK` skips the capacity curve, so the M4's analysed-fps edge is still
   unknown. Run the full `make uat` (about 25 min) twice, then UAT Part 2
   ([11-M4-UAT](./11-M4-UAT.md)). Every capacity decision on the day (§6.2)
   depends on that one number.
4. **Rehearse the 20 minutes (§4) three times with a timer**, once with the
   network off.
5. **Decide go/no-go on appearance ReID by Friday 18:00**
   ([14 — Appearance ReID design](./14-APPEARANCE-REID-DESIGN.md)). Default is
   **no-go**: present what exists (§7) and the design slide.

---

## 1. Their requirements, our answer

Every requirement on the [problem page](https://sentinel.gujarat.gov.in/problems)
and the [FAQ](https://sentinel.gujarat.gov.in/faqs), mapped to the Sentinel
feature that answers it, where the jury sees it, and how complete it is.
Re-checked against the live site on 11 October 2026: unchanged since 8 October.
The [phases page](https://sentinel.gujarat.gov.in/phases) adds the format: six
finalists, real CCTV feeds at scale, judged by Gujarat Police leadership and a
technical jury, plus a Special Jury Award for an outstanding aspect of any
solution.

Code and test evidence for each row is in
[12 — Requirements traceability](./12-REQUIREMENTS-TRACEABILITY.md); this
section is the on-stage view. **Slide** numbers refer to the 12-slide
[pitch deck](./Sentinel-Finale-Pitch.pptx) (01–12) and its appendix (A1–A9); **Demo 1–3** are the live steps in §4.

**Status:** **Built** — working and demonstrable · **Partial** — built, with the
stated limit · **Design** — documented and sized, not running · **Excluded** —
left out by decision.

### 1.1 The test case on the day (Step 4) — the part that must not fail

Bonus points never compensate for a failed mandatory test case. This table is
the one to rehearse.

| They ask | Sentinel feature | Show it | Status | Risk on the day |
|---|---|---|---|---|
| Onboard ~50 cameras across departments, technologies, formats and VMS | CSV import with a dry run; ONVIF, Hikvision and Dahua device discovery; catalogue sync; registry with department, location and tier | Slide 05 · Demo 1 (backup A2): Cameras map | **Built** — all 30 sandbox cameras onboarded from the live catalogue; H.264 and H.265, 720p to 1440p | Unseen network, credentials and ports (runbook §4) |
| Integrate the live feeds; centralised monitoring | Live wall (focus, 2×2, 3×3, 4×4) through the local relay, one upstream pull per camera; Health screen with fps and lag | Slide 05 · Demo 1 (backup A2): Live Wall, Health | **Built** | H.265 does not play in Chrome (use Safari or an H.264 profile); laptop CPU when preview and ANPR compete |
| AI-powered video analytics | ANPR with multi-frame voting; vehicle class and colour; people counts; zone rules; tamper | Demo 2–3; A5, A8 | **Built** — 78% exact plates after the vote | Plates too small on wide-angle cameras (§6.2) |
| Identify and trace the designated vehicle from its registration number | Find a Vehicle: exact, look-alike and one-character-off matching; 24 h / 48 h / 7 d windows | Slide 05 · Demo 2 (backup A3) | **Built** | **The vehicle passes a camera we were not analysing** (§6.1–6.2) |
| Complete route with timestamped, location-wise movement history | Map and timeline ordered by each camera's own clock; Movement Report (PDF, CSV, evidence frames, SHA-256 manifest) | Slide 05 · Demo 2 (backup A3): Export report | **Built** | A camera with no readable date-time overlay gives *time unknown* stops; one without coordinates is not mapped. Ask the organisers (runbook §1) |
| Continuous cross-referencing with a watchlist; automated real-time alerts | Every confirmed read matched against the watchlist; alert banner and sound on every console within a second; field app | Slide 05 · Demo 3 (backup A4) | **Built** | "Real-time" wording: a read is confirmed after several frames agree (§2 item 1) |
| Representative watchlist database | Stolen, wanted, missing and BOLO entries with priority, case reference and validity | Slide 05 · Demo 3 (backup A4) | **Built** | Arm entries from plates actually read that morning (§6.3) |
| Visualise on GIS | MapLibre map: camera pins, route with earliest-to-latest styling, coverage-gap layer | Demo 1–2 (backups A2, A3) | **Built** | No basemap offline; pins and routes still draw |
| Searchable events and history | Detections searchable by plate, camera and time; alert queue; zone-event queue | Demo 2–3 | **Built** | — |
| Evidence of integration, interoperability, scalability and end-to-end performance | Health screen; 600+ automated tests; measured capacity; DR drill | Slides 08, 09, A6, A8 | **Built**, measured on a laptop; 80,000 is arithmetic | — |

### 1.2 The solution they asked for (Step 3, Expected Solution Approach)

| They ask | Sentinel feature | Show it | Status |
|---|---|---|---|
| Continuously process the provided feeds | Registry-driven edge worker; picks up new cameras every 30 s without a restart | Demo 1 | **Built** |
| Watchlist database structure, matching logic, alerting mechanism, user interface | Watchlist entries; four-rung matching ladder; dedupe window; alert lifecycle new → acknowledged → resolved / not this vehicle | Slide A4 · Demo 3 | **Built** |
| Create and use representative datasets | Seeded watchlist; camera-import CSV template; recorded copy of the government grid | Demo 3 | **Built** |
| Identify specified vehicles *or other entities* (wanted or missing persons) | Vehicles by plate. People are counted and held to zones, never identified | Slides A4, A5 | **Partial** — persons **Excluded** by decision (no face recognition) |
| Open, modular, standards-based, vendor-neutral; documented APIs; adapter framework | OpenAPI at `/api/docs`; driver SDK with a conformance suite; open-source stack | Slides 08, A6 | **Built** |

### 1.3 The reference models (Step 2): we are a hybrid

Model 1 as the mandatory foundation, Models 2 and 3 adopted, Model 4 only where
it pays off. **This is slide 07**; its speaker notes carry the justification.

| Model · feature they list | Sentinel | Status |
|---|---|---|
| **M1** Bulk import, manual entry, API onboarding | CSV wizard, Add camera, `POST /api/v1/cameras` | **Built** |
| **M1** GIS with department, camera-type, status and coverage layers | Department and status filters, coverage-gap layer | **Partial** — no camera-type layer |
| **M1** Camera health and maintenance status | Live / stale / degraded / down, analysed fps and lag; maintenance status and AMC dates | **Built** |
| **M1** Gap analysis: uncovered zones, ageing infrastructure | Coverage & lifecycle screen with a CSV work list | **Built** |
| **M1** Role-based search, filter, export, metadata audit trail | RBAC and database row-level security; lifecycle CSV export; hash-chained audit log | **Built** |
| **M1** Deliverables: portal, onboarding demo, sample dataset, registry API docs, sample gap report | Console; `camera-import-template.csv`; `/api/docs`; lifecycle CSV | **Built** |
| **M2** Feed aggregation over RTSP, ONVIF or vendor APIs | Drivers for RTSP, ONVIF, Hikvision, Dahua, Genetec and Milestone | **Built**; Hikvision and Dahua tested against vendor-API mocks, not hardware |
| **M2** ANPR metadata, event tagging, camera-wise indexing | Every read stored with camera, time, class, colour and frame; alerts and zone events triaged with a status | **Built** |
| **M2** Searchable vehicle-movement records | Find a Vehicle | **Built** |
| **M2** Configurable video walls | Live wall layouts and camera selection | **Built** |
| **M2** Alerts for tagged events and vehicles of interest | Watchlist alerts; zone-event alerts | **Built** |
| **M2** Viewer on at least two different systems; departments unaffected | Government grid and our own feeds in one console; publishing to the relay forbidden and checked by a compliance test | **Built** |
| **M3** Adapter / plugin architecture for VMS vendors | Driver SDK, one interface, conformance suite | **Built** |
| **M3** Metadata exchange bus | Events travel over authenticated HTTP with a durable on-disk outbox; Kafka or NATS bus at scale | **Design** (01 §10) |
| **M3** Cross-system event correlation | One watchlist and one route across every department's cameras; impossible-travel check | **Built** |
| **M3** Unified workflow and alert dashboard | Alerts queue with triage; Overview | **Built** |
| **M4** Central ingestion and recording | Only critical cameras and alert clips recorded centrally; departments keep their own retention | **Selective by design** |
| **M4** Tiered hot, warm and cold storage | Retention engine (preview, then execute) built; tiering sized | **Partial** (04 §4) |
| **M4** ANPR, crowd / vehicle counting, anomaly detection | ANPR; people and vehicles in view per camera; tamper, zone rules, impossible travel | **Built** |
| **M4** Face recognition | — | **Excluded** by decision |
| **M4** Statewide vehicle tracking and route reconstruction | Find a Vehicle across the whole registry | **Built** at grid scale |
| **M4** VAHAN, SARTHI, eGujCop, AFIS, NAFIS readiness | Five connectors with retry, circuit breaker and audit; Admin → Integrations | **Built** against contract mocks; no live credentials exist |
| **M4** Redundancy, DR, encryption, network segmentation, RBAC | DR drill, mTLS, RBAC and RLS built; HA and segmentation designed | **Partial** (01 §9, 04 §5) |
| **M4** Load-test report for ~80,000 cameras | Measured per-laptop capacity plus the scale arithmetic | **Partial** — no 80,000-camera load test |

### 1.4 The design dimensions they listed (Step 3, FAQ 24)

| Dimension | Slide | Depth |
|---|---|---|
| Overall architecture | 07, 09 | [01 — Architecture](./01-ARCHITECTURE.md), HLD PDF |
| Integration strategy | 07, A2, A7 | [07 — Driver SDK](./07-DRIVER-SDK.md) |
| AI and video analytics | A4, A5 | [02 — ANPR](./02-ANPR-PIPELINE.md), [09 — Secondary analytics](./09-SECONDARY-ANALYTICS.md) |
| Cybersecurity, privacy, RBAC, audit | 06 | [08 — Security](./08-SECURITY-HARDENING.md) |
| Deployment architecture (central, regional, edge) | 09 | 01 §10 |
| Infrastructure sizing | A6 | [04 — Scale plan](./04-SCALE-PLAN.md) §3–4 |
| Cost-benefit analysis | 10 (cost); 08 and A7 (what it buys) | §9, 04 §6 |
| Department-wise information requirements | 12 | 04 §8 |
| Scalability strategy | 08, 09, A6 | 04 |
| Future roadmap | A8, A9 | 04 §7, [14 — Appearance ReID](./14-APPEARANCE-REID-DESIGN.md) |

### 1.5 Plan for scale (Step 6)

| They ask us to explain | Slide | Answer in one line |
|---|---|---|
| Central, regional and edge compute | 09 | Analysis in 34 district nodes plus edge boxes at remote sites; the state core does search, storage and alerts |
| GPU or accelerator requirements | A6 | ≈560 L4 GPUs with N+1, sized by tier — **say it; it is not on the slide** |
| Bandwidth and low-bandwidth strategies | 08 | ≈140 Mbps statewide; metadata-only mode at ≈4.5 Mbps; 72 h offline queue |
| Hot, warm and cold storage by retention | 08 | ≈390 TB usable instead of 12.1 PB a week; departments keep their 7–15 days |
| Load balancing, horizontal scaling, monitoring, logging, health checks | 09 | Health screen, JSON structured logs and health endpoints built; autoscaling on queue depth designed |
| HA, backup, DR, cybersecurity controls | 06, 09, A8 | RPO 15 min, RTO 1 h; DR drill restores a million records in 5.7 s and catches tampering |
| Estimated implementation and operational costs | 10 | ≈₹80 cr to build, ≈₹24 cr a year to run; ≈₹10,000 and ≈₹3,000 a year per camera; ₹0 licences; centralising is ₹400 cr+ (§9) |
| Phased statewide rollout | A9 | 500 → 5,000 → 30,000 → 80,000 cameras over 36 months |

### 1.6 The background asks

| They ask | Sentinel | Status |
|---|---|---|
| 26 departments, each controlling its own cameras | Department-scoped access enforced in the database | **Built** |
| Analog and IP cameras | IP directly; analog through its NVR or an encoder | **Built** for NVRs; no encoder tested |
| Leave cloud and local storage, 7–15 day retention, in place | Read-only pull; footage is not re-stored centrally | **Built** |
| Public-facing private cameras, "wherever feasible and permitted" | Consent reference and expiry enforced: without current consent a camera is never viewed or analysed | **Built** |
| Automated alerts from VAHAN, SARTHI, eGujCop, AFIS, NAFIS records | Connectors ready; watchlist alerts live on our own representative data | **Partial** — no live credentials |

### 1.7 Where each evaluation area is won

| # | Area | Slides | Live | Hand over |
|---|---|---|---|---|
| 01 | Successful test case | 05, A2, A3, A4 | Demo 1–3 on today's feeds | Movement Report ZIP |
| 02 | Presentation: problem, model and justification, key features | 02, 03, 04, 07, 11, A1, A7 | — | The deck |
| 03 | Solution architecture | 07, 08, 09, A6 | — | HLD PDF |
| 04 | Working platform, own feed and government feed | A2, A3, A4 | The console; the government-grid copy as fallback (§11) | — |
| 05 | Analytics: ANPR, vehicle and person detection, intrusion, objects, timestamps, reports | 06, A3, A4, A5 | Zone events, people counts, camera-clock times | Movement Report; `scripts/evidence_report.py` output |
| 06 | Scalability and PoC readiness | 08, 09, 10, A6, A8, A9 | Health screen | Runbook |
| 07 | Submission completeness | — | — | Already submitted (06 — Submission playbook) |
| Bonus | Hybrid architecture · cross-camera correlation · analytics beyond ANPR · edge and low bandwidth · security, privacy, audit, RBAC · dashboards, alerts, health, APIs | 06, 07, 08, 09, 10, 11, A4, A5, A6, A7 | Probable stops, impossible travel, Audit → Verify chain | — |

### 1.8 Gaps a juror can find, and the answer to give

| A juror notices | Answer |
|---|---|
| ~~The model choice and its justification are not on a slide~~ — **on slide 07** | If pressed on *why hybrid*: *"Model 1 is the foundation everything stands on; Models 2 and 3 connect every department without changing its system; Model 4's central recording only where it pays off, because centralising everything needs a backbone the State does not have (slide 08)."* |
| *"How firm are these costs?"* (slide 10) | Order of magnitude, for comparing approaches, not a tender. The biggest line, district analysis servers, rests on a vendor GPU benchmark; Phase 0's first exit criterion is measuring it. Every figure re-derives from the scale plan's formulas (04 §9). |
| Face recognition (Model 4, FAQ 22) | Excluded by decision. Faces are detected only to be blurred; the platform can host a recognition module behind the same access controls if policy allows. |
| Wanted and missing *persons* in the watchlist | Matching is by vehicle plate. Person records are reached through the eGujCop and AFIS connectors once access exists; no face matching. |
| Event bus, tiered storage, HA, network segmentation | Designed and sized (01, 04, 08), not running on a laptop. What is running is the same code that sits at each district. |
| No camera-type layer on the map | Filters by department and status, plus the coverage-gap layer; camera type is a registry field. |
| *"Where does the 12 / 28 / 35 / 25% split of the 80,000 cameras come from?"* (slide A6) | It is our planning assumption, labelled as such on the slide: the brief gives the total and how departments use cameras, not a breakdown. We estimated it from those uses — check-posts and highways continuous, junctions sampled, godowns and offices motion-triggered, indoor and private feeds view-only. The GPU count and server cost follow from it, so the pilot replaces it with each department's inventory and every figure re-derives (04 §1.1, §9). |
| No 80,000-camera load test | Measured capacity per machine plus the arithmetic, re-derivable from five formulas (04 §9); the pilot's first exit criterion is a measured benchmark. |
| Hikvision and Dahua not tested on hardware | Written to the vendors' published APIs and tested against mocks; ONVIF and RTSP reach the same devices. |
| The FAQ says the sandbox feeds were *"synchronised on a common timeline"* | Our measurement found the replayed clips came from different dates ([cross-camera finding](../evidence/CROSS-CAMERA-TRACKING-FINDINGS.md)); that is why every stop carries the camera's own clock, and why a mismatched route is visible rather than hidden. Raise it only if timing comes up. |

---

## 2. Review findings to fix or prepare for before Monday

Ordered by how badly each could hurt in front of the jury.

| # | Finding | Why it matters | Action |
|---|---|---|---|
| 1 | **Latency wording is inconsistent.** [04-SCALE-PLAN §7](./04-SCALE-PLAN.md) sets a pilot exit criterion of "alert latency < 5 s"; the [M14 run](../evidence/M14-EVIDENCE-RUN.md) measured **27.4 s median, 86.6 s p90** from scene time to stored detection (archived replays through a remote gateway, with temporal voting). | A juror who reads both will ask. | Measure on the M4 with the local synthetic grid. Say it precisely: *"An alert reaches every console within a second of a confirmed read. A read is confirmed after several frames agree — that is a deliberate choice for evidence quality; it is near-real-time for investigation, not boom-gate control."* Consider amending the pilot criterion to "< 5 s from confirmed read to operator". |
| 2 | **Analysis capacity vs ~50 cameras.** Measured edge on the M2 is ~16 analysed fps in total ([tier capacity](../evidence/TIER-CAPACITY.md)). Fifty cameras at 4 fps would need 200 fps. | If the designated vehicle passes an un-analysed camera, the route has a hole we cannot explain away. | Plate-yield triage on arrival (§6.2), then start analysis immediately and keep it running all day. |
| 3 | **Cross-camera has only ever been shown with one camera's sightings.** | It is the headline capability. | Own-car, three-camera drill before Monday (§0 item 2, §6.5). Record it as the fallback video. |
| 4 | **ANPR accuracy is 78% after the vote**, below the 85% gate. | "Is it good enough for evidence?" | Own it: the holdout, the method, the 8.6% → 78% story, and that every hop carries a snapshot an officer confirms. Never claim a higher number. |
| 5 | **The L4 300 fps/GPU figure is a vendor-benchmark estimate**, not measured. | The whole GPU count (≈560 L4) rests on it. | Say "estimated, and re-derivable": show the formula in [04 §9](./04-SCALE-PLAN.md) and offer a pilot-phase benchmark as Phase 0's first exit criterion. |
| 6 | **README screenshots predate the UI redesign** (README says so). | Slides must show the product they are about to see. | **Pitch deck done (11 Oct):** light-theme screenshots of the current console via `npm run screenshots:pitch`. The README set and the submission deck (`make deck`) are still the old screens. |
| 7 | ~~Uncommitted mirror work~~ (`scripts/gov_mirror.py`, `SOURCE=mirror`). | The sandbox grid is being taken down; the mirror is our only copy of real government footage. | **Done:** committed 10 Oct (`7f01c44`); all 30 cameras recorded to `data/gov-mirror/` (gitignored — copy it to the M4 by hand). |

---

## 3. Countdown

| Day | Must finish |
|---|---|
| **Thu 8 Oct** | Email organisers. Finish and commit the gov mirror; start `make mirror-capture`. Book the own-car drill. |
| **Fri 9 Oct** | M4: automated UAT already passed (QUICK, 8 Oct). Full `make uat` ×2 for the capacity curve, then Part 2 A–N; record the M4 fps edge. Own-car three-camera drill; record it. ReID go/no-go at 18:00. |
| **Sat 10 Oct** | Regenerate screenshots and deck. First full 20-minute rehearsal with a timer. Chase organiser answers before 18:00. |
| **Sun 11 Oct** | Offline rehearsal (Wi-Fi off). Real secrets and operator logins (runbook §3). Pack the kit. Print §12 cheat card and the CSV template. |
| **Mon 12 Oct** | Arrive early. Runbook §4–§6, then §6.2 triage below. Analysis running before the jury arrives. |

---

## 4. The 20 minutes

Slides: [Sentinel-Finale-Pitch.pptx](./Sentinel-Finale-Pitch.pptx) — **12 main slides and a 9-slide
appendix** (A1–A9), light theme. Rebuild with `make pitch` (screenshots: `npm run screenshots:pitch` in
`apps/web`). Speaker notes carry the talk track for every slide.

### 4.1 The room

The jury is **senior IPS officers and technology professors**. Pitch to both at once:

- **Officers decide on outcomes and trust.** Lead every slide with what changes on duty — a vehicle
  traced, an alert raised, a report that stands up in a case file. Use their words: investigation, case
  file, bandobast, chain of custody. Never explain policing to them.
- **Professors decide on rigour.** Give the method in one sentence, then the measurement, then the
  limitation: *"the clock is read off the frame and accepted only when a second reading agrees; when it
  can't be read we say time unknown."* Say the numbers we did not reach before they ask.
- **Relaxed means fewer slides, longer pauses.** Twelve slides in twenty minutes, seven of them on the
  live demo. Finish a sentence, pause, then click. If a slide has been understood, move on.

### 4.2 The storyline

The tracker in each slide's top-right shows the chapter: **Why → What → Demo → Trust → How → Value →
Next**. Every chapter answers the question the room is asking at that moment.

| Time | Chapter · the room is asking | Slide | On screen | Rubric area |
|---|---|---|---|---|
| 0:00–1:00 | **Opening** · *who are you?* | 01–02 | Title; team (20 s) | Presentation |
| 1:00–2:30 | **Why** · *what is wrong today?* | 03 | ~80,000 cameras, 26 systems; today versus with Sentinel | Presentation |
| 2:30–3:00 | **What** · *what is it?* | 04 | See, find, alert | Presentation |
| 3:00–10:00 | **Demo** · *does it work?* | 05, then live | Connect → trace the designated vehicle → watchlist alert → hand over the Movement Report | **Test case** |
| 10:00–11:00 | **Trust** · *can we rely on it in court?* | 06 | Camera's own clock, blur, hash-chained audit; live: Audit → Verify chain | Analytics; bonus: security |
| 11:00–15:00 | **How** · *will it work across the State?* | 07–09 | The hybrid model and why; send meaning, not video; five layers | Architecture; scalability |
| 15:00–17:30 | **Value** · *what does it cost, and why you?* | 10–11 | Estimated cost; three pillars with proof and a stated-plainly line | Scalability (costs); presentation |
| 17:30–18:30 | **Next** · *what do you need from us?* | 12 | Rollout and the three asks; the closing line | PoC readiness |
| 18:30–20:00 | Buffer and questions | Appendix | Jump to A1–A9 by number | — |

**If the jury gives the vehicle number at the start**, run the demo first and come back to slide 03.
**If time runs short**, shorten How to slides 07 and 08 only; the five layers are in the speaker notes.
Never cut the demo.

### 4.3 The appendix, for questions

Not presented. Each slide carries its number (A1–A9) in the corner; the divider after slide 12 lists
them. Type the number and press Enter in slideshow mode to jump.

| Likely question | Go to |
|---|---|
| *Who uses it day to day?* | A1 Who it serves |
| *Show me again* — if the live demo failed | A2–A4 Demo backups |
| *What else does it detect?* | A5 Beyond number plates |
| *How did you size 80,000 cameras?* | A6 Camera tiering (planning assumption) |
| *How is this different from a central VMS?* | A7 How Sentinel compares |
| *How accurate is it, really?* | A8 Measured results |
| *What exactly happens in each phase?* | A9 Rollout in detail |

Three roles, fixed in rehearsal:

- **Narrator** — faces the jury, tells the story, never touches the laptop.
- **Driver** — keyboard and mouse only; says nothing unless asked; jumps to appendix slides on request.
- **Anchor** — watches Health and the worker log; takes questions on architecture and cost.

---

## 5. Pitch script

Say it in your own words after the first rehearsal; the shape is what matters. Each chapter opens with
one line that answers the room's question.

**0:00 — Opening** (slides 01–02).
> "Sentinel lets an officer type a registration number and see where that
> vehicle went, across every government camera, in seconds — and be told the
> moment it is seen again."

Then twenty seconds on the team: *"We are Invental Data Labs. I'm Parth Patel;
I lead the team — a consulting AI solution architect who has worked with IBM and
United Airlines, with an MTech in Data Science from IIT Bombay. With me is Anuj
Patel, a data scientist from Göttingen."*

**1:00 — Why** (slide 03).
> "Gujarat already has about eighty thousand cameras across twenty-six
> departments. They exist; they don't work together. When a vehicle is used in
> a crime, tracing it means phoning each department, separate logins, manual
> review — while the footage is overwritten within a week or two."

**2:30 — What** (slide 04).
> "One platform, three jobs: see every camera, find any vehicle, and be alerted
> when one of interest appears. Let us show you, on today's cameras."

**3:00 — Demo** (slide 05, then live). Follow §6 and runbook §7; narrate each
step *before* clicking.
> "These are the cameras we were given this morning, on one map and one wall.
> We type the number you gave us — spacing and case don't matter. Every
> sighting appears in the order the cameras' own clocks give. Each stop: the
> camera, the time printed on its frame, the plate as read, the snapshot with
> faces blurred. A hop no vehicle could make is flagged, not drawn. We arm a
> watch, and the alert reaches every screen. And here is the Movement Report —
> sealed with a hash manifest — which we hand you now."

**10:00 — Trust** (slide 06).
> "The time in that report is the time the camera printed on its own frame. If
> it cannot be read, we say *time unknown* — we never guess. Every search,
> export and reveal is in a hash chain: change one entry and verification fails.
> And we do no face recognition at all."

**11:00 — How** (slides 07–09). §8 for the full walkthrough.
> "We built a hybrid of the four reference models — the registry as the
> foundation, one console over every department's system, adapters so nothing
> is replaced, and central recording only where it pays off. The reason is
> physics: centralising every camera needs 160 gigabits a second from sites a
> thousand kilometres apart. We read plates where the video is filmed and send
> only what we find — about 140 megabits. What you saw today is the district
> layer, on a laptop: the same code."

**15:00 — Value** (slides 10–11). Say *order of magnitude* before the first number.
> "About ₹80 crore to build and ₹24 crore a year to run, for eighty thousand
> cameras — roughly ten thousand rupees a camera — with no licence fees, against
> ₹400 crore-plus to centralise. Why us: it is proven on Gujarat's own cameras,
> its evidence holds up, and it fits what the State already owns."

Read the stated-plainly line on slide 11 aloud: *"Plate accuracy is 78%, below
our own target; the compute is sized from vendor benchmarks; plate-less
matching is designed, not built."*

**17:30 — Next** (slide 12).
> "Start with one district. Each phase is useful on its own; none needs a
> switch-over. To begin, we need each department's camera inventory, read-only
> access, and database access when it is ready. Type a plate — see where it
> went. Thank you."

Then stop, and wait for questions.

---

## 6. The live vehicle trace

The click-by-click drill is [runbook §7](./10-FINALE-RUNBOOK.md). What follows
is what has to be true **before** the number is read out.

### 6.1 The one rule

**A vehicle can only be found on cameras that were being analysed when it
passed.** Search is retrospective over stored reads; it cannot go back and
re-read footage nobody analysed. So the drill is won or lost in the first hour
on site, not in the five minutes in front of the jury.

### 6.2 Plate-yield triage on arrival (about 30 minutes)

On the sandbox, of the cameras we analysed, **only one** (cam06) produced valid
registrations — most wide-angle cameras put plates at 30–80 px, below what any
OCR resolves
([M1 findings](../evidence/M1-CAPACITY-FINDINGS.md)). So most of the ~50
cameras will never yield a plate however much compute they get. Find the ones
that will, and spend the compute there.

1. **Visual triage, zero analysis cost (5 min).** Put all cameras on the live
   wall in 16-tile pages. Mark each: *plates legible* / *maybe* / *no*
   (indoor, wide-angle, night, black frame).
2. **Yield test on the *legible* and *maybe* cameras.** Split them between the
   two laptops in batches sized to each machine's measured edge (§0 item 3),
   at a low rate:

   ```bash
   make worker SOURCE=registry CAMERAS=cam03,cam07,cam11,cam14 SAMPLED_FPS=2
   ```

   After ~8 minutes per batch:

   ```bash
   docker exec sentinel-postgres psql -U sentinel -d sentinel -c "
     select c.camera_id, c.tier,
            count(d.*)                                                 as reads,
            count(*) filter (where d.format_valid)                     as valid_reads,
            count(distinct d.plate_normalised) filter (where d.format_valid) as distinct_valid
     from cameras c
     left join detections d on d.camera_id = c.camera_id
                           and d.created_at > now() - interval '30 minutes'
     group by 1, 2 order by valid_reads desc, reads desc;"
   ```
3. **Assign tiers by yield**, by re-importing the CSV rows with a new `tier`
   (the worker applies it within 30 s, no restart):

   | Yield | Tier |
   |---|---|
   | Valid reads, on a road the vehicle is likely to use | `a_continuous` (STRIDE=3) or `b_sampled` |
   | Some valid reads | `b_sampled` at the fps the budget allows |
   | Reads but none valid | `c_motion_gated` |
   | Nothing / not legible | `d_registry_only` — still on the map and live wall |

4. **Budget check**:
   `cameras you can analyse = 0.75 × measured edge fps ÷ per-camera fps`.
   With the M2's 16 fps edge, that is **3 cameras at 4 fps** — so the M4 and
   sharding by department across both laptops (runbook §6) are not optional.
5. **Leave it running all day.** Watch `n s behind live` on the Cameras screen;
   a growing number means demote a camera.

**If feeds are looped recordings** (as in the sandbox), every camera's loop has
to be analysed at least once before the evaluation. Note each loop's length
and make sure each `a`/`b` camera has run for at least one full loop.

**Ask the organisers, politely, which corridor or cameras the designated
vehicle will pass.** They may decline; asking costs nothing, and the answer
turns triage into certainty.

### 6.3 Before the jury arrives

- Arm 3–4 representative watchlist entries (stolen, wanted, missing) built
  **from plates actually read today**, so a real alert fires during the
  session.
- Search window set to cover the whole day (48 h covers both days).
- One camera open on the live wall; Health green; worker log visible to the Anchor.

### 6.4 When the number is read out

- Repeat it aloud and type it. If there are **no sightings**: say so plainly,
  open Health to show which cameras were analysed, then try the ambiguity
  rung and the Overview recent reads for a near-miss. A calm, explained "not
  seen on analysed cameras" beats a fabricated route — and the system refuses
  to fabricate one by design.
- If there are sightings on **one** camera only: show it fully, then say which
  analysed cameras it did not pass, from Health.

### 6.5 Own-feed fallback (record it on Friday)

A team car with a known plate, driven past three phones running an RTSP camera
app at three known GPS points, onboarded by CSV, analysed live. It produces a
genuine three-hop route through the real pipeline — the exact claim the
organisers' grid could not let us prove. If the venue network fails, play this
recording and narrate it as what it is.

---

## 7. "What if the plate cannot be read?"

The bonus asks for multi-camera correlation. Be precise about what exists.

**Built and showable today** (all in
[`detections/service.py`](../services/core_api/src/core_api/detections/service.py)):

| Rung | What it catches | How it shows |
|---|---|---|
| Exact | Clean reads | Solid hop |
| OCR-ambiguity class | `0↔O`, `1↔I`, `8↔B`, `5↔S`, `2↔Z` — search `GJO1AB1Z34`, get `GJ01AB1234` | Solid hop |
| One character away | A single misread character | Dashed amber *probable* hop with the plate as read |
| Appearance-gated bridge | Reads sharing the last four characters, ≤ 3 edits away, **same vehicle class and colour** as every confirmed sighting, reachable at ≤ 120 km/h from the hops either side | Dashed amber *probable* hop |
| Feasibility gate | Two sightings implying > 150 km/h (cloned plate, clock skew, misread) | Hop flagged, not silently drawn |

**What to say:**
> "When the plate is partly readable, the ladder recovers it and marks the hop
> as probable, never confirmed — an officer checks it against the snapshot. We
> already use vehicle class and colour, plus road-speed feasibility, to bridge
> gaps. Full appearance re-identification — matching a vehicle whose plate was
> never read at all — is designed and costed; here is the design."
> Then show [14 — Appearance ReID design](./14-APPEARANCE-REID-DESIGN.md) §2.

**Never say** it matches vehicles with no plate read unless doc 14 has been
built, tested on the own-car footage, and passed the go/no-go.

---

## 8. Architecture walkthrough at 80,000 cameras (four minutes)

Draw or show it as five layers, bottom to top, with **one number at each
layer**. Numbers are from [04 — Scale Plan](./04-SCALE-PLAN.md).

```
  Command centres · Field PWA · VAHAN / SARTHI / eGujCop / AFIS / NAFIS
        ▲  REST + SSE, RBAC + department row-level security
  STATE CORE (HA) + warm DR site
        Kafka → correlator → alerting · Core API · Postgres/PostGIS/Timescale
        object storage ≈ 390 TB usable · 563 events/s · RPO 15 min, RTO 1 h
        ▲  mTLS, events + snapshots ≈ 140 Mbps statewide (4.5 Mbps metadata-only)
  DISTRICT EDGE ×34  (+ ~1,500 Jetson boxes at remote sites)
        relay (one pull per camera) → decode → ANPR + analytics → store-and-forward (72 h)
        ≈ 140 servers × 4 L4 ≈ 560 GPUs, sized by camera tier
        ▲  read-only RTSP / ONVIF / vendor SDK, pulled
  DEPARTMENT SYSTEMS (unchanged)  26 departments' cameras, NVRs and VMS,
        keeping their own 7–15 day retention
        ▲
  80,000 CAMERAS, tiered: A 12% continuous · B 28% sampled · C 35% motion-gated · D 25% view-only
```

Script, one breath per layer:

1. **Cameras, tiered.** "Not every camera needs AI. A highway check-post and a
   PDS godown are different jobs. Twelve percent run continuous ANPR, a quarter
   are view-only. Tier is a registry field a department can change live — a
   camera goes to tier A for a bandobast."
2. **Department systems stay.** "We pull read-only streams through standard
   protocols and adapters. Nothing is installed on a department's system, and
   their recording keeps running. Their 7–15 days of footage stays where it is
   and is retrieved on demand — we don't buy it twice."
3. **District edge.** "Video is decoded and analysed in the district it was
   filmed in. What leaves is a 1 KB event and a 30 KB snapshot. If the link
   drops, the district keeps reading plates against a cached watchlist, alerts
   locally, and queues up to 72 hours. What you saw today is this layer, on a
   laptop — the same code."
4. **State core.** "Five hundred and sixty-three events a second is a modest
   stream. The core is about search and storage, not throughput: Postgres with
   PostGIS and TimescaleDB, Kafka, horizontally scaled correlators. A warm DR
   site; we have drilled backup, restore and audit-chain verification."
5. **Consumers.** "Control rooms, officers' phones, and the national and state
   databases through one integration gateway, with department-scoped access
   enforced in the database itself."

Close with the formula slide:
> "Every number here re-derives from five formulas. Give us your camera mix and
> we will recompute it in front of you."

---

## 9. Impact on infrastructure cost

On screen: **slide 10**. Indicative, for comparing architectures, not for
tendering. Source: [04 — Scale Plan §6](./04-SCALE-PLAN.md). Per-camera figures
are derived here.

| | Sentinel (edge-first hybrid) | Full central VMS (Model 4) |
|---|---|---|
| Sustained backbone | **≈ 140 Mbps** | 160 Gbps |
| Hot storage, 7 days | **≈ 390 TB usable** (selective) | 12.1 PB |
| Capex | **≈ ₹80 cr** → ≈ ₹10,000 per camera | ₹400 cr+ → ≈ ₹50,000+ per camera |
| Opex | **≈ ₹24 cr/yr** → ≈ ₹3,000 per camera per year | Materially higher (not costed) |
| 5-year TCO | **≈ ₹200 cr** → ≈ ₹25,000 per camera, ≈ ₹420/camera/month | — |
| Software licences | ₹0 (open-source stack) | Per-camera VMS licensing |

Backup, if a juror asks how the totals are made up:

| Build (capex) | ₹ cr | Run (opex, a year) | ₹ cr |
|---|---|---|---|
| District analysis servers (140 × 4 L4 GPUs) | 28 | Power, cooling, data-centre space | 5 |
| State data centre (compute, 600 TB, network, HA) | 14 | Network and bandwidth | 7 |
| Integration, migration, training, rollout | 12 | AMC and support (≈12% of hardware) | 8 |
| Remote edge boxes (1,500) | 10.5 | Operations team (NOC, L1–L3) | 4 |
| District uplink upgrades (GSWAN reused) | 9 | | |
| Disaster-recovery site (warm standby) | 7 | | |
| Software licences | 0 | | |
| **Total** | **≈ 80** | **Total** | **≈ 24** |

Talking points:

- **Reuse is the saving.** No camera, NVR or VMS is replaced; department
  retention is reused, not re-stored; GSWAN is reused for backhaul.
- **Tiering is the lever.** Moving 10% of cameras between tiers moves the GPU
  count by a predictable amount — the department controls its own cost.
- **Bandwidth is physics, not budget.** 160 Gbps from sites 1,000 km apart is not
  available at any price on many taluka links; 140 Mbps is.
- **Value is measurable.** "Minutes to trace a vehicle across departments" goes
  from hours of phone calls to one search — propose it as the pilot's KPI,
  alongside alerts acted on and false-match rate.
- **Be honest about the basis.** GPU throughput is a benchmark estimate; capex
  is order-of-magnitude. Phase 0 exists to replace both with measured numbers.

---

## 10. Q&A bank

[06 — Submission Playbook §7](./06-SUBMISSION-PLAYBOOK.md) has the core
answers (privacy, disturbance, onboarding time, what we need, what doesn't
work). Additional likely questions:

| Question | Short answer |
|---|---|
| "Is this real-time?" | §2 item 1, word for word. |
| "Why is accuracy 78%?" | Measured on 81 hand-labelled real government plates, legible ones only; it was 8.6% before the measurement drove the fixes. Every hop shows the snapshot for confirmation. Fine-tuning on Gujarat plates is the Phase 0 work item. |
| "What happens with 80,000 cameras when the WAN goes down?" | District edge keeps analysing and alerting locally; 72-hour queue drains on reconnect, alerts first. |
| "Cloned plates?" | Feasibility gate: the same plate at two places at an impossible speed is flagged as an anomaly, not drawn as a route. |
| "How do you onboard a new vendor?" | A driver against one interface, verified by the conformance suite — [07 — Driver SDK](./07-DRIVER-SDK.md). |
| "Private cameras?" | Consent reference and expiry enforced: without current consent a camera is registered but never viewed or analysed. |
| "Why no face recognition?" | Excluded by decision; faces are only detected to blur them. The architecture can host an FRS module behind the same access controls if policy allows. |
| "Vendor lock-in?" | Open protocols, open-source stack, documented APIs; every component replaceable. |
| "What if someone turns a camera away, or the wind knocks it?" | Every camera learns its own view. If the view shifts it raises an alert within about 6 seconds with before and after frames; if it no longer recognises the scene at all, within a minute. It closes itself when the camera is put back. No false alarms on rain, traffic or wind shake in today's feeds. PTZ cameras opt out. Show it: Alerts → Camera views. |
| "How did you get 300 fps per GPU?" | It is a benchmark-based estimate; here is the formula; Phase 0 measures it. |

---

## 11. Fallback ladder

Use the highest rung that works, and **say which rung you are on.**

1. Organisers' feeds, live, on the M4 (+ M2 sharding).
2. Organisers' feeds on whichever laptop survives; fewer cameras, higher tier.
3. Phone hotspot + own RTSP cameras: re-run the own-car drill live.
4. Local gov mirror (`make mirror-start`, `make worker SOURCE=mirror`) — real
   government footage, offline. **Tested 8 Oct on the M2:** the drill works end
   to end (search, map, timeline, evidence, BOLO retro-hit, a live forward alert
   on every clip loop, Movement Report with matching hashes), but **only cam06
   yields valid plates**, so the route is single-camera. The same car reappears
   each time the clip loops (~16.5 min).
   **Times (10 Oct, after the camera-clock change):** a sighting's time is only
   ever the clock burned into its own evidence frame. cam06's frames are too
   damaged for that clock to be read (6–12% of seconds, 0 of 8 reads timed in a
   13-minute run), so **its plates show as "time unknown — camera clock
   unreadable"**, listed under the timeline and in the report's "Also seen"
   section. cam30 shows the clock working: 65 of 115 reads timed, e.g.
   `GJ39C8018` at 08 Aug 2026 21:10:33 — the time visible in its snapshot.
   Say plainly why cam06 is untimed before a juror asks.
   Good demo plates: `GJ11CD8389` (one-character twin `GJ11CD8889`, same white
   car), `GJ11S7924`, `GJ03MH7800` (search `GJO3MH78OO` for the ambiguity rung);
   `GJ39C8018` on cam30 for a timed sighting.
5. Recorded own-car video (§6.5) and the demo videos from local disk.

---

## 12. Cheat card (print it)

| Number | Value |
|---|---|
| Cameras / departments / districts | 80,000 / 26 / 34 |
| Central video vs Sentinel backbone | 160 Gbps vs ≈ 140 Mbps (≈ 1,140×) |
| Hot storage, one week | 12.1 PB vs ≈ 390 TB (≈ 31×) |
| Events statewide | ≈ 563/s, ≈ 48.7 M/day |
| GPUs | ≈ 560 L4 (N+1) in ≈ 140 4-GPU servers; ≈ 1,500 Jetson edge boxes |
| Capex / opex / 5-yr TCO | ≈ ₹80 cr / ≈ ₹24 cr/yr / ≈ ₹200 cr |
| Per camera | ≈ ₹10,000 capex, ≈ ₹3,000/yr opex |
| Model 4 comparison | ₹400 cr+ capex |
| ANPR accuracy (measured) | 78% exact after vote, 88% per character, 81 real plates |
| Laptop edge (measured, M2) | ≈ 16 analysed fps total |
| Event size / snapshot | ≈ 1 KB / ≈ 30 KB |
| Edge autonomy | 72 h store-and-forward |
| DR | RPO 15 min, RTO 1 h (5 min for alerting); drill: 1 M rows restored in 5.7 s |
| Tiers | A 12% · B 28% · C 35% · D 25% |
| Rollout | Pilot 500 cams (0–3 mo) → 5,000 (3–9) → 30,000 (9–21) → 80,000 (21–36) |

---

*Back to [10 — Finale Runbook](./10-FINALE-RUNBOOK.md) ·
[06 — Submission Playbook](./06-SUBMISSION-PLAYBOOK.md).*
