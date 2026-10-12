/**
 * Captures the console screenshots the pitch deck uses (scripts/build_pitch_deck.mjs)
 * into docs/images/pitch/, in the light theme the deck is set in.
 *
 * Unlike capture_screenshots.mjs (the README set), these screens are staged for
 * a story: a selected watchlist alert, a vehicle with a timed route, one whose
 * camera clock was unreadable, and a live wall showing four playing cameras.
 *
 * Usage (from apps/web, against a running stack with the gov mirror analysed):
 *   npm run screenshots:pitch
 *   PITCH_PLATE=GJ11S7924 PITCH_UNTIMED_PLATE=GJ11CD8389 npm run screenshots:pitch
 */

import { chromium } from '@playwright/test'
import { mkdir, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const OUT_DIR = resolve(HERE, '..', '..', '..', 'docs', 'images', 'pitch')

const WEB_URL = process.env.SHOT_WEB_URL ?? 'http://localhost:5173'
const API_URL = process.env.SHOT_API_URL ?? 'http://localhost:18000'
const EMAIL = process.env.SHOT_EMAIL ?? 'admin@sentinel-platform.com'
const PASSWORD = process.env.SHOT_PASSWORD ?? 'sentinel-admin-2026'
const PLATE = process.env.PITCH_PLATE ?? 'GJ11S7924'
const UNTIMED_PLATE = process.env.PITCH_UNTIMED_PLATE ?? 'GJ11CD8389'
// H.264 cameras with legible traffic; HLS in a browser cannot play H.265.
const WALL_CAMERAS = (process.env.PITCH_WALL ?? 'cam01,cam30,cam02,cam05').split(',')

const VIEWPORT = { width: 1600, height: 1000 }
const PHONE = { width: 414, height: 896 }

async function login() {
  const response = await fetch(`${API_URL}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: EMAIL, password: PASSWORD }),
  })
  if (!response.ok) throw new Error(`login failed: ${response.status}`)
  return (await response.json()).access_token
}

/** The newest alert for the plate that carries a camera-clock time. */
async function alertFor(token, plate) {
  const response = await fetch(`${API_URL}/api/v1/alerts`, { headers: { Authorization: `Bearer ${token}` } })
  const alerts = await response.json()
  return alerts.find((a) => a.plate_text === plate && a.last_seen_camera_time)?.id ?? alerts[0]?.id
}

/** CDP capture: MapLibre's WebGL canvas never settles for Playwright's own
 * screenshot stabilisation (see capture_screenshots.mjs). */
async function shoot(page, name) {
  const session = await page.context().newCDPSession(page)
  const { data } = await session.send('Page.captureScreenshot', { format: 'png' })
  await session.detach()
  await writeFile(resolve(OUT_DIR, `${name}.png`), Buffer.from(data, 'base64'))
  console.log(`  ${name}.png`)
}

async function context(browser, token, { viewport = VIEWPORT, phone = false } = {}) {
  const ctx = await browser.newContext({
    viewport,
    deviceScaleFactor: 2,
    serviceWorkers: 'block',
    ...(phone ? { isMobile: true, hasTouch: true } : {}),
  })
  await ctx.addInitScript(
    ([t]) => {
      localStorage.setItem('sentinel.auth.token', t)
      localStorage.setItem('sentinel-theme', 'light')
      localStorage.setItem('sentinel-language', 'en')
    },
    [token],
  )
  return ctx
}

async function visit(page, path, wait) {
  await page.goto(`${WEB_URL}${path}`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(wait)
}

async function main() {
  await mkdir(OUT_DIR, { recursive: true })
  const token = await login()
  const browser = await chromium.launch()

  const ctx = await context(browser, token)
  const page = await ctx.newPage()
  console.log('capturing the light-theme pitch set…')
  await visit(page, `/find-a-vehicle?plate=${encodeURIComponent(PLATE)}`, 8000)
  await shoot(page, 'find-a-vehicle')
  await visit(page, `/find-a-vehicle?plate=${encodeURIComponent(UNTIMED_PLATE)}`, 7000)
  await shoot(page, 'time-unknown')
  await visit(page, `/alerts?alert=${encodeURIComponent(await alertFor(token, PLATE))}`, 5000)
  await shoot(page, 'alerts')

  await visit(page, '/live-wall', 3000)
  await page.getByRole('button', { name: 'Clear selection' }).click()
  // The selection list only renders what the filter matches, so each camera
  // is found by typing its id first.
  const filter = page.getByPlaceholder('Filter cameras by name or ID')
  for (const id of WALL_CAMERAS) {
    await filter.fill(id)
    // The checkbox itself is visually hidden; its label is the click target.
    await page.locator('.monitoring-camera-option').first().click()
  }
  await filter.fill('')
  // HLS tiles need several segments before they play.
  await page.waitForTimeout(35000)
  await shoot(page, 'live-wall')
  await ctx.close()

  const phone = await context(browser, token, { viewport: PHONE, phone: true })
  const phonePage = await phone.newPage()
  await visit(phonePage, '/field', 5000)
  await shoot(phonePage, 'field-pwa')
  await phone.close()

  await browser.close()
  console.log(`\ndone — ${OUT_DIR}`)
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
