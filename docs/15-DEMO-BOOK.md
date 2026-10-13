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
30 cameras (12 Oct, 22:50); on 13 Oct at 06:45 cam06 played live from the
grid on this laptop, analysed; and from 06:53 the live feeds of cam06, cam30,
cam01 and cam05 were recorded to `data/gov-mirror/` for the fallback.

---

## 1. The plate and the camera

**Camera: cam06 — Timbavadi Gate, Junagadh.** The only camera on the grid
whose plates are large and front-on enough to read, with a date-time
overlay we read reliably. Every other camera is a wide-angle view; plates
there are 20–30 pixels tall.

**The grid changed overnight.** On 13 Oct cam06 replays **17 Jun 2026,
21:22–21:36, at night** — not the daytime footage the deck's screenshots
came from. So the deck's van (`GJ11S7924`) is not in today's feed. Today's
plate was found by recording the live feed this morning and running the full
edge pipeline over it, exactly as the demo will:

**Plate: `GJ11CL9596`** — an SUV with its headlights on, parked on the right
at the top of the frame, at **21:22:44 on cam06's clock** (17 Jun 2026). Read
exactly at 100%, agreed across three frames, its plate legible in the
evidence frame even at night. It is in shot for about 50 seconds, so the jury
has time to see it.

| Plate | Camera | cam06 clock | Use it for |
|---|---|---|---|
| **`GJ11CL9596`** | cam06 | 21:22:44 | **The trace**, then *Watch for this vehicle*: the alert banner fires on the spot. Search **GJ11CL9<u>S</u>96** (letter S for the 5) to show the look-alike match. |
| `DL1C1356` | cam06 | 21:22:16 | Pre-armed as *wanted*, so a watchlist alert is in the queue before the jury arrives. A Delhi car: Gujarat's cameras read every state. |
| `AS2A6440` | cam06 | 21:23:03 | Read once, just after. |

Measured on the recording of the live feed made on 13 Oct at 06:53
(`data/gov-mirror/`), at the demo's own settings: four frames a second, the
same models, the same voting, the same clock reader. On the night footage
the clock read every second from 21:22:46 to 21:23:00 without a miss.

**Night footage reads less.** In the 14 minutes recorded, the pipeline
committed four reads, three of them single frames; in daylight it commits
dozens. That is the reason to trace a plate already read during warm-up
rather than wait for a fresh one on stage.

**Do not trace cam30 plates.** Gandhidham's recording is past midnight
(9 Aug, 00:31–00:44) and produced no valid plate in the same test. It is a
camera to *watch* on the wall, not to read.

### Why the SUV will not flash on the tile again

The grid replays each camera's recording in a loop. Sentinel stores **one
read per camera, plate and printed second**: the first time the SUV is in
shot, it is read and stored; every later loop is the same moment and is
refused, by design — a loop or a reconnect must never look like a second
sighting. So after warm-up, `GJ11CL9596` is in the database but will not
light the tile again.

The script below does not depend on it. If cam06's clock is near **21:22**
when you open it, the jury sees the SUV; either way you then type the plate,
and the trace shows the printed time **21:22:44** and the frame of that
same SUV. Say it plainly if asked — it is one of the strongest evidence
points in the room:

> "This feed is a recording that loops. We read this car the first time it
> passed, and we never store the same printed second twice — otherwise every
> loop, and every reconnect, would look like a new sighting."

---

## 2. Quota: the one thing that can end the demo

The grid meters **viewing time per account**, across every machine using
our credentials.

**Measured on 13 Oct, it is tight.** After about ten minutes of one
connection at 06:45, two connections ran out the quota at 07:08 — about
fifteen minutes. It came back at 07:26, after about eighteen minutes at zero.
Plan on roughly **25–30 connection-minutes per window**:

| Open connections | Roughly lasts |
|---|---|
| 1 (cam06 analysed) | about 25–30 minutes |
| 2 | about 15 minutes |
| 4 (the 2×2 wall) | under 10 minutes |

That covers the twenty minutes with the jury **only if the quota is fully
rested when you go live, and you go live at T−10, not earlier**. So the
warm-up runs on today's recording of the feed, which costs nothing (§4.2),
and the live grid is used for the slot only (§4.3).

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
government credentials, and a recording of this morning's live feed in
`data/gov-mirror/` (13 Oct, 06:53–07:40): cam06 and cam01 about 14 minutes
each, cam05 14, cam30 about 6. The 8 Oct recording of all 30 cameras is kept
in `data/gov-mirror-2026-10-08/` — its footage is no longer what the grid
plays. Nothing to install or copy.

> **Login on this laptop** is the password `make demo` prints — not the
> published `sentinel-admin-2026`. Last night's phone test replaced it, and it
> is kept in `.env` (`SENTINEL_DEMO_ADMIN_PASSWORD`).

### 3.1 Dress rehearsal on the recording (20 min, no quota)

Exactly the order of the day (§4.2–4.3), so the quota is spent only in the
last step:

```bash
cd ~/Projects/personal/sentinel-hackathon
git pull                                   # stg; nothing to do if up to date
make demo SOURCE=mirror RESET=1 CAMERAS=cam06 WATCH="DL1C1356:wanted:critical"
```

It ends with `✓ 1 of 1 analysed cameras live`, the login, and Safari open.
Leave it one loop of cam06 (about 14 minutes), then confirm:

- [ ] Live Wall → **Focus view → 06 Timbavadi gate-Junagadh** plays, with
      the date and time on the frame. Then leave the Live Wall.
- [ ] **Find a Vehicle → `GJ11CL9596`** returns one sighting,
      *Jun 17, 09:22:44 PM*, Timbavadi Gate, exact, 100%.
- [ ] Alerts shows `DL1C1356` (wanted).
- [ ] Search **GJ11CL9<u>S</u>96** returns `GJ11CL9596`.
- [ ] **Watch for this vehicle** raises the banner with a chime.
- [ ] **Export report** downloads a ZIP whose PDF has a street map.
- [ ] `make demo-status`: **0** gateway connections.

If the SUV or its time differs, run Overview → *ANPR activity*, pick the
first exact, timed plate for cam06, and use it everywhere this book says
`GJ11CL9596`.

### 3.2 Go live once, and time it (5 min of quota)

```bash
make demo-down && make demo CAMERAS=cam06
```

- [ ] It ends with cam06 live, from the grid. **Note how long it took** — on
      stage, rung 3 of §8 is the same switch the other way.
- [ ] Find a Vehicle `GJ11CL9596` still returns the 21:22:44 sighting — the
      reads from the recording are kept.
- [ ] Live Wall → Focus view → Timbavadi Gate plays live (Safari).
- [ ] `make demo-status`: 1 gateway connection, no 403.

Then stop for good:

```bash
make demo-down
```

**Leave at least 20 minutes with zero gateway connections before going
live on the day** (§4.3), so the quota starts the slot rested.

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

### 4.2 Warm-up from the recording (T−40) — no quota

The quota cannot cover a live warm-up *and* the slot (§2). So warm up on
today's recording of the same feed, which holds the same SUV at the same
printed second, and switch to the live grid only for the slot:

```bash
make demo SOURCE=mirror RESET=1 CAMERAS=cam06 WATCH="DL1C1356:wanted:critical"
```

`RESET=1` starts from an empty database (backed up first), so the Alerts
queue and the audit log hold only today. Leave it running at least one loop
of cam06's recording (about 14 minutes): by then `DL1C1356` (21:22:16) and
`GJ11CL9596` (21:22:44) are both read, timed and stored, and the pre-armed
`DL1C1356` has raised its alert. `make demo-status` shows **0** gateway
connections throughout — the quota stays rested.

### 4.3 Go live (T−10) — about 2 minutes

Same database (no `RESET=1`), now pointed at the live grid:

```bash
make demo-down && make demo CAMERAS=cam06
```

The catalogue sync re-points all 30 cameras to the government grid; the reads
from the warm-up stay. This starts the quota clock: **about 25 minutes**, so
do this at T−10, not earlier. If the slot is delayed, go back to the
recording (`make demo-down && make demo SOURCE=mirror CAMERAS=cam06`) and
come live again at the new T−10.

### 4.4 The ten-minute check (T−8)

- [ ] `make demo-status`: cam06 **live**, 1 gateway connection, no 403.
- [ ] Find a Vehicle `GJ11CL9596` → one sighting at 09:22:44 PM.
- [ ] Alerts: `DL1C1356` (wanted) is there. Leave it unacknowledged.
- [ ] Safari, signed in, **one tab per screen** in this order: Overview,
      Cameras, Live Wall, Find a Vehicle, Alerts, Admin. Only one Live Wall
      tab — each one pulls video.
- [ ] The sound icon in the top bar is on (alerts chime).
- [ ] Safari is on **Overview**, not the Live Wall: nothing extra should
      be pulling video while you talk through slides 01–03.
- [ ] Deck on slide 01, presenter view.
- [ ] A Terminal window ready with the fallback command (§8, rung 3) typed
      but not run.

**The jury will not see a fresh read of the SUV live**: the live feed may
be anywhere in its loop, and a read already stored is not stored twice
(§1). Beat 3 shows the camera live; Beat 4 traces what it read. Say so if
asked.

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
- **If cam06's clock is near 21:22:** *"Watch the car parked on the right"* —
  the SUV is in shot from 21:22:44 for about 50 seconds.
- **If a plate flashes on the tile:** point at it — that is a read happening
  now. At night it is rare; do not wait for one.

**Beat 4 — Trace** (1–2 min) · *type `gj11 cl 9596` in the top search box →
Enter*

> "Spacing and case don't matter. Here it is: Timbavadi Gate, Junagadh,
> 21:22:44 on the camera's own clock, the plate as read, exact, and the frame
> it came from — at night, headlights on, faces blurred."

Click the stop; point at the evidence frame and the plate on the SUV.

For the professors, one of:
- *"Search it with a letter S for the 5"* — type **GJ11CL9<u>S</u>96**:
  `GJ11CL9596` comes back. Look-alike characters are one rung of the search.
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
`DL1C1356` (wanted) is there from this morning. Acknowledge it: *"that
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
| The search finds nothing | *"Not seen on the cameras we analysed — and the system will not invent a route."* Open **Health** to show cam06 analysed; widen the window to 48 h. Then trace `DL1C1356`. |
| A tile says *Connecting…* | Go on with the trace — it reads from stored sightings, not the tile. Fix later (§9). |
| `403` / tiles die mid-demo | *"The sandbox has a viewing quota; we've just used it. Here's the same grid, recorded."* Run the fallback (§8, rung 3) and talk through slides 05–06 while it starts. Calm and named is better than flawless. |
| A banner arrives mid-sentence | Point at it: *"That's correlation running on another camera while we talk."* |

---

## 7. The phone (optional)

Add `PHONE=1` to the go-live command (§4.3). It opens a temporary public address to
the API, redeploys the console to **https://sentinel-platform-bay.vercel.app**
built against it, and prints a QR code for `/field`. Because the API is then
on the internet, it runs in production mode with its own secrets and a
**new admin password, printed at the end** — use that on the laptop too.

- Scan the QR **after** going live and pull to refresh, so the
  phone loads tonight's build, not a cached one.
- Show it after Beat 5: the same alert on the phone, then **Look up →
  `GJ11CL9596`**. Live video plays on the laptop only.
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
live today — `GJ11CL9596` at 21:22:44, the `DL1C1356` alert, the audit log —
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
  WATCH="DL1C1356:wanted:critical"` starts from nothing; the SUV then
  passes within one loop of cam06's recording (about 14 minutes).

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
| **Plate** | `GJ11CL9596` · SUV parked on the right, headlights on · **21:22:44** on cam06's clock (night) |
| **Wanted, pre-armed** | `DL1C1356` · 21:22:16 |
| **Look-alike search** | type **GJ11CL9<u>S</u>96** (underlined: the letter S) → `GJ11CL9596` |
| **Warm up, T−40** | `make demo SOURCE=mirror RESET=1 CAMERAS=cam06 WATCH="DL1C1356:wanted:critical"` — recording, no quota |
| **Go live, T−10** | `make demo-down && make demo CAMERAS=cam06` — about 25 minutes of quota |
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
