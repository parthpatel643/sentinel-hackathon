/**
 * Records a narrated-pace walkthrough of the operator console as video.
 *
 * Playwright captures the browser viewport directly, which matters here for a
 * reason beyond convenience: these screens show live government CCTV, and a
 * desktop screen recorder would also capture whatever else is on the machine —
 * terminals holding credentials, other windows, notifications. Recording the
 * page and nothing else keeps the artefact to exactly what is meant to be in
 * it.
 *
 * Beats follow docs/06-SUBMISSION-PLAYBOOK.md section 4, minus the terminal
 * segments, which are not browser content and belong in a separate capture.
 *
 *   node scripts/record_demo.mjs                  # defaults below
 *   DEMO_PLATE=GJ11E1185 node scripts/record_demo.mjs
 *
 * Output: var/demo/sentinel-console-demo.webm (+ .mp4 when ffmpeg is present).
 */
import { chromium } from '@playwright/test'
import { mkdirSync, readdirSync, renameSync, rmSync, existsSync } from 'fs'
import { join, resolve } from 'path'

const BASE = process.env.DEMO_BASE_URL ?? 'http://localhost:5173'
const EMAIL = process.env.DEMO_EMAIL ?? 'admin@sentinel-platform.com'
const PASSWORD = process.env.DEMO_PASSWORD ?? 'sentinel-admin-2026'
const PLATE = process.env.DEMO_PLATE ?? 'GJ11CQ9625'
const CAMERA = process.env.DEMO_CAMERA ?? 'cam06'

const REPO = resolve(process.cwd(), '..', '..')
const OUT_DIR = join(REPO, 'var', 'demo')
const RAW_DIR = join(OUT_DIR, '.raw')

/** A beat holds for long enough to be read, not just rendered. Live video in
 *  particular needs several seconds before a viewer believes it is moving. */
const beat = (page, ms, label) => {
  console.log(`  ${label}`)
  return page.waitForTimeout(ms)
}

async function main() {
  rmSync(RAW_DIR, { recursive: true, force: true })
  mkdirSync(RAW_DIR, { recursive: true })

  // `channel: 'chromium'` is load-bearing, not a preference. Playwright now
  // defaults to the headless *shell*, which ships without the proprietary
  // codecs H.264 needs — video elements there report videoWidth 0 and never
  // decode a frame. The recording still succeeds and still looks plausible;
  // it simply has a black rectangle exactly where the live CCTV should be,
  // which is the one thing this video exists to show. Measured side by side:
  // headless shell gave videoWidth 0, full chromium gave 1920 at 40.9s.
  const browser = await chromium.launch({ channel: 'chromium' })
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    recordVideo: { dir: RAW_DIR, size: { width: 1440, height: 900 } },
  })
  const page = await context.newPage()

  console.log('recording:')

  // --- Sign in -----------------------------------------------------------
  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('input[type="email"]', { timeout: 30000 })
  await beat(page, 1800, 'login screen')
  // Typed rather than filled: a demo should look like someone using the
  // product, and an instantly-populated field does not.
  await page.type('input[type="email"]', EMAIL, { delay: 45 })
  await page.type('input[type="password"]', PASSWORD, { delay: 45 })
  await beat(page, 800, 'credentials entered')
  await page.evaluate(() => document.querySelector('form')?.requestSubmit())
  await page.waitForTimeout(6000)

  // --- The fleet on a map ------------------------------------------------
  await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded' })
  await beat(page, 9000, 'overview — the real grid plotted across Gujarat')

  // --- Live government video --------------------------------------------
  await page.goto(`${BASE}/live-wall`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('select', { timeout: 30000 })
  await beat(page, 6000, 'live wall - the grid')

  // Switch to single-camera focus for the main beat. A 2x2 of wide-area
  // traffic is hard to read at video bitrates, and four simultaneous HLS
  // sessions over a lossy uplink routinely leave a tile still negotiating,
  // which reads as a broken product rather than an idle camera. One large
  // tile is clearer and far more likely to actually be playing.
  const focus = page.locator('button', { hasText: /focus/i }).first()
  if (await focus.count()) {
    await focus.click()
    await page.waitForTimeout(3000)
    const selects = page.locator('select')
    const n = await selects.count()
    if (n > 1) await selects.nth(n - 1).selectOption(CAMERA).catch(() => {})
  }
  await beat(page, 36000, `focus on ${CAMERA} - government CCTV, no credentials in the browser`)

  // --- Find a vehicle ----------------------------------------------------
  await page.goto(`${BASE}/find-a-vehicle`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('input', { timeout: 30000 })
  await beat(page, 2500, 'find a vehicle')

  const field = await page.$('input[type="text"], input:not([type]):not([type="hidden"])')
  if (field) {
    await field.type(PLATE, { delay: 90 })
  } else {
    await page.evaluate((p) => {
      const t = [...document.querySelectorAll('input')].find((x) => x.closest('form'))
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set
      setter.call(t, p)
      t.dispatchEvent(new Event('input', { bubbles: true }))
    }, PLATE)
  }
  await beat(page, 1200, `plate ${PLATE} entered`)
  await page.evaluate(() => document.querySelector('form')?.requestSubmit())
  await beat(page, 14000, 'route, timeline and evidence snapshot')

  // --- Registry and health ----------------------------------------------
  await page.goto(`${BASE}/cameras`, { waitUntil: 'domcontentloaded' })
  await beat(page, 8000, 'camera registry')

  await page.goto(`${BASE}/health`, { waitUntil: 'domcontentloaded' })
  await beat(page, 7000, 'fleet health')

  await context.close() // flushes the video file
  await browser.close()

  // Playwright names videos by an internal id; give it a name a human can use.
  const raw = readdirSync(RAW_DIR).find((f) => f.endsWith('.webm'))
  if (!raw) throw new Error('playwright produced no video')
  const webm = join(OUT_DIR, 'sentinel-console-demo.webm')
  renameSync(join(RAW_DIR, raw), webm)
  rmSync(RAW_DIR, { recursive: true, force: true })
  console.log(`\nwebm: ${webm}`)
  if (existsSync(webm)) console.log('done')
}

await main()
