# 15 — Demo Book: the live government feed, on one laptop
### Sentinel · Grand finale, i-Hub Gujarat · 13 October 2026 · print this

Everything for today in one place: this morning's rehearsal, what to run on
arrival, the twenty minutes with the jury click by click, which plate to
trace, and what to do when something breaks. The reasoning behind it is in
[13 — Showcase Prep](./13-SHOWCASE-PREP.md) and
[10 — Finale Runbook](./10-FINALE-RUNBOOK.md); this book is what you hold.

| | |
|---|---|
| **Laptop** | **The M2** (this MacBook) — the deck, the console and the live government grid, `make demo` |
| **Fallback** | The same laptop, switched to its recorded copy of the grid — offline, no quota, today's reads kept (§8) |
| **Phone** | Field app on Vercel (optional, `PHONE=1`) |
| **Deck** | `docs/Sentinel-Finale-Pitch.pptx`, 15 slides + appendix A1–A10 |
| **Narrator** | Parth — faces the jury, never touches the keyboard |
| **Driver** | Anuj — keyboard and mouse; watches `make demo-status` between beats |

Checked: the government catalogue answers with our credentials and lists all
30 cameras (12 Oct, 22:50), and on 13 Oct at 06:45 cam06 played live from the
grid on this laptop, analysed, with no quota errors.

---

## 1. The plate and the camera

**Camera: cam06 — Timbavadi Gate, Junagadh.** The only camera on the grid
whose plates are large and front-on enough to read reliably, in daylight,
with a date-time overlay we read on most frames. Every other camera is a
wide-angle or night view; plates there are 20–30 pixels tall.

**Plate: `GJ11S7924`** — a white Maruti Omni van, centre lane, at
**18:01:21 on cam06's clock** (17 Jun 2026). It is read exactly at 100%,
its time is read off the frame, and it is the same van as slides 01, 06 and
09: what the jury saw in the deck is what they see live.

| Plate | Camera | cam06 clock | Use it for |
|---|---|---|---|
| **`GJ11S7924`** | cam06 | 18:01:21 | **The trace.** Then *Watch for this vehicle* for the live alert. |
| `GJ03MH7800` | cam06 | 18:02:49 | Pre-armed as *wanted*: already in the Alerts queue. Search **GJ<u>O</u>3MH78<u>OO</u>** (letter O for each zero) to show the look-alike match. |
| `GJ11CD8889` / `GJ11CDB889` | cam06 | time unknown | One car read both ways (8 ↔ B) — slide 08's example. |
| `GJ11CD8389`, `GJ23M1546` | cam06 | time unknown | Re-read every loop, so these are the plates most likely to flash on the tile while the jury watches. |

All from today's runs on the recorded copy of this grid; confirm them on the
live feed in tonight's dress rehearsal (§3).

**Do not trace cam30 plates.** Gandhidham is a night junction: its "reads"
today were things like `LA4B1331` and `DD1L0723` — valid-looking codes for
Ladakh and Daman, almost certainly misreads. It is a good camera to *watch*
on the wall, not to read.

### Why the van will not flash on the tile again

The grid replays recordings in a loop (cam06's runs from about 18:01 to
18:11 on its clock). Sentinel stores **one read per camera, plate and printed
second**: the first time the van passes, it is read and stored; every later
loop is the same moment and is refused, by design — a loop or a reconnect
must never look like a second sighting. So after warm-up, `GJ11S7924` is in
the database but will not light the tile again.

The script below does not depend on it. If cam06's clock is near **18:01**
when you open it, the jury watches the van pass; either way you then type the
plate, and the trace shows the printed time **18:01:21** and the frame of
that same van. Say it plainly if asked — it is one of the strongest
evidence points in the room:

> "This feed is a recording that loops. We read this van the first time it
> passed, and we never store the same printed second twice — otherwise every
> loop, and every reconnect, would look like a new sighting."

---

## 2. Quota: the one thing that can end the demo

The grid meters **viewing time per account**, across every machine using
our credentials.

| Open connections | Roughly lasts |
|---|---|
| 1 (cam06 analysed) | over 2 hours |
| 2 | about 2 hours |
| 4 (the 2×2 wall) | under 1 hour |

- **Analyse cam06 only** (`CAMERAS=cam06`). The wall can still show four
  cameras live: a view-only tile pulls only while it is on screen and is
  released about 10 seconds after you leave it.
- **Nothing else pulls with our credentials** — no other laptop, no teammate
  testing from home. The quota is the account's, not this laptop's.
- **Leave the Live Wall when you are not using it.** It opens in 2×2 with the
  first four cameras selected, so just opening it pulls four feeds. cam06's
  preview costs nothing extra: the worker and every viewer share one
  connection per camera.
- **Spent** shows as `403 watch time limit reached` or `401` in
  `make demo-status`. It returns only after **15–20 minutes at zero** — stop
  the worker completely, do not just reduce it, and go to the fallback (§8).
- **Always stop with `make demo-down`.** It stops the worker first and lets
  it hand back its relay paths; a worker killed with `-9` leaves the relay
  dialling the grid, quietly spending the quota.

Check at any time:

```bash
make demo-status                       # live cameras, gateway connections, recent 403s
lsof -nP -iTCP@103.250.160.189:8554 -sTCP:ESTABLISHED | grep -c ESTABLISHED
```

---

## 3. This morning

Everything is already on this laptop: dependencies, models, `.env` with the
government credentials, and the recorded copy of the grid in
`data/gov-mirror/` for the fallback. Nothing to install or copy.

> **Login on this laptop** is the password `make demo` prints — not the
> published `sentinel-admin-2026`. Last night's phone test replaced it, and it
> is kept in `.env` (`SENTINEL_DEMO_ADMIN_PASSWORD`).

### 3.1 Dress rehearsal on the live grid (20 min)

```bash
cd ~/Projects/personal/sentinel-hackathon
git pull                                   # stg; nothing to do if up to date
make demo RESET=1 CAMERAS=cam06 WATCH="GJ03MH7800:wanted:critical"
```

It ends with `✓ 1 of 1 analysed cameras live`, the login, and Safari open.
Then confirm, in this order:

- [ ] Live Wall → **Focus view → 06 Timbavadi gate-Junagadh** plays in
      Safari, with the date and time on the frame. Then leave the Live Wall.
- [ ] Watch cam06's clock pass **18:01:21** and the white van go by.
- [ ] Within about a minute: **Find a Vehicle → `GJ11S7924`** returns one
      sighting, *Jun 17, 06:01:21 PM*, Timbavadi Gate, exact, 100%.
- [ ] Alerts shows `GJ03MH7800` once cam06 passes 18:02:49.
- [ ] **Export report** downloads a ZIP whose PDF has a street map.
- [ ] `make demo-status`: 1 gateway connection, no 403.

If the van or its time differs on the live feed, the grid's recording has
changed: pick the first exact, timed plate Overview → *ANPR activity* shows
for cam06, and use it everywhere this book says `GJ11S7924`.

### 3.2 Rehearse the fallback once (5 min, no quota)

Time it — this is what you will do on stage if the grid fails:

```bash
make demo-down && make demo SOURCE=mirror CAMERAS=cam06
```

- [ ] It ends with cam06 live, from the recording. Note how long it took.
- [ ] Find a Vehicle `GJ11S7924` still returns the 18:01:21 sighting — the
      reads from the live grid are kept.
- [ ] Live Wall → Focus view → Timbavadi Gate plays (now the recording).
- [ ] `make demo-status`: **0** gateway connections.

Then stop for good:

```bash
make demo-down
```

**Leave at least 20 minutes with zero gateway connections before the
warm-up** (§4.2), so the quota starts the slot rested.

### 3.3 Before leaving

- [ ] Print this book (§11 is the one-page card). `npm run docs:demo-book` in
      `apps/web` writes `docs/Sentinel-Demo-Book.pdf`.
- [ ] Rehearse the twenty minutes (§5–6) once with a timer, saying it aloud.
- [ ] Charge the laptop fully; pack its charger — it runs the deck, the
      projector and the analysis at once, so **keep it plugged in** all day.
- [ ] Pack: USB-C to HDMI, an Ethernet adapter, a phone for the hotspot, the
      printed book.
- [ ] Turn off: macOS notifications (Focus → Do Not Disturb), automatic
      updates, the screen saver. Close everything but PowerPoint, Safari and
      Terminal.

---

## 4. Before the jury

### 4.1 On arrival (T−90)

- Wired network if there is one; the phone hotspot as backup.
- Check the grid is reachable from **this** network — venue firewalls often
  block RTSP's port 8554:

  ```bash
  nc -vz 103.250.160.189 8554           # must say "succeeded"
  uv run python scripts/verify_gov_catalogue.py   # must list 30 cameras; opens no video
  ```

  If 8554 is blocked, move to the hotspot and check again.
- Projector: mirror the display; Safari zoom 110–125% so the back row can
  read plates; PowerPoint in presenter view on the same screen.
- Charger in. `caffeinate -dimsu &` — a sleeping Mac stops Docker.

### 4.2 Warm-up (T−40)

```bash
make demo RESET=1 CAMERAS=cam06 WATCH="GJ03MH7800:wanted:critical"
#   + PHONE=1 to show the phone (see §7)
```

`RESET=1` starts from an empty database (backed up first), so the Alerts
queue and the audit log hold only today. Leave it running; by the slot the
van has passed at least once.

Not earlier than T−60: every minute of warm-up is viewing time.

### 4.3 The ten-minute check (T−10)

- [ ] `make demo-status`: cam06 **live**, 1 gateway connection, no 403.
- [ ] Find a Vehicle `GJ11S7924` → one sighting at 06:01:21 PM.
      **If not yet:** wait until cam06's clock passes 18:01:21 again.
- [ ] Alerts: `GJ03MH7800` is there. Leave it unacknowledged.
- [ ] Safari, signed in, **one tab per screen** in this order: Overview,
      Cameras, Live Wall, Find a Vehicle, Alerts, Admin. Only one Live Wall
      tab — each one pulls video.
- [ ] The sound icon in the top bar is on (alerts chime).
- [ ] Safari is on **Overview**, not the Live Wall: nothing extra should
      be pulling video while you talk through slides 01–03.
- [ ] Deck on slide 01, presenter view.
- [ ] A Terminal window ready with the fallback command (§8, rung 3) typed
      but not run.

---

## 5. The twenty minutes

| Time | Slide | What happens |
|---|---|---|
| 0:00 | 01 | Opening line; team in ten seconds — do not read the credentials out |
| 0:45 | 02 | The case: four steps of a manual trace |
| 2:00 | 03 | See · Find · Alert. *"Let us show you, on a camera you choose."* |
| **2:45** | **04** | **The live trace — switch to Safari (§6). About seven minutes.** |
| 10:00 | 10 | Time unknown, never a guess; no face recognition |
| 11:00 | 11 | Measured, not promised — read the *Stated plainly* panel aloud |
| 12:30 | 12–13 | Onboarding; analyse where it is filmed |
| 15:00 | 14 | Cost, "order of magnitude" before the first number |
| 16:30 | 15 | Start with one district; three asks; close and stop talking |
| 18:00 | A1–A10 | Questions: type the slide number and press Enter (A1 = 17 … A10 = 26). A1 is the system architecture. |

**If they ask for the trace first**, go straight to slide 04 and §6, then
come back to slide 02. **If time runs short**, cut slide 12 and give slide 14
in one sentence. **Never cut the trace or slide 11.**

The full spoken script is [13 — Showcase Prep §5](./13-SHOWCASE-PREP.md#5-pitch-script).

---

## 6. The live trace, click by click

Slide 04 on screen. Say the five steps, and the timing, **before** the first
click:

> "Pick any camera. We'll open it, a vehicle passes, we trace it, arm a
> watch, and hand you the report. A plate is committed only once several
> frames agree, so a read reaches the screen in about half a minute."

**Beat 1 — Every camera, one sync** (30 s) · *Cameras → Map*

> "Thirty cameras from the government's own catalogue, onboarded in one
> sync, never typed in by hand."

Optional, for the professors: **Discover cameras → Sync now**. The result
is shown as raw JSON — point at `"fetched": 30` and the empty `"onboarded"`:
re-syncing updates, never duplicates. It opens no video.

**Beat 2 — Four live** (1 min) · *Live Wall → Clear selection → tick cam06,
cam01, cam05, cam30 → 2×2*

> "Four feeds, live, through our relay — the department's system sees one
> viewer per camera however many of us watch. One of them is being read for
> plates; the others are watched, not read. That is a tier, set per camera."

**Gateway connections are now 4. Do not linger: under a minute.**

**Beat 3 — Open one** (30 s) · *Focus view → 06 Timbavadi gate-Junagadh*

The other three release in about ten seconds.

> "This is the camera. Look at the top left: that date and time is printed
> by the camera itself. Every sighting carries that time, not our laptop's."

- **If they name a different camera:** open it first, honestly. *"Plates
  here are about twenty pixels tall — no model reads them, and we won't
  guess. This is why a deployment chooses which cameras to read."* Then come
  back to cam06.
- **If cam06's clock is near 18:01:** *"Watch the centre lane"* — the white
  van passes at 18:01:21.
- **If a plate flashes on the tile** (likely `GJ11CD8389` or `GJ23M1546`):
  point at it — that is a read happening now.

**Beat 4 — Trace** (1–2 min) · *type `gj11 s 7924` in the top search box →
Enter*

> "Spacing and case don't matter. Here it is: Timbavadi Gate, Junagadh,
> 18:01:21 on the camera's own clock, the plate as read, exact, and the frame
> it came from — faces blurred."

Click the stop; point at the evidence frame and the van.

For the professors, one of:
- *"Search the plate with a letter O for the zero"* — type **GJ<u>O</u>3MH78<u>OO</u>** (letter O for each zero):
  `GJ03MH7800` comes back. Look-alike characters are one rung of the search.
- *"A vehicle seen on two cameras is drawn as a route; one that would have
  to drive faster than 150 km/h between them is flagged, not drawn."*
- If asked why one stop: *"Each camera on this grid replays a different
  day, so no vehicle passes two of them. On your cameras, the same search
  draws the route."*

**Beat 5 — Watch** (30 s) · *Watch for this vehicle*

The watch re-checks every past read at once: **the alert banner appears on
the spot**, with a chime.

> "Every plate any camera reads is now checked against this. The next
> sighting is on every open screen — and on an officer's phone."

Open **Alerts**: one row per vehicle, ranked, lit until someone acts.
`GJ03MH7800` (wanted) is there from this morning. Acknowledge it: *"that
action is now in the audit log."*

**Beat 6 — Hand over** (1 min) · *Find a Vehicle → Export report*

Open the ZIP from Downloads:

> "The route on a map, the camera's time in IST and UTC, the frame — and a
> manifest of SHA-256 hashes. Change one byte and it no longer verifies.
> This is yours."

Then **Admin → Audit log → Verify integrity**:

> "Every search, export and acknowledgement you just saw is in a hash chain.
> Change one entry and verification fails."

**Back to the deck: slide 10.**

### If something goes wrong in the middle

| You see | Say and do |
|---|---|
| The search finds nothing | *"Not seen on the cameras we analysed — and the system will not invent a route."* Open **Health** to show cam06 analysed; widen the window to 48 h. Then trace `GJ03MH7800`. |
| A tile says *Connecting…* | Go on with the trace — it reads from stored sightings, not the tile. Fix later (§9). |
| `403` / tiles die mid-demo | *"The sandbox has a viewing quota; we've just used it. Here's the same grid, recorded."* Run the fallback (§8, rung 3) and talk through slides 05–06 while it starts. Calm and named is better than flawless. |
| A banner arrives mid-sentence | Point at it: *"That's correlation running on another camera while we talk."* |

---

## 7. The phone (optional)

Add `PHONE=1` to the warm-up command. It opens a temporary public address to
the API, redeploys the console to **https://sentinel-platform-bay.vercel.app**
built against it, and prints a QR code for `/field`. Because the API is then
on the internet, it runs in production mode with its own secrets and a
**new admin password, printed at the end** — use that on the laptop too.

- Scan the QR **after** the warm-up finishes and pull to refresh, so the
  phone loads tonight's build, not a cached one.
- Show it after Beat 5: the same alert on the phone, then **Look up →
  `GJ11S7924`**. Live video plays on the laptop only.
- If the venue blocks the tunnel, skip it — it is the one optional part.

---

## 8. Fallback ladder

Use the highest rung that works and **say which one you are on**. Everything
runs on this one laptop; the recorded copy of the grid is already on it.

| Rung | When | How |
|---|---|---|
| 1 | Normal | Live grid, cam06 analysed |
| 2 | Laptop struggling (lag growing, fans) | `make demo-down && make demo CAMERAS=cam06 STRIDE=4` |
| 3 | Quota spent, grid down, or venue blocks 8554 | **Switch to the recorded copy:** `make demo-down && make demo SOURCE=mirror CAMERAS=cam06` |
| 4 | The laptop itself fails | Slides **05–09** are the same five steps as screenshots |

**Rung 3, in detail.** No `RESET=1`: the database is kept, so everything read
live today — `GJ11S7924` at 18:01:21, the `GJ03MH7800` alert, the audit log —
is still there, and the trace works the moment the console is back. Every
camera is re-pointed to its local recording, so tiles play again with no
internet and no quota. It takes as long as you timed in §3.2; talk through
slides 05–06 meanwhile, then carry on from where you were. Safari tabs stay
signed in; reload them once it is up.

- Showing the phone too? Add `PHONE=1` (about a minute longer): stopping the
  demo also closes the phone's tunnel.
- Back to the live grid, only after **15–20 minutes at zero**:
  `make demo-down && make demo CAMERAS=cam06` — the catalogue sync re-points
  the cameras to the grid.
- Database lost as well? `make demo SOURCE=mirror RESET=1 CAMERAS=cam06
  WATCH="GJ03MH7800:wanted:critical"` starts from nothing; the van then
  passes within one loop of cam06's recording (about 16 minutes).

---

## 9. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `make demo` stops with a red ✗ | It names the step | Read the line; each step's log is in `var/demo/<step>.log` |
| `403 watch time limit` / `401` | Quota | `make demo-down`, wait 15–20 min at zero, fallback meanwhile |
| Tile black in Chrome | cam06 is H.265 | Use Safari |
| Tile stuck on *Connecting…* | Quota, network, or relay | `make doctor GOV=1` names the break |
| cam06 live but no reads | Worker behind, or the loop is between plates | `make demo-status` for lag; check cam06's clock |
| Console loads, every request fails | Opened on another address | Use `http://localhost:5173` exactly |
| Sign-in rejected | A `PHONE=1` run changed the password | The password `make demo` printed (also in `.env`, `SENTINEL_DEMO_ADMIN_PASSWORD`) |
| Report PDF has no street map | No internet for map tiles | Expected offline; the route is drawn to scale and the caption says so |
| Postgres refused after the lid closed | Docker stopped | Open OrbStack, `make demo` again (data is kept) |
| `make demo` says a worker or port is busy | Something still running | `make demo-down` |

---

## 10. After the slot

```bash
make demo-down                 # releases the gateway first
make demo-status               # 0 connections
```

Then the post-event clean-up in
[10 — Finale Runbook §10](./10-FINALE-RUNBOOK.md#10-after-the-event): delete
what the organisers asked us not to keep, and remove the government
credentials from `.env` on both laptops.

---

## 11. The one-page card

| | |
|---|---|
| **Camera** | cam06 · Timbavadi Gate, Junagadh · Safari only (H.265) |
| **Plate** | `GJ11S7924` · white Maruti Omni van · **18:01:21** on cam06's clock |
| **Wanted, pre-armed** | `GJ03MH7800` · 18:02:49 · look-alike search: type **GJ<u>O</u>3MH78<u>OO</u>** (underlined: the letter O) |
| **Start, T−40** | `make demo RESET=1 CAMERAS=cam06 WATCH="GJ03MH7800:wanted:critical"` |
| **Check** | `make demo-status` · 1 connection · no 403 |
| **Stop** | `make demo-down` — always |
| **Fallback** | `make demo-down && make demo SOURCE=mirror CAMERAS=cam06` — same laptop, today's reads kept |
| **Login** | `admin@sentinel-platform.com` / as printed by `make demo` |

| Moment | Say |
|---|---|
| Before the wait | "Several frames must agree — about half a minute." |
| Asked why one stop | "Each camera here replays a different day." |
| Asked why it didn't flash again | "One read per camera, plate and printed second." |

| Number | Value |
|---|---|
| Plates read exactly (measured) | 80.5% — 33 of 41 vehicles, below our 85% target |
| Camera clocks read exactly | 97.7%, none wrong |
| Footage to stored sighting | median 27–40 s |
| One laptop | 4 cameras × 4 fps kept up (this M2) |
| Statewide | ≈140 Mbps vs 160 Gbps; ≈390 TB vs 12.1 PB a week |
| Cost | ≈₹80 cr build, ≈₹24 cr/yr run, ₹0 licences; centralising ₹400 cr+ |
| Rollout | 500 → 5,000 → 30,000 → 80,000 cameras over 36 months |

---

*Back to [13 — Showcase Prep](./13-SHOWCASE-PREP.md) ·
[10 — Finale Runbook](./10-FINALE-RUNBOOK.md).*
