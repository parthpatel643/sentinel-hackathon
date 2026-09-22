# Gujarat Police Innovation Challenge 2026 — Sentinel Hackathon
## Detailed Research & Build Guide (for Students + Startups)

**Source:** Entire `sentinel.gujarat.gov.in` website crawled on 20 Sept 2026 + press coverage
**Official portal:** https://sentinel.gujarat.gov.in/
**Status at research time:** Registration + Submission open, deadline **28 September 2026** (extended by popular demand)

> TL;DR: This is NOT a normal hackathon / PPT contest. You must build a **working, deployment-ready CCTV integration + AI video-analytics platform** that onboards ~50 heterogeneous live government CCTV feeds, runs ANPR + watchlist matching continuously, generates real-time alerts, shows GIS vehicle tracking, and can plausibly scale to ~80,000 cameras. Mock-ups / animations = instant reject.

---

## 1. Hackathon At-a-Glance

| Item | Detail |
|---|---|
| **Full name** | Gujarat Police Innovation Challenge 2026 — CCTV Integration Hackathon (aka Sentinel) |
| **Organizer** | Home Department, Govt. of Gujarat via **State Crime Records Bureau (SCRB)** |
| **Tagline** | "Protect What Matters. Not a simulation. Not a proof of concept. Design solutions built for real-world deployment." |
| **Core mission** | Integrate 80,000+ CCTV cameras from **26 independent Govt departments** across 34 districts into **one unified video management + analytics ecosystem** |
| **What winners get** | Cash (₹51,00,000 total) + Phase-1 money acts as **grant** for Phase-2 build + shot at **real statewide deployment / production PoC** with Gujarat Police |
| **Partners** | Tech Partner: **i-Hub Gujarat** (Govt enterprise). Knowledge Partners: **Dhirubhai Ambani University (DAU / DA-IICT)** + **National Forensic Sciences University (NFSU)** |
| **Venue (finale)** | i-Hub Gujarat, Ahmedabad |
| **Registration fee** | **Free** (Email OTP verification) |
| **Team format** | Individual OR team allowed |
| **Open-source mandate** | "All solutions should use open-source technologies" — recommended: React, Python, Node.js, PostgreSQL/PostGIS, WebRTC, RTSP, Kafka/RabbitMQ, TensorFlow/PyTorch, FFmpeg/GStreamer, Leaflet/OpenLayers |

### Important Dates (current, after extension)

| Milestone | Date |
|---|---|
| Registration Open | 4 August 2026 |
| **Last Date to Apply + Upload Submission** | **28 September 2026** |
| Shortlisting Announcement | 28 September 2026 |
| Hackathon Event (Grand Finale, Phase-2) | **12–13 October 2026** |
| Results + Prize Distribution | 13 October 2026 |

> Note: Press from mid-Aug 2026 still quotes old dates (10–11 Sept, ₹37 lakh pool). **Website is authoritative now: 12–13 Oct, ₹51 lakh.** Dates were extended due to demand.

### Contact / Helpdesk

- Email: `sentinel.hackathon@gujarat.gov.in`
- Phone: +91 95370 89982 (Mon–Sat, 10 AM–6 PM)
- Address: SCRB, Next to Police Bhavan, Sector-18, Gandhinagar, Gujarat 382009
- Socials: X `@GujaratPolice`, Instagram `gujaratpolice_`, Facebook `dgpgujaratofficial`

---

## 2. Who Can Participate? (Both Students + Startups — plus 4 more tracks)

Homepage lists **6 builder types**, FAQs / Phases compress them into **2 prize categories**:

### Category 1 — Students / Small & Medium Startups / Academia
- UG + PG student teams from any recognized institute in India
- Researchers: faculty, PhD scholars, independent R&D groups
- **DPIIT-recognized startups** (must show valid DPIIT Startup Recognition Certificate at registration/verification — Startup India criteria)
- Small & medium startups

### Category 2 — Large Startups / Industry
- Large startups + established tech enterprises / software firms
- System Integrators (security deployment teams who integrate at Govt scale)
- Working professionals / engineers in AI, Computer Vision, Security
- LLPs, partnerships, any business entity NOT eligible as DPIIT startup

Registration page offers 3 roles in dropdown:
1. 🎓 Student / Student Team / Researchers / Professionals
2. 🚀 DPIIT Startup
3. 🏢 Company / SI

**Practical takeaway for you:** As a student team you compete in Category 1 (₹7L Phase-1 pool, cheaper expectations, jury rewards innovation). As a startup you pick DPIIT vs Company carefully — it decides which Phase-1 prize table you fall in.

---

## 3. The Problem Statement — In Simple Language

### 3.1 Background (why this exists)
Right now **26 Gujarat Govt departments each run their own isolated CCTV island**:
- Mix of **analog + IP cameras**, different vendors, different VMS software, different AMC periods, different storage (some cloud, some local NVR), different retention (7 days vs 15+ days)
- Geographically spread up to **~1,000 km apart** (border districts to Valsad, Dahod, Somnath, Jamnagar, Dwarka, etc.)
- Different purposes: Home Dept = traffic / law & order / crime; Food & Civil Supplies = godowns / PDS shops; RTO = offices / testing tracks / checkpoints
- **No central inventory, no unified viewing, no cross-camera search.** To track a getaway car police must manually call each department and watch footage separately.

Government wants:
1. Integrate govt cameras in public domain into **one unified video management + analytics ecosystem**
2. Also support **viewing of private public-facing cameras** (societies, malls, shops) wherever feasible/permitted
3. Cross-reference live video with existing Govt databases — **VAHAN (vehicles), SARTHI (licences), eGujCop (Gujarat Police CCTNS), AFIS / NAFIS (arrested persons, fingerprints, wanted, missing, unidentified bodies)**
4. Auto-generate **real-time alerts** for law enforcement
5. Reuse existing infra to max extent — **secure, scalable, interoperable, cost-effective, vendor-neutral, no vendor lock-in**

### 3.2 Core Goal (one-liner for your PPT)
> Propose a secure, scalable, interoperable, technically feasible, cost-effective approach that uses existing infrastructure to the maximum practical extent to deliver unified viewing + AI analytics + database-driven alerts, scalable to ~80,000 cameras.

### 3.3 Four Key Challenges (must address in HLD)
1. **Heterogeneous infra** — vendors, VMS, AMCs, storage, codecs, protocols
2. **Geographical dispersion** — ~1,000 km, variable bandwidth
3. **Unified analytics** — one framework for events across all onboarded cameras
4. **Scalability** — add cameras / departments / analytics without redesign

### 3.4 What You Actually Have to Build (functional loop)
```
CCTV feeds (RTSP/ONVIF/SDK) → Ingest / Transcode / Relay
  → AI analytics (ANPR mandatory + face / person / vehicle / anomaly)
  → Watchlist DB (you create: stolen / wanted / missing / blacklisted / suspect)
  → Continuous matching → Real-time alert (dashboard + GIS + notification)
  → Searchable history (vehicle route, timestamps, locations, event index)
  + Registry/GIS foundation + health monitoring + RBAC + audit
```

During evaluation they give you a **designated vehicle number** — you must find it across feeds, show **complete timestamped route + location-wise movement history on GIS**, plus prove continuous watchlist cross-referencing.

---

## 4. The 5 Architecture Choices (Pick 1 or Hybrid)

> **Critical rule:** **Model 1 is MANDATORY for everyone** — it is the common CCTV registry + GIS foundation. You must combine Model 1 + (Model 2 and/or 3 and/or 4) OR propose Hybrid/Custom that includes Model-1-equivalent functionality.

### Model 1 — Centralised CCTV Registry & GIS Mapping (MANDATORY, metadata-only)
- **What:** Central inventory + map of every camera. NO live streaming/recording.
- **Features:** bulk import / manual entry / API onboarding; interactive GIS map (Leaflet/OpenLayers/PostGIS) with dept/type/status/coverage layers; health + maintenance monitoring; gap-analysis reports (uncovered zones, ageing infra); role-based search/filter/export + audit trail
- **Suggested stack:** GIS Leaflet/OpenLayers/PostGIS; Backend Node.js or Python (Django/FastAPI); DB PostgreSQL+PostGIS; Frontend React; Dept-wise RBAC
- **Deliverables:** working registry portal + GIS view; bulk+manual onboarding demo; sample metadata dataset; Registry API docs; sample gap-analysis report

### Model 2 — Unified Viewing & Metadata Analytics (direct connect, NO middleware)
- **What:** Single viewing pane that pulls directly from each dept VMS via RTSP/ONVIF/SDK/API. Dept systems keep running untouched. No central storage of all video.
- **Features:** feed aggregation; ANPR metadata; event tagging + camera-wise indexing; searchable vehicle-movement records; configurable video walls / multi-grid; alerts for tagged events
- **Stack:** Streaming WebRTC/HLS relay; ONVIF/RTSP libs/vendor SDKs; ANPR (open-source/custom); microservices Node/Python; Kafka, Elasticsearch, PostgreSQL
- **Deliverables:** unified viewer wired to ≥2 different systems; ANPR on live/recorded; searchable metadata dashboard; architecture note proving dept systems unaffected
- **Best for:** student teams — lightest infra, fastest to demo

### Model 3 — VMS Federation & Middleware Integration (middleware, NOT direct)
- **What:** Middleware/federation layer talks to each VMS, normalizes via adapters, exposes ONE unified API downstream. Depts keep control. Enables cross-system event correlation.
- **Features:** adapter/plugin architecture per vendor; metadata exchange bus; cross-system correlation engine; unified workflow/alert dashboard; extensible connector framework
- **Stack:** Middleware Node.js / Java Spring Boot; Kafka/RabbitMQ; API Gateway Kong/NGINX; PostgreSQL+Redis; React
- **Deliverables:** middleware demo federating ≥2 systems; unified event-correlation dashboard; adapter docs; sample federated analytics report
- **Best for:** teams strong in backend/distributed systems, System Integrators

### Model 4 — Central VMS & AI Platform (full centralisation, heaviest)
- **What:** One statewide Central VMS — central ingest, record, store, playback, AI. Needs massive backbone, storage, GPU, redundancy, security.
- **Features:** central ingest; tiered hot/warm/cold storage; ANPR + face + crowd/vehicle counting + anomaly; statewide vehicle tracking + route reconstruction; ready to plug VAHAN/SARTHI/eGujCop/AFIS/NAFIS; DR/encryption/segmentation/RBAC
- **Stack:** custom/extended open-source VMS; S3/Ceph storage; Kafka + GPU inference; PostgreSQL/TimescaleDB; Kubernetes; high-bandwidth backbone + regional edge
- **Deliverables:** central VMS prototype on multi-dept sample feeds; ANPR + multi-location tracking demo; load-test report for ~80k cameras; DR design; security architecture doc
- **Best for:** companies / large startups with infra muscle

### Hybrid / Innovative (explicitly allowed + bonus-worthy)
Combine 2+ models or go fully custom, provided you meet functional + interop + security + scalability + analytics requirements. Example winning pattern: **Model 1 (registry/GIS) + Model 2 (light unified viewing) + selective Model 3 adapters + edge ANPR + central metadata search** — avoids Model 4's impossible storage cost while showing scale path.

---

## 5. What You Must Submit (4 items — all mandatory)

### (1) Solution Presentation (PPT/PDF)
- Chosen model (1–5 / Hybrid / Custom) + justification
- Overview, objectives, key innovations
- High-level architecture + end-to-end workflow
- AI analytics approach (detection, recognition, events)
- Watchlist correlation + alerting methodology
- Tech stack, scalability, interop, security, deployment
- Operational benefit / policing impact

### (2) Technical Proposal — High-Level Design (HLD)
- Full architecture diagrams + component interactions
- Heterogeneous integration (IP/analog, multi-vendor, RTSP/ONVIF/SDK)
- Live ingest from dispersed sites (bandwidth, edge vs central)
- Watchlist integration + continuous correlation + alert workflow (prioritisation, visualisation, UX)
- Analytics detail: ANPR, FRS, object/person/vehicle tracking, etc.
- Scale plan to ~80k cameras; prereqs/assumptions + dept-wise info needed for feasibility

### (3) Demo on YOUR OWN feed (screen recording, max 2–3 min)
- Onboard live OR recorded feed of your choice
- Show AI detection (ANPR / Face / other)
- Show correlation vs YOUR representative watchlist DB + auto real-time alert + visualisation
- **Must be working software with operational backend. Mock-ups / animations / concept videos = rejected.**

### (4) Demo on GOVT-PROVIDED feed (screen recording + output report)
- Onboard govt feed(s) → show live/recorded viewing
- Show analytics output on that feed
- Output report: detected vehicles / plates + timestamps
- Submission method: **Unlisted YouTube link** OR **Drive/OneDrive "Anyone with link — Viewer"** + optionally hosted platform URL + test login + optionally GitHub/GitLab repo link

### (6th step) Scale Plan to ~80,000 cameras must explain:
central / regional / edge compute; GPU/accelerator sizing; bandwidth + low-bandwidth tactics; hot/warm/cold storage vs retention; LB + horizontal scaling + monitoring/logging/health; HA + backup + DR + cybersecurity; estimated capex/opex + phased rollout plan.

---

## 6. Live Test Case (Sandbox Eval — the real filter)

After registration you unlock the **Resources page** with ~50 geographically distributed cameras (different depts, tech, formats, VMS, storage). Official dataset description:

- **30+ cameras × 12 hrs footage each** across **5 depts: Health, Police, GSRTC, Panchayat, Municipal**
- Served as **simulated live** via Python streaming middleware (recorded footage synced on common timeline → per-camera live URL). This protects production infra + gives every team identical repeatable conditions.
- Grand-finale Phase-2 uses **real CCTV feeds at scale**.

**You must:**
1. Onboard ~50 cameras onto ONE platform
2. Central monitoring + AI analytics
3. Given a **designated vehicle number on eval day**, identify + trace it across locations/times
4. Show **route + timestamped location-wise history on GIS + searchable events**
5. Show **continuous watchlist cross-referencing (your own representative DB allowed) + auto alerts**

---

## 7. Resources They Give You (very generous for a govt hackathon)

| Resource | Detail | Where |
|---|---|---|
| **Live camera grid** | RTSP (`rtsp://<host>:8554/stream/<id>`) for AI inference; WebRTC-WHEP (`:8889/.../whep`) for low-latency browser preview; HLS (`/live/.../index.m3u8`) for dashboards/mobile/firewalled nets | Resources page after login → "Sentinel Gujarat Live Portal" |
| **Catalogue API** | `GET http://<host>/api/ingest` returns every camera: id, location, codec, live status, stream props, all 3 URLs. **Ids/camera set can change — always start from catalogue, never hard-code** | Same |
| **Integrator's Guide** | Full page: OpenCV / GStreamer / FFmpeg / DeepStream snippets, do/don'ts, pre-submission checklist | `/resource` page (public, no login) |
| **Docs + problem framework** | Background, 4 models, tech stacks, deliverables, scale guidance | `/problems` + `/faqs` (50 FAQs!) |
| **Mentoring + jury** | DAU + NFSU: AI/CV/analytics/cybersecurity/forensics guidance + evaluation | Via event |
| **Infra for finale** | i-Hub Gujarat venue; Phase-2 live production environment | 12–13 Oct |
| **AI assistant** | On-site chatbot on portal for quick answers | Every page |
| What they DON'T give | No footage download (live-consume only); no pushing streams to gateway; no control-API access; no VAHAN/AFIS real DB (you mock representative watchlist); no cloud credits announced | — |

### Streaming code snippets (from official guide)
```python
import os
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
import cv2
cap = cv2.VideoCapture("rtsp://<host>:8554/stream/1", cv2.CAP_FFMPEG)
while True:
    ok, frame = cap.read()
    if not ok: break  # reconnect with backoff
    pts_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
```
```bash
gst-launch-1.0 rtspsrc location=rtsp://<host>:8554/stream/1 protocols=tcp latency=200 ! rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! fakesink
ffplay -rtsp_transport tcp rtsp://<host>:8554/stream/1
```

---

## 8. Do's and Don'ts (official — most failures come from ignoring these)

### Technical Do's and Don'ts (`/resource` Integrator's Guide)
**DO:**
- Force **RTSP over TCP** everywhere (`rtsp_transport=tcp`); if port 8554 blocked, fall back to HLS
- Drive **all timing from PTS** (`CAP_PROP_POS_MSEC` / buffer PTS / RTP timestamps), never wall-clock arrival time (gateway replays GOP buffer on join → first 1–2s arrive faster than realtime, breaks trackers/Kalman if you use arrival time)
- Reconnect with **exponential backoff** (start ~2s, cap ~30s)
- Read camera list + per-camera props from `/api/ingest` every run
- Handle **mixed H.264/H.265 + mixed resolutions**; size batches/buffers/decoders per camera
- Expect **scene discontinuity** (feeds loop → hard cut like camera reboot); reset background models / ReID galleries / track IDs gracefully
- Pace load: open only cameras you process, close idle captures (each client gets its own copy)

**DON'T:**
- Trust `CAP_PROP_FPS` for speed/dwell math — measure real rate or use timestamps only
- Assume constant frame rate — tolerate gaps without disconnect
- Treat join-time decode warnings (`Error constructing frame RPS`, `Could not find ref with POC`) as fatal — wait for first IDR, they self-correct
- Assume uniform grid (fixed-shape batch across all cameras will break)
- Try to `curl/wget /stream/<id>` expecting a file — it's a range-served player fallback, yields partial file that looks complete. Build against live capture from day 1.
- **Publish streams or call gateway control API — consume only**
- Reconnect in tight loop (DDoSes yourself)

### Submission / Eligibility Don'ts
- No mock-ups / animations / simulated UI without backend
- Model 1 alone is insufficient — must pair with 2/3/4/hybrid
- Bonus features **do NOT compensate** for missing mandatory test/demo/docs
- DPIIT startups must actually hold certificate; don't register in wrong category

### Pre-submission Checklist (official)
- [ ] All clients force TCP
- [ ] No logic depends on FPS or arrival time
- [ ] Gaps don't crash pipeline
- [ ] Backoff reconnect tested (restart a feed)
- [ ] Decoder warnings logged, not fatal
- [ ] Catalogue-driven camera discovery
- [ ] Mixed codec/resolution handled
- [ ] Sane behaviour across loop cut

---

## 9. Phases, Prizes, Evaluation

### Format: 2 Phases
- **Phase 1 — Sandbox Round:** integrate with test feeds, compete **within your category**. Top 3 per category (6 teams total) advance. Prize money doubles as **grant** for Phase-2 build.
- **Phase 2 — Production Round (Grand Finale):** 6 finalists integrate with **real CCTV at scale**, judged live by Gujarat Police leadership + technical jury, irrespective of category.

### Prize Pool: ₹51,00,000

**Phase 1 — ₹18,00,000**
| Pos | Cat-1 (students/small-medium startups) | Cat-2 (large startups/companies) |
|---|---|---|
| 1st | ₹4,00,000 | ₹5,00,000 |
| 2nd | ₹2,00,000 | ₹3,00,000 |
| 3rd | ₹1,00,000 | ₹2,00,000 |
| Subtotal | ₹7,00,000 | ₹10,00,000 |
+ 4 consolation ₹25,000 each across both cats = ₹1,00,000

**Phase 2 — ₹31,00,000**
1st (Grand Winner) ₹16,00,000 · 2nd ₹8,00,000 · 3rd ₹7,00,000

**Additional — ₹2,00,000**
Consolation ₹50,000 × 3 non-top finalists = ₹1,50,000 + Special Jury Award ₹50,000

### Evaluation — 7 Common Areas (all mandatory)
1. Successful Test Case (onboard govt feed + analytics)
2. Solution Presentation (clarity, model justification)
3. Solution Architecture (soundness, feasibility, security, interop, HLD quality)
4. Working Platform + Demo (maturity on own + govt feed)
5. Video Analytics Output (ANPR/person/vehicle/intrusion/object quality, timestamps, reports)
6. Scalability + PoC Readiness (credible ~80k path)
7. Submission Completeness (all docs/videos/links/creds accessible + consistent)

**Bonus (only if mandatory met):** innovative hybrid/custom; advanced cross-camera tracking/correlation; extra reliable analytics beyond ANPR; edge + bandwidth optimisation / low-connectivity; cybersecurity/privacy/audit/RBAC; ops dashboards / auto alerts / health monitoring / integration-ready APIs.

---

## 10. How to Register (step-by-step)
1. Go to `sentinel.gujarat.gov.in/register` → Fill Name, Email, Mobile (+91), Role (Student/DPIIT/Company), Password (8+ chars, upper+lower+number+special)
2. Verify via Email OTP → Login
3. Open `Problems` (read Step 1–7 journey) + `Resources` (copy RTSP/HLS/WHEP + catalogue URL)
4. Build: registry/GIS + ingest + ANPR + watchlist + alerts + dashboard
5. Record 2 videos (own feed 2–3 min + govt feed + report), write PPT + HLD, push optional GitHub
6. Upload before **28 Sept 2026** via portal (YouTube unlisted / Drive with Anyone-viewer / hosted URL+creds / repo)
7. Shortlist → Finale at i-Hub 12–13 Oct (live vehicle-tracking task) → Results 13 Oct

---

## 11. Strategy — What to Build to Actually Win

### If you're a STUDENT team (Category 1)
Pick **Model 1 + Model 2 + light edge ANPR**. Judges don't expect Kubernetes at 80k from students — they expect:
- Clean registry + Leaflet GIS with gap analysis (easy marks, mandatory)
- Unified WebRTC/HLS grid that actually opens 10–20 feeds without crashing (backoff + PTS-correct tracking impresses jury)
- Solid open-source ANPR (e.g., YOLOv8-vehicle + EasyOCR / PaddleOCR fine-tuned on Indian plates) with timestamped evidence table
- Your own watchlist DB (Postgres: stolen/wanted/missing tables) + alert feed + GIS route replay
- Honest scale slide: edge → regional → central, bandwidth math (e.g., 2 Mbps × 80k = impossible centrally → edge metadata-only), costed tiers
- Avoid: promising full Central VMS — you can't demo credibly.

### If you're a STARTUP / COMPANY (Category 1-DPIIT or 2)
Aim **Model 1 + Model 3 (federation) + selective central analytics**, or full Model 4-lite:
- Adapter framework (ONVIF + Milestone/Genetec/Hikvision/Dahua SDK shims) — this is what police actually need
- Kafka event bus + Elasticsearch vehicle-movement search + video-wall + RBAC/audit
- GPU sizing + Ceph/S3 tiering + DR story with numbers
- Cybersecurity: TLS, encryption at rest, network segmentation, audit logs, privacy masking — bonus magnet
- PoC-readiness: "we can deploy edge boxes next week" beats 10 extra analytic types

### Tech stack that maps 1:1 to official hints
Frontend React + Leaflet; Backend FastAPI/Node microservices; DB PostgreSQL+PostGIS (+TimescaleDB for events, Redis cache, Elasticsearch search); Streaming FFmpeg/GStreamer + WebRTC/HLS relay; AI YOLOv8/v9 + DeepSORT/ByteTrack + ANPR OCR + optional FaceNet/ArcFace; Bus Kafka/RabbitMQ; Gateway Kong/NGINX; Orchestration Docker/K8s; Storage S3/Ceph.

### Biggest differentiators (from bonus list)
Cross-camera ReID + route reconstruction on GIS; working alert prioritisation; camera health dashboard; low-bandwidth mode (metadata-only when link weak); audit + privacy blur; integration-ready REST APIs for VAHAN/eGujCop (mock now, contract-ready).

---

## 12. Press Context & Caveats
- Mid-Aug 2026 press (Indian Express, HT, NIE, ET, Open Mag) called it "India's largest CCTV+AI hackathon", 700+ participants, ₹37L pool, 10–11 Sept at iHub. **All superseded by current site (₹51L, 12–13 Oct).** Cite site, not press, in your PPT.
- Core narrative consistent everywhere: 80k cameras, 26 depts, live-feed test, ANPR/tracking/watchlist/GIS, reuse existing infra, no rip-and-replace.
- Open Magazine flags privacy gap (retention, access control, oversight, false-match redressal) — addressing this head-on in your HLD (RBAC, audit, masking, retention policy) earns jury trust.
- DGP G.S. Malik guidance; i-Hub tech support cited in every article.

---

## 13. Your Action Checklist (next 8 days to deadline)
- [ ] Register + verify OTP today; pull `/api/ingest` catalogue
- [ ] Get 3–5 RTSP feeds rendering in OpenCV/VLC over TCP; log PTS vs arrival
- [ ] Scaffold: registry (Postgres+PostGIS+Leaflet) + viewer (HLS grid) + ANPR worker + watchlist tables + alert UI
- [ ] Record own-feed demo early (2 min: onboard → detect plate → watchlist hit → alert + GIS)
- [ ] Run govt feeds overnight; collect plate/timestamp evidence CSV for report
- [ ] Write HLD with scale math + cost + DR + security; PPT with model justification
- [ ] Upload unlisted YouTube + Drive mirror + (optional) hosted URL + GitHub; test links in incognito
- [ ] Keep phone/email helpdesk handy; watch portal announcements (deadline already moved once)

---
*Compiled from: `/`, `/about`, `/problems`, `/phases`, `/resource`, `/schedule`, `/faqs`, `/register`, `/contact` + web press (Aug 2026). Verify dates/prizes on portal before submitting — govt portals update without notice.*
