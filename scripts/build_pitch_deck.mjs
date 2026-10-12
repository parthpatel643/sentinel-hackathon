/**
 * Builds the grand-finale pitch deck: docs/Sentinel-Finale-Pitch.pptx.
 *
 * A business pitch for the 20-minute on-site evaluation (docs/13-SHOWCASE-PREP.md
 * §4), for a room of senior IPS officers and technology professors. Thirteen main
 * slides follow one storyline — Why, What, Demo, Trust, How, Value, Next — with
 * a chapter tracker so the room always knows where it is; each slide leads with
 * the operational outcome and gives the method underneath. Everything else is
 * an appendix, indexed, for questions. Cost is on one slide only, because the brief asks for estimated
 * implementation and operational costs; its figures are docs/04-SCALE-PLAN.md §6.
 *
 * Generated, so it cannot drift from what it cites: every number comes from a
 * document or measurement in this repository, and every screenshot is the real
 * console in its light theme, captured from a live stack with
 *   npm run screenshots:pitch      (from apps/web)
 * Speaker notes carry the talk track.
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

// Light, and continuous with the console's own light theme: its royal blue
// leads, deep navy carries the words, and saffron is the one warm accent for
// the numbers worth remembering. Teal marks what we measured; red marks today.
const WHITE = 'FFFFFF'
const SOFT = 'F3F5FA'
const TINT = 'EAF0FD'
const LINE = 'DDE3EE'
const INK = '0F1B33'
const MUTED = '536079'
const BLUE = '2456D6'
const SAFFRON = 'D97706'
const SAFFRON_TEXT = 'B45309'
const TEAL = '0F766E'
const RED = 'C2410C'

const H = 'Arial'
const B = 'Calibri'

const W = 13.333
const SLIDE_H = 7.5
const M = 0.6
const CW = W - 2 * M

const pres = new PptxGenJS()
pres.layout = 'LAYOUT_WIDE'
pres.author = 'Sentinel Platform'
pres.title = 'Sentinel — find any vehicle across every government camera in Gujarat'

// --- assets -----------------------------------------------------------------

const iconCache = new Map()

/** A Lucide icon (the console's own icon set) rendered to a PNG data URI. */
async function icon(name, color) {
  const key = `${name}:${color}`
  if (iconCache.has(key)) return iconCache.get(key)
  const Component = Lu[name]
  if (!Component) throw new Error(`no icon ${name}`)
  const svg = renderToStaticMarkup(
    React.createElement(Component, { size: 256, color: `#${color}`, strokeWidth: 1.9 }),
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
    .resize({ width: Math.min(width, 1800), withoutEnlargement: true })
    .jpeg({ quality: 82, mozjpeg: true })
    .toBuffer()
  return `image/jpeg;base64,${jpeg.toString('base64')}`
}

/** A region of a desktop screenshot, in the 1600x1000 CSS-pixel viewport it
 * was captured at (scaled to whatever pixel density it has). */
async function crop(name, { x, y, w, h }) {
  const image = sharp(SHOT(name))
  const k = (await image.metadata()).width / 1600
  const region = image.extract({
    left: Math.round(x * k), top: Math.round(y * k), width: Math.round(w * k), height: Math.round(h * k),
  })
  return { data: await encode(region, Math.round(w * k)), ratio: w / h }
}

/** A whole screenshot, for the phone capture. */
async function whole(name) {
  const image = sharp(SHOT(name))
  const { width, height } = await image.metadata()
  return { data: await encode(image, width), ratio: width / height }
}

// --- building blocks --------------------------------------------------------

// The storyline of the main slides. Each slide is tagged with its chapter by
// main(), and a small tracker in the top-right shows where the room is.
const CHAPTERS = ['Why', 'What', 'Demo', 'Trust', 'How', 'Value', 'Next']
const section = { chapter: null, appendix: false }
let mainCount = 0
let appendixCount = 0

/** Main slides are numbered 01, 02…; appendix slides A1, A2…. */
function nextLabel() {
  if (section.appendix) {
    appendixCount += 1
    return `A${appendixCount}`
  }
  mainCount += 1
  return String(mainCount).padStart(2, '0')
}

function pageNo(s, label) {
  s.addText(label, {
    x: W - M - 0.6, y: SLIDE_H - 0.45, w: 0.6, h: 0.25, margin: 0, align: 'right',
    fontFace: H, fontSize: 9, color: MUTED,
  })
}

function tracker(s) {
  const opts = { x: W - M - 6.2, y: 0.42, w: 6.2, h: 0.3, margin: 0, align: 'right', fontFace: H, fontSize: 10, charSpacing: 1 }
  if (section.appendix) {
    s.addText('APPENDIX  ·  FOR REFERENCE', { ...opts, bold: true, color: MUTED })
    return
  }
  if (!section.chapter) return
  const runs = []
  for (const [i, chapter] of CHAPTERS.entries()) {
    const current = chapter === section.chapter
    runs.push({ text: chapter, options: { bold: current, color: current ? BLUE : 'A3ADBF' } })
    if (i < CHAPTERS.length - 1) runs.push({ text: '   ', options: {} })
  }
  s.addText(runs, opts)
}

/** Every content slide: white ground, a saffron eyebrow, a large navy title,
 * the chapter tracker and a quiet page number. The variation belongs in the body. */
function frame({ eyebrow, title, notes, background = WHITE }) {
  const label = nextLabel()
  const s = pres.addSlide()
  s.background = { color: background }
  const prefix = section.appendix ? `${label}  ·  ` : ''
  s.addText((prefix + eyebrow).toUpperCase(), {
    x: M, y: 0.42, w: CW - 6.3, h: 0.3, margin: 0,
    fontFace: H, fontSize: 11, bold: true, color: SAFFRON_TEXT, charSpacing: 3,
  })
  tracker(s)
  s.addText(title, {
    x: M, y: 0.74, w: CW, h: 0.8, margin: 0, valign: 'top',
    fontFace: H, fontSize: 32, bold: true, color: INK,
  })
  pageNo(s, label)
  if (notes) s.addNotes(notes)
  return s
}

function panel(s, x, y, w, h, fill = SOFT, line = LINE) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x, y, w, h, rectRadius: 0.12, fill: { color: fill }, line: { color: line, width: 0.75 },
  })
}

/** A white card lifted off the page by a soft shadow. */
function card(s, x, y, w, h) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x, y, w, h, rectRadius: 0.12, fill: { color: WHITE }, line: { color: LINE, width: 0.75 },
    shadow: { type: 'outer', color: '1F2A44', blur: 14, offset: 3, angle: 90, opacity: 0.12 },
  })
}

async function badge(s, name, x, y, d = 0.6, bg = BLUE, fg = WHITE) {
  s.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: bg }, line: { color: bg } })
  const pad = d * 0.23
  s.addImage({ data: await icon(name, fg), x: x + pad, y: y + pad, w: d - 2 * pad, h: d - 2 * pad })
}

/** A screenshot in a light frame with a soft shadow, sized to width. */
function screenshot(s, img, x, y, w) {
  const h = w / img.ratio
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: x - 0.07, y: y - 0.07, w: w + 0.14, h: h + 0.14, rectRadius: 0.1,
    fill: { color: WHITE }, line: { color: LINE, width: 0.75 },
    shadow: { type: 'outer', color: '1F2A44', blur: 20, offset: 6, angle: 90, opacity: 0.16 },
  })
  s.addImage({ data: img.data, x, y, w, h })
  return h
}

function text(s, value, opts) {
  s.addText(value, { margin: 0, fontFace: B, color: INK, valign: 'top', ...opts })
}

/** Icon-in-circle, bold header, muted body: the deck's repeated row. */
async function iconRow(s, { icon: name, title, body, x, y, w, color = BLUE }) {
  await badge(s, name, x, y, 0.56, color)
  text(s, title, { x: x + 0.78, y: y - 0.02, w: w - 0.78, h: 0.34, fontFace: H, fontSize: 15, bold: true })
  text(s, body, { x: x + 0.78, y: y + 0.33, w: w - 0.78, h: 0.62, fontSize: 13, color: MUTED })
}

/** A small floating callout over a screenshot. */
async function chip(s, { icon: name, label, x, y, w, color = BLUE }) {
  card(s, x, y, w, 0.62)
  await badge(s, name, x + 0.14, y + 0.12, 0.38, color)
  text(s, label, { x: x + 0.62, y: y + 0.12, w: w - 0.72, h: 0.38, fontFace: H, fontSize: 12, bold: true, valign: 'middle' })
}

// --- slides -------------------------------------------------------------------

async function titleSlide() {
  nextLabel()
  const s = pres.addSlide()
  s.background = { color: WHITE }
  // Right half: the product, on the console's own tint.
  s.addShape(pres.shapes.RECTANGLE, { x: 6.75, y: 0, w: W - 6.75, h: SLIDE_H, fill: { color: TINT }, line: { color: TINT } })
  const shot = await crop('find-a-vehicle', { x: 0, y: 182, w: 1600, h: 782 })
  const sw = 5.75
  const sh = sw / shot.ratio
  const sy = (SLIDE_H - sh) / 2
  screenshot(s, shot, 7.15, sy, sw)
  await chip(s, { icon: 'LuRoute', label: 'Route traced across cameras', x: 6.45, y: sy - 0.4, w: 3.1 })
  await chip(s, { icon: 'LuBellRing', label: 'Watchlist alert raised', x: W - 3.35, y: sy + sh - 0.25, w: 2.8, color: SAFFRON })

  text(s, 'GUJARAT POLICE INNOVATION CHALLENGE 2026', {
    x: M, y: 1.25, w: 5.8, h: 0.3, fontFace: H, fontSize: 11, bold: true, color: SAFFRON_TEXT, charSpacing: 2,
  })
  text(s, 'Sentinel', { x: M, y: 1.7, w: 5.8, h: 1.2, fontFace: H, fontSize: 66, bold: true, color: INK })
  text(s, 'Find any vehicle, across every government camera in Gujarat — in seconds.', {
    x: M, y: 3.0, w: 5.7, h: 1.3, fontFace: H, fontSize: 25, color: INK,
  })
  text(s, 'One platform that connects the cameras departments already run, reads number plates where they are filmed, and alerts officers the moment a vehicle of interest is seen.', {
    x: M, y: 4.45, w: 5.6, h: 1.1, fontSize: 15, color: MUTED,
  })
  text(s, 'Presented by Invental Data Labs', {
    x: M, y: 5.72, w: 5.6, h: 0.35, fontFace: H, fontSize: 14, bold: true, color: BLUE,
  })
  await badge(s, 'LuMapPin', M, 6.3, 0.42, SAFFRON)
  text(s, 'Grand Finale  ·  i-Hub Gujarat, Ahmedabad  ·  12–13 October 2026', {
    x: M + 0.6, y: 6.38, w: 5.6, h: 0.3, fontSize: 13, color: MUTED,
  })
  s.addNotes(
    'Open with the outcome, not the technology. "Sentinel lets an officer type a registration number and see where that vehicle went, across every government camera, in seconds — and be told the moment it is seen again." Two sentences, then move: this room has heard many pitches. If the jury gives the vehicle number now, go straight to the demonstration (slide 5) and come back.',
  )
}

/** Who is presenting. Initials stand in for photographs, so the slide needs
 * no image files and renders identically on any machine. */
async function teamSlide() {
  const s = frame({
    eyebrow: 'Who we are',
    title: 'Invental Data Labs',
    notes: 'Twenty seconds, no more. "We are Invental Data Labs. I am Parth Patel — I lead the team; I am a consulting AI solution architect who has worked with IBM and United Airlines, and I hold an MTech in Data Science from IIT Bombay. With me is Anuj Patel, a data scientist from Göttingen, Germany." Then straight into the challenge: the background is there to earn trust, not to take time.',
  })
  text(s, 'Enterprise AI architecture and applied data science — built into a platform for Gujarat Police.', {
    x: M, y: 1.55, w: CW, h: 0.4, fontSize: 16, color: MUTED,
  })
  const people = [
    {
      initials: 'PP',
      name: 'Parth Patel',
      role: 'Team Lead',
      colour: BLUE,
      facts: [
        ['LuBriefcase', 'Consulting AI Solution Architect'],
        ['LuPlane', 'IBM  ·  United Airlines'],
        ['LuGraduationCap', 'MTech, Data Science — IIT Bombay'],
      ],
    },
    {
      initials: 'AP',
      name: 'Anuj Patel',
      role: 'Associate',
      colour: TEAL,
      facts: [
        ['LuBrainCircuit', 'Data Scientist'],
        ['LuMapPin', 'Göttingen, Germany'],
      ],
    },
  ]
  const gap = 0.4
  const cw = (CW - gap) / 2
  const top = 2.3
  const ch = 4.35
  for (const [i, person] of people.entries()) {
    const x = M + i * (cw + gap)
    card(s, x, top, cw, ch)
    const d = 1.45
    s.addShape(pres.shapes.OVAL, {
      x: x + 0.45, y: top + 0.45, w: d, h: d, fill: { color: person.colour }, line: { color: person.colour },
    })
    text(s, person.initials, {
      x: x + 0.45, y: top + 0.45, w: d, h: d, align: 'center', valign: 'middle',
      fontFace: H, fontSize: 40, bold: true, color: WHITE,
    })
    text(s, person.name, { x: x + 2.15, y: top + 0.55, w: cw - 2.45, h: 0.6, fontFace: H, fontSize: 28, bold: true })
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: x + 2.15, y: top + 1.25, w: 1.75, h: 0.42, rectRadius: 0.21,
      fill: { color: person.colour === BLUE ? TINT : 'E3F4F1' }, line: { color: person.colour, width: 0.75 },
    })
    text(s, person.role.toUpperCase(), {
      x: x + 2.15, y: top + 1.25, w: 1.75, h: 0.42, align: 'center', valign: 'middle',
      fontFace: H, fontSize: 11, bold: true, color: person.colour, charSpacing: 2,
    })
    for (const [j, [ic, fact]] of person.facts.entries()) {
      const y = top + 2.25 + j * 0.62
      await badge(s, ic, x + 0.45, y, 0.44, person.colour)
      text(s, fact, { x: x + 1.1, y: y + 0.02, w: cw - 1.4, h: 0.4, fontSize: 17, valign: 'middle' })
    }
  }
}

async function problemSlide() {
  const s = frame({
    eyebrow: 'The challenge',
    title: 'The cameras exist. They don’t work together.',
    notes: 'Speak to the officers first. Gujarat already has about eighty thousand cameras across twenty-six departments — Home, Civil Supplies, RTO and the rest. What it lacks is a way to use them together. When a vehicle is used in a crime, tracing it is phone calls to each department, separate logins and manual review, while the footage is overwritten within a week or two. The right-hand side is what the next eighteen minutes show.',
  })
  const stats = [
    ['~80,000', 'cameras already installed', 'LuCamera'],
    ['26', 'departments, each its own system', 'LuBuilding2'],
    ['7–15', 'days before footage is overwritten', 'LuHourglass'],
    ['~1,000', 'km between the farthest sites', 'LuMap'],
  ]
  const sw = (CW - 3 * 0.3) / 4
  for (const [i, [value, label, ic]] of stats.entries()) {
    const x = M + i * (sw + 0.3)
    card(s, x, 1.75, sw, 1.2)
    await badge(s, ic, x + 0.25, 2.07, 0.56)
    text(s, value, { x: x + 0.98, y: 1.88, w: sw - 1.15, h: 0.55, fontFace: H, fontSize: 26, bold: true, color: SAFFRON })
    text(s, label, { x: x + 0.98, y: 2.42, w: sw - 1.15, h: 0.45, fontSize: 12, color: MUTED })
  }
  const rows = [
    ['A vehicle is traced by phoning departments, one by one', 'One search traces it across every department’s cameras'],
    ['26 systems, 26 logins, no shared map', 'Every camera on one map, behind one login'],
    ['Footage is overwritten before anyone asks for it', 'Each sighting is kept, with its frame as evidence'],
  ]
  const colW = 5.55
  const top = 3.25
  const ph = 3.6
  const rightX = W - M - colW
  panel(s, M, top, colW, ph, SOFT)
  panel(s, rightX, top, colW, ph, TINT, 'C9D7F7')
  text(s, 'Today', { x: M + 0.35, y: top + 0.25, w: 3, h: 0.4, fontFace: H, fontSize: 18, bold: true, color: MUTED })
  text(s, 'With Sentinel', { x: rightX + 0.35, y: top + 0.25, w: 3, h: 0.4, fontFace: H, fontSize: 18, bold: true, color: BLUE })
  for (const [i, [before, after]] of rows.entries()) {
    const y = top + 0.95 + i * 0.85
    await badge(s, 'LuX', M + 0.35, y + 0.08, 0.38, 'B8C0CE')
    text(s, before, { x: M + 0.9, y, w: colW - 1.2, h: 0.55, fontSize: 15, color: MUTED, valign: 'middle' })
    await badge(s, 'LuCheck', rightX + 0.35, y + 0.08, 0.38, BLUE)
    text(s, after, { x: rightX + 0.9, y, w: colW - 1.2, h: 0.55, fontSize: 15, bold: true, valign: 'middle' })
  }
  await badge(s, 'LuArrowRight', W / 2 - 0.3, top + ph / 2 - 0.3, 0.6, SAFFRON)
}

async function platformSlide() {
  const s = frame({
    eyebrow: 'The platform',
    title: 'One platform, three jobs',
    notes: 'One idea per column, in plain words. See: every camera, from every department, on one map and one live wall. Find: any vehicle by its plate — the route, the evidence at every stop, and a report for the case file. Alert: stolen, wanted and missing vehicles flagged the moment any camera reads them. Each job maps to a role the officers in the room already command.',
  })
  const jobs = [
    ['LuMonitor', 'See', 'Every camera, from every department, on one map and one live wall — with its health at a glance.', 'Control rooms'],
    ['LuSearch', 'Find', 'Any vehicle by its registration number: its route, the evidence at every stop, and a signed report.', 'Investigators'],
    ['LuBellRing', 'Alert', 'Stolen, wanted and missing vehicles flagged the moment any camera reads them — on every console and phone.', 'Patrol and command'],
  ]
  const cw = (CW - 2 * 0.35) / 3
  for (const [i, [ic, title, body, who]] of jobs.entries()) {
    const x = M + i * (cw + 0.35)
    card(s, x, 1.85, cw, 3.95)
    await badge(s, ic, x + 0.4, 2.2, 0.85, i === 2 ? SAFFRON : BLUE)
    text(s, title, { x: x + 0.4, y: 3.25, w: cw - 0.8, h: 0.7, fontFace: H, fontSize: 30, bold: true })
    text(s, body, { x: x + 0.4, y: 3.98, w: cw - 0.8, h: 1.2, fontSize: 15, color: MUTED })
    text(s, `For ${who.toLowerCase()}`, { x: x + 0.4, y: 5.25, w: cw - 0.8, h: 0.35, fontFace: H, fontSize: 12, bold: true, color: BLUE })
  }
  await badge(s, 'LuLanguages', M, 6.2, 0.46, TEAL)
  text(s, 'Plus people counting, zone intrusion and camera-tamper alerts — in English, Hindi and Gujarati.', {
    x: M + 0.65, y: 6.27, w: CW - 0.65, h: 0.4, fontSize: 15,
  })
}

async function audienceSlide() {
  const s = frame({
    eyebrow: 'Who it serves',
    title: 'Built for everyone who keeps Gujarat safe',
    notes: 'Make it personal. The operator gets one screen instead of many. The investigator gets the route and a report they can put in a case file. The officer on patrol gets alerts and a plate lookup on their phone — it even works on a poor connection. Leadership gets a statewide picture: which cameras are working, where coverage is missing.',
  })
  const people = [
    ['LuMonitor', 'Control-room operator', 'One live wall for every department’s cameras; alerts arrive with a sound, on screen.'],
    ['LuFileSearch', 'Investigating officer', 'Route, timestamps and evidence frames for any plate, exported as a case-ready report.'],
    ['LuSmartphone', 'Officer on patrol', 'Alerts and plate lookup on a phone, with an offline mode for weak signal.'],
    ['LuLandmark', 'Leadership', 'A statewide view of the camera network: what works, what is down, where gaps are.'],
  ]
  const cw = 3.7
  for (const [i, [ic, title, body]] of people.entries()) {
    const x = M + (i % 2) * (cw + 0.3)
    const y = 1.9 + Math.floor(i / 2) * 2.45
    card(s, x, y, cw, 2.15)
    await badge(s, ic, x + 0.3, y + 0.3, 0.6, i === 2 ? SAFFRON : BLUE)
    text(s, title, { x: x + 0.3, y: y + 1.02, w: cw - 0.6, h: 0.4, fontFace: H, fontSize: 16, bold: true })
    text(s, body, { x: x + 0.3, y: y + 1.42, w: cw - 0.6, h: 0.7, fontSize: 13, color: MUTED })
  }
  const phone = await whole('field-pwa')
  const ph = 5.0
  const pw = ph * phone.ratio
  const px = W - M - pw - 1.2
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: px - 0.14, y: 1.85 - 0.14, w: pw + 0.28, h: ph + 0.28, rectRadius: 0.3,
    fill: { color: INK }, line: { color: INK },
    shadow: { type: 'outer', color: '1F2A44', blur: 22, offset: 8, angle: 90, opacity: 0.22 },
  })
  s.addImage({ data: phone.data, x: px, y: 1.85, w: pw, h: ph })
  text(s, 'The field app, on an officer’s phone', {
    x: px - 0.6, y: 7.0, w: pw + 1.2, h: 0.3, fontSize: 11, italic: true, color: MUTED, align: 'center',
  })
}

async function demoSlide() {
  const label = nextLabel()
  const s = pres.addSlide()
  s.background = { color: TINT }
  tracker(s)
  text(s, 'LIVE DEMONSTRATION', { x: M, y: 0.9, w: CW, h: 0.35, fontFace: H, fontSize: 13, bold: true, color: SAFFRON_TEXT, charSpacing: 4 })
  text(s, 'On today’s cameras, in front of you', { x: M, y: 1.3, w: CW, h: 0.9, fontFace: H, fontSize: 40, bold: true })
  const steps = [
    ['1', 'Connect and see', 'Today’s cameras on the map and the live wall, with their health.', 'LuCamera'],
    ['2', 'Trace the vehicle', 'The registration number you give us, traced camera by camera, with a report to hand over.', 'LuRoute'],
    ['3', 'Get alerted', 'A watchlist vehicle flagged on every open screen the moment it is read.', 'LuBellRing'],
  ]
  const cw = (CW - 2 * 0.4) / 3
  for (const [i, [n, title, body, ic]] of steps.entries()) {
    const x = M + i * (cw + 0.4)
    card(s, x, 2.75, cw, 3.4)
    text(s, n, { x: x + 0.35, y: 2.95, w: 1.2, h: 1.2, fontFace: H, fontSize: 64, bold: true, color: SAFFRON })
    await badge(s, ic, x + cw - 1.05, 3.15, 0.7)
    text(s, title, { x: x + 0.35, y: 4.25, w: cw - 0.7, h: 0.5, fontFace: H, fontSize: 20, bold: true })
    text(s, body, { x: x + 0.35, y: 4.8, w: cw - 0.7, h: 1.2, fontSize: 15, color: MUTED })
  }
  text(s, 'If the venue network fails, we say which fallback we are on: our own cameras, then a recorded copy of the government grid. Screens of each step are in Appendix A2–A4.', {
    x: M, y: 6.5, w: CW, h: 0.4, fontSize: 13, color: MUTED, italic: true,
  })
  pageNo(s, label)
  s.addNotes('About seven minutes, live. Say what you will do before you do it; the narrator faces the jury and the driver only clicks. If the vehicle number was already given, run step 2 first. For the officers, narrate it as an investigation: the number comes in, the route comes out, the report goes into the case file. For the professors, name the method at each step in one sentence — the camera’s own clock, the speed check, the hash-sealed report.')
}

async function connectSlide() {
  const s = frame({
    eyebrow: 'Demo backup · Connect and see',
    title: 'Works with the cameras you already have',
    notes: 'Nothing is replaced and nothing is installed on a department’s system. A camera list, a device on the network or a department’s catalogue — each is onboarded in minutes and appears on the map and the live wall. For the technical jury: RTSP, ONVIF, Hikvision and Dahua drivers; one connection per camera however many people watch; credentials never reach a browser.',
  })
  const shot = await crop('live-wall', { x: 302, y: 244, w: 1278, h: 702 })
  screenshot(s, shot, M + 0.07, 1.9, 6.9)
  const x = M + 7.45
  const w = CW - 7.45
  const rows = [
    ['LuFileSpreadsheet', 'Upload a camera list', 'Every row checked before anything is added; one bad row never blocks the rest.'],
    ['LuScanSearch', 'Or discover devices', 'Find a camera’s or recorder’s streams on the network and add them (ONVIF, Hikvision, Dahua).'],
    ['LuShieldCheck', 'Nothing installed', 'Read-only access. Each department’s own system and recording keep running untouched.'],
    ['LuLock', 'Secure viewing', 'One connection per camera, however many watch. Passwords never reach a browser.'],
  ]
  for (const [i, [ic, title, body]] of rows.entries()) {
    await iconRow(s, { icon: ic, title, body, x, y: 1.95 + i * 1.18, w })
  }
}

async function traceSlide() {
  const s = frame({
    eyebrow: 'Demo backup · Trace the vehicle',
    title: 'Type a plate. See where it went.',
    notes: 'Type the number — spacing and case do not matter. Every sighting appears on the map and the timeline, in the order the cameras’ own clocks give. Open a stop: the camera, the time printed on the frame, the plate as read, the snapshot with faces blurred. Arm a watch for future sightings. Then export the Movement Report and hand it over.',
  })
  const shot = await crop('find-a-vehicle', { x: 0, y: 182, w: 1600, h: 782 })
  const h = screenshot(s, shot, M + 0.07, 1.8, 7.5)
  const x = M + 8.1
  const w = CW - 8.1
  const rows = [
    ['LuClock', 'The camera’s own clock', 'Each stop is timed by the clock printed on its evidence frame.'],
    ['LuTriangleAlert', 'Impossible journeys flagged', 'A hop no vehicle could make is marked — a cloned plate stands out.'],
    ['LuFileCheck', 'A report to hand over', 'Route, times and evidence frames as PDF and CSV, sealed with a tamper-evident fingerprint.'],
  ]
  for (const [i, [ic, title, body]] of rows.entries()) {
    await iconRow(s, { icon: ic, title, body, x, y: 1.9 + i * 1.3, w })
  }
  text(s, 'The real console on recorded government footage: GJ11S7924 at Timbavadi Gate, Junagadh, 17 Jun 2026, 18:01 — the time printed on the frame.', {
    x: M, y: 1.8 + h + 0.22, w: 7.6, h: 0.45, fontSize: 11, color: MUTED, italic: true,
  })
}

async function alertSlide() {
  const s = frame({
    eyebrow: 'Demo backup · Get alerted',
    title: 'Flagged the moment it is seen',
    notes: 'Every plate any camera reads is checked against the watchlist — stolen, wanted, missing — automatically. A match raises a prioritised alert on every open console and on officers’ phones, with a sound, and repeat sightings at a red light do not flood anyone. It also catches the misreads cameras make: a zero read as an O, a one as an I. Anything less than an exact match is shown as probable, for an officer to confirm on the frame.',
  })
  const shot = await crop('alerts', { x: 600, y: 182, w: 980, h: 672 })
  screenshot(s, shot, M + 0.07, 1.85, 5.6)
  const x = M + 6.2
  const w = CW - 6.2
  text(s, 'It catches the misreads cameras make', { x, y: 1.85, w, h: 0.4, fontFace: H, fontSize: 18, bold: true })
  const rungs = [
    ['Exact match', 'The plate, read as it is', TEAL, 'Alert'],
    ['Look-alike characters', '0 for O, 1 for I, 8 for B, 5 for S', TEAL, 'Alert'],
    ['One character off', 'Shown with the plate as actually read', SAFFRON, 'Confirm'],
  ]
  for (const [i, [name, body, color, action]] of rungs.entries()) {
    const y = 2.42 + i * 0.95
    card(s, x, y, w, 0.78)
    s.addShape(pres.shapes.OVAL, { x: x + 0.25, y: y + 0.25, w: 0.28, h: 0.28, fill: { color }, line: { color } })
    text(s, name, { x: x + 0.7, y: y + 0.12, w: 2.6, h: 0.54, fontFace: H, fontSize: 15, bold: true, valign: 'middle' })
    text(s, body, { x: x + 3.2, y: y + 0.12, w: w - 4.5, h: 0.54, fontSize: 13, color: MUTED, valign: 'middle' })
    text(s, action, { x: x + w - 1.25, y: y + 0.12, w: 1.0, h: 0.54, fontFace: H, fontSize: 12, bold: true, color, align: 'right', valign: 'middle' })
  }
  await iconRow(s, {
    icon: 'LuPlugZap', x, y: 5.5, w, color: SAFFRON,
    title: 'Ready for the State’s databases',
    body: 'VAHAN, SARTHI, eGujCop, AFIS and NAFIS connectors are built. Access, once granted, is a setting.',
  })
}

async function trustSlide() {
  const s = frame({
    eyebrow: 'Evidence and privacy',
    title: 'Evidence that holds up. Privacy by default.',
    notes: 'This is the slide for both halves of the room. For the officers: the time in the report is the time printed on the camera’s own frame, and if it cannot be read we say “time unknown” rather than guess — a record that holds up under cross-examination. Every search, export and reveal is logged in a hash chain; change one entry and verification fails. For the professors: the clock reading is accepted only when a second reading agrees, and exports carry a SHA-256 manifest. And we do no face recognition at all — faces are detected only to be blurred. If time allows, show Admin, then Audit, then Verify integrity.',
  })
  const shot = await crop('time-unknown', { x: 753, y: 418, w: 827, h: 480 })
  screenshot(s, shot, M + 6.95, 1.9, CW - 7.0)
  const items = [
    ['LuClock', 'The time on the frame is the time in the report', 'Read from the camera’s own clock. If it cannot be read, we say “time unknown” — never a guess.'],
    ['LuEyeOff', 'Faces blurred by default', 'Seeing an original needs a stated reason, and is recorded.'],
    ['LuFingerprint', 'A chain of custody no one can quietly edit', 'Every search, export and reveal is logged and hash-chained; reports carry a SHA-256 manifest.'],
    ['LuKeyRound', 'Each department sees its own', 'Access scoped in the database itself; private cameras only with current consent.'],
  ]
  for (const [i, [ic, title, body]] of items.entries()) {
    await iconRow(s, { icon: ic, title, body, x: M, y: 1.95 + i * 1.18, w: 6.4, color: i === 0 ? SAFFRON : BLUE })
  }
  text(s, 'A sighting whose clock cannot be read stays a sighting — listed, clearly labelled, and kept off the timeline.', {
    x: M + 6.95, y: 6.35, w: CW - 7.0, h: 0.5, fontSize: 11, color: MUTED, italic: true,
  })
}

async function beyondSlide() {
  const s = frame({
    eyebrow: 'Beyond number plates',
    title: 'More than plates — never identities',
    notes: 'The same cameras answer more questions at no extra effort: what kind of vehicle, what colour, how many people, did anyone enter a restricted zone or loiter, is a vehicle going the wrong way, has a camera been covered or moved. And one thing we will not do: identify faces.',
  })
  const tiles = [
    ['LuCar', 'Vehicle type', 'Car, motorcycle, bus or truck — on every read.'],
    ['LuPalette', 'Vehicle colour', 'Body colour attached to each sighting.'],
    ['LuUsers', 'People counted', 'Counted per camera and held to zones. Never identified.'],
    ['LuCrosshair', 'Restricted zones', 'Intrusion and loitering, drawn on any camera.'],
    ['LuMoveHorizontal', 'Traffic rules', 'Wrong-way and stopped vehicles, per zone.'],
    ['LuCircleAlert', 'Camera tamper', 'Covered, blurred or moved — flagged on the camera.'],
  ]
  const cw = (CW - 2 * 0.3) / 3
  for (const [i, [ic, title, body]] of tiles.entries()) {
    const x = M + (i % 3) * (cw + 0.3)
    const y = 1.9 + Math.floor(i / 3) * 2.05
    card(s, x, y, cw, 1.8)
    await badge(s, ic, x + 0.3, y + 0.3, 0.6)
    text(s, title, { x: x + 1.1, y: y + 0.32, w: cw - 1.35, h: 0.45, fontFace: H, fontSize: 17, bold: true })
    text(s, body, { x: x + 1.1, y: y + 0.82, w: cw - 1.35, h: 0.8, fontSize: 14, color: MUTED })
  }
  await badge(s, 'LuEyeOff', M, 6.2, 0.46, TEAL)
  text(s, 'No face recognition, by decision. Faces are detected only so they can be blurred.', {
    x: M + 0.65, y: 6.27, w: CW - 0.65, h: 0.4, fontSize: 15,
  })
}

async function approachSlide() {
  const s = frame({
    eyebrow: 'Our approach',
    title: 'A hybrid of the four reference models',
    notes: 'This answers the brief’s “which model, and why”. A hybrid. Model 1’s registry and GIS is the foundation everything stands on. Model 2 gives one console that views and analyses every accessible stream. Model 3’s adapters mean no department changes its system — a new vendor is a driver, not a release. Model 4’s central recording is used only where it pays off. The next slide is the reason we do not centralise everything.',
  })
  const models = [
    ['Model 1', 'Registry & GIS', 'Every camera on one map, with health, coverage gaps and an ageing-asset work list.', 'The foundation every other part stands on.', 'LuMap', 'Foundation'],
    ['Model 2', 'Unified viewing & analytics', 'One live wall and plate reading on every accessible stream.', 'One console, instead of one per department.', 'LuMonitor', 'Adopted'],
    ['Model 3', 'Federation adapters', 'RTSP, ONVIF, Hikvision, Dahua, Genetec and Milestone drivers.', 'No department changes its system; a new vendor is a driver.', 'LuNetwork', 'Adopted'],
    ['Model 4', 'Central recording', 'Only critical cameras and alert clips are recorded centrally.', 'Full centralisation needs a backbone the State does not have.', 'LuServer', 'Selective'],
  ]
  const cw = (CW - 3 * 0.3) / 4
  for (const [i, [tag, name, body, why, ic, pill]] of models.entries()) {
    const x = M + i * (cw + 0.3)
    const selective = pill === 'Selective'
    card(s, x, 1.85, cw, 4.25)
    await badge(s, ic, x + 0.3, 2.15, 0.62, selective ? '7A869E' : BLUE)
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: x + cw - 1.45, y: 2.28, w: 1.15, h: 0.36, rectRadius: 0.18,
      fill: { color: selective ? WHITE : TINT }, line: { color: selective ? 'B8C0CE' : 'C9D7F7', width: 0.75 },
    })
    text(s, pill, {
      x: x + cw - 1.45, y: 2.28, w: 1.15, h: 0.36, align: 'center', valign: 'middle',
      fontFace: H, fontSize: 11, bold: true, color: selective ? MUTED : BLUE,
    })
    text(s, tag.toUpperCase(), { x: x + 0.3, y: 3.02, w: cw - 0.6, h: 0.3, fontFace: H, fontSize: 11, bold: true, color: SAFFRON_TEXT, charSpacing: 2 })
    text(s, name, { x: x + 0.3, y: 3.34, w: cw - 0.6, h: 0.75, fontFace: H, fontSize: 18, bold: true })
    text(s, body, { x: x + 0.3, y: 4.1, w: cw - 0.6, h: 0.9, fontSize: 13, color: MUTED })
    s.addShape(pres.shapes.LINE, { x: x + 0.3, y: 5.05, w: cw - 0.6, h: 0, line: { color: LINE, width: 0.75 } })
    text(s, why, { x: x + 0.3, y: 5.15, w: cw - 0.6, h: 0.8, fontSize: 13, bold: true })
  }
  await badge(s, 'LuShieldCheck', M, 6.4, 0.46, TEAL)
  text(s, 'Read-only and pull-based throughout: nothing is installed on a department’s cameras or VMS.', {
    x: M + 0.65, y: 6.47, w: CW - 0.65, h: 0.4, fontSize: 15,
  })
}

async function efficiencySlide() {
  const s = frame({
    eyebrow: 'Why it scales',
    title: 'Send meaning, not video',
    notes: 'For the professors, this is the argument the design rests on; for the officers, it is why it will work in Dahod and Dwarka, not only in Ahmedabad. Pulling every camera’s video to one centre needs about 160 gigabits a second sustained, from sites up to a thousand kilometres apart, and petabytes of storage for a single week. Reading plates where the video is filmed and sending only what was found needs about 140 megabits — roughly a thousand times less — and a district that loses its link keeps reading and alerting for up to three days. Every figure here re-derives from five formulas in our scale plan.',
  })
  const rows = [
    ['LuNetwork', 'Network backbone, statewide', '160 Gbps', '≈140 Mbps', '~1,000× less'],
    ['LuHardDrive', 'Storage for one week', '12.1 PB', '≈390 TB', '~30× less'],
    ['LuWifiOff', 'When a district’s link drops', 'Analysis stops', 'Keeps reading & alerting', 'up to 72 h'],
  ]
  const colX = [M + 0.3, M + 4.6, M + 7.6, M + 10.4]
  text(s, 'Send all video to the centre', { x: colX[1], y: 1.85, w: 2.9, h: 0.35, fontFace: H, fontSize: 13, bold: true, color: MUTED })
  text(s, 'Sentinel: analyse where filmed', { x: colX[2], y: 1.85, w: 2.9, h: 0.35, fontFace: H, fontSize: 13, bold: true, color: BLUE })
  for (const [i, [ic, label, central, ours, ratio]] of rows.entries()) {
    const y = 2.35 + i * 1.32
    card(s, M, y, CW, 1.12)
    await badge(s, ic, colX[0], y + 0.28, 0.56)
    text(s, label, { x: colX[0] + 0.78, y: y + 0.33, w: 3.0, h: 0.5, fontFace: H, fontSize: 15, bold: true, valign: 'middle' })
    const small = central.length > 9
    text(s, central, { x: colX[1], y: y + 0.2, w: 2.9, h: 0.75, fontFace: H, fontSize: small ? 19 : 32, bold: true, color: MUTED, valign: 'middle' })
    text(s, ours, { x: colX[2], y: y + 0.2, w: 2.8, h: 0.75, fontFace: H, fontSize: small ? 19 : 32, bold: true, color: BLUE, valign: 'middle' })
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: colX[3], y: y + 0.32, w: CW - (colX[3] - M) - 0.3, h: 0.48, rectRadius: 0.24,
      fill: { color: 'FDF1DF' }, line: { color: 'F5D6A6', width: 0.75 },
    })
    text(s, ratio, { x: colX[3], y: y + 0.32, w: CW - (colX[3] - M) - 0.3, h: 0.48, fontFace: H, fontSize: 14, bold: true, color: SAFFRON_TEXT, align: 'center', valign: 'middle' })
  }
  text(s, 'What travels is a small event and a snapshot per sighting. Video stays in the district — and in each department’s own system — until someone needs it.', {
    x: M, y: 6.4, w: CW, h: 0.6, fontSize: 14, color: MUTED,
  })
}

async function architectureSlide() {
  const s = frame({
    eyebrow: 'How it works at 80,000 cameras',
    title: 'Five layers, each doing one job',
    notes: 'Bottom to top, one sentence each. Cameras, tiered by how much analysis they need. Department systems stay as they are; we pull read-only. Each district decodes and analyses its own video and queues what it finds if its link drops. The state core does search, storage and alerts, with a warm disaster-recovery site. At the top, the control rooms, the field app and the State’s databases. What you just saw is the district layer running on a laptop — the same code.',
  })
  const layers = [
    ['Consumers', 'Command centres · Field app · VAHAN · SARTHI · eGujCop · AFIS · NAFIS', 'Live alerts · open APIs', 'LuUsers', false],
    ['State core  ·  high availability + disaster recovery', 'Event bus → watchlist matching → alerts · searchable sighting history', '≈563 events/s · RPO 15 min', 'LuDatabase', true],
    ['District edge  ×34  (+ edge boxes at remote sites)', 'One connection per camera → plate reading and analytics → 72 h offline queue', 'AI runs here', 'LuCpu', true],
    ['Department systems  ·  unchanged', 'Cameras, recorders and VMS keep their own 7–15 day retention', 'Read-only: RTSP · ONVIF · SDK', 'LuBuilding2', false],
    ['80,000 cameras, tiered', 'Continuous · sampled · motion-triggered · view-only', 'Tier set per camera', 'LuCamera', false],
  ]
  const top = 1.8
  const rowH = 0.82
  const gap = 0.2
  for (const [i, [name, body, metric, ic, accent]] of layers.entries()) {
    const y = top + i * (rowH + gap)
    if (accent) panel(s, M, y, CW, rowH, TINT, 'C9D7F7')
    else card(s, M, y, CW, rowH)
    await badge(s, ic, M + 0.2, y + 0.16, 0.5, accent ? BLUE : '7A869E')
    text(s, name, { x: M + 0.9, y: y + 0.1, w: 6.6, h: 0.32, fontFace: H, fontSize: 15, bold: true })
    text(s, body, { x: M + 0.9, y: y + 0.44, w: 7.2, h: 0.32, fontSize: 12, color: MUTED })
    text(s, metric, {
      x: M + 8.2, y: y + 0.18, w: CW - 8.45, h: 0.46, fontFace: H, fontSize: 14, bold: true,
      color: accent ? BLUE : INK, align: 'right', valign: 'middle',
    })
    if (i < layers.length - 1) {
      s.addShape(pres.shapes.UP_ARROW, {
        x: M + 0.36, y: y + rowH + 0.01, w: 0.18, h: gap - 0.02, fill: { color: 'B8C0CE' }, line: { color: 'B8C0CE' },
      })
    }
  }
}

async function stackSlide() {
  const s = frame({
    eyebrow: 'Tech stack',
    title: 'Open, proven parts, each chosen for one job',
    notes: 'For the professors, one line per layer, and the reason behind it. At the edge, Python and OpenCV around ONNX Runtime: five small models — vehicles, plates, plate characters, faces to blur, and the camera’s own clock — run unchanged on this laptop or a district GPU, with no internet. The tracker is our own Kalman filter, stepped by the video’s timestamps, not by arrival. MediaMTX pulls each camera once and serves analytics and browsers from that one connection, so passwords never reach a browser. The core is FastAPI over one PostgreSQL: PostGIS for the map, TimescaleDB for sightings over time, trigram search for misread plates; NATS JetStream carries events between district and state. The console is React and TypeScript with MapLibre, installable on a phone, in three languages. Everything is open source; the one copyleft piece is the vehicle detector, and an Apache-licensed replacement is identified. Every change runs through lint, type checks, unit tests and browser tests.',
  })
  const rows = [
    ['LuCpu', 'Edge analytics', 'Python 3.13 · OpenCV · ONNX Runtime · Kalman tracker on video timestamps\nYOLO11n vehicles · YOLOv9-t plates · CCT-XS plate OCR\nYuNet face blur · PP-OCRv6 camera clock', 'Same models on a laptop or a district GPU; no internet needed'],
    ['LuVideo', 'Video relay', 'MediaMTX: one pull per camera\nRTSP to analytics · HLS and WebRTC to browsers', 'One connection, however many watch; passwords never reach a browser'],
    ['LuDatabase', 'Core platform', 'FastAPI · async SQLAlchemy · NATS JetStream\nPostgreSQL 17 + PostGIS · TimescaleDB · pg_trgm', 'One database for the map, sightings over time and misread-plate search'],
    ['LuMonitorSmartphone', 'Console & field app', 'React 19 + TypeScript · Vite · MapLibre GL · hls.js\nInstallable PWA · English · हिन्दी · ગુજરાતી', 'Any browser; the field app installs on a phone'],
    ['LuShieldCheck', 'Security & engineering', 'JWT + bcrypt · per-department row-level security · nginx mTLS · hash-chained audit\nDocker · uv · ruff · mypy · pytest · Playwright', 'Every change is linted, type-checked and tested, browser tests included'],
  ]
  const top = 1.7
  const rowH = 0.82
  const gap = 0.08
  for (const [i, [ic, layer, parts, why]] of rows.entries()) {
    const y = top + i * (rowH + gap)
    card(s, M, y, CW, rowH)
    await badge(s, ic, M + 0.2, y + 0.17, 0.5)
    text(s, layer, { x: M + 0.88, y: y + 0.1, w: 2.3, h: rowH - 0.2, fontFace: H, fontSize: 14, bold: true, valign: 'middle' })
    text(s, parts, { x: M + 3.25, y: y + 0.06, w: 5.75, h: rowH - 0.12, fontSize: 12, valign: 'middle' })
    text(s, why, { x: M + 9.2, y: y + 0.1, w: CW - 9.4, h: rowH - 0.2, fontSize: 11.5, color: MUTED, valign: 'middle' })
  }
  const py = top + rows.length * (rowH + gap) + 0.06
  panel(s, M, py, CW, 0.52, TINT, 'C9D7F7')
  await badge(s, 'LuLockOpen', M + 0.2, py + 0.08, 0.36, TEAL)
  text(s, 'All open source, no licence fees. One copyleft part: the YOLO11n vehicle detector (AGPL-3.0), with an Apache-2.0 swap (RF-DETR) identified.', {
    x: M + 0.75, y: py + 0.04, w: CW - 0.95, h: 0.44, fontSize: 12.5, valign: 'middle',
  })
}

async function tieringSlide() {
  const s = frame({
    eyebrow: 'AI where it matters',
    title: 'Not every camera needs the same attention',
    notes: 'A highway check-post and a ration-shop godown are different jobs. About one camera in eight reads plates continuously; a quarter are view-only. The tier is a setting each department controls and can change live — a camera goes to continuous for a bandobast and back afterwards. That is what makes eighty thousand cameras tractable. Be clear that the split is our planning assumption: the brief gives the eighty thousand total and how departments use their cameras, not a breakdown. The GPU count and the server cost follow from it, and each department’s inventory replaces it in the pilot.',
  })
  s.addChart(pres.charts.DOUGHNUT, [{
    name: 'Cameras by tier',
    labels: ['Continuous', 'Sampled', 'Motion-triggered', 'View only'],
    values: [9600, 22400, 28000, 20000],
  }], {
    x: M, y: 1.75, w: 4.9, h: 4.9, holeSize: 58,
    chartColors: [SAFFRON, BLUE, '8FA9EA', 'D3DAE6'],
    showLegend: false, showValue: false, showPercent: true, showLabel: false,
    dataLabelColor: INK, dataLabelFontSize: 13, dataLabelFontFace: H, dataLabelFontBold: true,
    showTitle: false,
  })
  text(s, '80,000', { x: M + 1.45, y: 3.75, w: 2.0, h: 0.55, align: 'center', fontFace: H, fontSize: 28, bold: true })
  text(s, 'cameras', { x: M + 1.45, y: 4.28, w: 2.0, h: 0.35, align: 'center', fontSize: 13, color: MUTED })

  const x = M + 5.4
  const w = CW - 5.4
  const tiers = [
    [SAFFRON, 'Continuous', '9,600 cameras', 'Check-posts, highways, city entry points'],
    [BLUE, 'Sampled', '22,400 cameras', 'Junctions, markets and public spaces'],
    ['8FA9EA', 'Motion-triggered', '28,000 cameras', 'Godowns, offices and quiet premises'],
    ['D3DAE6', 'View only', '20,000 cameras', 'Indoor, admin and consented private feeds'],
  ]
  for (const [i, [color, name, count, use]] of tiers.entries()) {
    const y = 1.9 + i * 0.92
    card(s, x, y, w, 0.78)
    s.addShape(pres.shapes.OVAL, { x: x + 0.25, y: y + 0.25, w: 0.28, h: 0.28, fill: { color }, line: { color: LINE, width: 0.5 } })
    text(s, name, { x: x + 0.7, y: y + 0.12, w: 2.2, h: 0.54, fontFace: H, fontSize: 15, bold: true, valign: 'middle' })
    text(s, use, { x: x + 2.85, y: y + 0.12, w: w - 5.05, h: 0.54, fontSize: 12, color: MUTED, valign: 'middle' })
    text(s, count, { x: x + w - 2.15, y: y + 0.12, w: 1.9, h: 0.54, fontFace: H, fontSize: 13, bold: true, align: 'right', valign: 'middle' })
  }
  panel(s, x, 5.65, w, 0.85, TINT, 'C9D7F7')
  await badge(s, 'LuSlidersHorizontal', x + 0.2, 5.79, 0.56)
  text(s, 'Each department sets the tier, and can change it live — a camera moves to continuous for a bandobast and back afterwards.', {
    x: x + 0.95, y: 5.73, w: w - 1.15, h: 0.7, fontSize: 13, valign: 'middle',
  })
  text(s, 'Planning assumption, not a survey: the ~80,000 total is from the brief; the split is our estimate from how departments use their cameras. Compute and cost are sized from it; department inventories replace it in the pilot.', {
    x: M, y: 6.75, w: CW - 0.8, h: 0.45, fontSize: 10, italic: true, color: MUTED,
  })
}

async function costSlide() {
  const s = frame({
    eyebrow: 'Estimated cost',
    title: 'What it takes to run statewide',
    notes: 'The brief asks for estimated costs, so we show them — and say “order of magnitude” before the first number. About eighty crore to build and twenty-four crore a year to run for eighty thousand cameras: roughly ten thousand rupees a camera to build and three thousand a year to run. The largest line, district servers, follows from the camera tiering in Appendix A6, which is our planning assumption until departments’ inventories replace it. No software licences. Centralising every camera is conservatively four hundred crore to build. The saving is reuse: nothing installed is replaced. The pilot replaces every estimate with a measured number.',
  })
  s.addChart(pres.charts.BAR, [{
    name: 'Capex',
    labels: ['District analysis servers', 'State data centre', 'Integration & rollout', 'Remote edge boxes', 'Network uplinks', 'Disaster-recovery site'],
    values: [28, 14, 12, 10.5, 9, 7],
  }], {
    x: M, y: 1.75, w: 6.7, h: 4.05, barDir: 'bar', barGapWidthPct: 45,
    chartColors: [BLUE],
    catAxisOrientation: 'maxMin',
    showValue: true, dataLabelPosition: 'outEnd', dataLabelColor: INK, dataLabelFontSize: 13,
    dataLabelFontBold: true, dataLabelFontFace: H, dataLabelFormatCode: '"₹"General" cr"',
    catAxisLabelColor: INK, catAxisLabelFontSize: 13, catAxisLabelFontFace: B,
    valAxisHidden: true, valAxisMaxVal: 34, valGridLine: { style: 'none' }, catGridLine: { style: 'none' },
    catAxisLineShow: false, showLegend: false,
    showTitle: true, title: 'Build cost (capex), ₹ crore', titleColor: MUTED, titleFontSize: 13, titleFontFace: H,
  })
  const x = M + 7.1
  const w = CW - 7.1
  const cw = (w - 0.3) / 2
  const stats = [
    ['≈₹80 cr', 'to build', SAFFRON],
    ['≈₹24 cr', 'a year to run', SAFFRON],
    ['≈₹10,000', 'per camera to build', BLUE],
    ['≈₹3,000', 'per camera, per year', BLUE],
  ]
  for (const [i, [value, label, color]] of stats.entries()) {
    const cx = x + (i % 2) * (cw + 0.3)
    const cy = 1.85 + Math.floor(i / 2) * 1.5
    card(s, cx, cy, cw, 1.28)
    text(s, value, { x: cx + 0.25, y: cy + 0.18, w: cw - 0.5, h: 0.6, fontFace: H, fontSize: 26, bold: true, color })
    text(s, label, { x: cx + 0.25, y: cy + 0.8, w: cw - 0.5, h: 0.35, fontSize: 13, color: MUTED })
  }
  panel(s, x, 4.9, w, 1.0, TINT, 'C9D7F7')
  await badge(s, 'LuLockOpen', x + 0.22, 5.12, 0.56, TEAL)
  text(s, '₹0 in software licences', { x: x + 0.95, y: 5.02, w: w - 1.15, h: 0.36, fontFace: H, fontSize: 15, bold: true })
  text(s, 'Open-source stack: no per-camera VMS fees, which at this scale often outweigh the hardware.', {
    x: x + 0.95, y: 5.38, w: w - 1.15, h: 0.45, fontSize: 12, color: MUTED,
  })
  panel(s, M, 6.02, CW, 0.82, 'FFF4EC', 'F6D9C4')
  await badge(s, 'LuScale', M + 0.22, 6.15, 0.56, RED)
  text(s, [
    { text: 'Centralising every camera: ₹400 cr+ to build', options: { bold: true, color: INK } },
    { text: ' — about five times more, before its higher running cost. The difference is reuse: no camera, recorder or VMS is replaced.', options: { color: MUTED } },
  ], { x: M + 0.95, y: 6.07, w: CW - 1.2, h: 0.72, fontSize: 14, valign: 'middle' })
  text(s, 'Order of magnitude, for comparing approaches — not a tender. ~80,000 cameras; five-year cost of ownership ≈₹200 cr. The pilot replaces every estimate with a measurement.', {
    x: M, y: 7.02, w: CW - 0.8, h: 0.3, fontSize: 10, italic: true, color: MUTED,
  })
}

async function whySlide() {
  const s = frame({
    eyebrow: 'Why Sentinel',
    title: 'What sets Sentinel apart',
    notes: 'The answer to “why you”, in three claims, each with its proof. Proven on Gujarat’s own cameras — the government grid, its footage, its plates. Evidence that holds up — the camera’s own clock, the frame at every stop, a record no one can quietly change. Fits what Gujarat already owns — any vendor, nothing replaced, analysis in each district. Then read the stated-plainly line aloud: the professors will respect it, and the officers will trust the rest more for it.',
  })
  panel(s, M, 1.7, CW, 0.95, TINT, 'C9D7F7')
  text(s, 'Sentinel traces a vehicle across every department’s cameras — on the systems Gujarat already owns, with evidence that holds up.', {
    x: M + 0.35, y: 1.8, w: CW - 0.7, h: 0.75, fontFace: H, fontSize: 18, bold: true, color: BLUE, valign: 'middle',
  })
  const pillars = [
    ['LuMapPinned', SAFFRON, 'Proven on Gujarat’s own cameras',
      'Not a lab demonstration: built and tested on the government’s own camera grid.',
      'All 30 grid cameras onboarded from the live catalogue; plate reading measured on 81 hand-checked plates from that footage.'],
    ['LuGavel', BLUE, 'Evidence that holds up',
      'Every sighting carries the camera’s own time, its frame, and a record no one can quietly change.',
      'Times read off the frame — “time unknown” when unreadable, never a guess; impossible journeys flagged; reports digitally sealed.'],
    ['LuPuzzle', BLUE, 'Fits what Gujarat already owns',
      'Any vendor’s cameras and VMS, nothing replaced, analysis in each district.',
      'RTSP, ONVIF, Hikvision and Dahua; about 1,000× less network than centralising; keeps alerting offline for 72 hours.'],
  ]
  const cw = (CW - 2 * 0.3) / 3
  for (const [i, [ic, color, title, claim, proof]] of pillars.entries()) {
    const x = M + i * (cw + 0.3)
    const y = 2.95
    card(s, x, y, cw, 3.35)
    await badge(s, ic, x + 0.3, y + 0.3, 0.66, color)
    text(s, title, { x: x + 1.1, y: y + 0.32, w: cw - 1.35, h: 0.66, fontFace: H, fontSize: 17, bold: true, valign: 'middle' })
    text(s, claim, { x: x + 0.3, y: y + 1.15, w: cw - 0.6, h: 0.8, fontSize: 14 })
    s.addShape(pres.shapes.LINE, { x: x + 0.3, y: y + 2.02, w: cw - 0.6, h: 0, line: { color: LINE, width: 0.75 } })
    await badge(s, 'LuBadgeCheck', x + 0.3, y + 2.17, 0.3, TEAL)
    text(s, 'Proof', { x: x + 0.7, y: y + 2.17, w: 1.5, h: 0.3, fontFace: H, fontSize: 11, bold: true, color: TEAL, valign: 'middle' })
    text(s, proof, { x: x + 0.3, y: y + 2.52, w: cw - 0.6, h: 0.78, fontSize: 12, color: MUTED })
  }
  panel(s, M, 6.45, CW, 0.62, 'FDF1DF', 'F5D6A6')
  await badge(s, 'LuMessageSquareText', M + 0.15, 6.53, 0.46, SAFFRON)
  text(s, [
    { text: 'Stated plainly:  ', options: { bold: true, color: SAFFRON_TEXT } },
    { text: 'plate accuracy is 78%, below our 85% target  ·  compute is sized from vendor benchmarks  ·  plate-less matching is designed, not built.', options: { color: INK } },
  ], { x: M + 0.75, y: 6.47, w: CW - 0.9, h: 0.58, fontSize: 12.5, valign: 'middle' })
}

async function compareSlide() {
  const s = frame({
    eyebrow: 'Choosing an approach',
    title: 'How Sentinel compares',
    notes: 'There are really two other ways to do this. Leave every department on its own system — nothing changes, and nothing connects. Or pull every camera into one central system — it connects everything, but it re-routes all the video, needs a backbone the State does not have, and stops when a link drops. Sentinel gets the reach of the second without disturbing anything in the first. We compare approaches here, not named products.',
  })
  const cols = ['Separate department systems', 'Centralise every camera', 'Sentinel']
  const rows = [
    ['Trace a vehicle across all departments', ['no', 'Phone calls and manual review'], ['yes', 'Yes'], ['yes', 'One search, seconds']],
    ['Watchlist alerts statewide', ['no', 'Each system on its own'], ['yes', 'Yes'], ['yes', 'Every read, automatically']],
    ['Departments’ systems left untouched', ['part', 'Untouched, but isolated'], ['no', 'All video re-routed centrally'], ['yes', 'Read-only access']],
    ['Network the State must provide', ['part', 'Little — nothing is shared'], ['no', '≈160 Gbps, sustained'], ['yes', '≈140 Mbps']],
    ['When a district’s link drops', ['part', 'Works locally, still isolated'], ['no', 'Analysis stops'], ['yes', 'Keeps reading and alerting']],
  ]
  const labelW = 3.35
  const colW = (CW - labelW) / 3
  const top = 1.85
  const headH = 0.6
  const rowH = 0.8
  // The Sentinel column, lifted.
  panel(s, M + labelW + 2 * colW + 0.05, top - 0.08, colW - 0.1, headH + rows.length * rowH + 0.16, TINT, 'C9D7F7')
  for (const [j, c] of cols.entries()) {
    const sentinel = j === 2
    text(s, c, {
      x: M + labelW + j * colW + 0.25, y: top, w: colW - 0.5, h: headH, fontFace: H, fontSize: sentinel ? 18 : 14,
      bold: true, color: sentinel ? BLUE : MUTED, valign: 'middle',
    })
  }
  const mark = { yes: ['LuCircleCheck', TEAL], part: ['LuCircleMinus', SAFFRON], no: ['LuCircleX', RED] }
  for (const [i, [label, ...cells]] of rows.entries()) {
    const y = top + headH + i * rowH
    s.addShape(pres.shapes.LINE, { x: M, y, w: CW, h: 0, line: { color: LINE, width: 0.75 } })
    text(s, label, { x: M, y: y + 0.12, w: labelW - 0.2, h: rowH - 0.24, fontFace: H, fontSize: 14, bold: true, valign: 'middle' })
    for (const [j, [kind, value]] of cells.entries()) {
      const x = M + labelW + j * colW + 0.25
      const [ic, color] = mark[kind]
      s.addImage({ data: await icon(ic, color), x, y: y + 0.24, w: 0.32, h: 0.32 })
      text(s, value, {
        x: x + 0.45, y: y + 0.1, w: colW - 0.95, h: rowH - 0.2, fontSize: 13, valign: 'middle',
        bold: j === 2, color: j === 2 ? INK : MUTED,
      })
    }
  }
  text(s, 'Approaches compared, not named products. Network figures are for ~80,000 cameras, from our scale plan.', {
    x: M, y: 6.75, w: CW, h: 0.3, fontSize: 11, italic: true, color: MUTED,
  })
}

async function proofSlide() {
  const s = frame({
    eyebrow: 'Proven, not promised',
    title: 'Measured on real government footage',
    notes: 'Say “we measured that”. The plate accuracy is measured on hand-checked plates from the government grid — and it is below our own target, which we say plainly; it started at under ten percent and the measurement is what drove it up. The rest is the discipline behind it: a laptop handling live analysis, more than six hundred automated tests, and a disaster-recovery drill that restores a million records in seconds and proves nothing was altered.',
  })
  const stats = [
    ['78%', 'plates read exactly', 'On 81 hand-checked real government plates; 88% of characters correct'],
    ['16', 'frames a second, on one laptop', 'End-to-end live analysis on a CPU — the on-site set-up'],
    ['600+', 'automated tests', 'Plus interface tests in three languages and two themes'],
    ['5.7 s', 'to restore a million records', 'Disaster-recovery drill, with tampering detected'],
  ]
  const cw = (CW - 3 * 0.3) / 4
  for (const [i, [value, label, sub]] of stats.entries()) {
    const x = M + i * (cw + 0.3)
    card(s, x, 1.85, cw, 2.75)
    text(s, value, { x: x + 0.3, y: 2.05, w: cw - 0.6, h: 0.9, fontFace: H, fontSize: 44, bold: true, color: TEAL })
    text(s, label, { x: x + 0.3, y: 3.0, w: cw - 0.6, h: 0.6, fontFace: H, fontSize: 14, bold: true })
    text(s, sub, { x: x + 0.3, y: 3.62, w: cw - 0.6, h: 0.85, fontSize: 12, color: MUTED })
  }
  panel(s, M, 4.95, CW, 1.6)
  await badge(s, 'LuMessageSquareText', M + 0.35, 5.2, 0.56, SAFFRON)
  text(s, 'Stated plainly', { x: M + 1.1, y: 5.2, w: 4, h: 0.4, fontFace: H, fontSize: 17, bold: true })
  s.addText([
    { text: 'Plate accuracy is below our own 85% target', options: { bullet: { indent: 14 }, breakLine: true } },
    { text: 'Statewide compute is sized from vendor benchmarks', options: { bullet: { indent: 14 } } },
  ], { x: M + 1.1, y: 5.65, w: 5.4, h: 0.8, margin: 0, fontFace: B, fontSize: 14, color: INK, paraSpaceAfter: 6 })
  s.addText([
    { text: 'Matching vehicles with no readable plate is designed, not built', options: { bullet: { indent: 14 }, breakLine: true } },
    { text: 'The pilot replaces every estimate with a measurement', options: { bullet: { indent: 14 } } },
  ], { x: M + 6.6, y: 5.65, w: 5.6, h: 0.8, margin: 0, fontFace: B, fontSize: 14, color: INK, paraSpaceAfter: 6 })
}

async function rolloutSlide() {
  const s = frame({
    eyebrow: 'Path to statewide',
    title: 'Useful from the first district. No big-bang switch-over.',
    notes: 'Each phase is useful on its own and none needs a big-bang cutover: one district pilot in three months, four districts and the main VMS vendors by nine, every district by twenty-one months, and consented private cameras in the last phase.',
  })
  const phases = [
    ['Pilot', '0–3 months', '~500', '1 district, 2 departments', 'Plate reading validated on live feeds; operators sign off'],
    ['Expand', '3–9 months', '~5,000', '4 districts, 6 departments', 'Main VMS vendors connected; VAHAN and eGujCop live'],
    ['Statewide', '9–21 months', '~30,000', 'All 34 districts', 'Statewide vehicle tracking; operations centre in place'],
    ['Complete', '21–36 months', '80,000', 'Plus consented private cameras', 'Full coverage, with policy and audit established'],
  ]
  const cw = (CW - 3 * 0.3) / 4
  s.addShape(pres.shapes.LINE, { x: M + 0.31, y: 2.12, w: CW - 0.62, h: 0, line: { color: LINE, width: 2 } })
  for (const [i, [name, when, count, scope, exit]] of phases.entries()) {
    const x = M + i * (cw + 0.3)
    s.addShape(pres.shapes.OVAL, { x: x + 0.15, y: 1.96, w: 0.32, h: 0.32, fill: { color: i === 0 ? SAFFRON : BLUE }, line: { color: WHITE, width: 3 } })
    text(s, `${name}  ·  ${when}`, { x, y: 2.45, w: cw, h: 0.3, fontFace: H, fontSize: 12, bold: true, color: i === 0 ? SAFFRON_TEXT : BLUE })
    if (i === 0) panel(s, x, 2.9, cw, 3.55, TINT, 'C9D7F7')
    else card(s, x, 2.9, cw, 3.55)
    text(s, count, { x: x + 0.3, y: 3.1, w: cw - 0.6, h: 0.75, fontFace: H, fontSize: 36, bold: true })
    text(s, 'cameras', { x: x + 0.3, y: 3.82, w: cw - 0.6, h: 0.3, fontSize: 13, color: MUTED })
    text(s, scope, { x: x + 0.3, y: 4.3, w: cw - 0.6, h: 0.6, fontFace: H, fontSize: 14, bold: true })
    text(s, exit, { x: x + 0.3, y: 4.95, w: cw - 0.6, h: 1.3, fontSize: 13, color: MUTED })
  }
}

async function nextSlide() {
  const s = frame({
    eyebrow: 'The next step',
    title: 'Start with one district. Grow without a switch-over.',
    background: TINT,
    notes: 'Close calmly. Each phase is useful on its own — a district pilot in three months, then four districts, then every district, then consented private cameras — and none needs a big-bang cutover. To begin we need three things: each department’s camera inventory, read-only access, and database access when it is ready. Then the line, and stop talking. Hand over the Movement Report from the demonstration if it has not been handed over already.',
  })
  const phases = [
    ['Pilot', '0–3 months', '~500 cameras', '1 district, 2 departments', true],
    ['Expand', '3–9 months', '~5,000 cameras', '4 districts, 6 departments', false],
    ['Statewide', '9–21 months', '~30,000 cameras', 'All 34 districts', false],
    ['Complete', '21–36 months', '80,000 cameras', 'Plus consented private cameras', false],
  ]
  const pw = (CW - 3 * 0.3) / 4
  for (const [i, [name, when, count, scope, pilot]] of phases.entries()) {
    const x = M + i * (pw + 0.3)
    card(s, x, 1.75, pw, 1.35)
    text(s, `${name}  ·  ${when}`, { x: x + 0.25, y: 1.88, w: pw - 0.5, h: 0.3, fontFace: H, fontSize: 12, bold: true, color: pilot ? SAFFRON_TEXT : BLUE })
    text(s, count, { x: x + 0.25, y: 2.2, w: pw - 0.5, h: 0.45, fontFace: H, fontSize: 19, bold: true })
    text(s, scope, { x: x + 0.25, y: 2.67, w: pw - 0.5, h: 0.35, fontSize: 12, color: MUTED })
  }
  text(s, 'To begin the pilot, we need', { x: M, y: 3.35, w: CW, h: 0.4, fontFace: H, fontSize: 16, bold: true })
  const asks = [
    ['LuClipboardList', 'Each department’s camera inventory', 'Cameras, recorders, network, locations — and whether each feed shows the date and time.'],
    ['LuLink', 'Read-only access', 'To the streams or each VMS. Nothing installed on department infrastructure.'],
    ['LuKeyRound', 'Database access, when ready', 'VAHAN, SARTHI, eGujCop, AFIS, NAFIS — switched on as a setting the day it is granted.'],
  ]
  const aw = (CW - 2 * 0.3) / 3
  for (const [i, [ic, title, body]] of asks.entries()) {
    const x = M + i * (aw + 0.3)
    card(s, x, 3.8, aw, 1.75)
    await badge(s, ic, x + 0.25, 4.05, 0.56)
    text(s, title, { x: x + 0.95, y: 4.02, w: aw - 1.15, h: 0.62, fontFace: H, fontSize: 15, bold: true, valign: 'middle' })
    text(s, body, { x: x + 0.95, y: 4.68, w: aw - 1.15, h: 0.8, fontSize: 12.5, color: MUTED })
  }
  text(s, 'Type a plate. See where it went.', { x: M, y: 5.85, w: CW, h: 0.7, fontFace: H, fontSize: 32, bold: true, color: BLUE })
  text(s, 'Thank you — questions welcome.', { x: M, y: 6.55, w: CW, h: 0.4, fontSize: 16, color: MUTED })
}

const APPENDIX = [
  ['A1', 'Who it serves', 'Operator, investigator, patrol, leadership; field app'],
  ['A2', 'Demo backup — connect and see', 'The live wall on government footage'],
  ['A3', 'Demo backup — trace the vehicle', 'A route timed by the camera’s own clock'],
  ['A4', 'Demo backup — get alerted', 'A watchlist alert and how misreads are caught'],
  ['A5', 'Beyond number plates', 'Vehicle type and colour, people counts, zones, tamper'],
  ['A6', 'Camera tiering at 80,000', 'The planning split behind compute and cost'],
  ['A7', 'How Sentinel compares', 'Against separate systems and full centralisation'],
  ['A8', 'Measured results', 'Accuracy, capacity, tests and the DR drill'],
  ['A9', 'Rollout in detail', 'Each phase with its exit criteria'],
]

async function appendixDivider() {
  const s = pres.addSlide()
  s.background = { color: SOFT }
  text(s, 'APPENDIX', { x: M, y: 0.9, w: CW, h: 0.35, fontFace: H, fontSize: 13, bold: true, color: SAFFRON_TEXT, charSpacing: 4 })
  text(s, 'For reference and questions', { x: M, y: 1.3, w: CW, h: 0.8, fontFace: H, fontSize: 36, bold: true })
  const cw = (CW - 0.4) / 2
  for (const [i, [label, title, body]] of APPENDIX.entries()) {
    const col = i < 5 ? 0 : 1
    const row = i < 5 ? i : i - 5
    const x = M + col * (cw + 0.4)
    const y = 2.45 + row * 0.9
    card(s, x, y, cw, 0.74)
    text(s, label, { x: x + 0.25, y: y + 0.12, w: 0.7, h: 0.5, fontFace: H, fontSize: 18, bold: true, color: BLUE, valign: 'middle' })
    text(s, title, { x: x + 1.0, y: y + 0.08, w: cw - 1.2, h: 0.32, fontFace: H, fontSize: 14, bold: true })
    text(s, body, { x: x + 1.0, y: y + 0.4, w: cw - 1.2, h: 0.3, fontSize: 12, color: MUTED })
  }
  s.addNotes('Not presented. Jump here from a question: each appendix slide is numbered A1–A9 in its corner.')
}

async function main() {
  const story = [
    [null, titleSlide],
    [null, teamSlide],
    ['Why', problemSlide],
    ['What', platformSlide],
    ['Demo', demoSlide],
    ['Trust', trustSlide],
    ['How', approachSlide],
    ['How', efficiencySlide],
    ['How', architectureSlide],
    ['How', stackSlide],
    ['Value', costSlide],
    ['Value', whySlide],
    ['Next', nextSlide],
  ]
  for (const [chapter, build] of story) {
    section.chapter = chapter
    await build()
  }
  section.chapter = null
  section.appendix = true
  await appendixDivider()
  for (const build of [audienceSlide, connectSlide, traceSlide, alertSlide, beyondSlide, tieringSlide, compareSlide, proofSlide, rolloutSlide]) {
    await build()
  }
  await pres.writeFile({ fileName: OUT })
  console.log(`wrote ${OUT} (${mainCount} main slides, appendix A1–A${appendixCount})`)
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
