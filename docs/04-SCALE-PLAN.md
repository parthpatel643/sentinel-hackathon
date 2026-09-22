# 04 — Scale Plan to ~80,000 Cameras
### Sentinel · Bandwidth, compute, storage, resilience and cost

> The organisers ask for a credible path to ~80,000 cameras. This document gives the arithmetic, states every assumption, and shows why full centralisation is rejected on evidence rather than on preference. **Every formula is written out so the jury can re-derive the numbers with their own inputs.**

---

## 1. Baseline assumptions

| Parameter | Value used | Basis |
|---|---|---|
| Total cameras (target) | 80,000 | Stated by the organisers |
| Departments | 26 | Stated |
| Districts | 34 | Gujarat administrative divisions |
| Typical stream | 1080p, 15 fps, H.264 CBR **2 Mbps** (H.265 ≈ 1 Mbps) | Standard government CCTV profile |
| Existing retention | 7–15 days, department-local | Stated in the problem background |
| ANPR event record | ~1 KB JSON (compressed ~300 B at rest) | Schema in [01-ARCHITECTURE §5.3](./01-ARCHITECTURE.md) |
| Evidence snapshot | ~30 KB JPEG (plate crop + context) | Measured on the test grid |
| Alert clip | 30 s pre/post-roll, H.265 ≈ **6 MB** | 1.6 Mbps × 30 s |

### 1.1 Camera tiering — the key modelling decision

Not every camera needs continuous AI. A PDS godown camera and a highway check-post camera have nothing in common operationally. Tiering is what makes 80,000 tractable.

| Tier | Share | Count | Analytic rate | Typical deployment |
|---|---|---|---|---|
| **A — Continuous ANPR** | 12% | 9,600 | 10 fps | Traffic junctions, check-posts, highways, entry/exit points |
| **B — Sampled** | 28% | 22,400 | 2 fps | General public-domain, markets, civic areas |
| **C — Motion-gated** | 35% | 28,000 | ~0.3 fps effective | Godowns, PDS shops, offices, low-traffic premises |
| **D — View + registry only** | 25% | 20,000 | 0 | Indoor/administrative, private consented feeds, view-on-demand |

Tiering is an operational policy set per camera in the registry by the owning department, not a hard-coded constant — and it can be changed live (a camera can be promoted to tier A during a VIP movement or a bandobast).

---

## 2. Bandwidth

### 2.1 What full centralisation would cost (the rejected option)

```
Aggregate ingest = 80,000 cameras × 2 Mbps = 160,000 Mbps = 160 Gbps sustained
                 = 80 Gbps if every camera were re-encoded to H.265 (they are not; mixed fleet)
```

160 Gbps sustained, 24×7, arriving from sites up to 1,000 km apart, over links that in many talukas are a few Mbps. This is not a budget problem; it is a physics problem. **Rejected.**

### 2.2 What Sentinel actually sends

Event rate, using the tiering above and conservative traffic assumptions:

```
Tier A:  9,600 cameras × 150 events/hour = 1,440,000 /hr
Tier B: 22,400 cameras ×  20 events/hour =   448,000 /hr
Tier C: 28,000 cameras ×   5 events/hour =   140,000 /hr
                                    Total = 2,028,000 events/hour
                                          =       563 events/second

Payload = 563 ev/s × (1 KB metadata + 30 KB snapshot)
        = 563 × 31 KB ≈ 17.5 MB/s ≈ 140 Mbps  (peak, statewide, with imagery)
Metadata only (degraded mode) = 563 × 1 KB ≈ 0.56 MB/s ≈ 4.5 Mbps
```

| Design | Sustained WAN load | Ratio |
|---|---|---|
| Central video ingest (Model 4 full) | **160 Gbps** | 1× |
| Sentinel, events + snapshots | **~140 Mbps** | **~1,140× less** |
| Sentinel, metadata-only degraded mode | **~4.5 Mbps** | ~36,000× less |

### 2.3 The real WAN consumer is live viewing, not analytics

Analytics is cheap; operators watching video is not.

```
100 concurrent operators × 16 tiles × 2 Mbps = 3.2 Gbps
```

Mitigations, all implemented at the edge relay:
- **Adaptive viewing profile** — remote viewers get a 720p / 500 kbps transcode, not the source stream → 3.2 Gbps becomes **800 Mbps**.
- **Only visible tiles stream** (scrolled-off tiles pause) → typically halves it again.
- **Snapshot-first UI** — the map and alert rail use still images; video starts only on explicit intent.
- **Local viewing stays local** — a district operator watching district cameras never traverses the state backbone.

### 2.4 Low-bandwidth and disconnected operation

| Link quality | Behaviour |
|---|---|
| Good (≥ 10 Mbps) | Full: events + snapshots + on-demand clips + live view |
| Constrained (1–10 Mbps) | Snapshots downscaled to 8 KB; clips deferred to an off-peak window; live view 360p on request only |
| Poor (< 1 Mbps) | **Metadata-only mode** — 1 KB events; snapshots retained locally with a pointer; retrieved only when an alert fires |
| Offline | **Edge autonomy**: analytics continues locally against a cached watchlist; events queue in a durable store-and-forward buffer (72 h default) and drain on reconnect, alerts prioritised ahead of routine events |

Edge autonomy is a deliberate design claim: **a district node with a severed WAN link still reads plates, still matches the cached watchlist, still records evidence, and still alerts locally.** Nothing about the architecture makes policing depend on the backbone being up.

---

## 3. Compute and GPU sizing

### 3.1 Per-frame cost model

Measured/estimated on an NVIDIA L4 (TensorRT, FP16, batched), for the full ANPR chain:

```
vehicle detection (640², YOLO-class)      ≈ 2.5 ms/frame
plate detection on vehicle crops (×1.5)   ≈ 1.2 ms/frame
rectification + OCR on plate crops        ≈ 1.0 ms/frame
tracking + post-processing (CPU)          ≈ negligible on GPU
                                    Total ≈ 4.7 ms GPU per analysed frame
⇒ sustained capacity ≈ 300 analysed frames/second per L4 (at ~70% utilisation headroom)
```

### 3.2 GPUs required

```
Tier A:  9,600 cams × 10 fps   =  96,000 fps ÷ 300 = 320 L4
Tier B: 22,400 cams ×  2 fps   =  44,800 fps ÷ 300 = 149 L4
Tier C: 28,000 cams × 0.3 fps  =   8,400 fps ÷ 300 =  28 L4
                                              Total ≈ 497 L4  (≈ 560 with N+1 redundancy)
```

≈ **140 servers with 4× L4 each**, distributed across 34 districts weighted by camera density (Ahmedabad and Surat carry a disproportionate share; several districts need a single 2-GPU node).

**Decode is the co-constraint, and it is usually the one people forget.** Each L4 has NVDEC engines good for roughly 40–50 concurrent 1080p30 decodes. Because we decode at the analytic rate rather than full rate — and because motion gating means tier C cameras are usually not decoded at all — decode fits inside the same node budget. Where it does not, decode-only CPU nodes with Quick Sync are added; this is called out as a sizing input rather than assumed away.

### 3.3 Edge box option for remote sites

For sites where backhaul cannot carry even the viewing profile, an on-site **Jetson Orin NX 16 GB** handles 8–12 cameras at tier B. Recommended for ~1,500 remote locations rather than statewide, because district-level GPU servers are roughly 3× cheaper per camera. The architecture supports both because the edge agent is the same code on both.

### 3.4 Core plane sizing

563 events/s is a modest stream — the core is dominated by storage and query, not throughput.

| Component | Sizing |
|---|---|
| Kafka | 3 brokers, 8 vCPU / 32 GB / NVMe, ~2 MB/s ingress, 7-day retention |
| Correlator / alerting | 6–10 pods, horizontally scaled on consumer-group lag |
| PostgreSQL + PostGIS + TimescaleDB | Primary 32 vCPU / 256 GB / NVMe + 2 replicas, Patroni HA, PgBouncer; detections hypertable partitioned daily with continuous aggregates |
| OpenSearch (at this scale, now justified) | 6 data nodes for detection search; Postgres remains system of record |
| Core API | 8–20 pods behind an ingress, HPA on RPS |
| Object storage | Ceph or S3, erasure-coded, cross-site replication |

---

## 4. Storage

### 4.1 What full centralisation would cost (the rejected option)

```
Per camera per day = 2 Mbps ÷ 8 = 0.25 MB/s × 86,400 s = 21.6 GB/day
Statewide          = 80,000 × 21.6 GB = 1.73 PB/day
7-day hot tier     = 12.1 PB      15-day = 25.9 PB      30-day = 51.8 PB
```

12.1 PB of hot, always-writable storage for a one-week window — before redundancy, before DR. At cloud object pricing this is of the order of **₹20+ crore per month**; on-premises it is a multi-hundred-crore build with its own data-centre footprint. **Rejected, and explicitly so in the presentation.**

### 4.2 What Sentinel stores

| Data class | Volume | Retention | Tier |
|---|---|---|---|
| Detection events (metadata) | 48.7 M/day × ~300 B ≈ **14.6 GB/day** | 1 year online, then archive | Hot NVMe → warm |
| Evidence snapshots | 48.7 M/day × 30 KB ≈ **1.46 TB/day** | 7 days all; tier-A and watchlist-related kept 90 days | Hot 7 d → warm → purge |
| Alert clips (event-driven) | ~24,000/day × 6 MB ≈ **146 GB/day** | 90 days; case-linked clips 1 year+ | Warm → cold |
| Continuous recording, **critical cameras only** (2,000) | 2,000 × 10.8 GB (H.265) ≈ **21.6 TB/day** | 15 days | Warm (erasure-coded) |
| Audit log | < 1 GB/day | 5 years (statutory) | Warm, immutable, hash-chained |

```
Steady-state footprint
  events (1 yr)                    ≈   5.3 TB
  snapshots (7 d hot + 90 d tier-A) ≈  10.2 TB + ~40 TB
  alert clips (90 d)                ≈  13.1 TB
  critical continuous (15 d)        ≈ 324.0 TB
                            Total  ≈ 390 TB usable  (≈ 600 TB raw with EC + DR)
```

**390 TB versus 12.1 PB — a ~31× reduction — while preserving record, playback, scrub, export and chain-of-custody for everything that actually matters forensically.** Historical routine footage remains in each department's existing 7–15 day retention and is retrievable on demand through the federation layer, which is precisely the "reuse existing infrastructure" mandate.

### 4.3 Lifecycle

`Hot (NVMe, 0–7 d)` → `Warm (HDD/EC, 7–90 d)` → `Cold (object/archive, 90 d–1 yr+)` → `Purge`, driven by a policy engine with per-data-class rules, legal-hold override for case-linked evidence, and a visible retention countdown in the admin UI.

---

## 5. High availability, DR and failure domains

| Domain | Failure | Behaviour |
|---|---|---|
| Camera | Offline/tampered | Health alert within 30 s; registry marks degraded; gap-analysis map updates |
| Edge node | Crash | Local supervisor restart; peer node in the district picks up cameras via lease; buffered events replay |
| WAN link | Severed | Edge autonomy for 72 h; prioritised drain on reconnect |
| Core service | Pod failure | K8s reschedules; consumers resume from committed offsets |
| Database | Primary loss | Patroni automatic failover to a synchronous replica |
| Data centre | Site loss | Warm standby DC with streaming replication + object replication |

**Targets: RPO ≤ 15 min for central state (0 for edge-buffered events, which are durably queued locally), RTO ≤ 1 h for full service, RTO ≤ 5 min for alerting.** Quarterly DR drills with documented runbooks; automated backups with restore verification, because an unverified backup is a rumour.

---

## 6. Indicative cost (₹)

Order-of-magnitude, for comparison of architectures rather than for tendering.

| Line | Capex |
|---|---|
| District GPU analytics servers (140 × ~₹20 L, 4× L4) | ₹28 cr |
| Remote edge boxes (1,500 × ~₹70 k) | ₹10.5 cr |
| Core DC: compute, 600 TB storage, network, HA | ₹14 cr |
| DR site (warm standby) | ₹7 cr |
| District uplink upgrades (assumes GSWAN reuse) | ₹9 cr |
| Software licences | **₹0 — fully open-source stack** |
| Integration, migration, training, rollout services | ₹12 cr |
| **Total capex** | **≈ ₹80 cr** |

| Line | Opex / year |
|---|---|
| Power, cooling, DC space | ₹5 cr |
| Network/bandwidth | ₹7 cr |
| AMC + support (≈12% of hardware capex) | ₹8 cr |
| Operations team (NOC, L1–L3) | ₹4 cr |
| **Total opex** | **≈ ₹24 cr/yr** |

**For contrast**, a full central-VMS build (Model 4 at 80,000 cameras) requires ~160 Gbps of backbone and 12 PB of hot storage for a single week of retention — conservatively **₹400 cr+ capex** with a materially higher opex, for capabilities that this design already provides where they matter. The open-source stack also removes per-camera VMS licensing, which at 80,000 cameras is typically a larger line item than the hardware.

---

## 7. Phased rollout

| Phase | Duration | Scope | Exit criteria |
|---|---|---|---|
| **0 — Pilot** | 0–3 months | 1 district, ~500 cameras, 2 departments | ANPR accuracy validated on live feeds; alert latency < 5 s; operator acceptance |
| **1 — Multi-department** | 3–9 months | 4 districts, ~5,000 cameras, 6 departments, adapters for the top 3 VMS vendors | Federation proven across vendors; VAHAN/eGujCop integration live; DR drill passed |
| **2 — Statewide core** | 9–21 months | All 34 districts, ~30,000 cameras, 15 departments | Statewide vehicle tracking operational; SOC/NOC established; training delivered |
| **3 — Full scale + private** | 21–36 months | 80,000 cameras + consented private camera onboarding programme | Full coverage; policy framework and audit regime institutionalised |

Each phase is independently useful. The system delivers operational value at 500 cameras and never requires a big-bang cutover — which is the only kind of government rollout that actually finishes.

---

## 8. Prerequisites and information required from departments

The problem statement explicitly asks what is needed for feasibility. This is the data-collection template Sentinel requires per department — and it is itself a deliverable, because **no such consolidated inventory currently exists, and building it is Model 1's real value.**

| Field | Why it is needed |
|---|---|
| Camera count, make, model, firmware | Adapter selection, ONVIF profile support |
| Analog vs IP; encoder model where analog | Determines whether a site needs an encoder or an edge box |
| VMS/NVR vendor, version, API availability | Federation adapter selection (Model 3) |
| Codec, resolution, frame rate, bitrate per site | Decode sizing, ragged batching configuration |
| Current retention period and storage location | What we do *not* need to re-store centrally |
| Network: link type, bandwidth, static IP/NAT/firewall posture | Tier assignment, relay placement, VPN/mTLS design |
| Geo-coordinates, mounting height, viewing direction, FOV | GIS registry and genuine coverage gap analysis |
| AMC vendor and contract end date | Rollout sequencing; avoids touching cameras under a live AMC |
| Nodal officer, escalation contact | Onboarding and incident routing |
| Data-sensitivity classification, access policy | RBAC scoping, retention and masking defaults |

**Assumptions stated openly** (each with a mitigation, because a jury trusts stated assumptions far more than confident silence): GSWAN or equivalent connectivity is available to district headquarters; departments will permit read-only access to existing streams; a state data centre and DR site are available; VAHAN/SARTHI/eGujCop/AFIS integration will be granted through documented APIs; private camera onboarding will be governed by a consent and policy framework issued by the Home Department.

---

## 9. Capacity planning formulas (so the numbers can be re-derived)

```
WAN_analytics (Mbps)   = Σ_tiers (cameras × events_per_hour) ÷ 3600 × payload_KB × 8 ÷ 1000
GPUs_required          = Σ_tiers (cameras × analytic_fps) ÷ per_GPU_fps_capacity × (1 + redundancy)
Storage_hot (TB/day)   = events_per_day × (metadata_B + snapshot_B) ÷ 10¹²
                         + critical_cameras × bitrate_Mbps × 10,800 ÷ 10⁶
Viewing_WAN (Mbps)     = concurrent_operators × tiles × profile_Mbps × visible_fraction
Central_video (Gbps)   = cameras × bitrate_Mbps ÷ 1000        ← the number we refuse to pay
```

Change one input — camera mix, event rate, retention — and the whole model re-derives. That transparency is the point: it is a sizing model the department can own, not a vendor's assertion.

---

*Next: [05-DELIVERY-PLAN](./05-DELIVERY-PLAN.md) — the build sequence.*
