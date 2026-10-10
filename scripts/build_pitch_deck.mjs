/**
 * Builds the grand-finale pitch deck: docs/Sentinel-Finale-Pitch.pptx.
 *
 * This is the deck for the 20-minute on-site evaluation (docs/13-SHOWCASE-PREP.md
 * §4–§9), not the written submission deck (scripts/build_deck.mjs). It follows
 * the run of show: problem, approach, the live demo, then scale and cost.
 *
 * Generated, so it cannot drift from what it cites: every number comes from a
 * document or measurement in this repository, and every screenshot is the
 * real console, captured from a live stack into docs/images/pitch/ with
 *   SHOT_PLATE=GJ39C8018 SHOT_OUT_DIR=../../docs/images/pitch npm run screenshots
 * (from apps/web). Speaker notes carry the pitch script.
 *
 * Usage:
 *   NODE_PATH=$(npm root -g) node scripts/build_pitch_deck.mjs
 *   make pitch
 */

import { createRequire } from 'node:module'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
const PptxGenJS = require('pptxgenjs')
const React = require('react')
const { renderToStaticMarkup } = require('react-dom/server')
const sharp = require('sharp')
const Lu = require('react-icons/lu')

const HERE = dirname(fileURLToPath(import.meta.url))
const REPO = resolve(HERE, '..')
const SHOT = (name) => resolve(REPO, 'docs', 'images', 'pitch', `${name}.png`)
const OUT = resolve(REPO, 'docs', 'Sentinel-Finale-Pitch.pptx')

// Night-shift control room: deep ink ground, saffron as the one accent that
// carries attention, teal reserved for things we measured, coral for the
// numbers we refuse to pay. Dark throughout, matching the console's own theme.
const INK = '0A1020'
const PANEL = '131C30'
const PANEL_2 = '1B2742'
const LINE = '2C3A5C'
const TEXT = 'F2F5FA'
const MUTED = 'A9B6CB'
const SAFFRON = 'F5A524'
const TEAL = '34D3B4'
const CORAL = 'F2706B'

const H = 'Arial'
const B = 'Calibri'

const W = 13.333
const SLIDE_H = 7.5
const M = 0.6
const CW = W - 2 * M

const pres = new PptxGenJS()
pres.layout = 'LAYOUT_WIDE'
pres.author = 'Sentinel Platform'
pres.title = 'Sentinel — Gujarat Police Innovation Challenge 2026, Grand Finale'

// --- assets -----------------------------------------------------------------

const iconCache = new Map()

/** A Lucide icon (the console's own icon set) rendered to a PNG data URI. */
async function icon(name, color) {
  const key = `${name}:${color}`
  if (iconCache.has(key)) return iconCache.get(key)
  const Component = Lu[name]
  if (!Component) throw new Error(`no icon ${name}`)
  const svg = renderToStaticMarkup(
    React.createElement(Component, { size: 256, color: `#${color}`, strokeWidth: 1.75 }),
  )
  const png = await sharp(Buffer.from(svg)).resize(160, 160).png({ palette: true }).toBuffer()
  const data = `image/png;base64,${png.toString('base64')}`
  iconCache.set(key, data)
  return data
}

/** A region of a console screenshot, given in the 1600x1000 CSS-pixel
 * viewport it was captured at (scaled to whatever pixel density it has). */
async function crop(name, { x, y, w, h }) {
  const image = sharp(SHOT(name))
  const k = (await image.metadata()).width / 1600
  const png = await image
    .extract({ left: Math.round(x * k), top: Math.round(y * k), width: Math.round(w * k), height: Math.round(h * k) })
    // JPEG keeps the deck small enough to commit; at this quality the
    // console's text stays crisp at slide size.
    .jpeg({ quality: 80, mozjpeg: true })
    .toBuffer()
  return { data: `image/jpeg;base64,${png.toString('base64')}`, ratio: w / h }
}

// --- building blocks --------------------------------------------------------

let pageNumber = 0

/** Every content slide: ink ground, a saffron eyebrow, a large title, and a
 * quiet page number. The variation belongs in the body. */
function frame({ eyebrow, title, notes }) {
  pageNumber += 1
  const s = pres.addSlide()
  s.background = { color: INK }
  s.addText(eyebrow.toUpperCase(), {
    x: M, y: 0.42, w: CW, h: 0.3, margin: 0,
    fontFace: H, fontSize: 11, bold: true, color: SAFFRON, charSpacing: 3,
  })
  s.addText(title, {
    x: M, y: 0.74, w: CW, h: 0.8, margin: 0, valign: 'top',
    fontFace: H, fontSize: 32, bold: true, color: TEXT,
  })
  s.addText(String(pageNumber).padStart(2, '0'), {
    x: W - M - 0.6, y: SLIDE_H - 0.45, w: 0.6, h: 0.25, margin: 0, align: 'right',
    fontFace: H, fontSize: 9, color: MUTED,
  })
  if (notes) s.addNotes(notes)
  return s
}

function panel(s, x, y, w, h, fill = PANEL) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x, y, w, h, rectRadius: 0.12, fill: { color: fill }, line: { color: LINE, width: 0.75 },
  })
}

async function badge(s, name, x, y, d = 0.62, bg = SAFFRON, fg = INK) {
  s.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: bg }, line: { color: bg } })
  const pad = d * 0.22
  s.addImage({ data: await icon(name, fg), x: x + pad, y: y + pad, w: d - 2 * pad, h: d - 2 * pad })
}

/** A screenshot set in a framed panel with a soft shadow, sized to width. */
function screenshot(s, img, x, y, w) {
  const h = w / img.ratio
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: x - 0.06, y: y - 0.06, w: w + 0.12, h: h + 0.12, rectRadius: 0.1,
    fill: { color: PANEL_2 }, line: { color: LINE, width: 0.75 },
    shadow: { type: 'outer', color: '000000', blur: 18, offset: 6, angle: 90, opacity: 0.45 },
  })
  s.addImage({ data: img.data, x, y, w, h })
  return h
}

function text(s, value, opts) {
  s.addText(value, { margin: 0, fontFace: B, color: TEXT, valign: 'top', ...opts })
}

/** Icon-in-circle, bold header, muted body: the deck's repeated row. */
async function iconRow(s, { icon: name, title, body, x, y, w, color = SAFFRON }) {
  await badge(s, name, x, y, 0.56, color)
  text(s, title, { x: x + 0.78, y: y - 0.02, w: w - 0.78, h: 0.34, fontFace: H, fontSize: 15, bold: true })
  text(s, body, { x: x + 0.78, y: y + 0.33, w: w - 0.78, h: 0.62, fontSize: 13, color: MUTED })
}

// --- slides -------------------------------------------------------------------

async function titleSlide() {
  pageNumber += 1
  const s = pres.addSlide()
  s.background = { color: INK }
  const shot = await crop('05-find-a-vehicle', { x: 100, y: 255, w: 1500, h: 745 })
  const w = 6.25
  const h = w / shot.ratio
  const y = (SLIDE_H - h) / 2
  s.addImage({ data: shot.data, x: W - w, y, w, h })
  // Dim the screenshot so the title leads, without an edge stripe.
  s.addShape(pres.shapes.RECTANGLE, {
    x: W - w, y, w, h, fill: { color: INK, transparency: 72 }, line: { color: INK, transparency: 100 },
  })
  text(s, 'GUJARAT POLICE INNOVATION CHALLENGE 2026', {
    x: M, y: 1.2, w: 6.2, h: 0.3, fontFace: H, fontSize: 10.5, bold: true, color: SAFFRON, charSpacing: 2,
  })
  text(s, 'Sentinel', { x: M, y: 1.75, w: 6.2, h: 1.3, fontFace: H, fontSize: 72, bold: true })
  text(s, 'One search box for every government camera in Gujarat.', {
    x: M, y: 3.15, w: 5.9, h: 1.1, fontFace: H, fontSize: 26, color: TEXT,
  })
  text(s, 'Unified CCTV integration and AI video analytics: type a registration number, see where the vehicle went — camera by camera, on a map, with the evidence.', {
    x: M, y: 4.4, w: 5.7, h: 1.0, fontSize: 15, color: MUTED,
  })
  await badge(s, 'LuMapPin', M, 6.25, 0.42)
  text(s, 'Grand Finale  ·  i-Hub Gujarat, Ahmedabad  ·  12–13 October 2026', {
    x: M + 0.6, y: 6.33, w: 6, h: 0.3, fontSize: 13, color: MUTED,
  })
  s.addNotes(
    'Open with the problem, not the product. "Today, if a stolen car leaves Ahmedabad for Rajkot, tracing it means phone calls to several departments, each with its own CCTV system, its own viewer, its own retention. Sentinel turns that into one search box." If the jury gives the vehicle number now, go straight to the demo (slide 5) and come back.',
  )
}

async function problemSlide() {
  const s = frame({
    eyebrow: 'The problem',
    title: 'Twenty-six camera systems. No shared map.',
    notes: 'Twenty-six departments, about eighty thousand cameras, no shared map. Each department runs its own VMS with its own retention. Tracing one vehicle across them is phone calls and hours, not a search.',
  })
  const stats = [
    ['~80,000', 'cameras across the State', 'LuCamera'],
    ['26', 'departments, each with its own VMS', 'LuBuilding2'],
    ['7–15', 'days of retention, local or cloud, per department', 'LuHardDrive'],
    ['~1,000', 'km between the farthest camera sites', 'LuMap'],
  ]
  const cw = (CW - 3 * 0.3) / 4
  for (const [i, [value, label, ic]] of stats.entries()) {
    const x = M + i * (cw + 0.3)
    panel(s, x, 1.9, cw, 2.55)
    await badge(s, ic, x + 0.3, 2.15, 0.5)
    text(s, value, { x: x + 0.3, y: 2.85, w: cw - 0.6, h: 0.8, fontFace: H, fontSize: 38, bold: true, color: SAFFRON })
    text(s, label, { x: x + 0.3, y: 3.7, w: cw - 0.6, h: 0.6, fontSize: 14, color: MUTED })
  }
  panel(s, M, 4.85, CW, 1.65, PANEL_2)
  await badge(s, 'LuPhoneCall', M + 0.35, 5.33, 0.7, CORAL, INK)
  text(s, 'A stolen car leaves Ahmedabad for Rajkot.', {
    x: M + 1.3, y: 5.15, w: CW - 1.6, h: 0.45, fontFace: H, fontSize: 20, bold: true,
  })
  text(s, 'Tracing it today means phone calls to several departments — each with its own viewer, its own login and its own retention — while the footage ages out.', {
    x: M + 1.3, y: 5.62, w: CW - 1.6, h: 0.7, fontSize: 15, color: MUTED,
  })
}

async function approachSlide() {
  const s = frame({
    eyebrow: 'Our approach',
    title: 'A hybrid that leaves every department’s system running',
    notes: 'We chose a hybrid: Model 1’s registry and GIS as the foundation, Model 2’s unified viewing and analytics, Model 3’s adapter federation so no department changes its system — and Model 4’s central storage only for the few cameras that need it.',
  })
  const models = [
    ['Model 1', 'Registry & GIS', 'Every camera on one map, with coverage gaps and an ageing-asset work list.', 'LuMap', 'Foundation'],
    ['Model 2', 'Unified viewing & analytics', 'Live wall and ANPR on every accessible stream, in one console.', 'LuMonitor', 'Adopted'],
    ['Model 3', 'Federation adapters', 'RTSP, ONVIF, Hikvision and Dahua drivers — a driver, not a release.', 'LuNetwork', 'Adopted'],
    ['Model 4', 'Central recording', 'Only for critical cameras and alert clips; the rest stays where it is.', 'LuServer', 'Selective'],
  ]
  const cw = (CW - 3 * 0.3) / 4
  for (const [i, [tag, name, body, ic, pill]] of models.entries()) {
    const x = M + i * (cw + 0.3)
    const selective = pill === 'Selective'
    panel(s, x, 1.9, cw, 3.65, selective ? PANEL : PANEL_2)
    await badge(s, ic, x + 0.3, 2.2, 0.62, selective ? MUTED : SAFFRON)
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: x + cw - 1.45, y: 2.32, w: 1.15, h: 0.36, rectRadius: 0.18,
      fill: { color: selective ? PANEL_2 : SAFFRON }, line: { color: selective ? MUTED : SAFFRON, width: 0.75 },
    })
    text(s, pill, {
      x: x + cw - 1.45, y: 2.32, w: 1.15, h: 0.36, align: 'center', valign: 'middle',
      fontFace: H, fontSize: 11, bold: true, color: selective ? MUTED : INK,
    })
    text(s, tag.toUpperCase(), { x: x + 0.3, y: 3.1, w: cw - 0.6, h: 0.3, fontFace: H, fontSize: 11, bold: true, color: MUTED, charSpacing: 2 })
    text(s, name, { x: x + 0.3, y: 3.42, w: cw - 0.6, h: 0.75, fontFace: H, fontSize: 19, bold: true })
    text(s, body, { x: x + 0.3, y: 4.22, w: cw - 0.6, h: 1.2, fontSize: 14, color: MUTED })
  }
  await badge(s, 'LuShieldCheck', M, 5.95, 0.5, TEAL)
  text(s, 'Read-only and pull-based. Nothing is installed on a department’s cameras or VMS, and their own recording keeps running untouched.', {
    x: M + 0.7, y: 5.98, w: CW - 0.7, h: 0.6, fontSize: 16,
  })
}

async function refuseSlide() {
  const s = frame({
    eyebrow: 'The number we refuse to pay',
    title: 'Centralising 80,000 cameras is a physics problem',
    notes: 'Eighty thousand cameras at 2 Mbps is 160 gigabits per second sustained, from sites up to a thousand kilometres apart, and 12 petabytes of storage for one week. We analyse at the edge and send meaning, not video: about 140 megabits per second statewide — over a thousand times less.',
  })
  const rows = [
    ['Sustained backbone', '160 Gbps', '≈140 Mbps', '≈1,140× less'],
    ['Hot storage, one week', '12.1 PB', '≈390 TB', '≈31× less'],
    ['Capex, order of magnitude', '₹400 cr+', '≈₹80 cr', '≈5× less'],
  ]
  const colX = [M, M + 3.6, M + 6.85, M + 10.0]
  text(s, 'Central VMS (Model 4)', { x: colX[1], y: 1.85, w: 3, h: 0.35, fontFace: H, fontSize: 13, bold: true, color: CORAL })
  text(s, 'Sentinel, edge-first', { x: colX[2], y: 1.85, w: 3, h: 0.35, fontFace: H, fontSize: 13, bold: true, color: TEAL })
  for (const [i, [label, central, ours, ratio]] of rows.entries()) {
    const y = 2.35 + i * 1.32
    panel(s, M, y, CW, 1.12, i % 2 ? PANEL : PANEL_2)
    text(s, label, { x: colX[0] + 0.3, y: y + 0.36, w: 3.1, h: 0.45, fontFace: H, fontSize: 16, bold: true })
    text(s, central, { x: colX[1], y: y + 0.2, w: 3, h: 0.75, fontFace: H, fontSize: 34, bold: true, color: CORAL })
    text(s, ours, { x: colX[2], y: y + 0.2, w: 3, h: 0.75, fontFace: H, fontSize: 34, bold: true, color: TEAL })
    text(s, ratio, { x: colX[3], y: y + 0.36, w: 2.0, h: 0.45, fontFace: H, fontSize: 16, bold: true, color: SAFFRON, align: 'right' })
  }
  text(s, 'Video stays in the district where it was filmed. What travels is a 1 KB event and a 30 KB snapshot. Every figure re-derives from five formulas in our scale plan.', {
    x: M, y: 6.4, w: CW, h: 0.6, fontSize: 14, color: MUTED,
  })
}

async function demoSlide() {
  pageNumber += 1
  const s = pres.addSlide()
  s.background = { color: INK }
  text(s, 'LIVE DEMONSTRATION', { x: M, y: 0.9, w: CW, h: 0.35, fontFace: H, fontSize: 13, bold: true, color: SAFFRON, charSpacing: 4 })
  text(s, 'On today’s cameras, in front of you', { x: M, y: 1.3, w: CW, h: 0.9, fontFace: H, fontSize: 40, bold: true })
  const steps = [
    ['1', 'Onboard and see', 'Today’s cameras in the registry, on the map, on the live wall — and their health.', 'LuCamera'],
    ['2', 'Trace the vehicle', 'One registration number in; the timestamped route, the evidence and a signed report out.', 'LuRoute'],
    ['3', 'Alerts that find you', 'A watchlist hit lands on every open console the moment a confirmed read matches.', 'LuBellRing'],
  ]
  const cw = (CW - 2 * 0.4) / 3
  for (const [i, [n, title, body, ic]] of steps.entries()) {
    const x = M + i * (cw + 0.4)
    panel(s, x, 2.75, cw, 3.4)
    text(s, n, { x: x + 0.35, y: 2.95, w: 1.2, h: 1.2, fontFace: H, fontSize: 64, bold: true, color: SAFFRON })
    await badge(s, ic, x + cw - 1.05, 3.15, 0.7)
    text(s, title, { x: x + 0.35, y: 4.25, w: cw - 0.7, h: 0.5, fontFace: H, fontSize: 20, bold: true })
    text(s, body, { x: x + 0.35, y: 4.8, w: cw - 0.7, h: 1.2, fontSize: 15, color: MUTED })
  }
  text(s, 'If the venue network fails, we say which fallback we are on: our own cameras, then a recorded copy of the government grid.', {
    x: M, y: 6.5, w: CW, h: 0.4, fontSize: 13, color: MUTED, italic: true,
  })
  text(s, String(pageNumber).padStart(2, '0'), { x: W - M - 0.6, y: SLIDE_H - 0.45, w: 0.6, h: 0.25, fontFace: H, fontSize: 9, color: MUTED, align: 'right' })
  s.addNotes('Say what you will do before you do it. Narrator faces the jury; the driver only clicks. If the number was already given, run step 2 first.')
}

async function onboardSlide() {
  const s = frame({
    eyebrow: '1 · Onboard and see',
    title: 'Any camera, onboarded in minutes — without touching it',
    notes: 'These are the cameras we were given, onboarded from a CSV, ONVIF discovery or a catalogue. Each is in the registry with its department and location; Health shows each one live with its measured analysis rate; the live wall plays any of them — credentials never reach the browser.',
  })
  const shot = await crop('02-live-wall', { x: 400, y: 290, w: 1190, h: 710 })
  screenshot(s, shot, M + 0.06, 1.9, 6.9)
  const x = M + 7.45
  const w = CW - 7.45
  const rows = [
    ['LuFileSpreadsheet', 'Bulk CSV import', 'A dry run validates every row first; one bad row never blocks the rest.'],
    ['LuScanSearch', 'ONVIF and NVR discovery', 'Find a device’s streams and add them. Hikvision and Dahua drivers included.'],
    ['LuRefreshCw', 'Catalogue sync', 'A department endpoint keeps the registry current, with no restart.'],
    ['LuLock', 'One pull per camera', 'However many viewers. Stream credentials never reach a browser.'],
  ]
  for (const [i, [ic, title, body]] of rows.entries()) {
    await iconRow(s, { icon: ic, title, body, x, y: 1.95 + i * 1.18, w })
  }
}

async function traceSlide() {
  const s = frame({
    eyebrow: '2 · Trace the designated vehicle',
    title: 'One plate in. The route out.',
    notes: 'Type the number — spacing and case do not matter. Every read is searched, ordered by the cameras’ own clocks, and drawn as a route. Each stop: camera, department, the time printed on the frame, confidence, the plate as read, the snapshot with faces blurred. Then arm a watch, and export the Movement Report and hand it over.',
  })
  const shot = await crop('05-find-a-vehicle', { x: 100, y: 255, w: 1500, h: 745 })
  const h = screenshot(s, shot, M + 0.06, 1.75, 7.6)
  const x = M + 8.15
  const w = CW - 8.15
  const rows = [
    ['LuClock', 'The camera’s own clock', 'Every stop is timed by the clock burned into its evidence frame.'],
    ['LuTriangleAlert', 'Impossible travel flagged', 'A hop needing over 150 km/h is marked — a cloned plate, never a silent line.'],
    ['LuFileCheck', 'Movement Report', 'PDF and CSV in IST with a SHA-256 manifest, handed over on the spot.'],
  ]
  for (const [i, [ic, title, body]] of rows.entries()) {
    await iconRow(s, { icon: ic, title, body, x, y: 1.85 + i * 1.3, w })
  }
  text(s, 'Real console, recorded government footage: GJ39C8018 at Gandhidham, 8 Aug 2026, 21:10 — the time printed on the frame.', {
    x: M, y: 1.75 + h + 0.25, w: 7.7, h: 0.45, fontSize: 11, color: MUTED, italic: true,
  })
}

async function alertsSlide() {
  const s = frame({
    eyebrow: '3 · Alerts that find you',
    title: 'Every read, checked against the watchlist as it happens',
    notes: 'Watchlist correlation is continuous. A confirmed read is matched down a ladder — exact first, then OCR-ambiguity classes — and raises a prioritised, deduplicated alert on every open console, with a sound. Acknowledging or resolving it is audited. Registry adapters for VAHAN, SARTHI, eGujCop, AFIS and NAFIS are built against contract mocks: on the day access is granted, a configuration change.',
  })
  const shot = await crop('03-alerts', { x: 712, y: 262, w: 878, h: 600 })
  screenshot(s, shot, M + 0.06, 1.85, 5.6)
  const x = M + 6.2
  const w = CW - 6.2
  text(s, 'The matching ladder', { x, y: 1.85, w, h: 0.4, fontFace: H, fontSize: 18, bold: true })
  const rungs = [
    ['Exact', 'GJ01AB1234 = GJ01AB1234', TEAL],
    ['OCR-ambiguity class', '0↔O · 1↔I · 8↔B · 5↔S · 2↔Z', TEAL],
    ['One character away', 'Shown as probable, with the plate actually read', SAFFRON],
    ['Same tail, class and colour', 'Reachable at road speed — probable, officer confirms', SAFFRON],
  ]
  for (const [i, [name, body, color]] of rungs.entries()) {
    const y = 2.4 + i * 0.86
    panel(s, x, y, w, 0.72, PANEL)
    s.addShape(pres.shapes.OVAL, { x: x + 0.22, y: y + 0.22, w: 0.28, h: 0.28, fill: { color }, line: { color } })
    text(s, name, { x: x + 0.7, y: y + 0.1, w: 3.2, h: 0.5, fontFace: H, fontSize: 14, bold: true, valign: 'middle' })
    text(s, body, { x: x + 3.85, y: y + 0.1, w: w - 4.05, h: 0.5, fontSize: 12, color: MUTED, valign: 'middle' })
  }
  await iconRow(s, {
    icon: 'LuPlugZap', x, y: 6.0, w,
    title: 'VAHAN · SARTHI · eGujCop · AFIS · NAFIS',
    body: 'Adapters ready. A rejected credential raises — it never reads as “no record”.',
  })
}

async function unreadableSlide() {
  const s = frame({
    eyebrow: 'When the plate is hard to read',
    title: 'We never draw a hop we cannot defend',
    notes: 'When the plate is partly readable, the ladder recovers it and marks the hop as probable, never confirmed — an officer checks it against the snapshot. We already use vehicle class and colour plus road-speed feasibility to bridge gaps. Full appearance re-identification is designed and costed; it is not running today, and we say so.',
  })
  const cols = [
    ['LuScanLine', 'Recovered today', TEAL, [
      'OCR-ambiguity classes catch a misread like GJ1B67OS for GJ186705',
      'A one-character miss returns as a probable stop, plate shown',
      'Same tail, vehicle class and colour bridge a gap at road speed',
    ]],
    ['LuShieldCheck', 'Always checked', SAFFRON, [
      'Two sightings implying more than 150 km/h are flagged, not drawn',
      'Probable stops are dashed and amber; an officer confirms each on its frame',
      'Reads shorter than six characters are discarded — they match everything',
    ]],
    ['LuSparkles', 'Next: appearance ReID', MUTED, [
      'One embedding per vehicle track; matching within a reachable time window',
      'Designed and costed at about two days; off until calibrated on real footage',
      'Stated plainly: not running in today’s demonstration',
    ]],
  ]
  const cw = (CW - 2 * 0.3) / 3
  for (const [i, [ic, title, color, items]] of cols.entries()) {
    const x = M + i * (cw + 0.3)
    panel(s, x, 1.85, cw, 4.75, i === 2 ? PANEL : PANEL_2)
    await badge(s, ic, x + 0.35, 2.15, 0.62, color)
    text(s, title, { x: x + 1.15, y: 2.27, w: cw - 1.4, h: 0.45, fontFace: H, fontSize: 19, bold: true })
    s.addText(
      items.map((t, j) => ({ text: t, options: { bullet: { indent: 16 }, breakLine: j < items.length - 1 } })),
      { x: x + 0.35, y: 3.1, w: cw - 0.7, h: 3.3, margin: 0, fontFace: B, fontSize: 15, color: TEXT, valign: 'top', paraSpaceAfter: 12 },
    )
  }
}

async function evidenceSlide() {
  const s = frame({
    eyebrow: 'Evidence that holds up',
    title: 'The time on the frame is the time in the report',
    notes: 'A sighting is reported only with the clock the camera burned into its own frame, confirmed by a second reading. If that clock cannot be read, the sighting says “time unknown” — it stays searchable, but it is never given a time it does not have. Every search, export and reveal is in a hash-chained audit log; edit one row and verification fails. We do no face recognition: faces are detected only to be blurred.',
  })
  const shot = await crop('11-time-unknown', { x: 818, y: 422, w: 765, h: 520 })
  screenshot(s, shot, M + 6.95, 1.9, CW - 7.0)
  const items = [
    ['LuClock', 'The camera’s clock is the time', 'Confirmed by a second reading; unreadable means “time unknown”, never another clock.'],
    ['LuEyeOff', 'Faces blurred by default', 'Revealing an original needs a stated reason, and is logged.'],
    ['LuFingerprint', 'Hash-chained audit log', 'Every search, export and reveal. One edited row breaks verification.'],
    ['LuKeyRound', 'Scoped in the database', 'Department row-level security; private cameras only with live consent.'],
  ]
  for (const [i, [ic, title, body]] of items.entries()) {
    await iconRow(s, { icon: ic, title, body, x: M, y: 1.95 + i * 1.18, w: 6.4 })
  }
  text(s, 'A sighting whose clock cannot be read stays a sighting — off the timeline, clearly labelled.', {
    x: M + 6.95, y: 6.35, w: CW - 7.0, h: 0.5, fontSize: 11, color: MUTED, italic: true,
  })
}

async function beyondSlide() {
  const s = frame({
    eyebrow: 'Beyond number plates',
    title: 'More than plates — never identities',
    notes: 'Analytics beyond ANPR run on the same frames at no extra inference cost: class and colour, people counted, zone rules for intrusion, loitering, wrong-way and stopped vehicles, and camera tamper detection. Excluded by decision: face recognition.',
  })
  const tiles = [
    ['LuCar', 'Vehicle class', 'Car, motorcycle, bus, truck — on every read.'],
    ['LuPalette', 'Vehicle colour', 'Body colour attached to each sighting.'],
    ['LuUsers', 'People counted', 'Counted per camera and held to zones. Never identified.'],
    ['LuCrosshair', 'Zone intrusion', 'Intrusion and loitering zones on any camera, with dwell time.'],
    ['LuMoveHorizontal', 'Traffic rules', 'Wrong-way and stopped-vehicle rules per zone.'],
    ['LuCircleAlert', 'Camera tamper', 'Covered, blurred or moved — flagged on the camera.'],
  ]
  const cw = (CW - 2 * 0.3) / 3
  for (const [i, [ic, title, body]] of tiles.entries()) {
    const x = M + (i % 3) * (cw + 0.3)
    const y = 1.9 + Math.floor(i / 3) * 2.05
    panel(s, x, y, cw, 1.8, i % 2 ? PANEL : PANEL_2)
    await badge(s, ic, x + 0.3, y + 0.3, 0.6)
    text(s, title, { x: x + 1.1, y: y + 0.32, w: cw - 1.35, h: 0.45, fontFace: H, fontSize: 17, bold: true })
    text(s, body, { x: x + 1.1, y: y + 0.82, w: cw - 1.35, h: 0.8, fontSize: 14, color: MUTED })
  }
  await badge(s, 'LuEyeOff', M, 6.2, 0.46, TEAL)
  text(s, 'No face recognition, by decision. Faces are detected only so they can be blurred.', {
    x: M + 0.65, y: 6.27, w: CW - 0.65, h: 0.4, fontSize: 15,
  })
}

async function architectureSlide() {
  const s = frame({
    eyebrow: 'Architecture at 80,000 cameras',
    title: 'Analyse where it is filmed. Send meaning, not video.',
    notes: 'Five layers, one number each. Cameras, tiered. Department systems stay — we pull read-only. Each district decodes and analyses its own video; if its link drops it keeps reading plates and alerting locally for up to 72 hours. The state core is about search and storage, not throughput. What you saw today is the district layer on a laptop: the same code.',
  })
  const layers = [
    ['Consumers', 'Command centres · Field app · VAHAN · SARTHI · eGujCop · AFIS · NAFIS', 'REST · live events · scoped access', 'LuUsers', MUTED],
    ['State core  ·  HA + warm DR', 'Event bus → correlator → alerts · Postgres / PostGIS / Timescale', '≈563 events/s · ≈390 TB · RPO 15 min', 'LuDatabase', SAFFRON],
    ['District edge  ×34  (+ remote edge boxes)', 'Relay (one pull per camera) → decode → ANPR + analytics → 72 h queue', '≈560 GPUs · ≈140 Mbps uplink, statewide', 'LuCpu', SAFFRON],
    ['Department systems  ·  unchanged', 'Cameras, NVRs and VMS keep their own 7–15 day retention', 'Read-only RTSP / ONVIF / vendor SDK', 'LuBuilding2', MUTED],
    ['80,000 cameras, tiered', 'Continuous · sampled · motion-gated · view-only', 'A 12% · B 28% · C 35% · D 25%', 'LuCamera', MUTED],
  ]
  const top = 1.8
  const rowH = 0.82
  const gap = 0.2
  for (const [i, [name, body, metric, ic, color]] of layers.entries()) {
    const y = top + i * (rowH + gap)
    const accent = color === SAFFRON
    panel(s, M, y, CW, rowH, accent ? PANEL_2 : PANEL)
    await badge(s, ic, M + 0.2, y + 0.16, 0.5, color)
    text(s, name, { x: M + 0.9, y: y + 0.1, w: 4.6, h: 0.32, fontFace: H, fontSize: 15, bold: true })
    text(s, body, { x: M + 0.9, y: y + 0.44, w: 6.6, h: 0.32, fontSize: 12, color: MUTED })
    text(s, metric, {
      x: M + 7.6, y: y + 0.18, w: CW - 7.85, h: 0.46, fontFace: H, fontSize: 14, bold: true,
      color: accent ? SAFFRON : TEXT, align: 'right', valign: 'middle',
    })
    if (i < layers.length - 1) {
      s.addShape(pres.shapes.UP_ARROW, {
        x: M + 0.36, y: y + rowH + 0.01, w: 0.18, h: gap - 0.02, fill: { color: LINE }, line: { color: LINE },
      })
    }
  }
}

async function tieringSlide() {
  const s = frame({
    eyebrow: 'Compute sizing',
    title: 'Not every camera needs AI: tier them',
    notes: 'A highway check-post and a PDS godown are different jobs. Twelve percent run continuous ANPR; a quarter are view-only. Tier is a registry field a department changes live — a camera goes to tier A for a bandobast. That is about 560 L4 GPUs with redundancy, in about 140 four-GPU district servers. The per-GPU throughput is a benchmark estimate; Phase 0 measures it.',
  })
  s.addChart(pres.charts.DOUGHNUT, [{
    name: 'Cameras by tier',
    labels: ['A — continuous', 'B — sampled', 'C — motion-gated', 'D — view only'],
    values: [9600, 22400, 28000, 20000],
  }], {
    x: M, y: 1.75, w: 4.9, h: 4.9, holeSize: 58,
    chartColors: [SAFFRON, 'C98A2B', '7A6A4C', '3B4560'],
    showLegend: false, showValue: false, showPercent: true, showLabel: false,
    dataLabelColor: TEXT, dataLabelFontSize: 13, dataLabelFontFace: H, dataLabelFontBold: true,
    showTitle: false,
  })
  text(s, '80,000', { x: M + 1.45, y: 3.75, w: 2.0, h: 0.55, align: 'center', fontFace: H, fontSize: 28, bold: true })
  text(s, 'cameras', { x: M + 1.45, y: 4.28, w: 2.0, h: 0.35, align: 'center', fontSize: 13, color: MUTED })

  const x = M + 5.4
  const w = CW - 5.4
  const head = ['Tier', 'Cameras', 'Analysed', 'L4 GPUs']
  const colW = [2.4, 1.6, 1.6, w - 5.6]
  const rows = [
    ['A — continuous', '9,600', '10 fps', '320'],
    ['B — sampled', '22,400', '2 fps', '149'],
    ['C — motion-gated', '28,000', '~0.3 fps', '28'],
    ['D — view only', '20,000', '—', '0'],
  ]
  let cx = x
  for (const [j, h] of head.entries()) {
    text(s, h, { x: cx + 0.2, y: 1.85, w: colW[j] - 0.2, h: 0.3, fontFace: H, fontSize: 12, bold: true, color: MUTED, align: j ? 'right' : 'left' })
    cx += colW[j]
  }
  for (const [i, row] of rows.entries()) {
    const y = 2.25 + i * 0.62
    panel(s, x, y, w, 0.52, i % 2 ? PANEL : PANEL_2)
    cx = x
    for (const [j, v] of row.entries()) {
      text(s, v, { x: cx + 0.2, y: y + 0.1, w: colW[j] - 0.4, h: 0.34, fontSize: 14, bold: j === 0, align: j ? 'right' : 'left', valign: 'middle' })
      cx += colW[j]
    }
  }
  panel(s, x, 4.95, w, 1.55, PANEL_2)
  text(s, '≈560 L4 GPUs', { x: x + 0.3, y: 5.12, w: 3.6, h: 0.65, fontFace: H, fontSize: 32, bold: true, color: SAFFRON })
  text(s, 'with N+1 redundancy, in ≈140 four-GPU district servers; ≈1,500 Jetson boxes where backhaul is thin.', {
    x: x + 0.3, y: 5.8, w: w - 0.6, h: 0.6, fontSize: 13, color: MUTED,
  })
}

async function costSlide() {
  const s = frame({
    eyebrow: 'Impact on infrastructure cost',
    title: 'About one-fifth of the capex — by reusing what exists',
    notes: 'No camera, NVR or VMS is replaced; department retention is reused rather than re-stored; GSWAN carries the backhaul. Indicative figures for comparing architectures, not for tendering. Propose minutes-to-trace as the pilot KPI.',
  })
  s.addChart(pres.charts.BAR, [{
    name: 'Capex (₹ crore)',
    labels: ['Central VMS (Model 4)', 'Sentinel hybrid'],
    values: [400, 80],
  }], {
    x: M, y: 1.75, w: 6.3, h: 4.6, barDir: 'bar',
    chartColors: [CORAL, TEAL], varyColors: true,
    showValue: true, dataLabelPosition: 'outEnd', dataLabelColor: TEXT, dataLabelFontSize: 16, dataLabelFontBold: true, dataLabelFontFace: H,
    dataLabelFormatCode: '"₹"#,##0" cr"',
    catAxisLabelColor: TEXT, catAxisLabelFontSize: 14, catAxisLabelFontFace: H,
    valAxisHidden: true, valAxisMaxVal: 560, valGridLine: { style: 'none' }, catGridLine: { style: 'none' },
    catAxisLineShow: false, showLegend: false,
    showTitle: true, title: 'Capex, ₹ crore (order of magnitude)', titleColor: MUTED, titleFontSize: 13, titleFontFace: H,
  })
  const x = M + 6.75
  const w = CW - 6.75
  const stats = [
    ['≈₹10,000', 'capex per camera'],
    ['≈₹3,000', 'opex per camera, per year'],
    ['≈₹200 cr', 'five-year cost of ownership'],
    ['₹0', 'software licences — open-source stack'],
  ]
  for (const [i, [value, label]] of stats.entries()) {
    const y = 1.85 + i * 1.08
    panel(s, x, y, w, 0.92, i % 2 ? PANEL : PANEL_2)
    text(s, value, { x: x + 0.3, y: y + 0.14, w: 2.6, h: 0.64, fontFace: H, fontSize: 28, bold: true, color: TEAL, valign: 'middle' })
    text(s, label, { x: x + 2.95, y: y + 0.14, w: w - 3.2, h: 0.64, fontSize: 15, valign: 'middle' })
  }
  text(s, 'Reuse is the saving: no camera, NVR or VMS replaced; department retention reused, not re-stored; GSWAN for backhaul. Indicative, for comparing architectures.', {
    x: M, y: 6.45, w: CW, h: 0.55, fontSize: 12, color: MUTED,
  })
}

async function measuredSlide() {
  const s = frame({
    eyebrow: 'Measured, not claimed',
    title: 'What we measured — and what we did not',
    notes: 'Say “I measured that” and point at the artefact. The accuracy number is below our own target and we say so: it was 8.6% before the measurement drove the fixes. The GPU throughput behind the cost is a vendor estimate; Phase 0 replaces it with a measured one.',
  })
  const stats = [
    ['78%', 'exact plate after the multi-frame vote', '81 hand-labelled real government plates; 88% per character'],
    ['16 fps', 'analysed on one laptop CPU', 'End to end through the real worker, before falling behind'],
    ['616', 'automated tests passing', 'Plus 64 interface tests in three languages and two themes'],
    ['5.7 s', 'to restore 1 M detections', 'DR drill: backup, restore, audit chain re-verified, tamper caught'],
  ]
  const cw = (CW - 3 * 0.3) / 4
  for (const [i, [value, label, sub]] of stats.entries()) {
    const x = M + i * (cw + 0.3)
    panel(s, x, 1.85, cw, 2.75, PANEL_2)
    text(s, value, { x: x + 0.3, y: 2.05, w: cw - 0.6, h: 0.9, fontFace: H, fontSize: 44, bold: true, color: TEAL })
    text(s, label, { x: x + 0.3, y: 3.0, w: cw - 0.6, h: 0.6, fontFace: H, fontSize: 14, bold: true })
    text(s, sub, { x: x + 0.3, y: 3.62, w: cw - 0.6, h: 0.85, fontSize: 12, color: MUTED })
  }
  panel(s, M, 4.95, CW, 1.6)
  await badge(s, 'LuCircleAlert', M + 0.35, 5.2, 0.56, SAFFRON)
  text(s, 'Stated plainly', { x: M + 1.1, y: 5.2, w: 4, h: 0.4, fontFace: H, fontSize: 17, bold: true })
  s.addText([
    { text: 'ANPR is below our own 85% target', options: { bullet: { indent: 14 }, breakLine: true } },
    { text: 'GPU throughput (300 fps per L4) is a vendor estimate', options: { bullet: { indent: 14 } } },
  ], { x: M + 1.1, y: 5.65, w: 5.4, h: 0.8, margin: 0, fontFace: B, fontSize: 14, color: TEXT, paraSpaceAfter: 6 })
  s.addText([
    { text: 'Appearance ReID is designed, not built', options: { bullet: { indent: 14 }, breakLine: true } },
    { text: 'Face recognition is excluded by decision', options: { bullet: { indent: 14 } } },
  ], { x: M + 6.6, y: 5.65, w: 5.3, h: 0.8, margin: 0, fontFace: B, fontSize: 14, color: TEXT, paraSpaceAfter: 6 })
}

async function rolloutSlide() {
  const s = frame({
    eyebrow: 'Statewide rollout',
    title: 'Useful at 500 cameras. No big-bang cutover.',
    notes: 'This is useful at five hundred cameras and never needs a big-bang cutover: one district pilot in three months, then four districts, then statewide, then consented private cameras. Each phase is independently useful.',
  })
  const phases = [
    ['Phase 0', '0–3 months', '~500', 'cameras', '1 district, 2 departments', 'ANPR validated on live feeds; operator acceptance'],
    ['Phase 1', '3–9 months', '~5,000', 'cameras', '4 districts, 6 departments', 'Top three VMS vendors federated; VAHAN and eGujCop live; DR drill passed'],
    ['Phase 2', '9–21 months', '~30,000', 'cameras', 'All 34 districts, 15 departments', 'Statewide vehicle tracking; SOC/NOC in place'],
    ['Phase 3', '21–36 months', '80,000', 'cameras', 'Plus consented private cameras', 'Full coverage; policy and audit regime institutionalised'],
  ]
  const cw = (CW - 3 * 0.3) / 4
  s.addShape(pres.shapes.LINE, { x: M + 0.31, y: 2.12, w: CW - 0.62, h: 0, line: { color: LINE, width: 2 } })
  for (const [i, [name, when, count, unit, scope, exit]] of phases.entries()) {
    const x = M + i * (cw + 0.3)
    s.addShape(pres.shapes.OVAL, { x: x + 0.15, y: 1.96, w: 0.32, h: 0.32, fill: { color: SAFFRON }, line: { color: INK, width: 3 } })
    text(s, `${name}  ·  ${when}`, { x, y: 2.45, w: cw, h: 0.3, fontFace: H, fontSize: 12, bold: true, color: SAFFRON })
    panel(s, x, 2.9, cw, 3.55, i === 3 ? PANEL_2 : PANEL)
    text(s, count, { x: x + 0.3, y: 3.1, w: cw - 0.6, h: 0.75, fontFace: H, fontSize: 36, bold: true })
    text(s, unit, { x: x + 0.3, y: 3.82, w: cw - 0.6, h: 0.3, fontSize: 13, color: MUTED })
    text(s, scope, { x: x + 0.3, y: 4.3, w: cw - 0.6, h: 0.6, fontFace: H, fontSize: 14, bold: true })
    text(s, exit, { x: x + 0.3, y: 4.95, w: cw - 0.6, h: 1.3, fontSize: 13, color: MUTED })
  }
}

async function askSlide() {
  pageNumber += 1
  const s = pres.addSlide()
  s.background = { color: INK }
  text(s, 'WHAT WE NEED TO BEGIN', { x: M, y: 0.8, w: CW, h: 0.35, fontFace: H, fontSize: 13, bold: true, color: SAFFRON, charSpacing: 4 })
  text(s, 'Three things, and the pilot can start', { x: M, y: 1.2, w: CW, h: 0.85, fontFace: H, fontSize: 36, bold: true })
  const asks = [
    ['LuClipboardList', 'Department inventories', 'One template per department: camera, VMS and version, network, coordinates — and whether the feed carries a date-time overlay.'],
    ['LuLink', 'Read-only stream access', 'RTSP, ONVIF or the VMS’s own API. Nothing installed on department infrastructure.'],
    ['LuKeyRound', 'Registry API access', 'VAHAN, SARTHI, eGujCop, AFIS, NAFIS: on the day keys arrive, a configuration change, not a project.'],
  ]
  const cw = (CW - 2 * 0.35) / 3
  for (const [i, [ic, title, body]] of asks.entries()) {
    const x = M + i * (cw + 0.35)
    panel(s, x, 2.45, cw, 2.9)
    await badge(s, ic, x + 0.35, 2.75, 0.66)
    text(s, title, { x: x + 0.35, y: 3.6, w: cw - 0.7, h: 0.55, fontFace: H, fontSize: 18, bold: true })
    text(s, body, { x: x + 0.35, y: 4.18, w: cw - 0.7, h: 1.0, fontSize: 14, color: MUTED })
  }
  text(s, 'Type a plate. See where it went.', { x: M, y: 5.7, w: CW, h: 0.8, fontFace: H, fontSize: 34, bold: true, color: SAFFRON })
  text(s, 'Thank you — questions welcome.', { x: M, y: 6.5, w: CW, h: 0.45, fontSize: 18, color: MUTED })
  text(s, String(pageNumber).padStart(2, '0'), { x: W - M - 0.6, y: SLIDE_H - 0.45, w: 0.6, h: 0.25, fontFace: H, fontSize: 9, color: MUTED, align: 'right' })
  s.addNotes('Close on the ask, then the line. Hand over the Movement Report from the demo if it has not been handed over already. Questions: see docs/13-SHOWCASE-PREP.md §10.')
}

async function main() {
  await titleSlide()
  await problemSlide()
  await approachSlide()
  await refuseSlide()
  await demoSlide()
  await onboardSlide()
  await traceSlide()
  await alertsSlide()
  await unreadableSlide()
  await evidenceSlide()
  await beyondSlide()
  await architectureSlide()
  await tieringSlide()
  await costSlide()
  await measuredSlide()
  await rolloutSlide()
  await askSlide()
  await pres.writeFile({ fileName: OUT })
  console.log(`wrote ${OUT} (${pageNumber} slides)`)
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
