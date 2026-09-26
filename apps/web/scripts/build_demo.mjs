/**
 * Turns the raw walkthrough into the submission cut.
 *
 * Screen capture alone is not a demo: it has no framing, no emphasis, and a
 * jury cannot tell what it is looking at. This adds the three things that
 * close that gap — a title, a caption per beat saying what is being claimed,
 * and a punch-in on the moments that carry the claim (the plate read, the
 * reconstructed route) which are otherwise a few dozen pixels wide.
 *
 * Cards are rendered in the browser rather than with ffmpeg's text filter:
 * this ffmpeg has no libfreetype, and cards built from the product's own
 * palette and typeface look designed rather than assembled.
 *
 *   node scripts/build_demo.mjs
 *
 * Reads  var/demo/raw.webm + beats.json
 * Writes var/demo/sentinel-demo.mp4
 */
import { chromium } from '@playwright/test'
import { execFileSync } from 'child_process'
import { existsSync, mkdirSync, readFileSync, rmSync } from 'fs'
import { join, resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

const REPO = resolve(process.cwd(), '..', '..')
const OUT = join(REPO, 'var', 'demo')
const WORK = join(OUT, '.build')
const CARDS = join(WORK, 'cards')
const CARD_HTML = `file://${join(dirname(fileURLToPath(import.meta.url)), 'demo-cards.html')}`

const W = 1440
const H = 900
const FPS = 30

const ff = (args) => execFileSync('ffmpeg', ['-y', '-hide_banner', '-loglevel', 'error', ...args])

/**
 * What each beat claims, and where to look while it is claimed.
 *
 * `focus` is a region of the 1440x900 frame to punch into. The detail that
 * matters in this product is small — a confidence badge, a timeline entry —
 * and at video bitrates an un-zoomed capture reduces it to mush.
 */
const SCRIPT = {
  overview: {
    step: 'Step 01 — Discovery',
    head: 'Thirty government cameras, onboarded by catalogue',
    detail: 'No hand-typed endpoints. One call reads the department catalogue and registers the fleet.',
    hold: 7,
  },
  livewall: {
    step: 'Step 02 — Live video',
    head: 'Real government CCTV, no credentials in the browser',
    detail: 'The camera\u2019s authenticated URL never leaves the server. The browser only ever sees our own relay.',
    hold: 20,
    focus: { x: 415, y: 330, w: 1000, h: 560, at: 9 },
  },
  search: {
    step: 'Step 03 — Investigation',
    head: 'A registration goes in',
    detail: 'The same question an officer actually asks: where has this vehicle been?',
    hold: 5.5,
  },
  trail: {
    step: 'Step 04 — The answer',
    head: 'A timestamped, mapped route comes out',
    detail: 'Every sighting carries its camera, its time, its confidence, and the frame it came from.',
    hold: 14,
    focus: { x: 740, y: 420, w: 690, h: 470, at: 7 },
  },
  compliance: {
    step: 'Step 05 — Evidence',
    head: 'Checks, not claims',
    detail: 'Integrator rules asserted in a test suite — including the one this run could not satisfy.',
    hold: 9,
  },
}

async function renderCards(stats) {
  mkdirSync(CARDS, { recursive: true })
  const browser = await chromium.launch()
  const page = await browser.newPage({ viewport: { width: W, height: H } })

  const shot = async (url, file, transparent) => {
    await page.goto(url, { waitUntil: 'networkidle' })
    await page.waitForTimeout(500) // let the webfont land before capture
    await page.screenshot({ path: join(CARDS, file), omitBackground: !!transparent })
  }

  await shot(`${CARD_HTML}?card=title`, 'title.png', false)
  const foot =
    'Cross-camera tracking is not shown: the test grid replays each camera from a different date. Recorded in evidence/.'
  await shot(
    `${CARD_HTML}?card=end&reads=${stats.reads}&plates=${stats.plates}&foot=${encodeURIComponent(foot)}`,
    'end.png',
    false,
  )
  for (const [key, b] of Object.entries(SCRIPT)) {
    const q = `card=caption&step=${encodeURIComponent(b.step)}&head=${encodeURIComponent(b.head)}&detail=${encodeURIComponent(b.detail)}`
    await shot(`${CARD_HTML}?${q}`, `cap-${key}.png`, true)
  }
  await browser.close()
}

/** One beat: trimmed, optionally punched in, captioned, faded at both ends. */
function buildSegment(raw, key, beat, index) {
  const spec = SCRIPT[key]
  if (!spec) return null
  const start = beat.startS + 0.4 // skip the navigation flash
  const dur = Math.min(spec.hold, Math.max(2, beat.endS - start - 0.3))
  const seg = join(WORK, `seg-${index}-${key}.mp4`)
  const base = join(WORK, `base-${index}-${key}.mp4`)

  if (spec.focus) {
    // Hold wide, then move to the detail. Done as two shots crossfaded rather
    // than an animated crop: ffmpeg evaluates crop dimensions once, and a
    // filter whose output size changes per frame is not a thing it will
    // encode. Two shots also reads more deliberately than a slow drift.
    const f = spec.focus
    const cut = Math.max(2, Math.min(f.at, dur - 2.5))
    const wide = join(WORK, `w-${index}.mp4`)
    const tight = join(WORK, `t-${index}.mp4`)
    // Short enough to read as a cut. Dissolving between two scales of the
    // same shot double-exposes the text and looks like a mistake; a punch-in
    // is meant to feel decisive.
    const XF = 0.22
    ff(['-ss', start.toFixed(3), '-t', (cut + XF).toFixed(3), '-i', raw,
      '-vf', `setsar=1`, '-r', String(FPS), '-c:v', 'libx264', '-preset', 'medium',
      '-crf', '18', '-pix_fmt', 'yuv420p', wide])
    ff(['-ss', (start + cut).toFixed(3), '-t', (dur - cut).toFixed(3), '-i', raw,
      '-vf', `crop=${f.w}:${f.h}:${f.x}:${f.y},scale=${W}:${H}:flags=lanczos,setsar=1`,
      '-r', String(FPS), '-c:v', 'libx264', '-preset', 'medium', '-crf', '18',
      '-pix_fmt', 'yuv420p', tight])
    ff(['-i', wide, '-i', tight, '-filter_complex',
      `[0:v][1:v]xfade=transition=fade:duration=${XF}:offset=${cut.toFixed(3)}[o]`,
      '-map', '[o]', '-r', String(FPS), '-c:v', 'libx264', '-preset', 'medium',
      '-crf', '18', '-pix_fmt', 'yuv420p', base])
  } else {
    ff(['-ss', start.toFixed(3), '-t', dur.toFixed(3), '-i', raw,
      '-vf', 'setsar=1', '-r', String(FPS), '-c:v', 'libx264', '-preset', 'medium',
      '-crf', '18', '-pix_fmt', 'yuv420p', base])
  }

  ff([
    '-i', base,
    // `-loop 1` matters: without it the PNG is a single frame and the overlay
    // appears for exactly 1/30th of a second, which looks identical to the
    // caption never being drawn at all.
    '-loop', '1', '-t', dur.toFixed(3), '-i', join(CARDS, `cap-${key}.png`),
    '-filter_complex',
    `[0:v]fade=t=in:st=0:d=0.4,fade=t=out:st=${(dur - 0.4).toFixed(2)}:d=0.4,setsar=1[v];` +
      // The caption fades in just after the cut and out before it, so it never
      // collides with the crossfade into the next beat.
      `[1:v]format=rgba,fade=t=in:st=0.5:d=0.5:alpha=1,fade=t=out:st=${Math.max(1.2, dur - 1.1).toFixed(2)}:d=0.5:alpha=1[c];` +
      `[v][c]overlay=0:0:format=auto[out]`,
    '-map', '[out]', '-r', String(FPS), '-c:v', 'libx264', '-preset', 'medium',
    '-crf', '19', '-pix_fmt', 'yuv420p', seg,
  ])
  return { file: seg, dur }
}

function cardClip(png, seconds, name) {
  const file = join(WORK, name)
  ff([
    '-loop', '1', '-t', String(seconds), '-i', png,
    '-vf', `fade=t=in:st=0:d=0.5,fade=t=out:st=${seconds - 0.6}:d=0.6,setsar=1`,
    '-r', String(FPS), '-c:v', 'libx264', '-preset', 'medium', '-crf', '19',
    '-pix_fmt', 'yuv420p', file,
  ])
  return { file, dur: seconds }
}

/** Crossfade a list of clips into one timeline. */
function crossfade(clips, out) {
  // Short. Half a second of dissolve between two unrelated screens shows both
  // at once — the empty state ghosting through the results — which reads as a
  // rendering fault rather than an edit.
  const XF = 0.35
  const inputs = clips.flatMap((c) => ['-i', c.file])
  let filter = ''
  let prev = '[0:v]'
  let offset = clips[0].dur - XF
  for (let i = 1; i < clips.length; i++) {
    const label = i === clips.length - 1 ? '[out]' : `[x${i}]`
    filter += `${prev}[${i}:v]xfade=transition=fade:duration=${XF}:offset=${offset.toFixed(3)}${label};`
    prev = label
    offset += clips[i].dur - XF
  }
  ff([
    ...inputs, '-filter_complex', filter.replace(/;$/, ''),
    '-map', '[out]', '-r', String(FPS), '-c:v', 'libx264', '-preset', 'slow',
    '-crf', '20', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', out,
  ])
}

async function main() {
  const raw = join(OUT, 'raw.webm')
  if (!existsSync(raw)) throw new Error(`no raw recording at ${raw} — run record_demo.mjs first`)
  const beats = JSON.parse(readFileSync(join(OUT, 'beats.json'), 'utf8'))
  const stats = JSON.parse(process.env.DEMO_STATS ?? '{"reads":"—","plates":"—"}')

  rmSync(WORK, { recursive: true, force: true })
  mkdirSync(WORK, { recursive: true })

  console.log('rendering cards ...')
  await renderCards(stats)

  console.log('cutting beats ...')
  const clips = [cardClip(join(CARDS, 'title.png'), 4.5, 'title.mp4')]
  beats.forEach((b, i) => {
    const seg = buildSegment(raw, b.key, b, i)
    if (seg) {
      clips.push(seg)
      console.log(`  ${b.key} -> ${seg.dur.toFixed(1)}s`)
    }
  })
  clips.push(cardClip(join(CARDS, 'end.png'), 6.5, 'end.mp4'))

  console.log('composing ...')
  const out = join(OUT, 'sentinel-demo.mp4')
  crossfade(clips, out)
  rmSync(WORK, { recursive: true, force: true })

  const total = clips.reduce((s, c) => s + c.dur, 0) - 0.35 * (clips.length - 1)
  console.log(`\n${out}  (~${total.toFixed(0)}s)`)
}

await main()
