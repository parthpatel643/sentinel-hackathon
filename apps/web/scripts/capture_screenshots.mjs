/**
 * Regenerates the README/deck screenshots from a live stack.
 *
 * Screenshots go stale the moment the UI changes, and hand-taken ones are
 * never quite the same size or state twice. This script pins the viewport,
 * the theme and the language, signs in through the real API, and captures a
 * fixed set of screens — so re-running it after a UI change produces a
 * directly comparable set rather than a new mixture.
 *
 * Usage:
 *   npm run screenshots           (from apps/web)
 *   SHOT_PLATE=GJ186705 npm run screenshots
 *
 * Requires a running stack (core_api, the web app, and ideally a worker so
 * the screens have real data in them).
 */

import { chromium } from '@playwright/test'
import { mkdir, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const OUT_DIR = resolve(HERE, '..', '..', '..', 'docs', 'images')

const WEB_URL = process.env.SHOT_WEB_URL ?? 'http://localhost:5173'
const API_URL = process.env.SHOT_API_URL ?? 'http://localhost:18000'
const EMAIL = process.env.SHOT_EMAIL ?? 'admin@sentinel-platform.com'
const PASSWORD = process.env.SHOT_PASSWORD ?? 'sentinel-admin-2026'
const PLATE = process.env.SHOT_PLATE ?? ''

const VIEWPORT = { width: 1600, height: 1000 }
const MOBILE = { width: 414, height: 896 }

async function login() {
  const response = await fetch(`${API_URL}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: EMAIL, password: PASSWORD }),
  })
  if (!response.ok) throw new Error(`login failed: ${response.status}`)
  return (await response.json()).access_token
}

/**
 * MapLibre keeps a WebGL canvas repainting, which makes Playwright's default
 * screenshot stabilisation wait forever on map-heavy screens. Capturing over
 * CDP sidesteps that wait entirely, which is the only reliable way to shoot
 * these pages.
 */
async function shoot(page, name) {
  const session = await page.context().newCDPSession(page)
  const { data } = await session.send('Page.captureScreenshot', {
    format: 'png',
    captureBeyondViewport: false,
  })
  await session.detach()
  await writeFile(resolve(OUT_DIR, `${name}.png`), Buffer.from(data, 'base64'))
  console.log(`  ${name}.png`)
}

async function visit(page, path, { wait = 4000 } = {}) {
  await page.goto(`${WEB_URL}${path}`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(wait)
}

async function main() {
  await mkdir(OUT_DIR, { recursive: true })
  const token = await login()

  const browser = await chromium.launch()
  const context = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: 2,
    serviceWorkers: 'block',
  })
  // Seed auth and preferences before any app code runs, so no screenshot ever
  // catches a login redirect or a theme flash.
  await context.addInitScript(
    ([t]) => {
      localStorage.setItem('sentinel.auth.token', t)
      localStorage.setItem('sentinel-theme', 'dark')
      localStorage.setItem('sentinel-language', 'en')
    },
    [token],
  )

  const page = await context.newPage()

  console.log('capturing operator workspace (dark)…')
  await visit(page, '/', { wait: 6000 })
  await shoot(page, '01-operations-overview')

  await visit(page, '/live-wall', { wait: 16000 })
  await shoot(page, '02-live-wall')

  await visit(page, '/alerts')
  await shoot(page, '03-alerts')

  await visit(page, '/cameras')
  await shoot(page, '04-cameras')

  if (PLATE) {
    await visit(page, `/find-a-vehicle?plate=${encodeURIComponent(PLATE)}`, { wait: 8000 })
    await shoot(page, '05-find-a-vehicle')
  } else {
    console.log('  (skipping find-a-vehicle: set SHOT_PLATE to a plate with sightings)')
  }

  await visit(page, '/health')
  await shoot(page, '06-health')

  await visit(page, '/admin', { wait: 5000 })
  await shoot(page, '07-admin')

  console.log('capturing light theme…')
  const light = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: 2,
    serviceWorkers: 'block',
  })
  await light.addInitScript(
    ([t]) => {
      localStorage.setItem('sentinel.auth.token', t)
      localStorage.setItem('sentinel-theme', 'light')
      localStorage.setItem('sentinel-language', 'en')
    },
    [token],
  )
  const lightPage = await light.newPage()
  await visit(lightPage, '/', { wait: 6000 })
  await shoot(lightPage, '08-operations-overview-light')
  await light.close()

  console.log('capturing Gujarati…')
  const gu = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: 2,
    serviceWorkers: 'block',
  })
  await gu.addInitScript(
    ([t]) => {
      localStorage.setItem('sentinel.auth.token', t)
      localStorage.setItem('sentinel-theme', 'dark')
      localStorage.setItem('sentinel-language', 'gu')
    },
    [token],
  )
  const guPage = await gu.newPage()
  await visit(guPage, '/', { wait: 6000 })
  await shoot(guPage, '09-operations-overview-gujarati')
  await gu.close()

  console.log('capturing the Field PWA (phone viewport)…')
  const field = await browser.newContext({
    viewport: MOBILE,
    deviceScaleFactor: 3,
    isMobile: true,
    hasTouch: true,
    serviceWorkers: 'block',
  })
  await field.addInitScript(
    ([t]) => {
      localStorage.setItem('sentinel.auth.token', t)
      localStorage.setItem('sentinel-theme', 'dark')
      localStorage.setItem('sentinel-language', 'en')
    },
    [token],
  )
  const fieldPage = await field.newPage()
  await visit(fieldPage, '/field', { wait: 5000 })
  await shoot(fieldPage, '10-field-pwa')
  await field.close()

  await browser.close()
  console.log(`\ndone — ${OUT_DIR}`)
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
