# 12 · Requirements traceability
### Every requirement on sentinel.gujarat.gov.in, where it is met, and the evidence

Checked against the official problem statement, solution framework, evaluation
framework and FAQ on the hackathon site. **Status** is one of *Met*, *Partial*
(stated limit in the row) or *Not built*. Evidence links point at code, a test or
a measured run, never only at a design document.

---

## 1. Common evaluation areas

| # | Area | Status | Where | Evidence |
|---|---|---|---|---|
| 01 | Successful test case: onboard the government feed, view it, produce analytics output | **Met** | Registry import / catalogue onboarding, relay viewing, registry-driven worker | [M4 gov-grid integration](../evidence/M4-GOV-CAMERA-GRID-INTEGRATION.md), [M14 evidence run](../evidence/M14-EVIDENCE-RUN.md), runbook [§5](./10-FINALE-RUNBOOK.md) |
| 01 | Track the designated vehicle across cameras and times | **Met** | Find a Vehicle → route, movement report (PDF/CSV/ZIP with hashes) | [Cross-camera findings](../evidence/CROSS-CAMERA-TRACKING-FINDINGS.md), runbook [§7](./10-FINALE-RUNBOOK.md) |
| 02 | Solution presentation | **Met** | `make deck` → `docs/Sentinel-Platform-Deck.pptx` | [Submission playbook](./06-SUBMISSION-PLAYBOOK.md) |
| 03 | Solution architecture (HLD, diagrams, security, interoperability) | **Met** | `docs/Sentinel-Platform-HLD.pdf`, [01-ARCHITECTURE](./01-ARCHITECTURE.md), [08-SECURITY](./08-SECURITY-HARDENING.md) | Workflow diagram PDF in `docs/` |
| 04 | Working platform on own feed and government feed | **Met** | Operator console, field PWA, edge worker | [M15 fresh-clone test](../evidence/M15-FRESH-CLONE-TEST.md), [chaos drills](../evidence/M15-CHAOS-DRILLS.md) |
| 05 | ANPR | **Met, accuracy stated** | Detect → track → plate → OCR → grammar correction → vote | [ANPR accuracy](../evidence/ANPR-ACCURACY.md): 65% exact per crop, 78% after voting |
| 05 | Vehicle detection and classification | **Met** | YOLO11n, car / motorcycle / bus / truck, colour | `edge_agent/analytics/vehicle_detector.py` |
| 05 | Person detection | **Met** | Same inference as vehicles; people counted per camera and held to intrusion/loitering zones; never identified | [09-SECONDARY-ANALYTICS §3a](./09-SECONDARY-ANALYTICS.md) |
| 05 | Intrusion detection | **Met** | Zone rules: intrusion, loitering, wrong-way, stopped vehicle; triaged as alerts | `edge_agent/analytics/zone_rules.py`, Zone event queue |
| 05 | Timestamps | **Met** | Camera's burned-in clock preferred, PTS otherwise; IST everywhere in the UI and reports | `frame_clock.py`, `apps/web/src/lib/time.ts` |
| 05 | Output reports | **Met** | Movement report PDF with route sketch and evidence frames; CSV; evidence ZIP with SHA-256 manifest; `scripts/evidence_report.py` | `core_api/reports/service.py` |
| 06 | Scalability toward ~80,000 cameras | **Met (plan + measurement)** | Tiered analytics, federation, edge processing | [04-SCALE-PLAN](./04-SCALE-PLAN.md), [§4 below](#4-scale-measured-versus-projected) |
| 06 | PoC readiness | **Met** | Finale runbook, DR drill, `make doctor` / `make prefetch` | [10-FINALE-RUNBOOK](./10-FINALE-RUNBOOK.md), [DR drill](../evidence/DR-RESTORE-DRILL.md) |
| 07 | Submission completeness | **Met** | Checklist and packaging | [06-SUBMISSION-PLAYBOOK](./06-SUBMISSION-PLAYBOOK.md) |

## 2. Bonus considerations

| Bonus | Status | What is real |
|---|---|---|
| Innovative hybrid architecture | **Met** | Model 1 + 2 + 3 + selective 4 ([00-SOLUTION-PLAN §2](./00-SOLUTION-PLAN.md)) |
| Advanced cross-camera tracking / multi-camera correlation | **Met** | Matching ladder (exact, OCR-ambiguity, one-character, bridged unreadable hops), feasibility gate on implied speed |
| Additional reliable analytics beyond ANPR | **Met** | Colour, tamper, zone rules, people and vehicle counts, coverage-gap and lifecycle analysis |
| Edge processing, bandwidth optimisation, low connectivity | **Met** | Edge worker sends metadata only (plus snapshots of detections), tiered analysis, a durable outbox that replays detections after an outage |
| Cybersecurity, privacy, auditability, RBAC | **Met** | mTLS, RBAC/ABAC, Postgres RLS, hash-chained audit log (tamper detected, survives restore), face blur, admin-only registry writes, private-camera consent enforcement |
| Dashboards, automated alerts, health monitoring, APIs | **Met** | Server-sent-event alerts with sound, camera health (live / stale / degraded / down, analysed fps, lag), OpenAPI |

## 3. HLD content the FAQ requires

| Required in the HLD | Where |
|---|---|
| Overall architecture with diagrams | [01-ARCHITECTURE](./01-ARCHITECTURE.md), HLD PDF |
| Heterogeneous cameras / VMS (IP, analog via NVR, multi-vendor, mixed protocols) | [07-DRIVER-SDK](./07-DRIVER-SDK.md): RTSP, ONVIF, HLS, Hikvision ISAPI, Dahua CGI, Genetec and Milestone VMS |
| Geographically dispersed sites (bandwidth, connectivity, edge vs central) | [04-SCALE-PLAN §2](./04-SCALE-PLAN.md) |
| Video analytics approach (ANPR, cross-camera tracking) | [02-ANPR-PIPELINE](./02-ANPR-PIPELINE.md), [09-SECONDARY-ANALYTICS](./09-SECONDARY-ANALYTICS.md) |
| Scalability for ~80,000 cameras | [04-SCALE-PLAN](./04-SCALE-PLAN.md) |
| Technical details needed from departments | [04-SCALE-PLAN §8](./04-SCALE-PLAN.md), runbook [§1](./10-FINALE-RUNBOOK.md) |

## 4. Scale: measured versus projected

| Quantity | Measured (where) | Projected at 80,000 cameras |
|---|---|---|
| Analytics per laptop, dense traffic (a plated vehicle in every frame) | Base M2: about 16 analysed fps in total is the edge (2 cameras at 8 fps marginal, 4 at 4 fps keep up) ([tier capacity](../evidence/TIER-CAPACITY.md)) | Sized per GPU in [04 §3](./04-SCALE-PLAN.md); tiering means only 12% of cameras run continuous ANPR |
| Plate-read ceiling | ~30 reads/s on M2 CPU | GPU inference in production |
| Restore of 1 M detections | 5.7 s ([DR drill](../evidence/DR-RESTORE-DRILL.md)) | RTO via replica failover, not dump/restore |
| ANPR exact match | 65% per crop, 78% voted, one camera ([accuracy](../evidence/ANPR-ACCURACY.md)) | Fine-tuning on Indian plates first |
| 80,000 cameras deployed | Not deployed | Arithmetic in [04-SCALE-PLAN](./04-SCALE-PLAN.md) |

## 5. Government database integration readiness

The brief names five systems. Each has a provider behind one `ExternalRegistry`
port, with retry, circuit breaker, rate limit and a redacted audit record, and is
checked live from **Admin → Integrations**. No production credential exists, so
each runs against a contract-shaped mock; on the day access is granted it is a
configuration change.

| System | Owner | Provider | Operations | A rejected credential |
|---|---|---|---|---|
| VAHAN | MoRTH | `VahanProvider` | Vehicle registration lookup | Raises `RegistryAuthError` |
| SARTHI | MoRTH | `SarthiProvider` | Driving licence lookup | Raises |
| eGujCop (CCTNS) | Gujarat Police | `EGujCopProvider` | Person / case lookup, alert push | Raises |
| AFIS | Gujarat Police | `AfisProvider` | Biometric identity match | Raises |
| NAFIS | NCRB | `NafisProvider` | National biometric match, cross-state | Raises |

A credential failure never reads as "no record": an expired key must not make a
wanted vehicle look clean.

## 6. Known gaps, stated

| Requirement | Position |
|---|---|
| Face recognition (FRS) | **Excluded by decision.** Faces are detected only to be blurred. The system answers "where did this vehicle go", not "where did this person go" ([00-SOLUTION-PLAN §6](./00-SOLUTION-PLAN.md)). |
| Coarse make / model classification | Not built; needs a trained classifier. |
| Real Hikvision / Dahua hardware | Drivers are written to the vendors' published APIs and tested against mock servers that implement them, including digest auth; no physical device has been on the bench. ONVIF and plain RTSP reach the same devices. See [07-DRIVER-SDK](./07-DRIVER-SDK.md). |

## 7. Private cameras

The FAQ asks for viewing of public-facing private cameras (societies, malls,
shops) "wherever feasible and permitted". Permission is enforced, not assumed:

- A private camera is onboarded with `ownership=private`, the consent reference it
  was shared under (`consent_ref`) and when that consent ends (`consent_expires_on`).
- Without both, or after the date, the camera stays in the registry but is **not
  served to viewers and not analysed**: the worker manifest leaves it out and the
  stream endpoint refuses it with the reason.
- **Coverage & lifecycle** counts lapsed and expiring consents per department, so
  the owning station renews them before they lapse.
- Private cameras default to view-only (`d_registry_only`); analysing one is an
  explicit tier choice.
