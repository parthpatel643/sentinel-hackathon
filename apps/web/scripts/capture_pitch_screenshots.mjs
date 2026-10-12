/**
 * Captures everything the pitch deck (scripts/build_pitch_deck.mjs) shows into
 * docs/images/pitch/: one console screen per capability, in the light theme
 * the deck is set in, plus the real artefacts behind them — an evidence frame
 * and the Movement Report a search exports.
 *
 * The screens follow the live drill the jury asks for: open one camera, watch
 * a plate get read, trace it, be alerted, hand over the report. The
 * `live-camera` shot therefore waits for a genuinely new read on the focused
 * camera, so the plate on the tile is one the pipeline has just produced.
 *
 * Usage (from apps/web, against a running stack with the gov mirror analysed,
 * e.g. `make worker SOURCE=mirror CAMERAS=cam06,cam30,cam01,cam24 SAMPLED_FPS=2`):
 *   npm run screenshots:pitch
 *   PITCH_PLATE=GJ11S7924 PITCH_FOCUS_CAMERA=cam30 npm run screenshots:pitch
 *   PITCH_ONLY=live npm run screenshots:pitch      (artefacts, console, live, extras)
 *
 * Needs `pdftoppm` (poppler) on PATH to render the Movement Report page.
 */

import { chromium, webkit } from '@playwright/test'
import { execFile } from 'node:child_process'
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { promisify } from 'node:util'

const run = promisify(execFile)
const HERE = dirname(fileURLToPath(import.meta.url))
const OUT_DIR = resolve(HERE, '..', '..', '..', 'docs', 'images', 'pitch')

const WEB_URL = process.env.SHOT_WEB_URL ?? 'http://localhost:5173'
const API_URL = process.env.SHOT_API_URL ?? 'http://localhost:18000'
const EMAIL = process.env.SHOT_EMAIL ?? 'admin@sentinel-platform.com'
const PASSWORD = process.env.SHOT_PASSWORD ?? 'sentinel-admin-2026'
// A plate with a camera-clock time and a legible evidence frame.
const PLATE = process.env.PITCH_PLATE ?? 'GJ11S7924'
// A plate whose camera clock could not be read.
const UNTIMED_PLATE = process.env.PITCH_UNTIMED_PLATE ?? 'GJ39C8018'
// The watchlist vehicle selected on the Alerts screen.
const ALERT_PLATE = process.env.PITCH_ALERT_PLATE ?? 'GJ03MH7800'
// The camera opened in focus view. Its preview must come from the local
// mirror (cam06 and cam30 preview through the remote gateway). The live
// screens are shot in WebKit, which decodes H.265 as Safari does.
const FOCUS_CAMERA = process.env.PITCH_FOCUS_CAMERA ?? 'cam01'
// Seconds to wait for a fresh read on the focus camera, so its plate shows on
// the tile; 0 skips it (cam01 is a busy night junction whose plates are too
// small to read).
const READ_WAIT_S = Number(process.env.PITCH_READ_WAIT_S ?? 0)
const WALL_CAMERAS = (process.env.PITCH_WALL ?? 'cam01,cam05,cam24,cam06').split(',')
// Re-shoot only some groups: artefacts, console, live, extras.
const ONLY = process.env.PITCH_ONLY ? process.env.PITCH_ONLY.split(',') : null
const wants = (group) => !ONLY || ONLY.includes(group)

const VIEWPORT = { width: 1600, height: 1000 }
// Taller, so a focused tile's status line is in frame.
const WALL_VIEWPORT = { width: 1600, height: 1120 }
const PHONE = { width: 414, height: 896 }

let token = ''

async function api(path, init = {}) {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { Authorization: `Bearer ${token}`, ...(init.headers ?? {}) },
  })
  if (!response.ok) throw new Error(`${path}: ${response.status}`)
  return response
}

async function login() {
  const response = await fetch(`${API_URL}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: EMAIL, password: PASSWORD }),
  })
  if (!response.ok) throw new Error(`login failed: ${response.status}`)
  return (await response.json()).access_token
}

/** CDP capture in Chromium: MapLibre's WebGL canvas never settles for
 * Playwright's own screenshot stabilisation (see capture_screenshots.mjs).
 * WebKit has no CDP; the live wall has no map, so its own capture is fine. */
async function shoot(page, name) {
  const path = resolve(OUT_DIR, `${name}.png`)
  if (page.context().browser()?.browserType().name() === 'chromium') {
    const session = await page.context().newCDPSession(page)
    const { data } = await session.send('Page.captureScreenshot', { format: 'png' })
    await session.detach()
    await writeFile(path, Buffer.from(data, 'base64'))
  } else {
    await page.screenshot({ path, timeout: 60000 })
  }
  console.log(`  ${name}.png`)
}

async function context(browser, { viewport = VIEWPORT, phone = false, theme = 'light', language = 'en' } = {}) {
  const ctx = await browser.newContext({
    viewport,
    deviceScaleFactor: 2,
    serviceWorkers: 'block',
    ...(phone ? { isMobile: true, hasTouch: true } : {}),
  })
  await ctx.addInitScript(
    ([t, th, lang]) => {
      localStorage.setItem('sentinel.auth.token', t)
      localStorage.setItem('sentinel-theme', th)
      localStorage.setItem('sentinel-language', lang)
    },
    [token, theme, language],
  )
  return ctx
}

async function visit(page, path, wait) {
  await page.goto(`${WEB_URL}${path}`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(wait)
}

/** Waits until the camera produces a read the live wall will still flag
 * (it shows a plate for 30 s after ingest), or gives up after READ_WAIT_S. */
async function waitForFreshRead(cameraId) {
  const deadline = Date.now() + READ_WAIT_S * 1000
  let last = null
  process.stdout.write(`  waiting up to ${READ_WAIT_S}s for a new read on ${cameraId}`)
  while (Date.now() < deadline) {
    const [latest] = await (await api(`/api/v1/detections?camera_id=${cameraId}&limit=1`)).json()
    if (latest) {
      const age = Date.now() - new Date(latest.ingested_at).getTime()
      if (last && latest.event_id !== last && age < 12_000) {
        console.log(` — ${latest.plate_text}`)
        return latest
      }
      last ??= latest.event_id
    }
    process.stdout.write('.')
    await new Promise((r) => setTimeout(r, 3000))
  }
  console.log(' — none; shooting without a plate on the tile')
  return null
}

/** The evidence frame and box of the plate's newest timed sighting. */
async function saveEvidence(plate) {
  const detections = await (await api(`/api/v1/detections?plate=${encodeURIComponent(plate)}&limit=20`)).json()
  const hit = detections.find((d) => d.camera_time) ?? detections[0]
  if (!hit) throw new Error(`no detection for ${plate}`)
  const image = Buffer.from(await (await api(`/api/v1/detections/${hit.event_id}/snapshot`)).arrayBuffer())
  await writeFile(resolve(OUT_DIR, 'evidence-frame.jpg'), image)
  const { event_id, camera_id, plate_text, camera_time } = hit
  await writeFile(resolve(OUT_DIR, 'evidence-frame.json'), JSON.stringify(
    { event_id, camera_id, plate_text, camera_time }, null, 2,
  ) + '\n')
  console.log('  evidence-frame.jpg')
}

/** The Movement Report exactly as an officer exports it: page 1 of the PDF,
 * and the manifest that seals it. */
async function saveMovementReport(plate) {
  const zip = Buffer.from(await (await api(`/api/v1/vehicles/${encodeURIComponent(plate)}/movement-report`)).arrayBuffer())
  const dir = await mkdtemp(join(tmpdir(), 'sentinel-report-'))
  try {
    await writeFile(join(dir, 'report.zip'), zip)
    await run('unzip', ['-q', 'report.zip'], { cwd: dir })
    await run('pdftoppm', ['-png', '-r', '150', '-f', '1', '-l', '1', '-singlefile', 'report.pdf', 'page'], { cwd: dir })
    await writeFile(resolve(OUT_DIR, 'movement-report.png'), await readFile(join(dir, 'page.png')))
    await writeFile(resolve(OUT_DIR, 'movement-report-manifest.json'), await readFile(join(dir, 'manifest.json')))
    console.log('  movement-report.png')
  } finally {
    await rm(dir, { recursive: true, force: true })
  }
}

async function alertFor(plate) {
  const alerts = await (await api('/api/v1/alerts')).json()
  return alerts.find((a) => a.plate_text === plate && a.last_seen_camera_time)?.id ?? alerts[0]?.id
}

async function pickWallCameras(page, ids) {
  await page.getByRole('button', { name: 'Clear selection' }).click()
  // The selection list only renders what the filter matches, so each camera
  // is found by typing its id first.
  const filter = page.getByPlaceholder('Filter cameras by name or ID')
  for (const id of ids) {
    await filter.fill(id)
    // The checkbox itself is visually hidden; its label is the click target.
    await page.locator('.monitoring-camera-option').first().click()
  }
  await filter.fill('')
}

async function main() {
  await mkdir(OUT_DIR, { recursive: true })
  token = await login()
  const browser = await chromium.launch()

  if (wants('artefacts')) {
    console.log('artefacts…')
    await saveEvidence(PLATE)
    await saveMovementReport(PLATE)
  }

  const ctx = await context(browser)
  const page = await ctx.newPage()
  if (wants('console')) await consoleScreens(page)
  await ctx.close()
  if (wants('extras')) await extraScreens(browser)
  if (wants('live')) {
    const safari = await webkit.launch()
    const live = await context(safari, { viewport: WALL_VIEWPORT })
    await liveScreens(await live.newPage())
    await safari.close()
  }

  await browser.close()
  console.log(`\ndone — ${OUT_DIR}`)
}

async function consoleScreens(page) {
  console.log('light-theme console…')
  await visit(page, '/', 7000)
  await shoot(page, 'overview')
  await visit(page, `/find-a-vehicle?plate=${encodeURIComponent(PLATE)}`, 8000)
  await shoot(page, 'find-a-vehicle')
  await visit(page, `/find-a-vehicle?plate=${encodeURIComponent(UNTIMED_PLATE)}`, 7000)
  await shoot(page, 'time-unknown')
  await visit(page, `/alerts?alert=${encodeURIComponent(await alertFor(ALERT_PLATE))}`, 6000)
  await shoot(page, 'alerts')

  await visit(page, '/cameras', 3000)
  await page.getByRole('button', { name: 'Map', exact: true }).click()
  await page.waitForTimeout(6000)
  await shoot(page, 'cameras-map')
  await page.getByRole('button', { name: 'Table', exact: true }).click()
  // Only the analysed cameras: their rows carry analysis rate, counts and tamper state.
  await page.getByRole('button', { name: 'Live cameras', exact: true }).click()
  await page.waitForTimeout(3000)
  await shoot(page, 'cameras-table')
  await visit(page, '/cameras', 3000)
  await page.getByRole('button', { name: 'Import cameras' }).click()
  await page.waitForTimeout(2000)
  await shoot(page, 'onboard-import')
  await visit(page, '/cameras', 3000)
  await page.getByRole('button', { name: 'Discover cameras' }).click()
  await page.waitForTimeout(2000)
  await shoot(page, 'onboard-discover')

  await visit(page, '/health', 4000)
  await shoot(page, 'health')
  await visit(page, '/admin', 3000)
  await page.getByRole('button', { name: 'Integrations' }).click()
  await page.waitForTimeout(3000)
  await shoot(page, 'integrations')
  await page.getByRole('button', { name: 'Audit log' }).click()
  await page.waitForTimeout(2000)
  await page.getByRole('button', { name: 'Verify integrity' }).click()
  await page.waitForTimeout(3000)
  await shoot(page, 'audit-verified')
}

async function liveScreens(page) {
  console.log('live wall…')
  await visit(page, '/live-wall', 3000)
  await pickWallCameras(page, WALL_CAMERAS)
  // HLS tiles need several segments, and a keyframe, before they play
  // cleanly; low-fps cameras take longest.
  await page.waitForTimeout(60000)
  await shoot(page, 'live-wall')

  // "Open one camera": the focus view of an analysed camera, shot within
  // seconds of the pipeline reading a plate on it.
  await page.getByRole('button', { name: 'Focus view' }).click()
  const picker = page.locator('select').filter({ has: page.locator('option') }).last()
  const cameras = await (await api('/api/v1/cameras')).json()
  await picker.selectOption({ label: cameras.find((c) => c.camera_id === FOCUS_CAMERA)?.name ?? FOCUS_CAMERA })
  await page.waitForTimeout(40000)
  const read = READ_WAIT_S > 0 ? await waitForFreshRead(FOCUS_CAMERA) : null
  // The wall re-polls reads every 8 s.
  if (read) await page.waitForTimeout(9000)
  await shoot(page, 'live-camera')
}

async function extraScreens(browser) {
  console.log('dark theme, Gujarati and phone…')
  const dark = await context(browser, { theme: 'dark' })
  const darkPage = await dark.newPage()
  await visit(darkPage, `/find-a-vehicle?plate=${encodeURIComponent(PLATE)}`, 8000)
  await shoot(darkPage, 'find-a-vehicle-dark')
  await dark.close()

  const gu = await context(browser, { language: 'gu' })
  const guPage = await gu.newPage()
  await visit(guPage, '/', 7000)
  await shoot(guPage, 'overview-gujarati')
  await gu.close()

  const phone = await context(browser, { viewport: PHONE, phone: true })
  const phonePage = await phone.newPage()
  await visit(phonePage, '/field', 5000)
  await shoot(phonePage, 'field-pwa')
  await phone.close()
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
