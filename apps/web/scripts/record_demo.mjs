/**
 * Records the raw console walkthrough, and writes the beat timings alongside
 * it so `build_demo.mjs` can cut and title the footage without guessing.
 *
 * Capturing the page rather than the screen is deliberate: these screens carry
 * live government CCTV, and a desktop recorder would also take in whatever
 * else is on the machine — terminals holding credentials, notifications.
 *
 *   node scripts/record_demo.mjs
 *
 * Output: var/demo/raw.webm + var/demo/beats.json
 */
import { chromium } from '@playwright/test'
import { mkdirSync, readdirSync, renameSync, rmSync, writeFileSync } from 'fs'
import { join, resolve } from 'path'

const BASE = process.env.DEMO_BASE_URL ?? 'http://localhost:5173'
const EMAIL = process.env.DEMO_EMAIL ?? 'admin@sentinel-platform.com'
const PASSWORD = process.env.DEMO_PASSWORD ?? 'sentinel-admin-2026'
const PLATE = process.env.DEMO_PLATE ?? 'GJ11CQ9625'
const CAMERA = process.env.DEMO_CAMERA ?? 'cam06'

const REPO = resolve(process.cwd(), '..', '..')
const OUT = join(REPO, 'var', 'demo')
const RAW = join(OUT, '.raw')

async function main() {
  rmSync(RAW, { recursive: true, force: true })
  mkdirSync(RAW, { recursive: true })

  // `channel: 'chromium'` is load-bearing. Playwright defaults to the headless
  // *shell*, which ships without the codecs H.264 needs: video elements there
  // report videoWidth 0 and never decode a frame. The recording still succeeds
  // and still looks plausible — it just has a black rectangle exactly where
  // the live CCTV should be. Measured: shell 0, full chromium 1920 at 40.9s.
  const browser = await chromium.launch({ channel: 'chromium' })
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    recordVideo: { dir: RAW, size: { width: 1440, height: 900 } },
  })
  const page = await context.newPage()
  // Recording begins with the page, which is before the login. Anchoring beat
  // times to the first beat instead left every caption ~10s adrift of the
  // footage it described — the closing claim landed over the wrong screen.
  const t0 = Date.now()

  const beats = []
  const now = () => Date.now()
  /** Mark a span of the recording as a named beat. Timings are measured, not
   *  assumed, because live pages take a variable time to settle. */
  const beat = async (key, ms, fn) => {
    if (fn) await fn()
    const start = now()
    await page.waitForTimeout(ms)
    beats.push({ key, startS: (start - t0) / 1000, endS: (now() - t0) / 1000 })
    console.log(`  ${key}`)
  }

  // Sign in before the timeline starts — credentials being typed is not a
  // beat anyone needs to watch.
  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('input[type="email"]', { timeout: 30000 })
  await page.fill('input[type="email"]', EMAIL)
  await page.fill('input[type="password"]', PASSWORD)
  await page.evaluate(() => document.querySelector('form')?.requestSubmit())
  await page.waitForTimeout(6500)

  console.log('recording:')

  await beat('overview', 8000, async () => {
    await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(3500)
  })

  await beat('livewall', 30000, async () => {
    await page.goto(`${BASE}/live-wall`, { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('select', { timeout: 30000 })
    await page.waitForTimeout(2500)
    // Single-camera focus: a 2x2 of wide-area traffic is unreadable at video
    // bitrates, and four concurrent HLS sessions on a lossy uplink routinely
    // leave a tile still negotiating, which reads as a broken product.
    const focus = page.locator('button', { hasText: /focus/i }).first()
    if (await focus.count()) {
      await focus.click()
      await page.waitForTimeout(2500)
      const selects = page.locator('select')
      const n = await selects.count()
      if (n > 1) await selects.nth(n - 1).selectOption(CAMERA).catch(() => {})
    }
    await page.waitForTimeout(9000) // let HLS actually start before the beat counts
  })

  await beat('search', 4000, async () => {
    await page.goto(`${BASE}/find-a-vehicle`, { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('input', { timeout: 30000 })
    await page.waitForTimeout(2000)
    const field = await page.$('input[type="text"], input:not([type]):not([type="hidden"])')
    if (field) await field.type(PLATE, { delay: 85 })
  })

  await beat('trail', 15000, async () => {
    await page.evaluate(() => document.querySelector('form')?.requestSubmit())
    await page.waitForTimeout(7000)
  })

  await beat('compliance', 10000, async () => {
    await page.goto(`${BASE}/health`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(3500)
  })

  await context.close() // flushes the video
  await browser.close()

  const file = readdirSync(RAW).find((f) => f.endsWith('.webm'))
  if (!file) throw new Error('playwright produced no video')
  renameSync(join(RAW, file), join(OUT, 'raw.webm'))
  rmSync(RAW, { recursive: true, force: true })
  writeFileSync(join(OUT, 'beats.json'), JSON.stringify(beats, null, 2))
  console.log(`\nraw: ${join(OUT, 'raw.webm')}`)
  console.log(
    `beats: ${beats.map((b) => `${b.key} ${b.startS.toFixed(1)}-${b.endS.toFixed(1)}s`).join(', ')}`,
  )
}

await main()
