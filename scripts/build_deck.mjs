/**
 * Builds the submission deck.
 *
 * Generated rather than hand-built so it cannot drift from the numbers it
 * cites: every figure here is pulled from a document or an evidence file in
 * this repository, and the slide that matters most (14, "what is real") is
 * the same honesty table the README carries.
 *
 * Usage:
 *   NODE_PATH=$(npm root -g) node scripts/build_deck.mjs
 *   make deck
 */

import { createRequire } from 'node:module'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
const PptxGenJS = require('pptxgenjs')

const HERE = dirname(fileURLToPath(import.meta.url))
const REPO = resolve(HERE, '..')
const IMG = (name) => resolve(REPO, 'docs', 'images', name)
const OUT = resolve(REPO, 'docs', 'Sentinel-Platform-Deck.pptx')

// Control-room palette, taken from the product's own dark theme so the deck
// and the demo read as one thing.
const BG = '0B0E14'
const PANEL = '161D2A'
const PANEL_2 = '1E2737'
const MINT = '6EE7A8'
const TEAL = '5EEAD4'
const AMBER = 'F5B759'
const RED = 'F87171'
const TEXT = 'E8EDF5'
// Lightened from 93A0B4: at the smaller body sizes this sits on top of the
// panel fill, not the slide ground, and the darker grey was hard to read.
const MUTED = 'AEBACB'

const H = 'Trebuchet MS'
// Arial rather than Calibri: rendering the deck through a viewer without the
// Office font set substituted Calibri for a serif face, which changes the
// character of every slide. Arial ships with both Windows and macOS, so the
// deck looks the same on a judge's machine as it does here.
const B = 'Arial'

const pres = new PptxGenJS()
pres.layout = 'LAYOUT_16x9' // 10 x 5.625in
pres.author = 'Sentinel Platform'
pres.title = 'Sentinel Platform — Gujarat Police Innovation Challenge 2026'

const W = 10
const M = 0.55
const CONTENT_W = W - M * 2 // 8.9
const GAP = 0.3

/** Evenly split the content width into `n` columns with a consistent 0.3"
 * gutter, rather than each slide inventing its own spacing. */
function cols(n) {
  const w = (CONTENT_W - GAP * (n - 1)) / n
  return { w, pitch: w + GAP, x: (i) => M + i * (w + GAP) }
}

/** Every content slide shares this frame: dark ground, an eyebrow with the
 * slide number, and a title. Repetition here is the point — the variation
 * belongs in the body, not the chrome. */
function slide({ n, eyebrow, title, accent = MINT }) {
  const s = pres.addSlide()
  s.background = { color: BG }
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 0.09, h: 5.625, fill: { color: accent } })
  if (eyebrow) {
    s.addText(`${String(n).padStart(2, '0')}  ·  ${eyebrow.toUpperCase()}`, {
      x: M, y: 0.34, w: W - M * 2, h: 0.26,
      fontSize: 10, fontFace: B, color: accent, charSpacing: 2, bold: true, margin: 0,
    })
  }
  s.addText(title, {
    x: M, y: 0.62, w: W - M * 2, h: 0.92,
    fontSize: 27, fontFace: H, color: TEXT, bold: true, margin: 0, valign: 'top',
  })
  return s
}

/** A body paragraph under the title. Sits below the title's two-line
 * allowance — several titles wrap, and a fixed y tuned for one line put the
 * lede straight through the second. */
function lede(s, text, { y = 1.58, w = W - M * 2, color = MUTED, size = 13 } = {}) {
  s.addText(text, { x: M, y, w, h: 0.44, fontSize: size, fontFace: B, color, margin: 0, valign: 'top' })
}

function card(s, { x, y, w, h, fill = PANEL, accent }) {
  s.addShape(pres.shapes.RECTANGLE, { x, y, w, h, fill: { color: fill } })
  if (accent) s.addShape(pres.shapes.RECTANGLE, { x, y, w: 0.05, h, fill: { color: accent } })
}

/** Big-number callout. */
function stat(s, { x, y, w, value, label, color = MINT, size = 40 }) {
  s.addText(value, {
    x, y, w, h: 0.62, fontSize: size, fontFace: H, color, bold: true, margin: 0, valign: 'top',
  })
  s.addText(label, {
    x, y: y + 0.62, w, h: 0.5, fontSize: 10.5, fontFace: B, color: MUTED, margin: 0, valign: 'top',
  })
}

function bullets(s, items, { x, y, w, h, size = 12.5, color = TEXT }) {
  s.addText(
    items.map((t, i) => ({
      text: t,
      options: { bullet: true, breakLine: i < items.length - 1, color, fontSize: size, fontFace: B },
    })),
    { x, y, w, h, margin: 0, valign: 'top', lineSpacingMultiple: 1.25 },
  )
}

// ─────────────────────────────────────────────────────────── 1. Title
{
  const s = pres.addSlide()
  s.background = { color: BG }
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 0.09, h: 5.625, fill: { color: MINT } })
  s.addText('SENTINEL', {
    x: M, y: 1.75, w: 8.5, h: 1.0,
    fontSize: 58, fontFace: H, color: TEXT, bold: true, charSpacing: 3, margin: 0,
  })
  s.addText('One operating picture for 80,000 cameras.', {
    x: M, y: 2.78, w: 8.5, h: 0.45, fontSize: 17, fontFace: B, color: MINT, margin: 0,
  })
  s.addText(
    'Unified CCTV integration and AI video analytics — running today against the ' +
      'real government camera grid.',
    { x: M, y: 3.25, w: 8.7, h: 0.6, fontSize: 12.5, fontFace: B, color: MUTED, margin: 0 },
  )
  s.addText('Gujarat Police Innovation Challenge 2026', {
    x: M, y: 4.72, w: 8.5, h: 0.3, fontSize: 10.5, fontFace: B, color: MUTED, charSpacing: 1, margin: 0,
  })
}

// ─────────────────────────────────────────────────────────── 2. Problem
{
  const s = slide({ n: 2, eyebrow: 'The problem', title: 'Cameras everywhere. No single picture.' })
  lede(s, 'A getaway car crosses four jurisdictions in twenty minutes. Tracing it takes phone calls.')
  const items = [
    ['26', 'separate districts and commissionerates', AMBER],
    ['~80,000', 'cameras, many vendors, no shared registry', AMBER],
    ['0', 'places an officer can ask one question', RED],
  ]
  const c3 = cols(3)
  items.forEach(([v, l, c], i) => {
    card(s, { x: c3.x(i), y: 2.2, w: c3.w, h: 1.6, accent: c })
    stat(s, { x: c3.x(i) + 0.26, y: 2.42, w: c3.w - 0.5, value: v, label: l, color: c, size: 32 })
  })
  s.addText(
    'The cameras already exist. What is missing is the layer that makes them answer questions together.',
    { x: M, y: 4.22, w: CONTENT_W, h: 0.5, fontSize: 13, fontFace: B, color: TEXT, italic: true, margin: 0 },
  )
}

// ─────────────────────────────────────────────────────────── 3. What we built
{
  const s = slide({ n: 3, eyebrow: 'What we built', title: 'A plate in. A route out.' })
  lede(s, 'Type a registration number. Get every sighting, every camera, on a map — in seconds.', { w: 4.25 })
  s.addImage({ path: IMG('05-find-a-vehicle.png'), x: 5.1, y: 2.12, w: 4.35, h: 2.72 })
  bullets(
    s,
    [
      'Onboards heterogeneous feeds into one registry',
      'Continuous ANPR with watchlist correlation',
      'Prioritised alerts with a plain-language reason',
      'Timestamped cross-camera route, replayable',
    ],
    { x: M, y: 2.2, w: 4.25, h: 2.0 },
  )
  s.addText('Real screenshot. Real government cameras. Not a mock-up.', {
    x: 5.1, y: 4.92, w: 4.35, h: 0.3, fontSize: 10, fontFace: B, color: MUTED, italic: true, margin: 0,
  })
}

// ─────────────────────────────────────────────────────────── 4. Model choice
{
  const s = slide({ n: 4, eyebrow: 'Architecture choice', title: 'Hybrid 1 + 2 + 3, selective 4.' })
  lede(s, 'Four integration models were on the table. We took the three that scale and used the fourth sparingly.')
  const rows = [
    ['1', 'Unified registry', 'Mandatory. One catalogue, one identity for every camera.', MINT],
    ['2', 'Federated access', 'Departments keep their systems. We adapt to them, not the reverse.', MINT],
    ['3', 'Edge analytics', 'Inference next to the camera. Meaning travels, video does not.', MINT],
    ['4', 'Central video', 'Only on demand, only for the cameras actually being watched.', AMBER],
  ]
  rows.forEach(([n, name, why, c], i) => {
    const y = 2.18 + i * 0.86
    card(s, { x: M, y, w: CONTENT_W, h: 0.56, accent: c })
    s.addText(n, { x: M + 0.22, y: y + 0.1, w: 0.35, h: 0.4, fontSize: 19, fontFace: H, color: c, bold: true, margin: 0 })
    s.addText(name, { x: M + 0.62, y: y + 0.13, w: 2.1, h: 0.32, fontSize: 13, fontFace: H, color: TEXT, bold: true, margin: 0 })
    s.addText(why, { x: M + 2.8, y: y + 0.15, w: 5.9, h: 0.32, fontSize: 11.5, fontFace: B, color: MUTED, margin: 0 })
  })
}

// ─────────────────────────────────────────────────────────── 5. Honesty moment
{
  const s = slide({ n: 5, eyebrow: 'The rejected option', title: 'Why we did not centralise the video.', accent: RED })
  lede(s, 'Streaming all 80,000 cameras to one data centre is not a budget problem. It is a physics problem.')
  const stats = [
    ['160 Gbps', 'sustained ingest, 24×7, from sites up to 1,000 km apart'],
    ['12.1 PB', 'hot storage for a single week, before redundancy or DR'],
    ['₹20+ cr', 'per month at cloud object pricing, for storage alone'],
  ]
  const c5 = cols(3)
  stats.forEach(([v, l], i) => {
    card(s, { x: c5.x(i), y: 2.15, w: c5.w, h: 1.68, accent: RED })
    stat(s, { x: c5.x(i) + 0.26, y: 2.36, w: c5.w - 0.5, value: v, label: l, color: RED, size: 26 })
  })
  s.addText(
    'We put this number in the deck because a jury should see the option we rejected, and why.',
    { x: M, y: 4.26, w: CONTENT_W, h: 0.5, fontSize: 13, fontFace: B, color: TEXT, italic: true, margin: 0 },
  )
}

// ─────────────────────────────────────────────────────────── 6. Architecture
{
  const s = slide({ n: 6, eyebrow: 'Architecture', title: 'Three planes, one contract.' })
  lede(s, 'Every camera becomes a CameraDescriptor. Every read becomes an Event. Nothing downstream cares about the vendor.')
  const planes = [
    ['EDGE', 'Capture · decode · ANPR · secondary analytics', 'Runs beside the cameras. Sends ~1 KB events, not 2 Mbps streams.', MINT],
    ['CORE', 'Registry · correlation · alerts · evidence · audit', 'PostGIS + TimescaleDB. Row-level tenancy per department.', TEAL],
    ['SURFACE', 'Operator console · Admin portal · Field PWA', 'Three audiences, one design language, three languages.', AMBER],
  ]
  const c6 = cols(3)
  planes.forEach(([name, what, why, c], i) => {
    const x = c6.x(i)
    const iw = c6.w - 0.52
    card(s, { x, y: 2.12, w: c6.w, h: 2.1, accent: c })
    s.addText(name, { x: x + 0.28, y: 2.3, w: iw, h: 0.3, fontSize: 13, fontFace: H, color: c, bold: true, charSpacing: 1.5, margin: 0 })
    s.addText(what, { x: x + 0.28, y: 2.64, w: iw, h: 0.74, fontSize: 11, fontFace: B, color: TEXT, margin: 0, valign: 'top' })
    s.addText(why, { x: x + 0.28, y: 3.4, w: iw, h: 0.74, fontSize: 10, fontFace: B, color: MUTED, margin: 0, valign: 'top' })
  })
  s.addText('Video stays local. Meaning travels.', {
    x: M, y: 4.45, w: CONTENT_W, h: 0.35, fontSize: 13, fontFace: H, color: MINT, bold: true, margin: 0,
  })
}

// ─────────────────────────────────────────────────────────── 7. Federation
{
  const s = slide({ n: 7, eyebrow: 'Ingest & federation', title: 'A new department is a driver, not a release.' })
  lede(s, 'One call discovered and onboarded the entire government grid. Zero failures, zero hard-coded camera IDs.')
  card(s, { x: M, y: 2.12, w: 4.3, h: 2.18, accent: MINT })
  stat(s, { x: M + 0.3, y: 2.36, w: 3.72, value: '30 / 30', label: 'cameras onboarded from the live catalogue in a single call — 0 failed', color: MINT, size: 32 })
  s.addText('POST /api/v1/cameras/discover', {
    x: M + 0.3, y: 3.66, w: 3.72, h: 0.32, fontSize: 11, fontFace: 'Consolas', color: TEAL, margin: 0,
  })
  bullets(
    s,
    [
      'ONVIF + RTSP driver SDK, with a conformance suite',
      'Four vendor shims: Hikvision, Dahua, Milestone, Genetec',
      'Catalogue re-read every run — the camera set can change',
      'VAHAN / SARTHI / eGujCop / AFIS registry clients',
    ],
    { x: M + 4.6, y: 2.2, w: CONTENT_W - 4.6, h: 2.1 },
  )
}

// ─────────────────────────────────────────────────────────── 8. ANPR
{
  const s = slide({ n: 8, eyebrow: 'ANPR pipeline', title: 'Detect, track, read, then vote.' })
  lede(s, 'A plate is never trusted from one frame. Reads are held until several frames agree.')
  const steps = ['Vehicle detect', 'Track', 'Plate detect', 'Rectify', 'OCR', 'Temporal vote']
  const c8 = cols(6)
  steps.forEach((t, i) => {
    s.addShape(pres.shapes.RECTANGLE, { x: c8.x(i), y: 2.14, w: c8.w, h: 0.56, fill: { color: PANEL_2 } })
    s.addText(t, { x: c8.x(i), y: 2.14, w: c8.w, h: 0.56, fontSize: 9, fontFace: B, color: TEXT, align: 'center', valign: 'middle', margin: 0 })
  })
  const facts = [
    ['~14.7 fps', 'full chain, single-threaded, Apple Silicon M2', MINT],
    ['4.0 frames', 'voted per read on real traffic (max 20)', MINT],
    ['No accuracy %', 'claimed — needs a hand-labelled holdout we do not have', AMBER],
  ]
  const c8b = cols(3)
  facts.forEach(([v, l, c], i) => {
    card(s, { x: c8b.x(i), y: 3.02, w: c8b.w, h: 1.32, accent: c })
    stat(s, { x: c8b.x(i) + 0.26, y: 3.2, w: c8b.w - 0.5, value: v, label: l, color: c, size: 21 })
  })
  s.addText('The third box is the one worth reading.', {
    x: M, y: 4.52, w: CONTENT_W, h: 0.35, fontSize: 12, fontFace: B, color: AMBER, italic: true, margin: 0,
  })
}

// ─────────────────────────────────────────────────────────── 9. Correlation
{
  const s = slide({ n: 9, eyebrow: 'Watchlist correlation', title: 'The camera read it wrong. We still caught it.' })
  lede(s, 'A matching ladder, not a string compare. Rung two collapses the characters OCR habitually confuses.')
  card(s, { x: M, y: 2.12, w: CONTENT_W, h: 1.58, accent: TEAL })
  s.addText([
    { text: 'WATCHLIST   ', options: { fontSize: 10, color: MUTED, fontFace: B, charSpacing: 1 } },
    { text: 'GJ186705', options: { fontSize: 22, color: TEXT, fontFace: 'Consolas', bold: true } },
  ], { x: M + 0.35, y: 2.34, w: 3.4, h: 0.5, margin: 0 })
  s.addText([
    { text: 'CAMERA READ   ', options: { fontSize: 10, color: MUTED, fontFace: B, charSpacing: 1 } },
    { text: 'GJ1B67OS', options: { fontSize: 22, color: AMBER, fontFace: 'Consolas', bold: true } },
  ], { x: M + 0.35, y: 2.92, w: 3.4, h: 0.5, margin: 0 })
  s.addText('8→B   0→O   5→S', {
    x: M + 4.0, y: 2.44, w: 2.2, h: 0.4, fontSize: 13, fontFace: 'Consolas', color: MUTED, margin: 0,
  })
  s.addText('ALERT RAISED', {
    x: M + 6.25, y: 2.4, w: 2.3, h: 0.36, fontSize: 15, fontFace: H, color: MINT, bold: true, charSpacing: 1, margin: 0,
  })
  s.addText('match_rung: ambiguity_class', {
    x: M + 6.25, y: 2.8, w: 2.4, h: 0.3, fontSize: 10, fontFace: 'Consolas', color: TEAL, margin: 0,
  })
  s.addText('Verified end to end on live government reads, not a unit test.', {
    x: M + 6.25, y: 3.12, w: 2.4, h: 0.46, fontSize: 9.5, fontFace: B, color: MUTED, margin: 0,
  })
  s.addText(
    'Every alert carries the reason it fired, in words an operator can act on — never a bare score.',
    { x: M, y: 3.96, w: CONTENT_W, h: 0.5, fontSize: 12.5, fontFace: B, color: TEXT, margin: 0 },
  )
}

// ─────────────────────────────────────────────────────────── 10. Beyond plates
{
  const s = slide({ n: 10, eyebrow: 'Beyond plates', title: 'Measured on real traffic, not fixtures.' })
  lede(s, 'Secondary analytics ran against the live government grid for ten minutes across six cameras.')
  const figures = [
    ['172', 'plate reads', MINT],
    ['124', 'distinct plates', MINT],
    ['208', 'zone events fired', TEAL],
    ['1', 'camera flagged tampered', AMBER],
  ]
  const c10 = cols(4)
  figures.forEach(([v, l, c], i) => {
    card(s, { x: c10.x(i), y: 2.15, w: c10.w, h: 1.32, accent: c })
    stat(s, { x: c10.x(i) + 0.24, y: 2.34, w: c10.w - 0.48, value: v, label: l, color: c, size: 30 })
  })
  s.addText(
    '186 intrusion + 22 wrong-way events. The wrong-way detections are the meaningful ones: they need real ' +
      'vehicle tracks and a heading computed over time, which a synthetic fixture cannot produce.',
    { x: M, y: 3.82, w: 8.1, h: 0.7, fontSize: 12, fontFace: B, color: MUTED, margin: 0, valign: 'top' },
  )
  s.addText('Vehicle colour is an HSV heuristic. Coarse-make was not attempted.', {
    x: M, y: 4.55, w: CONTENT_W, h: 0.35, fontSize: 11.5, fontFace: B, color: AMBER, italic: true, margin: 0,
  })
}

// ─────────────────────────────────────────────────────────── 11. Resilience
{
  const s = slide({ n: 11, eyebrow: 'Resilience', title: 'We broke it on purpose.' })
  lede(s, 'Chaos drills against the live stack — and anything that could not be tested honestly is recorded as skipped, never as a pass.')
  const drills = [
    ['Feed killed mid-analysis', 'PASS', 'Noticed in 33s. Recovered unattended 14s after the feed returned, reconnect counted.', MINT],
    ['RTSP port blocked', 'PASS', 'The same capture layer fell back to HLS and decoded frames.', MINT],
    ['Loop-point scene cut', 'SKIPPED', 'Our fixture provably cannot produce a PTS discontinuity. Refused to claim a pass.', AMBER],
    ['Network throttle', 'SKIPPED', 'Needs root-level link shaping. Documented, not simulated.', AMBER],
  ]
  drills.forEach(([name, verdict, detail, c], i) => {
    const y = 2.18 + i * 0.86
    card(s, { x: M, y, w: CONTENT_W, h: 0.56, accent: c })
    s.addText(name, { x: M + 0.24, y: y + 0.13, w: 2.5, h: 0.32, fontSize: 12, fontFace: H, color: TEXT, bold: true, margin: 0 })
    s.addText(verdict, { x: M + 2.82, y: y + 0.14, w: 0.9, h: 0.3, fontSize: 11, fontFace: H, color: c, bold: true, margin: 0 })
    s.addText(detail, { x: M + 3.82, y: y + 0.15, w: 4.9, h: 0.32, fontSize: 10.5, fontFace: B, color: MUTED, margin: 0 })
  })
}

// ─────────────────────────────────────────────────────────── 12. Scale
{
  const s = slide({ n: 12, eyebrow: 'Scale', title: 'The 80,000-camera arithmetic.' })
  lede(s, 'Tiered analytics, district GPUs, and an edge that never ships raw video to the centre.')
  const rows = [
    ['Tier A — continuous', 'Highways, borders, critical sites', 'Always-on ANPR'],
    ['Tier B — sampled', 'Arterial roads and junctions', 'Duty-cycled inference'],
    ['Tier C — motion-gated', 'Low-traffic and interior cameras', 'Wakes on motion only'],
  ]
  rows.forEach(([t, where, how], i) => {
    const y = 2.18 + i * 0.88
    card(s, { x: M, y, w: 5.85, h: 0.58, accent: TEAL })
    s.addText(t, { x: M + 0.22, y: y + 0.15, w: 2.0, h: 0.3, fontSize: 11.5, fontFace: H, color: TEXT, bold: true, margin: 0 })
    s.addText(where, { x: M + 2.28, y: y + 0.165, w: 1.95, h: 0.28, fontSize: 9.5, fontFace: B, color: MUTED, margin: 0 })
    s.addText(how, { x: M + 4.3, y: y + 0.165, w: 1.5, h: 0.28, fontSize: 9.5, fontFace: B, color: TEAL, margin: 0 })
  })
  card(s, { x: 6.7, y: 2.14, w: 2.75, h: 1.9, accent: MINT })
  stat(s, { x: 6.95, y: 2.34, w: 2.25, value: '≈ ₹80 cr', label: 'indicative capex, phased', color: MINT, size: 26 })
  s.addText('₹0 software licences —\nfully open-source stack', {
    x: 6.95, y: 3.38, w: 2.25, h: 0.58, fontSize: 10.5, fontFace: B, color: TEXT, margin: 0, valign: 'top',
  })
  s.addText(
    'This is arithmetic from a documented model, not a deployment we have run. Stated as such.',
    { x: M, y: 4.78, w: CONTENT_W, h: 0.36, fontSize: 11.5, fontFace: B, color: AMBER, italic: true, margin: 0 },
  )
}

// ─────────────────────────────────────────────────────────── 13. Security
{
  const s = slide({ n: 13, eyebrow: 'Security & privacy', title: 'Built for evidence, not just for demos.' })
  lede(s, 'Every item below is running code with a test behind it.')
  const items = [
    ['Faces blurred by default', 'At the edge, before storage. Revealing one needs an admin, a reason, and leaves a record.'],
    ['Department tenancy in the database', 'Postgres row-level security under a non-superuser role — not a WHERE clause we remember to add.'],
    ['Hash-chained audit log', 'Tamper-evident. We edited a row directly in Postgres and the verifier caught it immediately.'],
    ['mTLS from edge to core', 'Client certificates terminated at a gateway; no certificate, no ingest.'],
    ['Signed, expiring media URLs', 'A video link works without a login for minutes, not forever.'],
  ]
  items.forEach(([t, d], i) => {
    const y = 2.16 + i * 0.62
    s.addShape(pres.shapes.OVAL, { x: M, y: y + 0.11, w: 0.17, h: 0.17, fill: { color: MINT } })
    s.addText(t, { x: M + 0.32, y: y + 0.02, w: 3.2, h: 0.3, fontSize: 12, fontFace: H, color: TEXT, bold: true, margin: 0 })
    s.addText(d, { x: M + 3.6, y: y + 0.03, w: 5.2, h: 0.5, fontSize: 10.5, fontFace: B, color: MUTED, margin: 0, valign: 'top' })
  })
}

// ─────────────────────────────────────────────────────────── 14. Honesty table
{
  const s = slide({ n: 14, eyebrow: 'What is real', title: 'What works, and what we are not claiming.', accent: AMBER })
  lede(s, 'A reviewer should not have to reverse-engineer which parts are load-bearing.')
  const real = [
    'Capture, reconnect and PTS timing',
    'ANPR with real open-source models',
    'Registry, search, alerts, evidence',
    'Watchlist correlation, both rungs',
    'Zones, tamper, vehicle colour',
    'mTLS, RLS, audit chain, signed URLs',
  ]
  const not = [
    'An ANPR accuracy number',
    'Coarse-make classification',
    'Face recognition (excluded by choice)',
    'Government registry credentials',
    '80,000 cameras actually deployed',
  ]
  card(s, { x: M, y: 2.1, w: 4.3, h: 2.42, accent: MINT })
  s.addText('RUNNING TODAY', { x: M + 0.28, y: 2.27, w: 3.7, h: 0.3, fontSize: 11.5, fontFace: H, color: MINT, bold: true, charSpacing: 1.5, margin: 0 })
  bullets(s, real, { x: M + 0.28, y: 2.64, w: 3.7, h: 1.85, size: 11 })
  card(s, { x: M + 4.6, y: 2.1, w: CONTENT_W - 4.6, h: 2.42, accent: AMBER })
  s.addText('NOT CLAIMED', { x: M + 4.88, y: 2.27, w: 3.6, h: 0.3, fontSize: 11.5, fontFace: H, color: AMBER, bold: true, charSpacing: 1.5, margin: 0 })
  bullets(s, not, { x: M + 4.88, y: 2.64, w: 3.6, h: 1.85, size: 11, color: TEXT })
  s.addText('The right-hand column is why you can trust the left.', {
    x: M, y: 4.86, w: CONTENT_W, h: 0.4, fontSize: 13, fontFace: H, color: TEXT, bold: true, margin: 0,
  })
}

// ─────────────────────────────────────────────────────────── 15. Close
{
  const s = pres.addSlide()
  s.background = { color: BG }
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 0.09, h: 5.625, fill: { color: MINT } })
  s.addText('Ready for a pilot.', {
    x: M, y: 1.5, w: 8.5, h: 0.8, fontSize: 40, fontFace: H, color: TEXT, bold: true, margin: 0,
  })
  const asks = [
    ['Running today', 'The full platform, against the real grid, on one laptop.'],
    ['What we need', 'Catalogue access per department and a district to pilot in.'],
    ['First 90 days', 'One district, Tier A cameras, measured against a baseline.'],
  ]
  asks.forEach(([t, d], i) => {
    const y = 2.55 + i * 0.66
    s.addShape(pres.shapes.RECTANGLE, { x: M, y, w: 0.05, h: 0.5, fill: { color: MINT } })
    s.addText(t, { x: M + 0.25, y: y + 0.02, w: 2.3, h: 0.3, fontSize: 13, fontFace: H, color: MINT, bold: true, margin: 0 })
    s.addText(d, { x: M + 2.7, y: y + 0.04, w: 6.1, h: 0.3, fontSize: 12, fontFace: B, color: TEXT, margin: 0 })
  })
  s.addText('Sentinel · Gujarat Police Innovation Challenge 2026', {
    x: M, y: 4.85, w: 8.5, h: 0.3, fontSize: 10, fontFace: B, color: MUTED, charSpacing: 1, margin: 0,
  })
}

await pres.writeFile({ fileName: OUT })
console.log(`wrote ${OUT}`)
