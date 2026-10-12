/**
 * Builds the grand-finale pitch deck: docs/Sentinel-Finale-Pitch.pptx.
 *
 * For a 20-minute evaluation in front of senior IPS officers and technology
 * professors, where the jury asks us to open one camera and trace a vehicle
 * live. The deck is built around that drill: the case (why), the live trace in
 * five steps (each step's slide doubles as the backup if the venue network
 * fails), trust, scale and cost, and the pilot we propose. Appendix slides
 * answer the questions each half of the room tends to ask.
 *
 * It is set in the console's own identity (DESIGN.md): a departures board for
 * vehicles — ink on cool paper, one amber signal, numbered hops for the
 * points worth looking at. Every screenshot is the real console on the
 * recorded copy of the government grid, captured with
 *   npm run screenshots:pitch      (from apps/web)
 * and every number comes from evidence/ or docs/04-SCALE-PLAN.md; the speaker
 * notes carry the talk track and docs/13-SHOWCASE-PREP.md the full script.
 *
 * Usage:
 *   NODE_PATH=$(npm root -g) node scripts/build_pitch_deck.mjs
 *   make pitch
 */

import { createRequire } from 'node:module'
import { readFileSync } from 'node:fs'
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
const PITCH = resolve(REPO, 'docs', 'images', 'pitch')
const SHOT = (name) => resolve(PITCH, name.includes('.') ? name : `${name}.png`)
const OUT = resolve(REPO, 'docs', 'Sentinel-Finale-Pitch.pptx')

// The console's palette (DESIGN.md). Ink and cool paper carry everything;
// amber is the one signal, used as a fill, never as text on paper.
const INK = '111417'
const INK2 = '2F353B'
const MUTED = '4C5157'
const FAINT = '8A8F95'
const GROUND = 'EDEEEA'
const PANEL = 'FBFBF9'
const INSET = 'F3F4F0'
const RULE = 'D5D7D2'
const AMBER = 'FFB000'
const SIGNAL_TINT = 'FFF4DA'
const SIGNAL_RULE = 'ECCB78'
const SIGNAL_INK = '5A4410'
const LIVE = '1F7A4A'
const DARK = '0E1012'
const DARK_PANEL = '16191C'
const DARK_PASS = '23272B'
const DARK_RULE = '2E3338'
const DARK_INK = 'EEF0EC'
const DARK_MUTED = 'A9AFB5'
const WHITE = 'FFFFFF'

// Condensed signage for display, as the console uses Sofia Sans Condensed;
// these ship with Microsoft Office on macOS and Windows.
const D = 'Franklin Gothic Demi Cond'
const B = 'Franklin Gothic Book'
const BB = 'Franklin Gothic Demi'
const MONO = 'Consolas'

const W = 13.333
const SLIDE_H = 7.5
const M = 0.6
const CW = W - 2 * M

const pres = new PptxGenJS()
pres.layout = 'LAYOUT_WIDE'
pres.author = 'Invental Data Labs'
pres.company = 'Invental Data Labs'
pres.title = 'Sentinel — type a plate, see where it went'

// --- assets -----------------------------------------------------------------

const iconCache = new Map()

/** A Lucide icon (the console's own icon set) rendered to a PNG data URI. */
async function icon(name, color) {
  const key = `${name}:${color}`
  if (iconCache.has(key)) return iconCache.get(key)
  const Component = Lu[name]
  if (!Component) throw new Error(`no icon ${name}`)
  const svg = renderToStaticMarkup(
    React.createElement(Component, { size: 256, color: `#${color}`, strokeWidth: 1.8 }),
  )
  const png = await sharp(Buffer.from(svg)).resize(160, 160).png({ palette: true }).toBuffer()
  const data = `image/png;base64,${png.toString('base64')}`
  iconCache.set(key, data)
  return data
}

/** JPEG keeps the deck small enough to commit; at this quality the console's
 * text stays crisp at slide size. */
async function encode(image, width) {
  const jpeg = await image
    .resize({ width: Math.min(width, 2400), withoutEnlargement: true })
    .jpeg({ quality: 84, mozjpeg: true })
    .toBuffer()
  return `image/jpeg;base64,${jpeg.toString('base64')}`
}

/** A region of a screenshot. Console captures are given in the 1600x1000
 * CSS-pixel viewport they were taken at; `base` overrides that for other
 * images (the 1920-wide evidence frame, the phone). */
async function crop(name, { x, y, w, h }, base = 1600) {
  const image = sharp(SHOT(name))
  const k = (await image.metadata()).width / base
  const region = image.extract({
    left: Math.round(x * k), top: Math.round(y * k), width: Math.round(w * k), height: Math.round(h * k),
  })
  return { data: await encode(region, Math.round(w * k)), ratio: w / h, region: { x, y, w, h } }
}

async function whole(name) {
  const image = sharp(SHOT(name))
  const { width, height } = await image.metadata()
  return { data: await encode(image, width), ratio: width / height }
}

const manifest = JSON.parse(readFileSync(SHOT('movement-report-manifest.json'), 'utf8'))
const evidence = JSON.parse(readFileSync(SHOT('evidence-frame.json'), 'utf8'))

// --- the frame every slide shares ------------------------------------------

const CHAPTERS = ['The case', 'Live', 'Trust', 'Scale', 'Next']
const section = { chapter: null, appendix: false }
let mainCount = 0
let appendixCount = 0

function nextLabel() {
  if (section.appendix) return `A${++appendixCount}`
  return String(++mainCount).padStart(2, '0')
}

function text(s, value, opts) {
  s.addText(value, { margin: 0, fontFace: B, color: INK, valign: 'top', ...opts })
}

function pageNo(s, label, dark) {
  text(s, label, {
    x: W - M - 0.8, y: SLIDE_H - 0.42, w: 0.8, h: 0.22, align: 'right',
    fontFace: MONO, fontSize: 9, color: dark ? DARK_MUTED : FAINT,
  })
}

/** The chapter line, top right, read like a board's column of stops. */
function tracker(s, dark) {
  const opts = { x: W - M - 6.0, y: 0.42, w: 6.0, h: 0.26, align: 'right', fontFace: MONO, fontSize: 10 }
  if (section.appendix) {
    text(s, 'APPENDIX · FOR QUESTIONS', { ...opts, color: dark ? DARK_MUTED : MUTED })
    return
  }
  if (!section.chapter) return
  const runs = []
  for (const [i, chapter] of CHAPTERS.entries()) {
    const current = chapter === section.chapter
    const color = current ? (dark ? DARK_INK : INK) : (dark ? '5B6168' : 'A3A8AD')
    runs.push({ text: chapter.toUpperCase(), options: { bold: current, color } })
    if (i < CHAPTERS.length - 1) runs.push({ text: '  ·  ', options: { color: dark ? '5B6168' : 'A3A8AD' } })
  }
  s.addText(runs, { ...opts, margin: 0 })
}

/** A content slide: cool-paper ground, a mono kicker, a condensed title. */
function frame({ kicker, title, notes, dark = false, titleSize = 36 }) {
  const label = nextLabel()
  const s = pres.addSlide()
  s.background = { color: dark ? DARK : GROUND }
  const prefix = section.appendix ? `${label} · ` : ''
  text(s, (prefix + kicker).toUpperCase(), {
    x: M, y: 0.42, w: CW - 6.2, h: 0.26, fontFace: MONO, fontSize: 11, bold: true,
    color: dark ? AMBER : MUTED, charSpacing: 1,
  })
  tracker(s, dark)
  text(s, title, {
    x: M, y: 0.74, w: CW, h: 0.8, fontFace: D, fontSize: titleSize, color: dark ? DARK_INK : INK,
  })
  pageNo(s, label, dark)
  if (notes) s.addNotes(notes)
  return s
}

function panel(s, x, y, w, h, { fill = PANEL, line = RULE, radius = 0.08 } = {}) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x, y, w, h, rectRadius: radius, fill: { color: fill }, line: { color: line, width: 0.75 },
  })
}

/** A console screenshot in a thin paper frame, lifted by a soft shadow. */
function shot(s, img, x, y, w, { h: forced, dark = false } = {}) {
  const h = forced ?? w / img.ratio
  s.addShape(pres.shapes.RECTANGLE, {
    x: x - 0.04, y: y - 0.04, w: w + 0.08, h: h + 0.08,
    fill: { color: dark ? DARK_PANEL : WHITE }, line: { color: dark ? DARK_RULE : RULE, width: 0.75 },
    shadow: { type: 'outer', color: '111417', blur: 18, offset: 5, angle: 90, opacity: 0.14 },
  })
  s.addImage({ data: img.data, x, y, w, h })
  return h
}

/** Where a CSS-pixel point of a cropped screenshot landed on the slide. */
function at(img, x0, y0, w, cssX, cssY) {
  const { region } = img
  return { x: x0 + ((cssX - region.x) / region.w) * w, y: y0 + ((cssY - region.y) / region.h) * (w / img.ratio) }
}

/** Lines a string wraps to in a box `w` inches wide, by greedy word wrap at
 * an average glyph width of `em` × the font size (calibrated against
 * PowerPoint's own render of Franklin Gothic). Good enough to stack blocks
 * without overlap. */
function lineCount(value, size, w, em = 0.5) {
  const perLine = Math.max(1, Math.floor(w / ((em * size) / 72)))
  let lines = 1
  let used = 0
  for (const word of value.split(/\s+/)) {
    const need = used === 0 ? word.length : used + 1 + word.length
    if (need > perLine && used > 0) {
      lines += 1
      used = word.length
    } else {
      used = need
    }
  }
  return lines
}

const lineH = (size, n) => (n * size * 1.2) / 72

/** A numbered amber hop, as the console numbers a vehicle's sightings. */
function hop(s, n, cx, cy, d = 0.44) {
  s.addShape(pres.shapes.OVAL, {
    x: cx - d / 2, y: cy - d / 2, w: d, h: d, fill: { color: AMBER }, line: { color: INK, width: 1.25 },
  })
  text(s, String(n), {
    x: cx - d / 2, y: cy - d / 2, w: d, h: d, align: 'center', valign: 'middle', fontFace: D, fontSize: d * 36, color: INK,
  })
}

/** A hop beside a bold line and a muted explanation; returns its bottom. */
function callout(s, { n, title, body, x, y, w, dark = false, titleSize = 16, bodySize = 13 }) {
  hop(s, n, x + 0.22, y + 0.2)
  const tw = w - 0.62
  const th = lineH(titleSize, lineCount(title, titleSize, tw, 0.42))
  const bh = lineH(bodySize, lineCount(body, bodySize, tw, 0.44))
  text(s, title, { x: x + 0.62, y: y + 0.02, w: tw, h: th, fontFace: BB, fontSize: titleSize, color: dark ? DARK_INK : INK })
  text(s, body, { x: x + 0.62, y: y + th + 0.1, w: tw, h: bh, fontSize: bodySize, color: dark ? DARK_MUTED : MUTED })
  return y + th + 0.1 + bh
}

/** A registration plate, set as the console sets it. */
function plate(s, value, x, y, { size = 20, fill = INK, color = WHITE } = {}) {
  const w = (value.length * 0.55 * size) / 72 + 0.34
  const h = (size / 72) * 1.55
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.05, fill: { color: fill }, line: { color: fill } })
  text(s, value, { x, y, w, h, align: 'center', valign: 'middle', fontFace: MONO, bold: true, fontSize: size, color })
  return w
}

async function glyph(s, name, x, y, d, color) {
  s.addImage({ data: await icon(name, color), x, y, w: d, h: d })
}

/** Icon, bold line, muted line: the deck's quiet row; returns its bottom. */
async function iconRow(s, { icon: name, title, body, x, y, w, color = INK, dark = false }) {
  await glyph(s, name, x, y + 0.02, 0.36, color)
  const tw = w - 0.56
  const th = lineH(15, lineCount(title, 15, tw, 0.42))
  const bh = lineH(12.5, lineCount(body, 12.5, tw, 0.44))
  text(s, title, { x: x + 0.56, y, w: tw, h: th, fontFace: BB, fontSize: 15, color: dark ? DARK_INK : INK })
  text(s, body, { x: x + 0.56, y: y + th + 0.06, w: tw, h: bh, fontSize: 12.5, color: dark ? DARK_MUTED : MUTED })
  return y + th + 0.06 + bh
}

/** A mono note at the foot of a slide: where a screenshot or number is from. */
function source(s, value, { y = 6.88, dark = false, w = CW - 1.0 } = {}) {
  text(s, value, { x: M, y, w, h: 0.3, fontFace: B, fontSize: 10, italic: true, color: dark ? DARK_MUTED : MUTED })
}

// --- 1. The case ------------------------------------------------------------

async function titleSlide() {
  nextLabel()
  const s = pres.addSlide()
  s.background = { color: DARK }
  // The timeline and the evidence frame of a real sighting, in the dark theme.
  const img = await crop('find-a-vehicle-dark', { x: 752, y: 418, w: 828, h: 476 })
  const sw = 6.15
  const sx = W - M - sw
  const sh = shot(s, img, sx, 1.25, sw, { dark: true })
  // The same sighting as one row of the board.
  const ry = 1.25 + sh + 0.35
  s.addShape(pres.shapes.RECTANGLE, { x: sx, y: ry, w: sw, h: 0.62, fill: { color: DARK_PASS }, line: { color: DARK_RULE, width: 0.75 } })
  s.addShape(pres.shapes.RECTANGLE, { x: sx, y: ry, w: 0.95, h: 0.62, fill: { color: AMBER }, line: { color: AMBER } })
  text(s, 'SEEN', { x: sx, y: ry, w: 0.95, h: 0.62, align: 'center', valign: 'middle', fontFace: MONO, bold: true, fontSize: 13, color: INK })
  text(s, '17 JUN · 18:01:21', { x: sx + 1.15, y: ry, w: 1.75, h: 0.62, valign: 'middle', fontFace: MONO, fontSize: 12, color: DARK_MUTED })
  text(s, evidence.plate_text, { x: sx + 2.95, y: ry, w: 1.5, h: 0.62, valign: 'middle', fontFace: MONO, bold: true, fontSize: 17, color: DARK_INK })
  text(s, 'Timbavadi Gate, Junagadh', { x: sx + 4.45, y: ry, w: sw - 4.6, h: 0.62, valign: 'middle', fontSize: 13, color: DARK_INK })

  text(s, 'GUJARAT POLICE INNOVATION CHALLENGE 2026 · GRAND FINALE · i-HUB GUJARAT, 12–13 OCT', {
    x: M, y: 0.6, w: 9, h: 0.3, fontFace: MONO, fontSize: 11, bold: true, color: AMBER, charSpacing: 1,
  })
  text(s, 'Sentinel', { x: M, y: 1.05, w: 5.6, h: 1.2, fontFace: D, fontSize: 80, color: DARK_INK })
  text(s, 'Type a plate.\nSee where it went.', { x: M, y: 2.3, w: 5.6, h: 1.4, fontFace: D, fontSize: 36, color: DARK_INK })
  text(s, 'One platform over the cameras Gujarat’s departments already run. It reads plates where the video is filmed and alerts officers when a vehicle of interest is seen.', {
    x: M, y: 3.85, w: 5.4, h: 0.85, fontSize: 15, color: DARK_MUTED,
  })
  await team(s, M, 4.85, sx - M - 0.4)
  s.addNotes([
    '[0:00–0:45] Open with the outcome, not the technology.',
    '“Sentinel lets an officer type a registration number and see where that vehicle went, across the government’s cameras — and be told the moment it is seen again.”',
    'Then ten seconds on who we are — and do not read the credentials out; the panel has heard every team list theirs. Point at them and say what they mean for this room: “I’m Parth Patel, I lead the team; with me is Anuj Patel. Our backgrounds are on the slide — enterprise AI architecture and data science. What that means for you: every number we show today, we measured, and we will tell you where we fell short.”',
    'If asked: Parth is a consulting AI solution architect who has worked with IBM and United Airlines, with an MTech in Data Science from IIT Bombay. Anuj is a data scientist based in Göttingen, Germany.',
    'The row under the screenshot is a real sighting from the government grid: the plate, the camera, and the time printed on that camera’s own frame.',
    'If the jury hands over a vehicle number or asks for the live trace now, go straight to slide 04 and come back.',
  ].join('\n\n'))
}

/** Who is presenting: one row each, initials and credentials as chips the
 * panel can scan without being read to. Facts only, as the team gave them. */
async function team(s, x, y, w) {
  text(s, 'INVENTAL DATA LABS', { x, y, w, h: 0.26, fontFace: MONO, bold: true, fontSize: 10.5, color: DARK_MUTED, charSpacing: 1 })
  const people = [
    ['PP', 'Parth Patel', 'Team lead · AI solution architect', ['IIT Bombay · MTech', 'IBM', 'United Airlines']],
    ['AP', 'Anuj Patel', 'Data scientist', ['Göttingen, Germany']],
  ]
  const rowH = 0.86
  for (const [i, [initials, name, role, chips]] of people.entries()) {
    const ry = y + 0.38 + i * (rowH + 0.12)
    s.addShape(pres.shapes.RECTANGLE, { x, y: ry, w, h: rowH, fill: { color: DARK_PANEL }, line: { color: DARK_RULE, width: 0.75 } })
    const d = 0.52
    s.addShape(pres.shapes.OVAL, { x: x + 0.17, y: ry + (rowH - d) / 2, w: d, h: d, fill: { color: i === 0 ? AMBER : DARK_PASS }, line: { color: i === 0 ? AMBER : DARK_RULE, width: 0.75 } })
    text(s, initials, { x: x + 0.17, y: ry + (rowH - d) / 2, w: d, h: d, align: 'center', valign: 'middle', fontFace: D, fontSize: 17, color: i === 0 ? INK : DARK_INK })
    const tx = x + 0.86
    text(s, [
      { text: name, options: { fontFace: BB, color: DARK_INK } },
      { text: `   ${role}`, options: { color: DARK_MUTED } },
    ], { x: tx, y: ry + 0.1, w: w - 1.0, h: 0.3, fontSize: 14 })
    let cx = tx
    for (const chip of chips) {
      const cw = (chip.length * 0.56 * 11) / 72 + 0.26
      s.addShape(pres.shapes.RECTANGLE, { x: cx, y: ry + 0.47, w: cw, h: 0.27, fill: { color: DARK_PASS }, line: { color: DARK_RULE, width: 0.75 } })
      text(s, chip, { x: cx, y: ry + 0.47, w: cw, h: 0.27, align: 'center', valign: 'middle', fontFace: MONO, fontSize: 11, color: DARK_INK })
      cx += cw + 0.1
    }
  }
}

async function caseSlide() {
  const s = frame({
    kicker: 'The case',
    title: 'A vehicle is reported. Where did it go?',
    notes: [
      '[0:45–2:00] Speak to the officers first; this is their working day.',
      'Gujarat already has about eighty thousand cameras, run by twenty-six departments. They exist; they do not work together. To trace one vehicle today an officer works out whose cameras are on the route, calls each department, asks for footage, and reviews it by hand — racing a retention window of one to two weeks.',
      'Do not put a number of hours on it; the room knows better than we do. Ask instead: “How many calls did the last such trace take?”',
      'The three figures on the right are from the challenge brief, not ours.',
    ].join('\n\n'),
  })
  text(s, 'Today, to trace one vehicle an officer has to:', { x: M, y: 1.75, w: 6.6, h: 0.36, fontFace: BB, fontSize: 17 })
  const steps = [
    ['Work out whose cameras are on the route', 'Police, municipal, transport, irrigation — each department runs its own.'],
    ['Call each department, one by one', 'A separate system and a separate login for every one of them.'],
    ['Request the footage and review it by hand', 'Camera by camera, frame by frame, with no shared map or timeline.'],
    ['Race the overwrite', 'Most recorders keep 7–15 days. Then the evidence is gone.'],
  ]
  const top = 2.35
  const gap = 1.08
  s.addShape(pres.shapes.LINE, { x: M + 0.22, y: top + 0.2, w: 0, h: gap * 3, line: { color: RULE, width: 1.5 } })
  for (const [i, [title, body]] of steps.entries()) {
    const y = top + i * gap
    s.addShape(pres.shapes.OVAL, { x: M, y: y - 0.02, w: 0.44, h: 0.44, fill: { color: GROUND }, line: { color: FAINT, width: 1.25 } })
    text(s, String(i + 1), { x: M, y: y - 0.02, w: 0.44, h: 0.44, align: 'center', valign: 'middle', fontFace: D, fontSize: 16, color: MUTED })
    text(s, title, { x: M + 0.65, y: y - 0.02, w: 6.0, h: 0.36, fontFace: BB, fontSize: 17 })
    text(s, body, { x: M + 0.65, y: y + 0.37, w: 6.0, h: 0.5, fontSize: 13.5, color: MUTED })
  }
  const facts = [
    ['≈80,000', 'cameras already installed across the State'],
    ['26', 'departments, each with its own system'],
    ['7–15 days', 'before most recordings are overwritten'],
  ]
  const fx = 7.85
  const fw = W - M - fx
  for (const [i, [value, label]] of facts.entries()) {
    const y = 1.75 + i * 1.6
    panel(s, fx, y, fw, 1.38)
    text(s, value, { x: fx + 0.35, y: y + 0.16, w: fw - 0.7, h: 0.7, fontFace: D, fontSize: 44 })
    text(s, label, { x: fx + 0.35, y: y + 0.88, w: fw - 0.7, h: 0.36, fontSize: 14, color: MUTED })
  }
  source(s, 'Camera, department and retention figures are from the challenge brief.')
}

async function answerSlide() {
  const s = frame({
    kicker: 'Our answer',
    title: 'One number in. One route out.',
    notes: [
      '[2:00–2:45] Three jobs, one sentence each, in the officers’ words.',
      'See: every department’s cameras on one map and one wall. Find: type a plate, get every sighting with its time and its frame, and a report for the case file. Alert: a watchlist vehicle flagged on every screen the moment any camera reads it.',
      'Then the line that answers the departments’ first worry: “Nothing is installed on anyone’s system. We only read.”',
      'Transition: “Rather than describe it, let us show you — on a camera you choose.”',
    ].join('\n\n'),
  })
  const jobs = [
    // Each crop is cut to the card's 1.48 : 1 image box.
    ['SEE', 'Every camera, one map', 'Each department’s cameras on one map and one live wall, with their health.', await crop('cameras-map', { x: 545, y: 346, w: 801, h: 540 })],
    ['FIND', 'Any vehicle, by its plate', 'Every sighting with the time printed on its frame — and a report to hand over.', await crop('find-a-vehicle', { x: 752, y: 405, w: 828, h: 558 })],
    ['ALERT', 'Flagged when it is read', 'Stolen, wanted and missing vehicles raised on every open screen.', await crop('alerts', { x: 995, y: 182, w: 585, h: 394 })],
  ]
  const gap = 0.35
  const cw = (CW - 2 * gap) / 3
  const ih = 2.3
  for (const [i, [tag, title, body, img]] of jobs.entries()) {
    const x = M + i * (cw + gap)
    panel(s, x, 1.75, cw, 4.45)
    s.addImage({ data: img.data, x: x + 0.2, y: 1.95, w: cw - 0.4, h: ih })
    s.addShape(pres.shapes.RECTANGLE, { x: x + 0.2, y: 1.95, w: cw - 0.4, h: ih, fill: { type: 'none' }, line: { color: RULE, width: 0.75 } })
    s.addShape(pres.shapes.RECTANGLE, { x: x + 0.2, y: 4.45, w: 0.95, h: 0.32, fill: { color: i === 2 ? AMBER : INK }, line: { color: i === 2 ? AMBER : INK } })
    text(s, tag, { x: x + 0.2, y: 4.45, w: 0.95, h: 0.32, align: 'center', valign: 'middle', fontFace: MONO, bold: true, fontSize: 11, color: i === 2 ? INK : WHITE })
    text(s, title, { x: x + 0.2, y: 4.9, w: cw - 0.4, h: 0.42, fontFace: D, fontSize: 22 })
    text(s, body, { x: x + 0.2, y: 5.36, w: cw - 0.4, h: 0.75, fontSize: 13.5, color: MUTED })
  }
  await glyph(s, 'LuShieldCheck', M, 6.45, 0.36, LIVE)
  text(s, 'Read-only: nothing is installed on a department’s cameras, recorders or VMS.', {
    x: M + 0.55, y: 6.45, w: 7.6, h: 0.36, fontSize: 13.5, valign: 'middle',
  })
  await glyph(s, 'LuLanguages', M + 8.55, 6.45, 0.36, INK)
  text(s, 'English · हिन्दी · ગુજરાતી', { x: M + 9.1, y: 6.45, w: CW - 9.1, h: 0.36, fontSize: 13.5, valign: 'middle' })
}

// --- 2. Live ----------------------------------------------------------------

async function liveSlide() {
  const s = frame({
    dark: true,
    kicker: 'Live, on a camera you choose',
    title: 'Pick any camera. We will trace a vehicle from it.',
    titleSize: 40,
    notes: [
      '[2:45–10:00] This is the test case. Switch to the console now; the next five slides are the same steps as backup.',
      'Say what you will do before you click, facing the jury. Roles: the narrator talks, the driver clicks.',
      'CLICK PATH — 01 OPEN: Live Wall → Focus view → choose the camera they name (or the one we are analysing on their road). 02 READ: keep the tile up; when a vehicle passes, its plate appears in the tile’s top-right corner. 03 TRACE: type that plate into the search box at the top (spacing and case do not matter) → Find a Vehicle. Open the stop: camera, printed time, plate as read, evidence frame. If it passed other analysed cameras, the route and Replay route appear. 04 WATCH: “Watch for this vehicle” — the next read raises the banner and sound on every open screen. 05 HAND OVER: Export report → hand them the ZIP.',
      'SAY THE TIMING BEFORE YOU START: “A plate is committed only once several frames agree, so it reaches the screen in about half a minute — sometimes up to a minute and a half.” Fill the wait by opening Overview → ANPR activity, which shows reads arriving per camera.',
      'IF THEY GIVE A PLATE INSTEAD: start at 03. If there is no sighting: say so plainly, open Health to show which cameras were analysed and when, widen the search window to 48 h, and show any probable (one-character-off) matches. Never improvise a route — the system will not draw one it cannot support, and neither should we.',
      'IF THE NETWORK FAILS: say which fallback we are on — our own feed, then the recorded copy of the government grid — and continue on slides 05–09.',
    ].join('\n\n'),
  })
  const cols = [
    ['STEP', 0, 1.75],
    ['DO', 1.75, 3.15],
    ['YOU WILL SEE', 4.9, 4.95],
    ['ON SCREEN', 9.85, CW - 9.85],
  ]
  const top = 1.85
  for (const [label, dx, w] of cols) {
    text(s, label, { x: M + dx + 0.2, y: top, w, h: 0.3, fontFace: MONO, fontSize: 10, color: DARK_MUTED, charSpacing: 1 })
  }
  const rows = [
    ['01 OPEN', 'Open the camera you choose', 'Its live video, through our relay — the department’s system sees one viewer', 'Live Wall → Focus view'],
    ['02 READ', 'Let a vehicle pass', 'Its plate on the tile, once several frames agree on it', 'Live Wall'],
    ['03 TRACE', 'Type that plate', 'Every sighting, timed by each camera’s own clock, on the map', 'Find a Vehicle'],
    ['04 WATCH', 'Arm a watch on it', 'The next sighting raises an alert on every open screen', 'Watch for this vehicle'],
    ['05 HAND OVER', 'Export the report', 'PDF, CSV and evidence frames, sealed with SHA-256', 'Export report'],
  ]
  const rh = 0.72
  for (const [i, [step, doing, see, screen]] of rows.entries()) {
    const y = top + 0.4 + i * (rh + 0.08)
    s.addShape(pres.shapes.RECTANGLE, { x: M, y, w: CW, h: rh, fill: { color: DARK_PANEL }, line: { color: DARK_RULE, width: 0.75 } })
    s.addShape(pres.shapes.RECTANGLE, { x: M, y, w: 1.75, h: rh, fill: { color: DARK_PASS }, line: { color: DARK_RULE, width: 0.75 } })
    text(s, step, { x: M + 0.2, y, w: 1.5, h: rh, valign: 'middle', fontFace: MONO, bold: true, fontSize: 13, color: AMBER })
    text(s, doing, { x: M + 1.95, y, w: 2.95, h: rh, valign: 'middle', fontFace: BB, fontSize: 15, color: DARK_INK })
    text(s, see, { x: M + 5.1, y, w: 4.65, h: rh, valign: 'middle', fontSize: 13.5, color: DARK_INK })
    text(s, screen, { x: M + 10.05, y, w: CW - 10.2, h: rh, valign: 'middle', fontFace: MONO, fontSize: 11, color: DARK_MUTED })
  }
  const ny = top + 0.4 + 5 * (rh + 0.08) + 0.15
  await glyph(s, 'LuTimer', M, ny + 0.02, 0.34, AMBER)
  text(s, [
    { text: 'Timing, stated up front: ', options: { fontFace: BB, color: DARK_INK } },
    { text: 'a plate is committed only once several frames agree, so a read reaches the console in about half a minute — sometimes up to a minute and a half. Near-real-time, for investigation; not for lifting a boom gate.', options: { color: DARK_MUTED } },
  ], { x: M + 0.5, y: ny, w: CW - 0.5, h: 0.6, fontSize: 13 })
}

/** A live step: the console large on the left, numbered hops on it, and the
 * same numbers explained on the right. */
async function stepSlide({ step, name, title, notes, image, region, width = 8.4, markers, callouts, extra }) {
  const s = frame({ kicker: `Live · step ${step} of 5 · ${name}`, title, notes })
  const img = await crop(image, region)
  const x = M + 0.04
  const y = 1.78
  shot(s, img, x, y, width)
  for (const [n, cssX, cssY] of markers) {
    const p = at(img, x, y, width, cssX, cssY)
    hop(s, n, p.x, p.y)
  }
  const rx = M + width + 0.45
  const rw = W - M - rx
  let cy = 1.8
  for (const [i, c] of callouts.entries()) {
    cy = callout(s, { ...c, n: i + 1, x: rx, y: cy, w: rw }) + 0.32
  }
  if (extra) await extra(s, { rx, rw, cy, imgBottom: y + width / img.ratio })
  return s
}

async function openSlide() {
  // The focus view of one camera, and the banner that arrived while it was open.
  const banner = await crop('live-camera', { x: 1224, y: 74, w: 360, h: 124 })
  await stepSlide({
    step: 1, name: 'Open',
    title: 'Open any camera, from any department',
    image: 'live-camera',
    region: { x: 318, y: 298, w: 1244, h: 752 },
    width: 8.25,
    markers: [[1, 610, 329], [2, 905, 383]],
    callouts: [
      { title: 'The camera you choose', body: 'Any camera in the registry, from any department — in focus, or on a wall of 4, 9 or 16.' },
      { title: 'Its own clock', body: 'Every sighting is timed by the date and time the camera prints on its frame.' },
      { title: 'Alerts reach you anywhere', body: 'This watchlist hit, at another camera, arrived while we watched this one.' },
    ],
    extra: async (s, { rx, rw, cy }) => {
      shot(s, banner, rx + 0.62, cy - 0.1, rw - 0.66)
    },
    notes: [
      'Backup for live step 1. If the live wall is up, skip this slide.',
      'Officers: “This is the camera you chose. The department’s own recorder keeps running; we only read.” Point at the clock on the frame: that printed time, not our laptop’s, is what every sighting carries.',
      'Professors: the local relay (MediaMTX) pulls each camera once and serves both the analytics and every browser from that one connection, so a camera that is analysed and watched still costs its owner one stream. RTSP, ONVIF, NVRs, Hikvision, Dahua, Genetec and Milestone drivers sit behind one interface. Stream passwords stay on the server; operators see rtsp://***@host.',
      'The banner is real: a watchlist hit on Gandhidham Rambaugh arrived while this camera was open. Alerts reach every open console within a second, with a sound.',
      'Shown: Chiman bhai Bridge, Ahmedabad, from the recorded copy of the government grid.',
    ].join('\n\n'),
  })
}

async function readSlide() {
  const s = frame({
    kicker: 'Live · step 2 of 5 · Read',
    title: 'How a frame becomes a sighting',
    notes: [
      'Backup for live step 2, and the slide for the professors. One real frame from the government grid, the four things the edge does to it.',
      '1 Detect and track the vehicle (YOLO11n, a Kalman tracker stepped by the video’s own timestamps, not arrival time). 2 Find the plate (YOLOv9-t) and read it (CCT-XS OCR) on several frames, then vote: a plate is committed only when the frames agree and it fits the Indian registration grammar. 3 Read the date and time burned into the frame (PP-OCRv6), accepted only when a second reading agrees. 4 Store one sighting: camera, printed time, plate, frame.',
      'The numbers are measured on hand-labelled government footage, blind to the OCR’s output. Say the accuracy plainly: 80.5% of vehicles (33 of 41) read exactly after the vote — below our own 85% target. It was 8.6% before we measured; the measurement drove the fixes. If asked about RapidOCR: that reads the camera’s clock (the 97.7%), not plates. Half the plate crops on these wide-angle cameras were unreadable even to a person; no model reads a 20-pixel plate. On-site, that is why we pick cameras by plate yield.',
      'All five models run on ONNX Runtime on this laptop’s CPU, with no internet.',
    ].join('\n\n'),
  })
  const FRAME = 'evidence-frame.jpg'
  const frameImg = await crop(FRAME, { x: 0, y: 0, w: 1920, h: 760 }, 1920)
  const vehicle = await crop(FRAME, { x: 1185, y: 215, w: 360, h: 470 }, 1920)
  const plateZoom = await crop(FRAME, { x: 1292, y: 610, w: 132, h: 42 }, 1920)
  const clock = await crop(FRAME, { x: 0, y: 6, w: 470, h: 66 }, 1920)
  const top = 2.2
  const tileH = 1.6
  const cols = [
    { w: 4.05, label: 'Detect and track', caption: 'A vehicle is found and followed from frame to frame.' },
    { w: 1.23, label: 'Isolate', caption: 'Its box, every frame.' },
    { w: 2.75, label: 'Read the plate', caption: 'Read on several frames; kept only when they agree.' },
    { w: 2.75, label: 'Read the camera’s clock', caption: 'The time printed on the frame, not when it arrived.' },
  ]
  const gap = (CW - cols.reduce((a, c) => a + c.w, 0)) / 3
  let x = M
  for (const [i, col] of cols.entries()) {
    hop(s, i + 1, x + 0.22, 1.86, 0.4)
    text(s, col.label, { x: x + 0.52, y: 1.7, w: col.w + 0.3, h: 0.34, fontFace: BB, fontSize: 15 })
    if (i === 0) {
      shot(s, frameImg, x, top, col.w, { h: tileH })
      // The vehicle's box, where the detector put it.
      const kx = col.w / 1920
      const ky = tileH / 760
      s.addShape(pres.shapes.RECTANGLE, {
        x: x + 1168 * kx, y: top + 222 * ky, w: 343 * kx, h: 448 * ky, fill: { type: 'none' }, line: { color: AMBER, width: 2 },
      })
    } else if (i === 1) {
      shot(s, vehicle, x, top, col.w, { h: tileH })
    } else if (i === 2) {
      shot(s, plateZoom, x, top, col.w, { h: col.w / plateZoom.ratio })
      plate(s, evidence.plate_text, x + 0.2, top + 1.05, { size: 22 })
    } else {
      shot(s, clock, x, top, col.w, { h: col.w / clock.ratio })
      text(s, '17 Jun 2026 · 18:01:21 IST', { x, y: top + 0.62, w: col.w, h: 0.4, fontFace: MONO, bold: true, fontSize: 13 })
      text(s, 'Timbavadi Gate · cam06', { x, y: top + 1.05, w: col.w, h: 0.3, fontFace: MONO, fontSize: 12, color: MUTED })
    }
    text(s, col.caption, { x, y: top + tileH + 0.15, w: col.w, h: 0.55, fontSize: 12.5, color: MUTED })
    if (i < cols.length - 1) {
      s.addShape(pres.shapes.LINE, {
        x: x + col.w + 0.1, y: top + tileH / 2, w: gap - 0.2, h: 0, line: { color: FAINT, width: 1.5, endArrowType: 'triangle' },
      })
    }
    x += col.w + gap
  }
  const stats = [
    ['80.5%', 'plates read exactly', '33 of 41 vehicles, after the vote'],
    ['88.6%', 'plate characters correct', '81 legible plate crops'],
    ['97.7%', 'camera clocks read exactly', '87 legible clocks · none wrong'],
    ['49 ms', 'to find and read a plate', 'per crop, on a laptop CPU'],
  ]
  const sw = (CW - 3 * 0.3) / 4
  for (const [i, [value, label, sub]] of stats.entries()) {
    const sx = M + i * (sw + 0.3)
    panel(s, sx, 4.65, sw, 1.62, i === 0 ? { fill: SIGNAL_TINT, line: SIGNAL_RULE } : {})
    text(s, value, { x: sx + 0.25, y: 4.75, w: sw - 0.5, h: 0.72, fontFace: D, fontSize: 40 })
    text(s, label, { x: sx + 0.25, y: 5.47, w: sw - 0.5, h: 0.34, fontFace: BB, fontSize: 13 })
    text(s, sub, { x: sx + 0.25, y: 5.82, w: sw - 0.5, h: 0.36, fontSize: 11.5, color: MUTED })
  }
  source(s, 'Measured on hand-labelled government-grid footage, blind to the OCR. 79 of 160 plate crops were unreadable even to a person and are excluded. 80.5% is below our own 85% target. evidence/ANPR-ACCURACY.md · evidence/CLOCK-READER-ACCURACY.md', { y: 6.45, w: CW })
}

async function traceSlide() {
  await stepSlide({
    step: 3, name: 'Trace',
    title: 'Type the plate. Every sighting, in order.',
    image: 'find-a-vehicle',
    region: { x: 0, y: 250, w: 1600, h: 715 },
    width: 8.45,
    markers: [[1, 800, 575], [2, 1500, 440], [3, 330, 765]],
    callouts: [
      { title: 'The camera’s own clock', body: 'Each stop is timed by the clock printed on its frame — never by when the video arrived.' },
      { title: 'The evidence at every stop', body: 'The frame, the plate as read, the camera and how the match was made.' },
      { title: 'On the map, in order', body: 'Numbered stops and a replayable route over 24 h, 48 h or 7 days.' },
    ],
    extra: async (s, { imgBottom }) => {
      const y = imgBottom + 0.35
      const half = (CW - 0.3) / 2
      await iconRow(s, { icon: 'LuSpellCheck', x: M, y, w: half, title: 'A misread is shown, not hidden', body: 'One character off comes back as a dashed “probable” stop, with the plate as read, to confirm by eye.' })
      await iconRow(s, { icon: 'LuGauge', x: M + half + 0.3, y, w: half, title: 'An impossible journey is flagged', body: 'Two stops more than 150 km/h apart are flagged, not drawn — a cloned plate stands out.' })
    },
    notes: [
      'Backup for live step 3.',
      'Type the plate — spacing and case do not matter. Every sighting appears on the map and the timeline, in the order the cameras’ own clocks give. Open a stop: camera, the time printed on the frame, the plate as read, the evidence frame.',
      'Be honest about this screenshot before a professor asks: on the government grid each camera replays footage from a different day, so no vehicle there passes two cameras, and this example has one stop. A multi-camera route is exactly what the live trace on today’s cameras shows.',
      'Probable stops: a read one character away, or a look-alike (0/O, 1/I, 8/B, 5/S, 2/Z), is drawn dashed with the plate as read — never silently merged. The 150 km/h check catches cloned plates and clock errors.',
    ].join('\n\n'),
  })
}

async function watchSlide() {
  await stepSlide({
    step: 4, name: 'Watch',
    title: 'Flagged on every screen the moment it is read',
    image: 'alerts',
    region: { x: 20, y: 180, w: 1560, h: 600 },
    width: 8.15,
    markers: [[1, 30, 387], [2, 1555, 470], [3, 948, 342]],
    callouts: [
      { title: 'One row per vehicle, ranked', body: 'Lit amber until someone acts; a banner and a sound on every open console and phone.' },
      { title: 'Evidence before action', body: 'The frame, the camera and the time printed on it — before anyone acts.' },
      { title: 'Every action on the record', body: 'Acknowledge, resolve or “not this vehicle” — each one in the audit log.' },
    ],
    extra: async (s, { imgBottom }) => {
      const py = imgBottom + 0.35
      const pw = 8.15
      panel(s, M, py, pw, 1.0, { fill: INSET })
      await glyph(s, 'LuSpellCheck', M + 0.25, py + 0.32, 0.36, INK)
      text(s, 'It catches the camera’s misreads', { x: M + 0.8, y: py + 0.14, w: 3.3, h: 0.32, fontFace: BB, fontSize: 14 })
      text(s, 'One car at Timbavadi Gate, read both ways today. Either read raises the alert.', { x: M + 0.8, y: py + 0.48, w: 3.4, h: 0.45, fontSize: 11.5, color: MUTED })
      const w1 = plate(s, 'GJ11CD8889', M + 4.45, py + 0.3, { size: 16 })
      text(s, '≈', { x: M + 4.5 + w1, y: py + 0.3, w: 0.35, h: 0.39, align: 'center', valign: 'middle', fontFace: BB, fontSize: 18 })
      plate(s, 'GJ11CDB889', M + 4.9 + w1, py + 0.3, { size: 16 })
    },
    notes: [
      'Backup for live step 4. Live: press “Watch for this vehicle” on the route; it re-checks past reads at once and raises the next sighting on every screen.',
      'Every confirmed read is checked against the watchlist — stolen, wanted, missing, be-on-the-lookout — with priority, case reference and validity.',
      'The misread example is real, from today’s run on Timbavadi Gate: the same blue car read as GJ11CD8889 on some passes and GJ11CDB889 on others. Exact match first, then the look-alike class (0/O, 1/I, 8/B, 5/S, 2/Z), so either read raises the alert.',
      'VAHAN, SARTHI, eGujCop, AFIS and NAFIS connectors are built — retry, circuit breaker, audit — and tested against mock services, because no live credentials exist yet. A rejected credential raises an error; it never reads as “no record”.',
    ].join('\n\n'),
  })
}

async function handoverSlide() {
  const s = frame({
    kicker: 'Live · step 5 of 5 · Hand over',
    title: 'A report that holds up',
    notes: [
      'Backup for live step 5. Live: Export report, then hand the ZIP to the jury.',
      'Officers: the report is the route, the time each camera printed, the plate as read and the evidence frame — in IST, with UTC alongside in the CSV.',
      'Professors: every file in the ZIP is SHA-256-hashed in a manifest, and the report hash binds the PDF and CSV together; change one byte and it no longer verifies. Separately, every search, export, reveal and watchlist change is written to a hash-chained audit log — Admin → Audit log → Verify integrity — and our disaster-recovery drill proved a tampered row is caught.',
    ].join('\n\n'),
  })
  const report = await crop('movement-report', { x: 30, y: 30, w: 1694, h: 960 }, 1754)
  const rw = 6.35
  shot(s, report, M + 0.04, 1.8, rw)
  const rx = M + rw + 0.5
  const w = W - M - rx
  panel(s, rx, 1.8, w, 1.95, { fill: INK, line: INK })
  text(s, 'manifest.json', { x: rx + 0.25, y: 1.92, w: w - 0.5, h: 0.3, fontFace: MONO, bold: true, fontSize: 12, color: AMBER })
  const files = Object.entries(manifest.files).map(([name, f]) => [name.replace(/^evidence\/hop-01-.*\.jpg$/, 'evidence/hop-01.jpg'), f.sha256])
  files.push(['report_sha256', manifest.report_sha256])
  for (const [i, [name, sha]] of files.entries()) {
    const y = 2.3 + i * 0.34 
    text(s, name, { x: rx + 0.25, y, w: 2.1, h: 0.3, fontFace: MONO, fontSize: 11, color: DARK_MUTED })
    text(s, `${sha.slice(0, 16)}…`, { x: rx + 2.35, y, w: w - 2.6, h: 0.3, fontFace: MONO, fontSize: 11, color: DARK_INK })
  }
  const items = [
    { title: 'The camera’s time, in IST and UTC', body: 'As each camera printed it, with the plate as read and the frame.' },
    { title: 'Sealed with SHA-256', body: 'Change one byte of the PDF, CSV or a frame and it no longer verifies.' },
    { title: 'A chain of custody', body: 'Every search, export and reveal is hash-chained; Verify integrity proves none was altered.' },
  ]
  let cy = 4.05
  for (const [i, c] of items.entries()) cy = callout(s, { ...c, n: i + 1, x: rx, y: cy, w, bodySize: 12.5 }) + 0.25
  source(s, `The Movement Report exported for ${evidence.plate_text} from the recorded government grid; page 1 of 2.`)
}

// --- 3. Trust ---------------------------------------------------------------

async function trustSlide() {
  const s = frame({
    kicker: 'Trust',
    title: 'It says what it does not know',
    notes: [
      '[10:00–11:00] The slide for both halves of the room.',
      'Officers: a sighting whose printed clock cannot be read is still a sighting — listed, labelled “time unknown” and kept off the route. We never put a guessed time in an evidence record; that is what holds up under cross-examination.',
      'Professors: the clock reader accepts a time only when a second reading agrees. Replayed across all 30 grid cameras, 37% of stream-seconds get a verified time; the rest are honestly unknown, mostly streams with no legible clock. That number is why we ask organisers whether every feed carries a date-time overlay.',
      'Privacy: no face recognition, by decision — faces are detected only so they can be blurred, and the detector misses some small faces, which we say rather than hide. Access is scoped per department inside the database, and private cameras are viewed or analysed only with current consent.',
    ].join('\n\n'),
  })
  const img = await crop('time-unknown', { x: 752, y: 418, w: 828, h: 545 })
  const w = 6.0
  shot(s, img, W - M - w - 0.04, 1.8, w)
  const items = [
    ['LuClockAlert', '“Time unknown” — never a guess', 'If the clock on a frame cannot be read, the sighting is listed and labelled, and kept off the route.'],
    ['LuScanFace', 'No face recognition', 'By decision. Faces are detected only so they can be blurred.'],
    ['LuBuilding2', 'Each department sees its own', 'Access is enforced inside the database itself, not only in the screens.'],
    ['LuHandshake', 'Private cameras need consent', 'Without current consent a camera is registered, but never viewed or analysed.'],
  ]
  for (const [i, [ic, title, body]] of items.entries()) {
    await iconRow(s, { icon: ic, title, body, x: M, y: 1.85 + i * 1.18, w: CW - w - 0.6, color: i === 0 ? SIGNAL_INK : INK })
  }
  source(s, 'Shown: a vehicle read repeatedly at Gandhidham Rambaugh, on frames whose clock could not be read.')
}

async function proofSlide() {
  const s = frame({
    kicker: 'Trust',
    title: 'Measured, not promised',
    notes: [
      '[11:00–12:30] Say “we measured that” for each row, and read the right-hand panel aloud — the professors will respect it, and the officers will trust the rest more for it.',
      'Plate accuracy: 80.5% of 41 vehicles (33) read exactly, re-measured 12 October, on hand-labelled government footage; it started at 8.6% and the measurement drove the fixes. Clock reading: 97.7% exact on 87 frames with a legible clock, with no wrong times. Capacity: on one base M2 laptop, four cameras analysed at 4 frames a second kept up; eight cameras’ worth did not. Latency: median 27–40 s from the moment in the footage to the stored sighting, p90 67–87 s, across two evidence runs — mostly the multi-frame vote, bought on purpose. DR: a million detections restored in 5.7 s, and a tampered audit row caught. 698 backend and 65 browser tests.',
      'If asked “why 80.5%?”: the cameras are wide-angle; half of all plate crops were unreadable even to a person. Fine-tuning on Gujarat plates and choosing cameras by plate yield are the pilot’s first work items.',
    ].join('\n\n'),
  })
  const rows = [
    ['Plates read exactly', '80.5%', '33 of 41 vehicles, hand-labelled government footage, after the vote'],
    ['Camera clocks read exactly', '97.7%', '87 frames with a legible clock; no wrong times'],
    ['Analysis on one laptop', '4 × 4 fps', 'Four cameras at 4 frames a second kept up (base M2, CPU)'],
    ['Footage to stored sighting', '27–40 s', 'Median over two evidence runs; p90 67–87 s'],
    ['Restore a million records', '5.7 s', 'Disaster-recovery drill; a tampered audit row was caught'],
    ['Automated tests', '763', '698 backend and 65 browser tests, run on every change'],
  ]
  const lw = 7.75
  const rh = 0.7
  text(s, 'MEASURE', { x: M + 0.2, y: 1.78, w: 2.6, h: 0.26, fontFace: MONO, fontSize: 10, color: MUTED })
  text(s, 'RESULT', { x: M + 2.9, y: 1.78, w: 1.4, h: 0.26, fontFace: MONO, fontSize: 10, color: MUTED })
  text(s, 'UNDER WHAT CONDITIONS', { x: M + 4.45, y: 1.78, w: 3.2, h: 0.26, fontFace: MONO, fontSize: 10, color: MUTED })
  for (const [i, [measure, result, conditions]] of rows.entries()) {
    const y = 2.1 + i * (rh + 0.06)
    panel(s, M, y, lw, rh, { radius: 0.04 })
    text(s, measure, { x: M + 0.2, y, w: 2.6, h: rh, valign: 'middle', fontFace: BB, fontSize: 14 })
    text(s, result, { x: M + 2.9, y, w: 1.45, h: rh, valign: 'middle', fontFace: D, fontSize: 24 })
    text(s, conditions, { x: M + 4.45, y, w: lw - 4.6, h: rh, valign: 'middle', fontSize: 12, color: MUTED })
  }
  const px = M + lw + 0.4
  const pw = W - M - px
  panel(s, px, 1.78, pw, 4.85, { fill: SIGNAL_TINT, line: SIGNAL_RULE })
  await glyph(s, 'LuMessageSquareWarning', px + 0.3, 2.0, 0.4, SIGNAL_INK)
  text(s, 'Stated plainly', { x: px + 0.85, y: 2.02, w: pw - 1.1, h: 0.38, fontFace: D, fontSize: 22 })
  const limits = [
    'Plate accuracy is below our own 85% target.',
    'Near-real-time, for investigation — not for lifting a boom gate.',
    'The grid’s footage cannot show a multi-camera route; today’s live trace does.',
    'Statewide sizing is arithmetic, not an 80,000-camera load test.',
    'VAHAN and eGujCop connectors run against mocks until access is granted.',
    'Matching a vehicle whose plate is never read is designed, not built.',
  ]
  s.addText(limits.map((l, i) => ({ text: l, options: { bullet: { indent: 14 }, breakLine: i < limits.length - 1 } })), {
    x: px + 0.3, y: 2.6, w: pw - 0.55, h: 3.9, margin: 0, fontFace: B, fontSize: 13.5, color: INK, paraSpaceAfter: 7, valign: 'top',
  })
  source(s, 'evidence/ANPR-ACCURACY.md · CLOCK-READER-ACCURACY.md · TIER-CAPACITY.md · M14-EVIDENCE-RUN(-FINDINGS).md · DR-RESTORE-DRILL.md')
}

// --- 4. Scale ---------------------------------------------------------------

async function onboardSlide() {
  const s = frame({
    kicker: 'Scale',
    title: 'Bring the cameras you already have',
    notes: [
      '[12:30–13:15] For the officers: nothing is replaced. For the professors: catalogue-driven discovery, never hard-coded camera IDs.',
      'Three ways in: a department’s catalogue synced in one step — that is how all 30 grid cameras were onboarded; a camera list uploaded as CSV, checked row by row in a dry run before anything is added; or a device on the network — an ONVIF camera or an NVR — whose streams are listed before you add them.',
      'Each camera carries a tier — continuous, sampled, motion-triggered or view-only — that the department sets and can change live; the edge picks it up within 30 seconds without a restart. That is how analysis is spent where plates are legible.',
    ].join('\n\n'),
  })
  const map = await crop('cameras-map', { x: 20, y: 380, w: 1560, h: 446 })
  const mw = CW
  shot(s, map, M + 0.04, 1.75, mw - 0.08)
  const y = 1.75 + (mw - 0.08) / map.ratio + 0.4
  const items = [
    ['LuRefreshCw', 'Sync a catalogue', 'How all 30 grid cameras were onboarded.'],
    ['LuFileSpreadsheet', 'Upload a camera list', 'Every row checked in a dry run first.'],
    ['LuScanSearch', 'Discover devices', 'ONVIF cameras and NVRs; streams listed first.'],
    ['LuSlidersHorizontal', 'Set each camera’s tier', 'Live changes apply in 30 s, no restart.'],
  ]
  const iw = (CW - 3 * 0.3) / 4
  for (const [i, [ic, title, body]] of items.entries()) {
    await iconRow(s, { icon: ic, title, body, x: M + i * (iw + 0.3), y, w: iw })
  }
  source(s, '30 government cameras across 8 districts, onboarded from the live catalogue: H.264 and H.265, 576p to 1440p. 9 have no recorded location and are listed, not mapped.')
}

async function architectureSlide() {
  const s = frame({
    kicker: 'Scale',
    title: 'Analyse where it is filmed. Send meaning, not video.',
    notes: [
      '[13:15–15:00] The argument the design rests on. One breath per box, left to right.',
      'Cameras, tiered: not every camera needs AI; a highway check-post and a ration-shop godown are different jobs. Department systems stay as they are; we pull read-only and their 7–15 days of recording stay where they are. Each district decodes and reads plates on its own video; what leaves is a 1 KB event and a 30 KB snapshot, and if the link drops it keeps reading against a cached watchlist and queues up to 72 hours. The state core is search, storage and alerts, with a warm disaster-recovery site. At the end, the people and systems that act.',
      'Then the physics: pulling every camera’s video to one centre needs about 160 gigabits a second, sustained, from sites a thousand kilometres apart, and 12 petabytes for one week. Sending what we find needs about 140 megabits and 390 terabytes.',
      '“What you saw today is the district box, on one laptop — the same code.” Every figure re-derives from five formulas in our scale plan; offer to recompute with their camera mix.',
    ].join('\n\n'),
  })
  const nodes = [
    ['LuCctv', '80,000 cameras', 'Tiered: continuous, sampled, motion-triggered or view-only.'],
    ['LuBuilding2', 'Department systems', 'Unchanged. Their 7–15 days of recording stay where they are.'],
    ['LuCpu', 'District edge ×34', 'Reads plates where the video is. Keeps working offline for 72 h.'],
    ['LuDatabase', 'State core', 'Search, watchlist, alerts. Warm DR site: RPO 15 min, RTO 1 h.'],
    ['LuUsers', 'Officers and systems', 'Control rooms, field phones, VAHAN · SARTHI · eGujCop.'],
  ]
  const gap = 0.42
  const nw = (CW - 4 * gap) / 5
  const top = 1.8
  const nh = 2.55
  for (const [i, [ic, title, body]] of nodes.entries()) {
    const x = M + i * (nw + gap)
    const edge = i === 2
    panel(s, x, top, nw, nh, edge ? { fill: INK, line: INK } : {})
    await glyph(s, ic, x + 0.22, top + 0.22, 0.42, edge ? AMBER : INK)
    text(s, title, { x: x + 0.22, y: top + 0.76, w: nw - 0.4, h: 0.62, fontFace: D, fontSize: 19, color: edge ? DARK_INK : INK, valign: 'bottom' })
    text(s, body, { x: x + 0.22, y: top + 1.46, w: nw - 0.4, h: 1.0, fontSize: 12.5, color: edge ? DARK_MUTED : MUTED })
    if (i < nodes.length - 1) {
      s.addShape(pres.shapes.LINE, {
        x: x + nw + 0.06, y: top + nh / 2, w: gap - 0.12, h: 0, line: { color: INK, width: 1.5, endArrowType: 'triangle' },
      })
    }
  }
  const ex = M + 2 * (nw + gap)
  s.addShape(pres.shapes.RECTANGLE, { x: ex, y: top + nh + 0.12, w: nw, h: 0.34, fill: { color: AMBER }, line: { color: AMBER } })
  text(s, 'TODAY: ONE LAPTOP', { x: ex, y: top + nh + 0.12, w: nw, h: 0.34, align: 'center', valign: 'middle', fontFace: MONO, bold: true, fontSize: 10.5, color: INK })
  const sx = M + 3 * (nw + gap)
  text(s, '≈31 KB per sighting arrives', {
    x: sx, y: top + nh + 0.14, w: nw, h: 0.3, align: 'center', fontFace: MONO, fontSize: 10, color: MUTED,
  })

  const cy = 5.05
  const half = (CW - 0.3) / 2
  const compare = [
    ['Centralise all video', '160 Gbps', '12.1 PB', 'sustained backbone', 'hot storage for one week', false],
    ['Sentinel: analyse at the edge', '≈140 Mbps', '≈390 TB', 'events and snapshots', 'selective, usable', true],
  ]
  for (const [i, [label, net, store, netSub, storeSub, ours]] of compare.entries()) {
    const x = M + i * (half + 0.3)
    panel(s, x, cy, half, 1.55, ours ? { fill: SIGNAL_TINT, line: SIGNAL_RULE } : {})
    text(s, label, { x: x + 0.3, y: cy + 0.15, w: half - 0.6, h: 0.32, fontFace: BB, fontSize: 14, color: ours ? INK : MUTED })
    text(s, net, { x: x + 0.3, y: cy + 0.5, w: 2.6, h: 0.6, fontFace: D, fontSize: 34, color: ours ? INK : MUTED })
    text(s, netSub, { x: x + 0.3, y: cy + 1.1, w: 2.6, h: 0.3, fontSize: 12, color: MUTED })
    text(s, store, { x: x + 3.0, y: cy + 0.5, w: 2.6, h: 0.6, fontFace: D, fontSize: 34, color: ours ? INK : MUTED })
    text(s, storeSub, { x: x + 3.0, y: cy + 1.1, w: 2.6, h: 0.3, fontSize: 12, color: MUTED })
  }
  source(s, 'Statewide figures are planning arithmetic for ~80,000 cameras at 2 Mbps (docs/04-SCALE-PLAN.md), not a deployment: ≈1,000× less network, ≈30× less storage.')
}

async function costSlide() {
  const s = frame({
    kicker: 'Scale',
    title: 'What it costs, to an order of magnitude',
    notes: [
      '[15:00–16:30] Say “order of magnitude, for comparing approaches — not a tender” before the first number.',
      'About ₹80 crore to build and ₹24 crore a year to run, for eighty thousand cameras: roughly ₹10,000 a camera to build and ₹3,000 a year to run. No software licences — at this scale per-camera VMS fees often outweigh the hardware. Centralising every camera is conservatively ₹400 crore or more to build, before its higher running cost.',
      'The largest line, district analysis servers, rests on a vendor GPU benchmark and our camera-tier split; the pilot’s first exit criterion is measuring both. The saving is reuse: no camera, recorder or VMS is replaced, and GSWAN carries the backhaul.',
    ].join('\n\n'),
  })
  s.addChart(pres.charts.BAR, [{
    name: 'Build cost',
    labels: ['District analysis servers', 'State data centre', 'Integration and rollout', 'Remote edge boxes', 'District uplinks', 'Disaster-recovery site'],
    values: [28, 14, 12, 10.5, 9, 7],
  }], {
    x: M, y: 1.75, w: 6.9, h: 4.3, barDir: 'bar', barGapWidthPct: 40,
    chartColors: [INK2],
    catAxisOrientation: 'maxMin',
    showValue: true, dataLabelPosition: 'outEnd', dataLabelColor: INK, dataLabelFontSize: 13,
    dataLabelFontBold: true, dataLabelFontFace: B, dataLabelFormatCode: '"₹"General" cr"',
    catAxisLabelColor: INK, catAxisLabelFontSize: 13, catAxisLabelFontFace: B,
    valAxisHidden: true, valAxisMaxVal: 34, valGridLine: { style: 'none' }, catGridLine: { style: 'none' },
    catAxisLineShow: false, showLegend: false,
    showTitle: true, title: 'Build cost (capex), ₹ crore', titleColor: MUTED, titleFontSize: 13, titleFontFace: B,
  })
  const x = M + 7.3
  const w = W - M - x
  const cw = (w - 0.3) / 2
  const stats = [
    ['≈₹80 cr', 'to build', true],
    ['≈₹24 cr', 'a year to run', true],
    ['≈₹10,000', 'per camera to build', false],
    ['₹0', 'in software licences', false],
  ]
  for (const [i, [value, label, signal]] of stats.entries()) {
    const cx = x + (i % 2) * (cw + 0.3)
    const cy = 1.85 + Math.floor(i / 2) * 1.5
    panel(s, cx, cy, cw, 1.28, signal ? { fill: SIGNAL_TINT, line: SIGNAL_RULE } : {})
    text(s, value, { x: cx + 0.25, y: cy + 0.16, w: cw - 0.5, h: 0.65, fontFace: D, fontSize: 32 })
    text(s, label, { x: cx + 0.25, y: cy + 0.82, w: cw - 0.5, h: 0.32, fontSize: 13, color: MUTED })
  }
  panel(s, x, 4.95, w, 1.1, { fill: INSET })
  text(s, [
    { text: 'Centralising every camera: ₹400 cr+ to build', options: { fontFace: BB, color: INK, breakLine: true } },
    { text: 'About five times more, before its higher running cost.', options: { color: MUTED } },
  ], { x: x + 0.25, y: 5.05, w: w - 0.5, h: 0.9, fontSize: 13.5, valign: 'middle' })
  source(s, 'Order of magnitude for ~80,000 cameras, from docs/04-SCALE-PLAN.md §6 — not a tender. Five-year cost of ownership ≈₹200 cr. The pilot replaces each estimate with a measurement.', { y: 6.45, w: CW })
}

// --- 5. Next ----------------------------------------------------------------

async function nextSlide() {
  const s = frame({
    dark: true,
    kicker: 'Next',
    title: 'Start with one district.',
    titleSize: 44,
    notes: [
      '[16:30–18:00] Each phase is useful on its own; none needs a switch-over.',
      'One district and two departments in three months, with exit criteria we measure rather than promise: plate accuracy on live feeds, GPU throughput, and operators signing off. Then four districts and the main VMS vendors, then every district, then consented private cameras.',
      'To begin we need three things: each department’s camera inventory, read-only access to its streams or VMS, and access to VAHAN and eGujCop when it is ready.',
      'Close on the line, then stop and wait: “Type a plate. See where it went. Thank you.”',
    ].join('\n\n'),
  })
  const phases = [
    ['PILOT', '0–3 months', '≈500', '1 district · 2 departments'],
    ['EXPAND', '3–9 months', '≈5,000', '4 districts · main VMS vendors'],
    ['STATEWIDE', '9–21 months', '≈30,000', 'All 34 districts'],
    ['COMPLETE', '21–36 months', '80,000', 'Plus consented private cameras'],
  ]
  const pw = (CW - 3 * 0.25) / 4
  for (const [i, [name, when, count, scope]] of phases.entries()) {
    const x = M + i * (pw + 0.25)
    const first = i === 0
    s.addShape(pres.shapes.RECTANGLE, { x, y: 1.9, w: pw, h: 1.95, fill: { color: first ? AMBER : DARK_PANEL }, line: { color: first ? AMBER : DARK_RULE, width: 0.75 } })
    text(s, `${name} · ${when}`, { x: x + 0.25, y: 2.05, w: pw - 0.5, h: 0.3, fontFace: MONO, bold: true, fontSize: 11, color: first ? INK : AMBER })
    text(s, count, { x: x + 0.25, y: 2.42, w: pw - 0.5, h: 0.7, fontFace: D, fontSize: 38, color: first ? INK : DARK_INK })
    text(s, `cameras · ${scope}`, { x: x + 0.25, y: 3.15, w: pw - 0.5, h: 0.55, fontSize: 12.5, color: first ? INK : DARK_MUTED })
  }
  text(s, 'To begin, we need', { x: M, y: 4.2, w: 5, h: 0.36, fontFace: BB, fontSize: 16, color: DARK_INK })
  const asks = [
    ['LuListChecks', 'Each department’s camera inventory'],
    ['LuKeyRound', 'Read-only access to its streams or VMS'],
    ['LuDatabaseZap', 'VAHAN and eGujCop access, when ready'],
  ]
  const aw = (CW - 2 * 0.3) / 3
  for (const [i, [ic, label]] of asks.entries()) {
    const x = M + i * (aw + 0.3)
    s.addShape(pres.shapes.RECTANGLE, { x, y: 4.65, w: aw, h: 0.72, fill: { color: DARK_PANEL }, line: { color: DARK_RULE, width: 0.75 } })
    await glyph(s, ic, x + 0.2, 4.83, 0.36, AMBER)
    text(s, label, { x: x + 0.72, y: 4.65, w: aw - 0.9, h: 0.72, valign: 'middle', fontSize: 14, color: DARK_INK })
  }
  text(s, 'Type a plate. See where it went.', { x: M, y: 5.75, w: 8, h: 0.7, fontFace: D, fontSize: 36, color: DARK_INK })
  text(s, 'Thank you — questions welcome.', { x: M, y: 6.45, w: 6, h: 0.35, fontSize: 15, color: DARK_MUTED })
}

// --- Appendix ---------------------------------------------------------------

const APPENDIX = [
  ['A1', 'Tech stack', 'Every part, and why it was chosen'],
  ['A2', 'Our approach', 'A hybrid of the four reference models'],
  ['A3', 'Camera tiers', 'How 80,000 cameras are sized'],
  ['A4', 'Cost, line by line', 'Build and run'],
  ['A5', 'Beyond number plates', 'Vehicles, people, zones, tamper'],
  ['A6', 'Field app and languages', 'Phones, Hindi and Gujarati'],
  ['A7', 'Operations', 'Health checks and integrations'],
  ['A8', 'Approaches compared', 'Separate, centralised, Sentinel'],
  ['A9', 'When the plate is unreadable', 'What exists, what is designed'],
]

function appendixDivider() {
  section.appendix = true
  const s = pres.addSlide()
  s.background = { color: DARK }
  text(s, 'APPENDIX', { x: M, y: 0.6, w: 6, h: 0.3, fontFace: MONO, bold: true, fontSize: 11, color: AMBER, charSpacing: 1 })
  text(s, 'For questions', { x: M, y: 0.95, w: 8, h: 0.9, fontFace: D, fontSize: 44, color: DARK_INK })
  const cw = (CW - 0.3) / 2
  for (const [i, [id, title, sub]] of APPENDIX.entries()) {
    const x = M + (i % 2) * (cw + 0.3)
    const y = 2.15 + Math.floor(i / 2) * 0.88
    s.addShape(pres.shapes.RECTANGLE, { x, y, w: cw, h: 0.72, fill: { color: DARK_PANEL }, line: { color: DARK_RULE, width: 0.75 } })
    text(s, id, { x: x + 0.2, y, w: 0.6, h: 0.72, valign: 'middle', fontFace: MONO, bold: true, fontSize: 14, color: AMBER })
    text(s, title, { x: x + 0.85, y: y + 0.1, w: cw - 1.0, h: 0.3, fontFace: BB, fontSize: 15, color: DARK_INK })
    text(s, sub, { x: x + 0.85, y: y + 0.4, w: cw - 1.0, h: 0.26, fontSize: 12, color: DARK_MUTED })
  }
  s.addNotes('Jump here for questions; each appendix slide stands alone.')
}

async function stackSlide() {
  const s = frame({
    kicker: 'Tech stack',
    title: 'Open, proven parts, each chosen for one job',
    notes: 'For the professors, one line per layer and the reason. At the edge, Python and OpenCV around ONNX Runtime: five small models — vehicles, plates, plate characters, faces to blur, and the camera’s own clock — run unchanged on a laptop or a district GPU, with no internet. The tracker is our own Kalman filter, stepped by the video’s timestamps. MediaMTX pulls each camera once and serves analytics and browsers from that connection. The core is FastAPI over one PostgreSQL: PostGIS for the map, TimescaleDB for sightings over time, trigram search for misread plates; NATS JetStream carries events. The console is React and TypeScript with MapLibre, installable on a phone, in three languages. Everything is open source; the one copyleft piece is the vehicle detector (AGPL-3.0), with an Apache-2.0 replacement (RF-DETR) identified.',
  })
  const rows = [
    ['LuCpu', 'Edge analytics', 'Python 3.13 · OpenCV · ONNX Runtime · Kalman tracker on video timestamps\nYOLO11n vehicles · YOLOv9-t plates · CCT-XS plate OCR · YuNet faces · PP-OCRv6 clock', 'Same models on a laptop or a district GPU; no internet'],
    ['LuVideo', 'Video relay', 'MediaMTX: one pull per camera\nRTSP to analytics · HLS and WebRTC to browsers', 'One connection, however many watch'],
    ['LuDatabase', 'Core platform', 'FastAPI · async SQLAlchemy · NATS JetStream\nPostgreSQL 17 + PostGIS · TimescaleDB · pg_trgm', 'One database for map, time and misread search'],
    ['LuMonitorSmartphone', 'Console and field app', 'React 19 + TypeScript · Vite · MapLibre GL · hls.js\nInstallable PWA · English · हिन्दी · ગુજરાતી', 'Any browser; installs on a phone'],
    ['LuShieldCheck', 'Security and engineering', 'JWT + bcrypt · row-level security per department · nginx mTLS · hash-chained audit\nDocker · uv · ruff · mypy · pytest · Playwright', 'Every change linted, type-checked and tested'],
  ]
  const rh = 0.84
  for (const [i, [ic, layer, parts, why]] of rows.entries()) {
    const y = 1.75 + i * (rh + 0.08)
    panel(s, M, y, CW, rh, { radius: 0.04 })
    await glyph(s, ic, M + 0.22, y + 0.24, 0.36, INK)
    text(s, layer, { x: M + 0.8, y, w: 2.3, h: rh, valign: 'middle', fontFace: BB, fontSize: 14 })
    text(s, parts, { x: M + 3.15, y, w: 6.1, h: rh, valign: 'middle', fontSize: 11.5 })
    text(s, why, { x: M + 9.45, y, w: CW - 9.65, h: rh, valign: 'middle', fontSize: 11.5, color: MUTED })
  }
  source(s, 'All open source, no licence fees. One copyleft part: the YOLO11n vehicle detector (AGPL-3.0), with an Apache-2.0 swap (RF-DETR) identified.', { y: 6.45 })
}

async function approachSlide() {
  const s = frame({
    kicker: 'Our approach',
    title: 'A hybrid of the four reference models',
    notes: 'This answers the brief’s “which model, and why”. Model 1’s registry and GIS is the foundation everything stands on. Model 2 gives one console that views and analyses every accessible stream. Model 3’s adapters mean no department changes its system — a new vendor is a driver, verified by a conformance suite. Model 4’s central recording is used only where it pays off — critical cameras and alert clips — because full centralisation needs a backbone the State does not have (slide 11).',
  })
  const models = [
    ['MODEL 1', 'Registry and GIS', 'Every camera on one map, with health, coverage gaps and an ageing-asset work list.', 'FOUNDATION', 'Everything else stands on it.'],
    ['MODEL 2', 'Unified viewing and analytics', 'One live wall, and plate reading on every accessible stream.', 'ADOPTED', 'One console, not one per department.'],
    ['MODEL 3', 'Federation adapters', 'RTSP, ONVIF, Hikvision, Dahua, Genetec and Milestone drivers behind one interface.', 'ADOPTED', 'A new vendor is a driver, not a rebuild.'],
    ['MODEL 4', 'Central recording', 'Only critical cameras and alert clips are recorded centrally.', 'SELECTIVE', 'All of it needs a backbone the State lacks.'],
  ]
  const cw = (CW - 3 * 0.3) / 4
  for (const [i, [tag, name, body, pill, why]] of models.entries()) {
    const x = M + i * (cw + 0.3)
    panel(s, x, 1.8, cw, 4.2)
    s.addShape(pres.shapes.LINE, { x: x + 0.25, y: 5.05, w: cw - 0.5, h: 0, line: { color: RULE, width: 0.75 } })
    text(s, why, { x: x + 0.25, y: 5.15, w: cw - 0.5, h: 0.75, fontFace: BB, fontSize: 13 })
    s.addShape(pres.shapes.RECTANGLE, { x: x + 0.25, y: 2.05, w: 1.45, h: 0.32, fill: { color: i === 3 ? INSET : INK }, line: { color: i === 3 ? RULE : INK } })
    text(s, pill, { x: x + 0.25, y: 2.05, w: 1.45, h: 0.32, align: 'center', valign: 'middle', fontFace: MONO, bold: true, fontSize: 10, color: i === 3 ? MUTED : WHITE })
    text(s, tag, { x: x + 0.25, y: 2.6, w: cw - 0.5, h: 0.28, fontFace: MONO, fontSize: 11, color: MUTED })
    text(s, name, { x: x + 0.25, y: 2.92, w: cw - 0.5, h: 0.85, fontFace: D, fontSize: 22 })
    text(s, body, { x: x + 0.25, y: 3.85, w: cw - 0.5, h: 1.1, fontSize: 13.5, color: MUTED })
  }
  source(s, 'Read-only and pull-based throughout: nothing is installed on a department’s cameras or VMS.', { y: 6.3 })
}

async function tierSlide() {
  const s = frame({
    kicker: 'Camera tiers',
    title: 'Not every camera needs the same attention',
    notes: 'About one camera in eight reads plates continuously; a quarter are view-only. The tier is a setting each department controls and can change live — a camera goes to continuous for a bandobast and back afterwards. Be clear the split is our planning assumption, not a survey; department inventories replace it in the pilot. Compute and cost on the cost slide are sized from it: about 560 L4 GPUs with N+1 across 34 district nodes.',
  })
  s.addChart(pres.charts.DOUGHNUT, [{
    name: 'Cameras by tier',
    labels: ['Continuous', 'Sampled', 'Motion-triggered', 'View only'],
    values: [9600, 22400, 28000, 20000],
  }], {
    x: M, y: 1.75, w: 4.8, h: 4.8, holeSize: 60,
    chartColors: [AMBER, INK2, FAINT, RULE],
    showLegend: false, showValue: false, showPercent: true, showLabel: false,
    dataLabelColor: INK, dataLabelFontSize: 13, dataLabelFontFace: B, dataLabelFontBold: true, showTitle: false,
  })
  text(s, '80,000', { x: M + 1.4, y: 3.75, w: 2.0, h: 0.55, align: 'center', fontFace: D, fontSize: 30 })
  text(s, 'cameras', { x: M + 1.4, y: 4.3, w: 2.0, h: 0.3, align: 'center', fontSize: 13, color: MUTED })
  const x = M + 5.3
  const w = CW - 5.3
  const tiers = [
    [AMBER, 'Continuous', '9,600', 'Check-posts, highways, city entry points'],
    [INK2, 'Sampled', '22,400', 'Junctions, markets and public spaces'],
    [FAINT, 'Motion-triggered', '28,000', 'Godowns, offices and quiet premises'],
    [RULE, 'View only', '20,000', 'Indoor, admin and consented private feeds'],
  ]
  for (const [i, [color, name, count, use]] of tiers.entries()) {
    const y = 1.9 + i * 0.95
    panel(s, x, y, w, 0.8, { radius: 0.04 })
    s.addShape(pres.shapes.RECTANGLE, { x: x + 0.25, y: y + 0.27, w: 0.26, h: 0.26, fill: { color }, line: { color: FAINT, width: 0.5 } })
    text(s, name, { x: x + 0.7, y, w: 2.2, h: 0.8, valign: 'middle', fontFace: BB, fontSize: 15 })
    text(s, use, { x: x + 2.95, y, w: w - 4.5, h: 0.8, valign: 'middle', fontSize: 12.5, color: MUTED })
    text(s, count, { x: x + w - 1.45, y, w: 1.2, h: 0.8, valign: 'middle', align: 'right', fontFace: D, fontSize: 20 })
  }
  panel(s, x, 5.8, w, 0.75, { fill: SIGNAL_TINT, line: SIGNAL_RULE })
  text(s, 'Each department sets the tier and can change it live — continuous for a bandobast, back afterwards.', {
    x: x + 0.25, y: 5.8, w: w - 0.5, h: 0.75, valign: 'middle', fontSize: 13.5,
  })
  source(s, 'Planning assumption, not a survey: the ~80,000 total is from the brief; the split is our estimate. Department inventories replace it in the pilot.')
}

async function costDetailSlide() {
  const s = frame({
    kicker: 'Cost, line by line',
    title: 'Build ≈₹80 crore · run ≈₹24 crore a year',
    notes: 'If a juror asks how the totals are made up. Every line re-derives from docs/04-SCALE-PLAN.md §6. The biggest build line, district analysis servers (140 servers × 4 L4 GPUs), rests on a vendor GPU benchmark; Phase 0 measures it. AMC is about 12% of hardware a year. Software licences are zero.',
  })
  const build = [
    ['District analysis servers (140 × 4 L4 GPUs)', '28'],
    ['State data centre (compute, 600 TB, network, HA)', '14'],
    ['Integration, migration, training, rollout', '12'],
    ['Remote edge boxes (≈1,500)', '10.5'],
    ['District uplink upgrades (GSWAN reused)', '9'],
    ['Disaster-recovery site (warm standby)', '7'],
    ['Software licences', '0'],
  ]
  const run = [
    ['Power, cooling, data-centre space', '5'],
    ['Network and bandwidth', '7'],
    ['AMC and support (≈12% of hardware)', '8'],
    ['Operations team (NOC, L1–L3)', '4'],
  ]
  const tables = [['BUILD (CAPEX)', build, '≈80'], ['RUN (OPEX, A YEAR)', run, '≈24']]
  const tw = (CW - 0.4) / 2
  for (const [t, [label, lines, total]] of tables.entries()) {
    const x = M + t * (tw + 0.4)
    text(s, label, { x, y: 1.78, w: tw - 1.2, h: 0.28, fontFace: MONO, fontSize: 10.5, color: MUTED })
    text(s, '₹ CR', { x: x + tw - 1.2, y: 1.78, w: 1.0, h: 0.28, align: 'right', fontFace: MONO, fontSize: 10.5, color: MUTED })
    const all = [...lines, ['Total', total]]
    for (const [i, [name, value]] of all.entries()) {
      const y = 2.12 + i * 0.56
      const last = i === all.length - 1
      panel(s, x, y, tw, 0.48, { radius: 0.03, ...(last ? { fill: SIGNAL_TINT, line: SIGNAL_RULE } : {}) })
      text(s, name, { x: x + 0.2, y, w: tw - 1.5, h: 0.48, valign: 'middle', fontSize: 13, fontFace: last ? BB : B })
      text(s, value, { x: x + tw - 1.2, y, w: 1.0, h: 0.48, valign: 'middle', align: 'right', fontFace: D, fontSize: 18 })
    }
  }
  source(s, 'Order of magnitude for comparing approaches, not a tender. docs/04-SCALE-PLAN.md §6.', { y: 6.75 })
}

async function beyondSlide() {
  const s = frame({
    kicker: 'Beyond number plates',
    title: 'More than plates — never identities',
    notes: 'The same cameras answer more questions at no extra effort: vehicle type and colour on every read, people counted per camera and held to zones, intrusion and loitering zones, wrong-way and stopped vehicles, and camera tamper — covered, blurred or moved — raised with before-and-after frames and closed when restored. Vehicle colour is a heuristic, not a trained classifier; say so if asked. People are counted, never identified.',
  })
  const img = await crop('cameras-table', { x: 20, y: 346, w: 1560, h: 270 })
  const h = shot(s, img, M + 0.04, 1.8, CW - 0.08)
  const tiles = [
    ['LuCar', 'Vehicle type and colour', 'On every read.'],
    ['LuUsers', 'People counted', 'Held to zones; never identified.'],
    ['LuCrosshair', 'Zones', 'Intrusion, loitering, wrong-way, stopped.'],
    ['LuCameraOff', 'Camera tamper', 'Covered, blurred or moved: raised and closed itself.'],
  ]
  const iw = (CW - 3 * 0.3) / 4
  const y = 1.8 + h + 0.4
  for (const [i, [ic, title, body]] of tiles.entries()) {
    await iconRow(s, { icon: ic, title, body, x: M + i * (iw + 0.3), y, w: iw })
  }
  source(s, 'Shown: the camera table — tier, analysis rate, people and vehicles in view, and tamper state per camera.')
}

async function fieldSlide() {
  const s = frame({
    kicker: 'Field app and languages',
    title: 'On an officer’s phone, in their language',
    notes: 'The field app installs from the browser: alerts, a plate lookup, nearby cameras, and a sighting report that queues offline and sends when signal returns. The console runs in English, Hindi and Gujarati, in light and dark themes for day offices and dark control rooms.',
  })
  const phone = await whole('field-pwa')
  const ph = 4.95
  const pw = ph * phone.ratio
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: M + 0.3 - 0.12, y: 1.8 - 0.12, w: pw + 0.24, h: ph + 0.24, rectRadius: 0.28, fill: { color: INK }, line: { color: INK },
  })
  s.addImage({ data: phone.data, x: M + 0.3, y: 1.8, w: pw, h: ph })
  const gu = await crop('overview-gujarati', { x: 0, y: 95, w: 1600, h: 870 })
  const gx = M + pw + 1.0
  shot(s, gu, gx, 1.8, W - M - gx - 0.04)
  source(s, 'Left: the field app on a phone. Right: the operations overview in Gujarati.')
}

async function opsSlide() {
  const s = frame({
    kicker: 'Operations',
    title: 'Checked, and honest about what is a mock',
    notes: 'The Health screen runs the integrator compliance checks continuously: RTSP over TCP, timing from the video’s own timestamps, reconnect backoff, catalogue-driven discovery, mixed codecs, and publishing to the government gateway disabled. Integrations shows each government connector with its last test; they are marked “Connected (mock)” because no live credentials exist yet — the client, retry, circuit breaker and audit are real.',
  })
  const health = await crop('health', { x: 0, y: 180, w: 1320, h: 700 })
  const integ = await crop('integrations', { x: 0, y: 240, w: 1600, h: 620 })
  const hw = (CW - 0.4) / 2
  shot(s, health, M + 0.04, 1.8, hw - 0.08)
  shot(s, integ, M + hw + 0.4, 1.8, hw - 0.04)
  source(s, 'Left: integrator compliance on the Health screen. Right: government connectors — VAHAN, SARTHI, eGujCop, AFIS, NAFIS — tested against mocks.')
}

async function compareSlide() {
  const s = frame({
    kicker: 'Approaches compared',
    title: 'Why not leave it, or centralise it?',
    notes: 'Two other ways to do this. Leave every department on its own system — nothing changes, and nothing connects. Or pull every camera into one central system — it connects everything, but re-routes all the video, needs a backbone the State does not have, and stops when a link drops. Sentinel gets the reach of the second without disturbing the first. Approaches, not named products.',
  })
  const cols = ['Separate systems', 'Centralise every camera', 'Sentinel']
  const rows = [
    ['Trace a vehicle across departments', 'Phone calls, manual review', 'Yes', 'One search'],
    ['Watchlist alerts statewide', 'Each system on its own', 'Yes', 'Every read, automatically'],
    ['Department systems untouched', 'Untouched, but isolated', 'All video re-routed', 'Read-only access'],
    ['Network the State must provide', 'Little', '≈160 Gbps sustained', '≈140 Mbps'],
    ['When a district link drops', 'Local only', 'Analysis stops', 'Keeps reading, 72 h queue'],
  ]
  const lw = 3.4
  const cw = (CW - lw) / 3
  const top = 1.85
  panel(s, M + lw + 2 * cw, top - 0.05, cw, 0.62 + rows.length * 0.78 + 0.1, { fill: SIGNAL_TINT, line: SIGNAL_RULE })
  for (const [j, c] of cols.entries()) {
    text(s, c, { x: M + lw + j * cw + 0.25, y: top, w: cw - 0.5, h: 0.55, valign: 'middle', fontFace: j === 2 ? D : BB, fontSize: j === 2 ? 22 : 14, color: j === 2 ? INK : MUTED })
  }
  for (const [i, [label, ...cells]] of rows.entries()) {
    const y = top + 0.62 + i * 0.78
    s.addShape(pres.shapes.LINE, { x: M, y, w: CW, h: 0, line: { color: RULE, width: 0.75 } })
    text(s, label, { x: M, y, w: lw - 0.2, h: 0.78, valign: 'middle', fontFace: BB, fontSize: 14 })
    for (const [j, value] of cells.entries()) {
      text(s, value, { x: M + lw + j * cw + 0.25, y, w: cw - 0.5, h: 0.78, valign: 'middle', fontSize: 13.5, color: j === 2 ? INK : MUTED, fontFace: j === 2 ? BB : B })
    }
  }
  source(s, 'Approaches compared, not products. Network figures are for ~80,000 cameras, from docs/04-SCALE-PLAN.md.', { y: 6.6 })
}

async function unreadableSlide() {
  const s = frame({
    kicker: 'When the plate is unreadable',
    title: 'What exists today, and what is only designed',
    notes: 'Be precise. Built: exact matching; the look-alike class (0/O, 1/I, 8/B, 5/S, 2/Z); one-character-off reads returned as dashed probable stops; a bridge across a partly read plate when the last four characters agree, vehicle class and colour match, and the hop is reachable at road speed; and the 150 km/h feasibility gate. Designed and costed, not built: full appearance re-identification for a vehicle whose plate is never read (docs/14-APPEARANCE-REID-DESIGN.md). Never say it matches vehicles with no plate read.',
  })
  const rungs = [
    ['Exact', 'A clean read', 'Solid stop', true],
    ['Look-alike characters', '0↔O, 1↔I, 8↔B, 5↔S, 2↔Z', 'Solid stop', true],
    ['One character off', 'A single misread character', 'Dashed “probable” stop', true],
    ['Appearance-gated bridge', 'Same last four characters, class and colour, reachable at road speed', 'Dashed “probable” stop', true],
    ['Feasibility gate', 'Two stops implying more than 150 km/h', 'Flagged, not drawn', true],
    ['Appearance re-identification', 'A vehicle whose plate is never read', 'Designed and costed', false],
  ]
  for (const [i, [name, catches, shows, built]] of rungs.entries()) {
    const y = 1.8 + i * 0.76
    panel(s, M, y, CW, 0.66, { radius: 0.04, ...(built ? {} : { fill: INSET }) })
    s.addShape(pres.shapes.RECTANGLE, { x: M + 0.2, y: y + 0.17, w: 1.05, h: 0.32, fill: { color: built ? LIVE : INSET }, line: { color: built ? LIVE : FAINT } })
    text(s, built ? 'BUILT' : 'DESIGN', { x: M + 0.2, y: y + 0.17, w: 1.05, h: 0.32, align: 'center', valign: 'middle', fontFace: MONO, bold: true, fontSize: 10, color: built ? WHITE : MUTED })
    text(s, name, { x: M + 1.5, y, w: 3.4, h: 0.66, valign: 'middle', fontFace: BB, fontSize: 14.5 })
    text(s, catches, { x: M + 5.0, y, w: 4.6, h: 0.66, valign: 'middle', fontSize: 13, color: MUTED })
    text(s, shows, { x: M + 9.7, y, w: CW - 9.9, h: 0.66, valign: 'middle', fontSize: 13 })
  }
  source(s, 'Built rungs: services/core_api/src/core_api/detections/service.py. Design: docs/14-APPEARANCE-REID-DESIGN.md.', { y: 6.5 })
}

// --- build ------------------------------------------------------------------

async function main() {
  const story = [
    [null, titleSlide],
    ['The case', caseSlide],
    ['The case', answerSlide],
    ['Live', liveSlide],
    ['Live', openSlide],
    ['Live', readSlide],
    ['Live', traceSlide],
    ['Live', watchSlide],
    ['Live', handoverSlide],
    ['Trust', trustSlide],
    ['Trust', proofSlide],
    ['Scale', onboardSlide],
    ['Scale', architectureSlide],
    ['Scale', costSlide],
    ['Next', nextSlide],
  ]
  for (const [chapter, build] of story) {
    section.chapter = chapter
    await build()
  }
  appendixDivider()
  for (const build of [stackSlide, approachSlide, tierSlide, costDetailSlide, beyondSlide, fieldSlide, opsSlide, compareSlide, unreadableSlide]) {
    await build()
  }
  await pres.writeFile({ fileName: OUT })
  console.log(`wrote ${OUT} — ${mainCount} main slides, ${appendixCount} appendix`)
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
