# 03 — Experience Design
### Sentinel · Design language, surfaces and screen specifications

> **The bar:** a police constable who has never used a VMS should find a vehicle in under 30 seconds, without training, without reading a manual, and without being afraid of breaking something.

---

## Implemented workspace

The current UI uses a **balanced operations workspace**: monitoring and vehicle investigation have equal prominence. A 94px navy navigation rail keeps every destination labelled while giving operational content most of the viewport. Operators can expand it to 224px; that preference persists on the device. Cobalt identifies active navigation and primary actions. The compact toolbar provides current-route context, local date/time, persistent plate search, a visible command-palette launcher, and preferences. Below 768px, navigation becomes a keyboard-accessible drawer and the toolbar wraps into two rows.

The overview leads with four linked summaries derived from API responses: registered cameras, live cameras, down/degraded cameras, and new alerts returned by the queue endpoint. The queue count is not an all-time or fleet-wide alert total. Unknown and connecting cameras are not counted as live. Errors replace summary values with "Not available"; an empty successful response shows zero.

A plate-entry form launches investigation directly. The network workbench switches between a map and searchable camera list; camera-health buttons filter both views. The activity panel switches between watchlist matches and the latest 12 recorded detections. Clicking a match opens that alert in triage; clicking a detection opens its plate investigation. Records without coordinates remain available in the list and are explicitly excluded from the located-camera count. Camera and detection data refresh every 8 seconds, alerts every 6 seconds; manual refresh retries all three. View tabs support arrow keys, Home and End.

Vehicle investigation keeps a persistent registration-plate query bar above its results. The workbench separates movement map, selectable sighting timeline and evidence inspector, with first/last sightings, mapped-sighting counts, replay and export together. Missing coordinates and missing snapshots are explained rather than silently omitted. Empty searches retain the BOLO action.

Alerts use a master-detail triage workbench: lifecycle filters, plate/camera search, severity filtering and sorting act on the loaded queue. The selected alert exposes matching facts, evidence and lifecycle actions. Refresh and action failures retain context and support retry.

The surveillance workbench has a camera selector, filtering, selectable grid density and single-camera focus. Camera inventory combines health filters, searchable records, and a map with a persistent camera list. Bulk CSV import and catalogue discovery are direct onboarding entry points; the detail workspace retains preview, health and zone creation.

Administration is a section hub with a searchable access register, contextual user creation, watchlists, integration checks, audit verification, and retention impact preview. Changing retention periods invalidates a previous deletion confirmation. Health groups integrator checks and can filter checks needing attention; these checks describe configuration, not camera availability.

The field experience uses a task-first mobile shell with lookup, alerts, reporting and nearby cameras. Lookup results hand off to reporting; reports group vehicle details and optional evidence and still enter the existing offline outbox. Alert cards expose actions on demand; nearby cameras can be searched in map/list views, with distances only when location is available.

Light and dark themes, and English, Hindi and Gujarati, are device-persistent preferences. New sessions start in light mode; an existing dark preference is preserved. The sign-in surface pairs a navy product introduction with a focused credential form, stacking on phones; a labelled password-visibility toggle preserves the entered value. No demo credentials or fabricated readiness claims are displayed. API refresh failures show a retry action and warn that retained data may be stale; missing data is not presented as a healthy zero. The toolbar searches **registration plates**, not arbitrary camera names or places; camera filtering and the command palette are separate controls.

The sections below also describe longer-term product aspirations. Features such as reversible destructive actions, alert sounds, saved wall layouts and cases are not implied to be implemented by this redesign.

Validation: from `apps/web`, run `npm run test:ui` for mocked-browser acceptance tests (first install Chromium with `npx playwright install chromium`). The runner starts an isolated Vite server on port 5188. Run `npm run build` and `npm run lint` for production and static checks.

The full redesign is covered by 62 browser tests across the original workspace suite and new command, investigation, monitoring, management and translation suites. A 61-test integrated run passed, followed by all 12 investigation tests after the final deep-link regression was added. On shared or resource-constrained machines, use `npm run test:ui -- --workers=1`: concurrent WebGL/browser contexts can contend with live inference. These tests validate UI/API contracts using fixtures, not live OCR accuracy or successful government-stream playback.

## 1. Design philosophy

Apple's three HIG pillars — **Clarity, Deference, Depth** — translated into a command-and-control context:

| Pillar | In a control room | Concretely |
|---|---|---|
| **Clarity** | One glance, one truth | Plates in mono type at 28 px. Severity never encoded in colour alone. No screen shows two competing "most important things". |
| **Deference** | The interface supports the video and the map | Navy navigation, pale working surfaces and cobalt actions; semantic colours belong to status. No decorative gradients or logo watermarks over video. |
| **Depth** | Layers communicate hierarchy, not decoration | Bordered working surfaces; shadows reserved for dialogs. Dialogs are dismissible and scroll within the viewport. |

Four additional principles specific to this product:

4. **Calm under pressure.** The UI must not add adrenaline. No flashing, no red-on-red, no alarm fatigue. A critical alert earns exactly one soft chime, one pulse, and a persistent but quiet presence.
5. **Plain language, always.** `Camera not responding — last seen 4 minutes ago. Retrying automatically.` Never `RTSP DESCRIBE failed: 503`. The technical detail lives behind a "Details" disclosure for the engineer who wants it.
6. **Evidence is always one click away.** Every number, alert and route hop is traceable to a snapshot and a timestamp. Nothing is asserted without proof attached.
7. **Forgiving by default.** Undo over confirm. Destructive actions are reversible for 10 seconds via a toast. Nothing a nervous first-time user does should be unrecoverable.

---

## 2. Design tokens

### 2.1 Colour

Light is the default for new sessions. Dark remains a first-class peer for control rooms, and saved preferences always win. Navigation stays navy in both themes.

| Token | Dark | Light |
|---|---|---|
| Base | `#101725` | `#f3f5fa` |
| Raised | `#182235` | `#ffffff` |
| Overlay | `#25334b` | `#e9edf6` |
| Inset | `#131c2c` | `#f7f8fc` |
| Primary text | `#edf3f7` | `#17243b` |
| Secondary text | `#c4cfe0` | `#465772` |
| Tertiary text | `#b2bed2` | `#556580` |
| Accent | `#a4bfff` | `#2456d6` |
| On accent | `#10224c` | `#ffffff` |

The complete semantic palette is defined in [index.css](../apps/web/src/index.css). Text and primary-action contrast are covered by browser tests. Severity is conveyed by icon, label and colour, never colour alone. Blue is reserved for actions, selection and focus; success, warning and failure keep their semantic colours.

### 2.2 Typography

```
--font-ui:    "Public Sans", system-ui            /* UI, body */
--font-data:  ui-monospace, "SF Mono", monospace  /* plates, timestamps, IDs, coordinates */

--text-xs: 11/16   --text-sm: 13/18   --text-base: 15/22
--text-lg: 17/24   --text-xl: 20/28   --text-2xl: 24/32   --text-3xl: 32/40
```

- All numerals use `font-variant-numeric: tabular-nums` so timestamps and counters never shift width.
- Public Sans regular, semibold and bold are self-hosted under `apps/web/public/fonts`, with their SIL Open Font License. Fonts are included in the PWA precache; no runtime font-service request is required. Hindi and Gujarati use the device's script-capable fallback.
- **Plates are rendered in mono, letter-spaced, with a slashed zero** — a deliberate cue that this is machine-read data, and it kills the 0/O ambiguity visually. Uncertain characters render at reduced opacity with a subtle underline, so an operator instantly sees *which* character the model was unsure about.

### 2.3 Space, shape, elevation, motion

```
--space: 4px base · 4 8 12 16 20 24 32 40 48 64
--radius-sm: 4px · --radius-md: 8px · --radius-lg: 12px · --radius-xl: 16px · --radius-full
--shadow-1: 0 1px 2px rgb(0 0 0 / .32)
--shadow-2: 0 4px 12px rgb(0 0 0 / .36)
--shadow-3: 0 12px 32px rgb(0 0 0 / .44)
--blur-material: saturate(180%) blur(20px)   /* floating panels over video/map */

--ease-out:    cubic-bezier(0.22, 1, 0.36, 1)
--ease-inout:  cubic-bezier(0.65, 0, 0.35, 1)
--spring-soft: spring(1, 120, 16, 0)   /* panels, sheets */
--spring-snap: spring(1, 300, 24, 0)   /* toggles, chips */
--dur-fast: 120ms · --dur-base: 200ms · --dur-slow: 320ms · --dur-map: 700ms
```

Motion rules: elements enter from where they belong (a detail panel slides from the edge it is anchored to, never fades in from nowhere); nothing animates longer than 320 ms except map camera flights; **`prefers-reduced-motion` disables all transforms and keeps opacity-only transitions.** Layout must never shift after load — skeletons occupy the exact final geometry.

### 2.4 Sound

Three sounds only, all short, soft and pitched to be audible over room noise without startling: `alert-critical` (two-tone), `alert-normal` (single tone), `success` (soft click). Muted state is one click away and remembered per user. Sound is never the only channel for information.

---

## 3. Surfaces

| Surface | Primary user | Device | Core job |
|---|---|---|---|
| **Operator Console** | Control-room operator, investigating officer | Desktop 1440–2560 px, often dual monitor | Watch, search, triage, trace |
| **Field PWA** | Officer on the ground, checkpost staff | Phone, installable, offline-tolerant | Receive alerts, look up a plate, report a sighting |
| **Admin Portal** | Department nodal officer, SCRB administrator | Desktop/laptop | Onboard cameras, manage users/watchlists, audit, policies |

One React codebase, one design system, three shells. The Field PWA is not a "responsive squeeze" of the console — it is a separate, drastically reduced information architecture built on the same primitives.

---

## 4. Operator Console

### 4.1 Information architecture

```
Home (Situational Awareness)  ·  Live Wall  ·  Find a Vehicle  ·  Alerts  ·  Cameras  ·  Cases  ·  Health
```

The implemented destinations are Overview, Live Wall, Find a Vehicle, Alerts, Cameras and Health, with role-gated Admin and a link to the Field PWA. Cases remains planned. A readable sidebar becomes a navigation drawer on phones; the global ⌘K command palette remains available.

### 4.2 Home — balanced monitoring and investigation

The implemented overview is an interactive network/activity workbench, not a passive map dashboard: view switching, camera search, health filters, plate-entry and linked detection/alert records are described above. The map-first wireframe and decisions below are the earlier concept, retained as background rather than a specification of the current layout.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ▣ Sentinel            ⌕ Search a plate, camera or place…          🔔 3  ⚙  PP │  56px
├────┬─────────────────────────────────────────────────────┬───────────────────┤
│ ▤  │                                                     │  NEEDS ATTENTION  │
│ ▦  │                                                     │ ┌───────────────┐ │
│ ⌕  │            MapLibre · dark vector basemap           │ │🔴 Stolen car  │ │
│ ⚑  │                                                     │ │ GJ01AB1234    │ │
│ ▧  │      ● ● ●  camera dots, clustered, status-tinted   │ │ [snapshot]    │ │
│ ▩  │      ◆ live alert pins, gently pulsing              │ │ Sector 18 · 2m│ │
│ ◈  │                                                     │ │ Ack   Details │ │
│    │                                                     │ └───────────────┘ │
│    │                                                     │ ┌───────────────┐ │
│    │  ┌──────────────────────────┐                       │ │🟠 Camera down │ │
│    │  │ 48 live · 2 down · 1 deg │  ← health pill        │ │ AHM-0142 · 6m │ │
│    │  └──────────────────────────┘                       │ └───────────────┘ │
├────┴─────────────────────────────────────────────────────┴───────────────────┤
│  Last hour: 1,284 plates read · 3 watchlist hits · 12 cameras in low-bandwidth │
└──────────────────────────────────────────────────────────────────────────────┘
```

Decisions that carry the whole product:

- **The map is the application.** Everything else floats above it. This matches how police actually think — geographically.
- **The right rail answers exactly one question: "what needs me?"** It is not an event firehose. Events live in Alerts; the rail shows only what is unacknowledged and relevant to this user's jurisdiction.
- **The search field is the single most prominent control** and accepts a plate, a camera name, or a place. Typing a plate-shaped string immediately offers *"Find vehicle GJ01AB1234"* as the first action — this is the eval-day path, and it is one keystroke deep.
- **Camera dots are tinted by health, sized by importance, clustered by zoom.** Hovering peeks a live thumbnail; clicking opens a compact card with a live preview and three actions (Watch, Recent detections, Details).
- **The bottom strip is ambient, not interactive** — a calm heartbeat that tells an operator the system is alive.

### 4.3 Live Wall

**Implemented workbench:** select the cameras to view, filter the selection list, change grid density, or focus one selected camera. Camera details are reachable with labelled buttons as well as the existing double-click interaction. Only visible mounted tiles resolve their streams; empty selection and unavailable streams have explicit states. On phones, the entire wall remains vertically scrollable. Camera registration, zone editing, CSV preview-before-commit and catalogue discovery remain real API actions.

The following capabilities remain the earlier target design; saved layouts, drag reordering, transport switching and playback scrubbers are not implied by the workbench redesign.

- Adaptive grid: 1 / 2×2 / 3×3 / 4×4 / custom, drag to rearrange, layouts saved per user and shareable to a colleague as a link.
- **WebRTC (WHEP) by default; automatic HLS fallback** with a small, honest badge showing the transport and the current latency. A firewall problem should be visible, not mysterious.
- Each tile: name, department chip, live/degraded/offline dot, measured fps, and a detection overlay toggle (plate boxes with the read text pinned beside the vehicle).
- **Only visible tiles stream.** Scrolled-off tiles pause and show the last keyframe — this is both a performance requirement and an explicit organiser instruction ("open only cameras you process").
- Double-click a tile → immersive single view with playback scrubber (for recorded cameras) and recent detections.
- Spotlight behaviour: when a critical alert fires, the wall offers a non-intrusive *"Jump to camera"* chip. It never hijacks the view — hijacking is how operators learn to distrust software.

### 4.4 Find a Vehicle — the flagship screen

Two states. Nothing else.

**State 1 — Ask.** A single large input, centred, with a mono placeholder `GJ 01 AB 1234`. Below it, three quiet helpers: *Don't know the full number?* (switches to a per-character grid where any position can be left blank) · *Last 24 hours ▾* · *All departments ▾*. No advanced-search panel. The advanced options reveal themselves only when the simple path is insufficient.

**State 2 — Answer.**

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  GJ01AB1234   ⬤ Stolen vehicle · reported 18 Sep         [Add to watchlist ✓] │
│  7 sightings across 5 cameras · 14:02 → 15:47 · 23.4 km travelled              │
├───────────────────────────────────────┬──────────────────────────────────────┤
│                                       │  TIMELINE                            │
│    map with route polyline,           │  ● 14:02  Sarkhej Circle      ▓ 0.96 │
│    numbered hops, direction arrows,   │  ● 14:19  SG Highway Gate 2   ▓ 0.94 │
│    dashed segment = probable          │  ◌ 14:41  Bopal Junction      ▒ 0.71 │
│    (matched by appearance, not plate) │     probable · matched by appearance │
│    ▶ Replay route                     │  ● 15:12  Iskcon Crossroad    ▓ 0.98 │
│                                       │  ● 15:47  Prahladnagar        ▓ 0.93 │
├───────────────────────────────────────┴──────────────────────────────────────┤
│  [thumb] [thumb] [thumb] [thumb] [thumb]   ← evidence strip, click to enlarge │
│                        Export report  ·  Add to case  ·  Share               │
└──────────────────────────────────────────────────────────────────────────────┘
```

- **Confidence is shown, not hidden.** A filled bar and a number, with a plain-language tooltip: *"Read clearly at this camera"* / *"Two characters uncertain — matched using vehicle colour and timing."*
- **Probable hops are visually distinct** (hollow marker, dashed route segment) and can be toggled off. A jury will ask "how do you know?" — the interface answers before they ask.
- **Replay route** animates the vehicle along the polyline with the timeline scrubbing in sync. It reads as a story, and it is the single most demo-able interaction in the product.
- **Export report** produces the PDF/CSV movement report — the literal eval-day artefact — in one click.
- Empty result is never a dead end: *"No sightings for GJ01AB1234 in the last 24 hours. Watch for this vehicle →"* arms a BOLO, turning a failed search into a standing instruction.

### 4.5 Alerts

- Inbox metaphor, grouped by priority then recency, with filter chips (Mine · Unacknowledged · Critical · My district · Today).
- **Alert card = Apple notification, evolved:** snapshot thumbnail, plate in mono, *why it matched in one plain sentence* ("Exact match on stolen-vehicle list, added by PI Shah, 18 Sep"), camera and time, and two actions — **Acknowledge** and **Open**.
- Opening an alert slides in a detail panel: the clip with pre/post-roll, the full detection, the vehicle's other sightings, the watchlist entry with its case reference, and the action bar (Assign · Resolve · Not this vehicle).
- **"Not this vehicle" is given equal visual weight to "Resolve"** — making false-positive reporting effortless is how the model improves and how the system stays trusted. It also directly answers the redressal critique levelled at such systems.
- Repeat sightings collapse into one card with a count and a mini-timeline. Never five cards for one car at one traffic light.

### 4.6 Cameras (registry + onboarding)

- Table ⇄ map toggle, sharing one filter state. Columns: name, department, type, status, last seen, analytics tier, resolution/codec.
- **Onboarding wizard, three steps, non-technical language:**
  1. *Where is it?* — map pin with address autocomplete, plus a draggable field-of-view cone.
  2. *How do we connect?* — big choices first ("Discover on my network" / "I have a link" / "Import a file" / "Connect a department system"). The RTSP URL field is there, but it is not the first thing a nervous user sees.
  3. *What should it watch for?* — plain-language analytics choices ("Read number plates", "Alert on people entering a restricted zone") mapping to the tier system underneath.
  A **live preview appears the moment credentials validate** — instant feedback that it worked, which is the difference between confidence and a support ticket.
- Bulk import: drag a CSV, get a column-mapping screen with a live preview of the first five rows, per-row validation with inline fixes, and a dry-run before commit.
- **Coverage gap analysis** renders as a heat layer with plain-language findings: *"Sector 21 has no camera coverage within 800 m of the main road"* and an exportable report.

### 4.7 Health & Ops

- Fleet status board: live/degraded/offline counts, uptime sparklines, first-IDR latency, measured-vs-declared fps, reconnect counts, discontinuity events, queue depth, inference latency, GPU/CPU per node.
- **Integrator Compliance panel** — a live green-tick board mirroring the organisers' pre-submission checklist (TCP forced ✓, PTS-driven timing ✓, backoff active ✓, catalogue-driven discovery ✓, mixed-codec handling ✓, publish disabled ✓). Cheap to build, and it tells a technical jury in three seconds that you read their guide.

---

## 5. Field PWA

Radically reduced. Four things, large touch targets, one-handed, works on a weak network.

1. **Alerts** — a single scrollable list of cards, newest first, with a full-bleed snapshot. Tap to expand: plate, location with distance-from-me, "Navigate" (opens maps), "Acknowledge", "I see it".
2. **Look up** — a numeric-friendly plate keypad; result shows the vehicle's status (clear / stolen / wanted) as a full-screen colour-and-icon verdict readable at arm's length in sunlight, with the last sighting below.
3. **Report a sighting** — camera capture + auto plate read + GPS, queued offline and synced when connectivity returns.
4. **Nearby cameras** — map of cameras around me, tap to view (HLS, low-bandwidth profile).

PWA specifics: installable with a proper icon set, Web Push for alerts, service-worker offline shell, IndexedDB outbox for queued reports, a low-bandwidth mode that suppresses snapshots and shows text-only alerts, and an explicit "last synced" line so the officer always knows whether they are seeing fresh data.

---

## 6. Admin Portal

Quieter visual tone (light theme default), denser tables, built for correctness over speed.

- **Departments & sites** — hierarchy, contacts, camera counts, integration status per department.
- **Users & roles** — role matrix editor with a live "what this person can see" preview; jurisdiction scoping on a map.
- **Watchlists** — list management, bulk import, each entry carrying type, priority, purpose, validity window, requesting officer and case reference. Expired entries visibly fade and stop matching automatically.
- **Retention & privacy policies** — per-data-class retention sliders with a plain-language consequence preview ("Event clips will be deleted after 30 days. About 1.2 TB affected.") and default-blur settings.
- **Audit log** — filterable, exportable, with a **"Verify integrity"** button that recomputes the hash chain and shows a green seal. Demonstrating a tamper-evident audit trail live is a quiet showstopper.
- **Integrations** — VAHAN / SARTHI / eGujCop / AFIS connector cards with status, last sync, request volume and a test-connection button.

---

## 7. Cross-cutting interaction rules

| Rule | Why |
|---|---|
| **Optimistic UI with undo**, not confirmation dialogs | Acknowledging an alert should feel instant; a 10-second undo toast is safer *and* faster than a modal |
| **Skeletons that match final geometry** | Zero layout shift; the screen never "jumps" while an operator is reading |
| **Relative time + absolute on hover**, PTS-accurate | "2 min ago" for scanning, `22 Sep 2026, 14:02:18.340 IST` for evidence |
| **Errors state the cause and the next action** | "Camera not responding — retrying automatically (next attempt in 8s). Details ▾" |
| **⌘K command palette** | Power users fly; everything in it is also reachable by mouse |
| **Keyboard map**: `/` search · `A` acknowledge · `←/→` timeline · `Space` play/pause · `Esc` dismiss | Control rooms are keyboard places |
| **ARIA live regions for new alerts**, visible focus rings, full keyboard reachability, WCAG 2.2 AA | Accessibility is a government procurement requirement, not a nicety |
| **No dead ends** — every empty state teaches and offers the next action | First-run experience decides whether a non-technical user stays |
| **Density toggle** (comfortable / compact) | A 4K control-room wall and a 13" laptop are different rooms |

**Performance budgets** (they are part of the feeling of quality, not separate from it): first contentful paint < 1.2 s, interaction latency < 100 ms, map sustained at 60 fps with 5,000 camera markers (deck.gl layer, not DOM), live wall of 16 WebRTC tiles without dropped frames, alert appears in the UI < 2 s after the detection PTS.

---

## 8. Build approach for a backend-heavy solo developer

This is the honest part of the plan: polish is achieved by *choosing well*, not by hand-crafting CSS.

1. **Steal the hard parts.** Radix/shadcn primitives give correct focus management, keyboard behaviour and ARIA for free. Never hand-roll a dropdown or a dialog.
2. **Tokens first, components second, screens third.** One afternoon spent on `tokens.css` makes every subsequent screen look intentional, because coherence — not ornament — is what reads as "Apple-level".
3. **Constrain the palette brutally.** One accent, four severity colours, a neutral ramp. Most amateur UI looks amateur because it uses too many colours and too many type sizes.
4. **Build a component gallery page early** (`/dev/gallery`) showing every component in every state. It is the fastest way to spot inconsistency, and it doubles as a portfolio artefact.
5. **Motion last, and sparingly.** Add spring transitions only to panels, sheets and the route replay. Animating everything is the signature of a first draft.
6. **Two screens carry the demo** — Home and Find a Vehicle. Spend disproportionate time there; make the rest merely clean and consistent.
7. **Test with a non-technical person.** Hand them a plate number and say nothing. Watch where they hesitate. That hesitation is the design brief.

---

*Next: [04-SCALE-PLAN](./04-SCALE-PLAN.md) — the 80,000-camera argument with numbers.*
