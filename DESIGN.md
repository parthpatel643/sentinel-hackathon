---
name: Sentinel
description: A departures gate board for vehicles. Ranked rows, one lit signal, and a perforated sighting pass.
colors:
  ink: "#111417"
  ink-hover: "#272c31"
  ink-secondary: "#2f353b"
  ink-muted: "#4c5157"
  cool-ground: "#edeeea"
  paper-panel: "#fbfbf9"
  paper-inset: "#f3f4f0"
  paper-overlay: "#e9eae5"
  rule: "#d5d7d2"
  rule-strong: "#8a8f95"
  signal-amber: "#ffb000"
  on-signal: "#111417"
  signal-tint: "#fff4da"
  signal-tint-hover: "#ffedc4"
  signal-rule: "#eccb78"
  signal-ink: "#5a4410"
  critical-fill: "#c4282f"
  critical-ink: "#c4282f"
  danger-fill: "#b3262d"
  caution-ochre: "#865209"
  info-blue: "#17658e"
  live-green: "#1f7a4a"
  hatch-line: "#858a90"
  hatch-ground: "#e4e5e1"
  chrome: "#111417"
  on-chrome: "#f3f4f0"
  on-chrome-muted: "#b9bec4"
  evidence-black: "#0b0d0f"
  dark-ground: "#0e1012"
  dark-panel: "#16191c"
  dark-pass: "#23272b"
  dark-inset: "#1b1e22"
  dark-hover: "#1f2327"
  dark-rule: "#2e3338"
  dark-rule-strong: "#6e757d"
  dark-ink: "#eef0ec"
  dark-ink-secondary: "#c3c8cc"
  dark-ink-muted: "#a9afb5"
  dark-chrome: "#08090a"
  dark-signal-rule: "#b07a12"
  dark-critical-ink: "#ff8a8f"
  dark-caution-ochre: "#f1c17b"
  dark-info-blue: "#8ccdf2"
  dark-live-green: "#3fbf7a"
  dark-hatch-ground: "#2a2e33"
typography:
  display:
    fontFamily: "Sofia Sans Condensed, Atkinson Hyperlegible Next, Hind, Hind Vadodara, sans-serif"
    fontSize: "34px"
    fontWeight: 800
    lineHeight: 1
    letterSpacing: "-0.005em"
  headline:
    fontFamily: "Sofia Sans Condensed, Atkinson Hyperlegible Next, Hind, Hind Vadodara, sans-serif"
    fontSize: "23px"
    fontWeight: 800
    lineHeight: 1
    letterSpacing: "0"
  title:
    fontFamily: "Sofia Sans Condensed, Atkinson Hyperlegible Next, Hind, Hind Vadodara, sans-serif"
    fontSize: "20px"
    fontWeight: 800
    lineHeight: 1
    letterSpacing: "0.005em"
  figure:
    fontFamily: "Sofia Sans Condensed, Atkinson Hyperlegible Next, sans-serif"
    fontSize: "40px"
    fontWeight: 700
    lineHeight: 1
    fontFeature: "tnum"
  figure-row:
    fontFamily: "Sofia Sans Condensed, Atkinson Hyperlegible Next, sans-serif"
    fontSize: "22px"
    fontWeight: 700
    lineHeight: 1
    fontFeature: "tnum"
  body:
    fontFamily: "Atkinson Hyperlegible Next, Hind, Hind Vadodara, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
    fontFeature: "tnum"
  body-strong:
    fontFamily: "Atkinson Hyperlegible Next, Hind, Hind Vadodara, system-ui, sans-serif"
    fontSize: "13.5px"
    fontWeight: 700
    lineHeight: 1.25
  label:
    fontFamily: "Atkinson Hyperlegible Next, Hind, Hind Vadodara, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "normal"
  data:
    fontFamily: "Red Hat Mono, ui-monospace, SF Mono, monospace"
    fontSize: "14.5px"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "0.01em"
    fontFeature: "tnum"
  plate:
    fontFamily: "Red Hat Mono, ui-monospace, SF Mono, monospace"
    fontSize: "15px"
    fontWeight: 600
    lineHeight: 1.1
    letterSpacing: "0.06em"
  plate-pass:
    fontFamily: "Red Hat Mono, ui-monospace, SF Mono, monospace"
    fontSize: "46px"
    fontWeight: 600
    lineHeight: 1
    letterSpacing: "0.06em"
rounded:
  glyph: "2px"
  ref: "5px"
  sm: "6px"
  control-sm: "8px"
  md: "10px"
  menu: "12px"
  lg: "14px"
  xl: "16px"
  pill: "999px"
spacing:
  hair: "2px"
  xs: "6px"
  sm: "8px"
  md: "12px"
  stack: "14px"
  inset: "16px"
  pass-inset: "18px"
  gutter: "20px"
  gutter-phone: "14px"
components:
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper-panel}"
    typography: "{typography.body-strong}"
    rounded: "{rounded.md}"
    padding: "0 14px"
    height: "36px"
  button-primary-hover:
    backgroundColor: "{colors.ink-hover}"
    textColor: "{colors.paper-panel}"
  button-secondary:
    backgroundColor: "{colors.paper-panel}"
    textColor: "{colors.ink}"
    typography: "{typography.body-strong}"
    rounded: "{rounded.md}"
    padding: "0 14px"
    height: "36px"
  button-secondary-hover:
    backgroundColor: "{colors.paper-inset}"
    textColor: "{colors.ink}"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.ink-secondary}"
    typography: "{typography.body-strong}"
    rounded: "{rounded.md}"
    padding: "0 14px"
    height: "36px"
  button-small:
    rounded: "{rounded.control-sm}"
    padding: "0 10px"
    height: "30px"
  button-pass-action:
    height: "42px"
    rounded: "{rounded.md}"
  field:
    backgroundColor: "{colors.paper-panel}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.md}"
    padding: "0 12px"
    height: "42px"
  field-plate:
    backgroundColor: "{colors.paper-panel}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "0 12px"
    height: "42px"
  plate-search:
    backgroundColor: "{colors.paper-inset}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    height: "34px"
    width: "340px"
  segmented-control:
    backgroundColor: "{colors.paper-panel}"
    rounded: "{rounded.md}"
    padding: "3px"
  segmented-control-active:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper-panel}"
    rounded: "7px"
    height: "30px"
  top-bar:
    backgroundColor: "{colors.chrome}"
    textColor: "{colors.on-chrome}"
    height: "44px"
  nav-row:
    backgroundColor: "{colors.paper-panel}"
    textColor: "{colors.ink-secondary}"
    height: "48px"
  nav-link-active:
    textColor: "{colors.ink}"
  count-pill:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper-panel}"
    rounded: "{rounded.pill}"
    padding: "3px 6px"
  board:
    backgroundColor: "{colors.paper-panel}"
    rounded: "{rounded.lg}"
  board-row:
    backgroundColor: "{colors.paper-panel}"
    textColor: "{colors.ink}"
    height: "58px"
  board-row-lit:
    backgroundColor: "{colors.signal-tint}"
    textColor: "{colors.ink}"
  lamp-cell-lit:
    backgroundColor: "{colors.signal-amber}"
    textColor: "{colors.on-signal}"
    width: "78px"
  netline:
    backgroundColor: "{colors.paper-panel}"
    textColor: "{colors.ink-secondary}"
    rounded: "{rounded.md}"
    height: "38px"
  sighting-pass:
    backgroundColor: "{colors.paper-panel}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
  sighting-pass-head:
    backgroundColor: "{colors.chrome}"
    textColor: "{colors.on-chrome}"
    typography: "{typography.title}"
    height: "46px"
    padding: "0 16px"
  chip-new:
    backgroundColor: "{colors.signal-amber}"
    textColor: "{colors.on-signal}"
    rounded: "{rounded.sm}"
    height: "26px"
    padding: "0 10px 0 8px"
  priority-critical:
    backgroundColor: "{colors.critical-fill}"
    textColor: "#ffffff"
    rounded: "{rounded.sm}"
    height: "24px"
    padding: "0 9px"
  priority-high:
    backgroundColor: "{colors.caution-ochre}"
    textColor: "{colors.paper-panel}"
    rounded: "{rounded.sm}"
    height: "24px"
    padding: "0 9px"
  priority-quiet:
    backgroundColor: "transparent"
    textColor: "{colors.ink-secondary}"
    rounded: "{rounded.sm}"
    height: "24px"
    padding: "0 9px"
  state-badge:
    backgroundColor: "{colors.paper-panel}"
    textColor: "{colors.ink-secondary}"
    rounded: "{rounded.pill}"
    height: "22px"
    padding: "0 8px"
  reference-stub:
    textColor: "{colors.ink}"
    typography: "{typography.plate}"
    rounded: "{rounded.ref}"
    padding: "4px 7px"
---

# Design System: Sentinel

## Overview

**Creative North Star: "The Departures Gate Board"**

Sentinel's operator console reads like the board above an airport gate, rebuilt for vehicles. Anything that needs a person is a ranked row on a ruled board, sorted by priority and then by camera time. A row that changed moves into place and stays lit in signal amber until someone acknowledges it. When an operator picks a vehicle, it opens on the right as a sighting pass: a boarding-pass-shaped card cut into segments by dotted perforations, ending in a stub that carries the watchlist reference and the three decisions (Acknowledge, Investigate, Seal clip). Scale works the same way at every level. State, district, camera and vehicle all appear as the same board form, and each drill-down opens inside its parent row.

The world is paper and ink: paper-white panels on a cool, slightly grey ground, ink-black rules, and column grids with a heavier ink rule under each header. Colour is held back on purpose. Amber appears only for change nobody has seen yet. Red appears only beside the words Critical, Down or an error message. Green appears only as the Live dot. Unknown always shows as a hatched grey patch next to its word, so it never passes for healthy. Type uses three voices: a condensed industrial display face for titles and figures, a highly legible face for every word, and a monospace for machine-read data. Density is control-room density, with 48–58px rows, 12px cell padding and tabular figures everywhere. It stays calm because only one thing is ever lit.

The system rejects the KPI-card + map + feed dashboard. Summary numbers sit in one ruled strip (the netline) rather than a row of cards, the map is a tool inside Find a Vehicle rather than the home screen, and the home view is a queue of things that need a person, not a stream. Dark is the unthemed CSS default for dark control rooms. New sessions open in light, and a saved preference is respected.

**Key Characteristics:**
- Ranked board rows sorted by priority, then camera time. Time-unknown rows sink below the others and carry a dashed reason strip.
- One signal colour (amber) that means only "not yet acknowledged".
- Status is always a glyph plus a word, never colour alone.
- Condensed display for titles and figures, Atkinson Hyperlegible Next for words, Red Hat Mono for data only.
- The selected vehicle opens as a perforated sighting pass, the only lifted object on the page.
- An ink-black chrome strip on top and a paper nav row below it. On phones the nav moves to a bottom bar.

## Colors

Ink and paper carry the whole system. Each remaining hue has exactly one job and appears only next to its word.

### Primary
- **Gate Ink** (`ink`): the action colour as well as the text colour. Primary buttons, the active segment, the count pill, the active nav underline, header rules (1.5px) and the selected-row outline (2px) are all ink. The system has no brand hue. Hover lifts to **Ink Lift** (`ink-hover`).
- **Signal Amber** (`signal-amber`): a lit, unseen change. Used for the lamp cell of a new board row, the `New` chip on the pass head, and the "Lit = not yet acknowledged" key. Text on it is always `on-signal` ink. In light theme a lit row also gets **Signal Wash** (`signal-tint`, hover `signal-tint-hover`), an **Amber Seam** (`signal-rule`) under it, and **Amber Ink** (`signal-ink`) for its muted text.

### Secondary
- **Critical Red** (`critical-fill`): the filled `Critical` priority tag, the Down cross glyph, and down segments in the camera mix bar. **Critical Ink** (`critical-ink`; dark `dark-critical-ink`) is the text form, used for the word Down and for error lines. **Danger Fill** (`danger-fill`) is reserved for destructive buttons.
- **Caution Ochre** (`caution-ochre`; dark `dark-caution-ochre`): the Degraded triangle, the outlined Stale square, and the `High` priority tag. This is a separate token from Signal Amber. A degraded camera is not new.
- **Live Green** (`live-green`; dark `dark-live-green`): the Live dot only.
- **Connecting Blue** (`info-blue`; dark `dark-info-blue`): Medium severity and the connecting state. Used sparingly.

### Neutral
- **Cool Ground** (`cool-ground`): the page behind every board. Light theme.
- **Paper Panel** (`paper-panel`): boards, pass, nav row, fields, secondary buttons.
- **Paper Inset** (`paper-inset`) / **Paper Overlay** (`paper-overlay`): row hover, the plate-search well, open drill-down rows, table heads.
- **Hairline Rule** (`rule`) and **Strong Rule** (`rule-strong`): 1px row dividers and the borders of fields, buttons and badges.
- **Ink Secondary** (`ink-secondary`) and **Ink Muted** (`ink-muted`): body copy, column heads, labels, units.
- **Chrome** (`chrome`; dark `dark-chrome`): the top strip and the sighting-pass head. Text on chrome is `on-chrome` and `on-chrome-muted`.
- **Hatch** (`hatch-line` on `hatch-ground`; dark `dark-hatch-ground`): a 135° stripe (1.5px line, 4px period) that marks Unknown.
- **Evidence Black** (`evidence-black`): the frame behind evidence stills.
- **Dark room set** (`dark-ground`, `dark-panel`, `dark-inset`, `dark-hover`, `dark-rule`, `dark-rule-strong`, `dark-ink*`): the same roles at control-room luminance. In dark, the pass sits on `dark-pass` so it reads as lifted without a bright edge.

### Named Rules
**The Unseen-Only Amber Rule.** Signal amber means "changed and not yet acknowledged", and nothing else. It is not used for warnings, hovers, focus, brand or decoration. In dark rooms, amber stays to the lamp cell and a 1px amber outline. The whole row is never filled.

**The Word-Beside-Red Rule.** Red appears only directly beside the word Critical, Down or a stated error. Green appears only as the Live dot. If a coloured mark has no word next to it, it is wrong.

**The Hatched Unknown Rule.** Unknown, unavailable or unreadable data is shown as the grey hatch next to its word. It is never shown as green, empty or zero.

## Typography

**Display Font:** Sofia Sans Condensed (500–800, self-hosted woff2), falling back to Atkinson Hyperlegible Next
**Body Font:** Atkinson Hyperlegible Next (400–700, self-hosted), with Hind (Devanagari) and Hind Vadodara (Gujarati) in the stack and promoted by `:lang(hi)` / `:lang(gu)`
**Label/Mono Font:** Red Hat Mono (400–700, self-hosted), falling back to ui-monospace

**Character:** The condensed industrial face sets gate-board figures and board titles with the height of a departures display. Atkinson keeps every word readable in three scripts under pressure. The mono marks anything a machine read, so an operator can tell a plate from prose at a glance.

### Hierarchy
- **Display** (800, 34px, line-height 1): page titles ("Operations overview"), with the Gujarati/Hindi alternate names in muted 14px beside them. 28px on phones. Start-state headings use 36px.
- **Headline** (800, 23px, 1): board titles ("Watchlist board", "Detections"). Smaller boards use 20px.
- **Title** (800, 20px, 1): the "Sighting pass" head and section headings inside workspaces.
- **Figure** (700, 40px, 1, tabular): read confidence on the pass. Hits and sightings on the pass use 30px. Tallies and numeric board cells use **Figure-row** (700, 22px). The netline uses 19px and the clock 22px.
- **Body** (400, 14px, 1.5): running UI copy. Long explanatory copy uses line-height 1.7 and a measure of 52–65ch.
- **Body-strong** (700, 13.5px): buttons, status words (13px), netline lead cells. Nav links are 600 at 14px, and the current link is 800.
- **Label** (700, 12px, 1.2, sentence case, muted): pass cell labels ("Camera", "Last seen"). Column heads are 700 at 12.5px, muted, and sit on a 1.5px ink rule.
- **Data** (Red Hat Mono 600, 14.5px): camera times. Dates and camera ids use mono 500 at 12px. References use mono 500 at 12.5px.
- **Plate** (Red Hat Mono 600, 15px, +0.06em): plates in rows. 20px for emphasis, 46px on the pass (32px on phones). Plate inputs are mono 600 at 16px, +0.08em, uppercase.

### Named Rules
**The Three Voices Rule.** Condensed display is for titles and figures. Atkinson is for words. Red Hat Mono is only for data a machine produced or reads: plates, camera ids, camera times, references, keys. Mono must never set a label or a sentence.

**The Sentence-Case Label Rule.** Labels and column heads are bold, small, muted and in sentence case, with normal tracking. Table heads explicitly reset `text-transform` and `letter-spacing`. The system has no uppercase kickers.

**The Tabular Everything Rule.** Every element uses `tabular-nums`, so columns of times and counts line up like a departures board.

## Layout

- **Shell.** A four-row grid filling `100dvh`: a 44px chrome strip (brand, jurisdiction select, scope note, clock bracketed by hairlines, language, sound, theme), then a 48px paper nav row (links with icons, a 340px plate search pushed right, a ⌘K key), then scrolling content, then a 34px account footer. The page gutter is 20px (14px on phones).
- **Page head.** The display title and alternate-script names sit on one baseline, with a muted 13px lede (max 80ch) below and page actions aligned right.
- **First viewport (Overview).** A netline strip, then a 62/38 split (`minmax(0,62fr) minmax(0,38fr)`, 20px gap). The left stack holds the watchlist board, capped with a "Showing n of m" footer, then a two-up row of Detections and Cameras by district. The right stack holds the plate-trace board, then the sighting pass. Stacks use a 14px gap.
- **Board grid.** Each board defines its columns with a `--cols` template. The vehicle board uses 78 / 124 / 116 / flexible ≥150 / 48 / 92 / 82 / 136px. Numbers are right-aligned. Rows are 48px by default and 58px for vehicle rows, with 12px horizontal cell padding. Drill-down rows indent 36px into a lighter tray.
- **Find a Vehicle.** A sticky query toolbar, then a result grid with the map and evidence on one side and a calling-points timeline on the other. The timeline is a 2px ink rail with numbered stops.
- **Responsive.** Up to 1199px the scope note and footer note hide and nav padding tightens. Up to 1023px nav icons drop. Up to 1100px the split collapses to one column, and on Overview it reorders to trace → board → pass → lower boards. Up to 767px the nav row becomes a full-width plate search, a five-slot bottom bar (52px targets, safe-area padding) and a "More" sheet replace the links, the footer hides, each vehicle row becomes a three-line strip (lamp column 64px, then plate/priority, camera/hits, time/action), the netline becomes a 2-column grid, and the pass grid drops from 4 to 2 columns.

### Named Rules
**The Ranked Row Rule.** Anything that needs a person is a row on a board, ordered by priority and then camera time. A row with no trustworthy time sinks below the timed rows and says why. It does not disappear.

## Elevation & Depth

Depth comes from tone and rules. Boards, netline, fields and nav are flat: paper on cool ground with a 1px rule. The sighting pass is the one object that lifts (`shadow-3`), together with transient popovers (menus, the phone "More" sheet). Focus never uses elevation. It uses a 2px ink outline offset 3px, and fields add a 3px soft ink ring.

### Shadow Vocabulary
- **Lift** (light `0 1px 2px rgb(17 20 23 / 0.06), 0 18px 36px -18px rgb(17 20 23 / 0.28)`; dark `0 18px 36px -18px rgb(0 0 0 / 0.6)`): the sighting pass only.
- **Pop** (light `0 2px 4px rgb(17 20 23 / .06), 0 16px 32px -8px rgb(17 20 23 / .22)`; dark `0 2px 4px rgb(0 0 0 / .2), 0 16px 32px -8px rgb(0 0 0 / .5)`): menus and the phone More sheet.
- **Focus ring** (`0 0 0 3px rgb(17 20 23 / .10)`; dark `rgb(238 240 236 / .18)`): fields and plate search when focused.

### Named Rules
**The One Lifted Object Rule.** Only the open sighting pass casts a resting shadow. Boards stay flat and ruled. If two things on a screen float, one of them is wrong.

## Shapes

The geometry is soft-cornered, ruled and gridded. Boards and the pass use 14px corners. Controls, fields and the netline use 10px. Small buttons use 8px, segment pills 7px, and priority tags and the New chip 6px. Pills (999px) are kept for counts and state badges. Rows inside a board are square-cornered and divided by hairlines. Header rows sit on a 1.5px ink rule, and the selected row gets a 2px inset ink outline. Dashed outlines mean "explanation, not data": the time-unknown reason strip, the history note, empty states.

Status glyphs are a small, strict vocabulary at 10px. Live is a filled green dot. Down is a red cross mask. Degraded is an ochre triangle (clip-path). Stale is a square outlined in ochre (2px inset). Unknown is a hatched square with a 2px corner. Connecting/idle is a hollow ring. The board lamp is an 11px ring that fills ink, with a white halo, when lit.

### Named Rules
**The Perforation Rule.** The sighting pass is divided by perforations: a 2px dotted rule inset 14px, with half-circle notches cut in the ground colour at both edges. Perforations separate the plate block, the fact grid and the stub. Only the pass is perforated.

## Components

### Buttons
Buttons are inked, plain and firm, and press 1px down on `:active`.
- **Shape:** gently rounded (10px). Small buttons use 8px.
- **Primary:** ink fill, paper text, 700 at 13.5px, 36px high, 14px horizontal padding. Hover moves to Ink Lift. A screen has at most one primary, usually the pass's Acknowledge.
- **Secondary:** paper fill with a strong-rule border. On hover the fill turns paper-inset and the border turns ink.
- **Ghost:** no border, ink-secondary text. On hover it gains the inset fill and a hairline. Rows use ghost "Open ›" once a vehicle has been acknowledged.
- **Sizes:** small is 30px (row actions), the pass action grid is 42px (auto-fit, min 128px), the field row is 42px. Disabled buttons drop to 50% opacity.
- **Icons:** 16px Lucide line icons lead the label. The label is always present.

### Chips / Tags
- **New chip:** signal amber, 26px, ink dot with "New". Appears only on the pass head of an unseen vehicle.
- **Priority tag:** a 24px square-ish tag. Critical is filled red with white text. High is filled ochre. Medium and Low are outlined in ink-secondary.
- **State badge:** a 22px pill with a strong-rule outline ("Working", "Closed").
- **Count pill:** ink with paper mono 700 text at 11.5px, on the Alerts nav link.
- **Reference stub:** the watchlist id split at its hyphens into mono 13px boxes with a strong-rule border, set like a ticket serial.

### Cards / Containers
- **Corner Style:** 14px boards. The interior is ruled, never carded.
- **Background:** paper panel on cool ground.
- **Shadow Strategy:** flat (see Elevation). The pass is the exception.
- **Border:** 1px hairline. The header bottom is a 1.5px ink rule.
- **Internal Padding:** board top 12px/16px (min-height 52px). Cells use 12px horizontal. Footers are 38px tall.

### Inputs / Fields
- **Style:** 42px, paper fill, strong-rule border, 10px corners, leading 16px icon. Plate fields use mono 600 at 16px, +0.08em, uppercase, including the placeholder ("GJ 01 AB 1234").
- **Hover / Focus:** on hover the border goes to ink-secondary. On focus the border goes to ink with a 3px soft ring. The nav plate search is a 34px inset well that turns paper on focus.
- **Native selects:** an appearance-reset chevron, 34–36px.

### Navigation
- **Top strip:** chrome background, condensed 21px wordmark beside a square mark, an outlined jurisdiction select ("Jurisdiction **Gujarat · all districts**"), and the clock as a 22px condensed time plus a 12px zone, bracketed by translucent hairlines.
- **Nav row:** 600 at 14px ink-secondary links with muted 16px icons. On hover the text turns ink and an inset wash appears. The current link is 800 ink with a 3px ink underline that has rounded top corners.
- **Phone:** a five-slot bottom bar (Overview, Live Wall, Find, Alerts, More) with 12px labels. The current slot is ink 800 on an inset wash. The count pill floats on the icon.
- **Segmented control:** a 3px-padded rail with a strong-rule border. The active segment is ink-filled. Mono counts sit inside segments.

### Watchlist Board (signature)
There is one row per vehicle, never one row per hit. Columns are Status lamp, Last seen (IST, camera clock), Plate (mono), Camera (name and id), Hits, Times seen, Priority and Action. A lit row has an amber lamp cell reading "New", a signal-wash body, an amber seam beneath it, and an inline small Acknowledge button. Once acknowledged it goes dark and its action becomes a ghost "Open". The selected row gets a 2px ink outline. A time-unknown row shows a clock icon and "Time unknown", a dashed top rule, and a full-width dashed reason strip with a "Check camN in Cameras" link. **Motion:** arrivals slide in 12px from above over 550ms on `cubic-bezier(0.16,1,0.3,1)`, then the lamp cell fills from paper to amber over 900ms. Rows move. They never blink. All motion is off under `prefers-reduced-motion`.

### Sighting Pass (signature)
The pass has a chrome head ("Sighting pass", kind, a New chip or state badge), then a plate block (46px mono plate on the left, 40px confidence figure on the right). The detailed variant adds a 16:9 evidence frame with a mono caption. After a perforation comes a 2-up grid (Camera with status word, Last seen with "From the camera's own clock"), then a 4-up grid (Hits, Times seen, Match, Priority) with ruled cells. A second perforation leads to the stub: watchlist reference, then the action grid (Acknowledge primary, Investigate, Seal clip), with a quiet "Open in Alerts" or "Not this vehicle" link below. Seal clip progresses through Seal clip → Sealing… → Watch sealed clip.

### District Board
District rows use the same board form: worst state as a status word, camera count, live, down and unknown columns, and a 8px **mix bar** of 2px-gapped segments (down red, degraded ochre, stale ochre-outlined, live green, unknown hatched). Rows expand inline into a camera drill-down tray.

### Netline
A single ruled strip replaces KPI cards. The lead cell is bold ink. Each following cell is a condensed 19px figure plus its word and glyph, divided by hairlines. Quiet secondary facts are muted 12.5px.

## Do's and Don'ts

### Do:
- **Do** put every item that needs a person on a board row ordered by priority, then camera time. Group vehicles one row per plate and cap the board with a "Showing n of m" footer.
- **Do** keep a changed row lit (amber lamp cell + signal wash) until it is acknowledged, and let it slide into place rather than flash.
- **Do** pair every status colour with its glyph and word: Live green dot, Degraded ochre triangle, Stale ochre-outlined square, Down red cross, Unknown hatched grey, Connecting hollow ring.
- **Do** set plates, camera ids, camera times and references in Red Hat Mono with tabular figures. Set titles and figures in Sofia Sans Condensed and everything else in Atkinson Hyperlegible Next.
- **Do** say when data is missing: "Time unknown — Camera clock unreadable", match confidence as a percentage, "From the camera's own clock".
- **Do** make the open sighting pass the only lifted surface, and separate its segments with perforations.
- **Do** use ink for primary actions and selection. Use a 2px ink focus outline offset 3px.
- **Do** ship both themes from the same tokens. Dark is the CSS default for control rooms. New sessions open light.

### Don't:
- **Don't** build a KPI-card row, a map-first home or a live feed as the overview. Summaries go in the netline, and the map belongs in Find a Vehicle.
- **Don't** use signal amber for anything except unseen change: no warnings, hovers, brand marks, map markers or decorative icons.
- **Don't** fill a whole row with amber in dark theme. Use the lamp cell and a 1px amber outline.
- **Don't** put red anywhere it isn't beside Critical, Down or a stated error. Don't show Unknown as green, blank or zero.
- **Don't** use mono for labels or prose, or uppercase-tracked kickers for labels.
- **Don't** give boards or rows resting shadows, or wrap board rows in cards.
- **Don't** reintroduce a brand hue (navy rail, cobalt actions). The action colour is ink.
