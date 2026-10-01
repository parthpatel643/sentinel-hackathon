# 10 — Phase-2 Finale Runbook
### Sentinel · On-site procedure for 12–13 October 2026, i-Hub Gujarat, Ahmedabad

Phase 1 ran against the organisers' sandbox grid. Phase 2 is different in the
ways that matter on the day:

- **Real CCTV feeds at scale**, not the 30-camera sandbox catalogue. Expect
  plain RTSP URLs, ONVIF cameras, NVR channels or a new catalogue, on a
  network we have not seen ([phases](https://sentinel.gujarat.gov.in/phases)).
- **Judged live** by Gujarat Police leadership and a technical jury.
- **A designated vehicle registration number is given on the day.** We must
  trace it across cameras and show the timestamped, location-wise route on GIS,
  plus continuous watchlist cross-referencing with automatic real-time alerts
  ([problems, Step 4](https://sentinel.gujarat.gov.in/problems)).
- Evaluation area 6 now reads as "preparedness for the **on-site
  proof-of-concept**".

This runbook covers what [06 — Submission Playbook §7](./06-SUBMISSION-PLAYBOOK.md)
does not: preparing for a network and camera set we have not seen yet.

---

## 1. Ask the organisers now

Email `sentinel.hackathon@gujarat.gov.in` (helpdesk +91 95370 89982, Mon–Sat
10:00–18:00) well before 12 October. Every answer below changes a step in
§4–§5.

| Question | Why it matters |
|---|---|
| In what form will feeds arrive: RTSP URLs, ONVIF devices, NVR/VMS access, HLS, or a catalogue endpoint like the sandbox's? | Picks the onboarding path in §5. |
| Roughly how many cameras, and will each come with latitude/longitude and a department? | Cameras without coordinates cannot appear on the route map. |
| Will we get a camera list in advance (CSV/Excel)? | We can pre-build the import CSV and validate it the night before. |
| Codecs and resolutions (H.264/H.265, 1080p/4K)? | Sets `STRIDE` and how many cameras one laptop can analyse (§6). |
| Network: wired Ethernet or Wi-Fi? Is there internet? Which outbound ports reach the cameras (554, 8554, 80)? Any proxy or VPN? | Offline preparation (§3) and the first connectivity test (§4). |
| Can two of our laptops reach each other on that network? | Needed to shard analysis across machines (§6). |
| Are the feeds live, or recorded footage replayed? If replayed, are the cameras' burned-in clocks correct? | Route times come from the scene clock; replayed footage from different days will not line up across cameras (see [the cross-camera finding](../evidence/CROSS-CAMERA-TRACKING-FINDINGS.md)). |
| May detections and snapshots stay on our laptops after the event, or must they be deleted? | Retention and the post-event reset (§9). |
| Display: HDMI or USB-C to the projector? Power at the table? | Physical kit. |

---

## 2. Kit

- **Two laptops**, both fully installed and tested from a fresh clone
  ([fresh-clone test](../evidence/M15-FRESH-CLONE-TEST.md)). Either can run
  the whole stack; together they share the analysis load.
- Chargers, a power strip, HDMI and USB-C adapters, a USB-Ethernet adapter and
  cable.
- A phone hotspot as the fallback network.
- The recorded demo videos on local disk.
- A printed copy of this runbook and the CSV template in §5.

---

## 3. The day before (on a working internet connection)

```bash
git pull && make install
make up                                                     # pulls/starts the containers
(cd services/core_api && uv run --project ../.. alembic upgrade head)
make prefetch                                               # every model, for offline use
make doctor                                                 # every check green
```

**Set real secrets.** The development defaults are published in this
repository. Put fresh values in `.env` on the laptop running the API:

```bash
for name in JWT_SECRET EDGE_SERVICE_TOKEN MTLS_GATEWAY_SHARED_SECRET MEDIA_URL_SIGNING_SECRET; do
  echo "SENTINEL_${name}=$(openssl rand -hex 32)"
done >> .env
echo "SENTINEL_ENVIRONMENT=prod" >> .env    # the API now refuses to start with a default left
```

Copy the same `SENTINEL_EDGE_SERVICE_TOKEN` into the second laptop's `.env`.

**Create the operator logins with a strong password.** Do not demo on the
default seed credential:

```bash
uv run --package core_api python scripts/seed_admin_user.py \
  --email admin@<team-domain> --password '<strong password>' --role admin
```

**Rehearse offline.** Turn Wi-Fi off, start everything (§4), run the
designated-vehicle drill (§7) on the synthetic grid or a phone's RTSP camera
app. What must still work offline: capture, ANPR, alerts, search, reports,
live wall. What will not: basemap tiles, unless you point
`VITE_MAP_TILE_URL` in `apps/web/.env` at a local tile server. Without tiles the
map says so, and camera pins, routes and gap cells still draw correctly.

---

## 4. On arrival

1. Connect, then prove each camera is reachable from the laptop before
   touching the platform:

   ```bash
   ffprobe -v error -rtsp_transport tcp -show_entries stream=codec_name,width,height \
     'rtsp://user:p%40ss@10.20.1.15:554/Streaming/Channels/101'
   ```

   A 401 means wrong credentials or an unencoded special character in the
   password (§5). A timeout means the network blocks that port — ask the
   organisers before anything else.
2. Start the stack, one terminal each:

   ```bash
   make up
   make api          # add --host 0.0.0.0 via uvicorn only if a second laptop must reach it (§6)
   make web
   ```
3. `make doctor` — all green except "edge worker", which §5 starts.

---

## 5. Onboarding the real cameras

All paths write to the same registry, and the worker analyses whatever the
registry holds.

**A. A camera list (most likely).** Build a CSV and import it from
**Cameras → Import cameras**: the wizard validates every row as a dry run
first, and one bad row never blocks the rest.

```csv
camera_id,name,department_name,site_name,lat,lon,protocol,url,codec,installed_on,amc_expires_on,maintenance_status,vendor
pol-cg-01,CG Road junction,Police,CG Road,23.0300,72.5600,rtsp,rtsp://viewer:p%40ss@10.20.1.15:554/Streaming/Channels/101,h265,2019-06-01,2027-03-31,ok,Hikvision
```

- Only `camera_id` and `name` are required; without `lat`/`lon` a camera
  still records sightings but cannot be drawn on the route map.
- Percent-encode `@ : / # ?` inside usernames and passwords (`@` → `%40`).
- A typo is fixed by importing the corrected row again: the camera is updated
  in place and the worker restarts it with the new URL on its next resync.
- The lifecycle columns are optional; they feed **Cameras → Coverage &
  lifecycle**.
- A private camera needs `ownership=private`, `consent_ref` and
  `consent_expires_on`; without current consent it is registered but never
  viewed or analysed.

**B. ONVIF cameras and NVRs.** **Cameras → Discover cameras → Discover a
device**: choose ONVIF / Hikvision NVR / Dahua NVR, enter the address and
account, **Find streams**, check the list, **Add**. Admin role required.
ONVIF is a real protocol implementation; the Hikvision and Dahua drivers
follow each vendor's documented API shape but have not been tested against
physical units, so prefer plain RTSP or ONVIF on a device you have not used
before. URL templates, NVR channel numbering and the two ONVIF traps (a separate
ONVIF user on Hikvision, and device clock skew) are on the field card in
[07 — Driver SDK §6a](./07-DRIVER-SDK.md).

**C. A catalogue endpoint like the sandbox.** Set `SENTINEL_GOV_CATALOGUE_URL`
(and the RTSP/HLS host overrides in `.env.example`) and use **Discover cameras
→ Sync now**.

**Start analysis:**

```bash
make worker SOURCE=registry            # SAMPLED_FPS=8 by default; see §6
```

New cameras are picked up within 30 seconds, with no restart. Each camera's
`tier` (CSV column) decides how much of it is analysed (§6); `d_registry_only`
keeps it on the map and live wall but out of ANPR.

**Before any demo:** open one camera on the **Live Wall**, and check the
**Health** screen shows it live with a measured frame rate.

---

## 6. Capacity: be deliberate about which cameras run ANPR

Measured end to end on the base M2 ([tier capacity](../evidence/TIER-CAPACITY.md)),
on a dense scene with a plate to read in nearly every frame: **about 16 analysed
frames per second in total**, so 2 cameras at 8 fps or 4 cameras at 4 fps. The
plate detector is the limit. Measure the M4 the same way during UAT
([11-M4-UAT](./11-M4-UAT.md)) and use its figure, not this one.

Every camera's **tier** in the registry decides what it costs:

| Tier | Analyses | Use it for |
|---|---|---|
| `a_continuous` | Every frame, or every `STRIDE`-th | The few junctions the vehicle must pass. On the M2 use `STRIDE=3` (about 8 fps) |
| `b_sampled` | `SAMPLED_FPS` frames a second (default 8), paced by the stream's own timestamps | Most roads |
| `c_motion_gated` | `SAMPLED_FPS`, only while something moves | Quiet gates and depots |
| `d_registry_only` | Nothing: view-only | Everything beyond capacity |

- **Every camera** goes into the registry, onto the map and the live wall
  (preview is on demand and costs nothing until opened).
- **Watch the Cameras screen.** Each analysed camera shows `ANPR n fps`, and
  `n s behind live` in red once analysis trails live by 5 s or more. A number
  that keeps growing means the laptop is over capacity: lower `SAMPLED_FPS`, raise `STRIDE`, or move a camera down a tier.
  The worker re-reads the registry every 30 s, so a tier change applies without
  a restart. A camera whose analysis stops shows **stale**.
- **Shard across both laptops by department:**

  | Laptop A (runs the API) | Laptop B (worker only) |
  |---|---|
  | `make up && make api && make web` | `docker compose -f infra/compose/docker-compose.yml up -d mediamtx` |
  | API reachable from B: `uv run --package core_api uvicorn core_api.app:app --host 0.0.0.0 --port 18000` | `SENTINEL_CORE_API_URL=http://<A's IP>:18000` and the same `SENTINEL_EDGE_SERVICE_TOKEN` in `.env` |
  | `make worker SOURCE=registry DEPARTMENT=Police SAMPLED_FPS=8` | `make worker SOURCE=registry DEPARTMENT=GSRTC SAMPLED_FPS=8` |

  Laptop B uploads each detection's snapshots to A, so evidence images work for
  every camera. If the link between the laptops drops, B keeps analysing and
  queues its detections on disk (`data/edge-outbox.sqlite3`); they are replayed
  as soon as A answers again, and the log says how many.
- Alerts reach every open console within a second (server-sent events), with a
  sound. If the banner does not appear, reload the page: the stream reconnects.

---

## 7. The designated-vehicle drill

Rehearse this until it takes under two minutes.

1. **Before the number is given:** arm a few representative watchlist entries
   (stolen, wanted, missing) so continuous cross-referencing is visibly
   running — an alert banner appears on whatever screen is open when any of
   them is read.
2. Type the plate into the top search box. Spacing, hyphens and case do not
   matter (`gj 01-ab 1234` = `GJ01AB1234`).
3. If the vehicle may have passed before today, set **Search window** to 48
   hours or 7 days. Say so out loud.
4. Walk the route: numbered hops on the map, the timeline beside it, then
   **Replay route**.
5. Open a hop: camera, department, IST time, confidence, the plate as read,
   the snapshot (faces blurred by default).
6. **Probable** hops (dashed, amber) are reads one character away or in an
   OCR-ambiguity class. Show the plate actually read and confirm it against the
   snapshot in front of the jury rather than letting them find it.
7. **Watch for this vehicle** arms a forward BOLO and re-checks every past
   detection immediately — the alert banner proves correlation is live.
8. **Export report**: the Movement Report ZIP (PDF and CSV in IST with UTC
   alongside, plus a hash manifest). Hand it over. Every one of these actions
   is in **Admin → Audit log**; **Verify chain** proves nothing was altered.

If there are no sightings: check **Health** that the cameras on the vehicle's
likely path are live and analysed, widen the window, and search the raw read
list (**Overview** recent reads) for a near-miss plate.

---

## 8. What to show for each evaluation area in the time left

| Area | Show |
|---|---|
| Model 1 registry & GIS | Cameras map with the department filter and **Show coverage gaps**; **Coverage & lifecycle** with its CSV work list; bulk CSV and device discovery; the Registry API at `/api/docs` |
| Model 2 viewing & analytics | Live wall layouts; ANPR reads on the overview; camera-wise search |
| Alerts | The banner on a live hit, the Alerts queue, acknowledging one (audited) |
| Security & privacy | Stream credentials shown as `***` everywhere; blurred snapshots and reveal-with-reason; RLS department scoping; audit-chain verification |
| Operations | Health screen, integrator compliance panel, `make doctor` |
| Scale | [04 — Scale Plan](./04-SCALE-PLAN.md): measured on this hardware vs. projected to 80,000 |

---

## 9. When something breaks

| Symptom | Likely cause | Fix |
|---|---|---|
| Camera never goes live | Credentials, unencoded `@` in the password, blocked port | `ffprobe` it (§4); re-import the corrected CSV row |
| Camera shows *live* but no reads | Nothing on that camera is running ANPR, or it is `d_registry_only` | Check the worker log for the camera id; `make doctor` |
| Status stays *live* after a worker stopped | Status is the last heartbeat, not a timeout | Check **Last seen** in the camera's details; restart the worker |
| Map is grey | No internet for tiles | Expected offline; pins and routes are correct. Or set `VITE_MAP_TILE_URL` |
| Preview tiles stall, CPU pinned | Too many analysed cameras | Raise `STRIDE`, move a department to laptop B (§6) |
| API refuses to start: "still hold the development defaults" | `SENTINEL_ENVIRONMENT=prod` with a default secret | Set the named variables (§3) |
| No new alert for a repeat sighting | Same plate, same camera within 5 minutes updates the existing alert | Expected; the sighting count goes up |
| Worker exits: "could not read the camera registry" | API down, or the service tokens differ | Start the API; match `SENTINEL_EDGE_SERVICE_TOKEN` on both sides |
| Venue network fails completely | — | Switch both laptops to the hotspot, or run the drill on the synthetic grid and the recorded videos, narrating what changed |

Narrate every recovery. A reconnect handled calmly on camera is stronger
evidence than a flawless run.

---

## 10. After the event

Delete what the organisers asked us not to keep (§1). This also wipes every
earlier run's snapshots and database, so archive anything worth keeping first:

```bash
make down
make clean      # drops the database, relay and object-store volumes
rm -rf data/snapshots data/snapshot_originals data/field_reports
```

---

*Back to [06 — Submission Playbook](./06-SUBMISSION-PLAYBOOK.md) ·
[00 — Solution Plan](./00-SOLUTION-PLAN.md).*
