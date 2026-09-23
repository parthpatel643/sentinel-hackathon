import { expect, test } from '@playwright/test'
import { monitoringCopy } from '../src/locales/monitoring'

const cameras = [
  { camera_id: 'river', name: 'Riverfront', status: 'live', department_name: 'Traffic', site_name: 'West', tier: 'b_sampled', location: null, measured_fps: 12, reconnects: 0 },
  { camera_id: 'east', name: 'East Gate', status: 'down', department_name: 'Traffic', tier: 'b_sampled', location: null, measured_fps: null, reconnects: 2 },
  { camera_id: 'station', name: 'Station', status: 'unknown', department_name: null, tier: 'b_sampled', location: null, measured_fps: null, reconnects: 0 },
]

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    if (!localStorage.getItem('sentinel-language')) localStorage.setItem('sentinel-language', 'en')
    if (!localStorage.getItem('sentinel-theme')) localStorage.setItem('sentinel-theme', 'light')
    localStorage.setItem('sentinel.auth.token', 'ui-test')
  })
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    const body = path.endsWith('/auth/me')
      ? { id: 'operator', full_name: 'Operator', email: 'operator@example.test', role: 'admin', active: true }
      : path.endsWith('/cameras') ? cameras
      : path.endsWith('/stream') ? { available: false, hls_url: null, reason: 'Relay unavailable' }
      : []
    await route.fulfill({ json: body })
  })
})

test('surveillance selector controls the actual wall and exposes keyboard camera details', async ({ page }) => {
  await page.goto('/live-wall')
  const selector = page.getByRole('region', { name: 'Camera selection' })
  await expect(selector).toBeVisible()
  await selector.getByRole('checkbox', { name: 'East Gate' }).uncheck()
  const wall = page.getByRole('region', { name: 'Monitoring wall' })
  await expect(wall.getByRole('button', { name: 'Open details: East Gate' })).toHaveCount(0)
  await wall.getByRole('button', { name: 'Open details: Riverfront' }).click()
  const detail = page.getByRole('dialog', { name: 'Riverfront' })
  await expect(detail.getByRole('heading', { name: 'Camera information' })).toBeVisible()
  await expect(detail.getByText('Relay unavailable')).toBeVisible()
  await detail.getByRole('button', { name: 'Add zone' }).click()
  await expect(detail.getByRole('textbox', { name: 'Zone name' })).toBeVisible()
  let savedZone: Record<string, unknown> | null = null
  await page.route('**/api/v1/cameras/river/zones', async (route) => {
    if (route.request().method() === 'POST') {
      savedZone = route.request().postDataJSON()
      await route.fulfill({ json: { id: 'zone-1', ...savedZone } })
    } else {
      await route.fulfill({ json: savedZone ? [{ id: 'zone-1', ...savedZone }] : [] })
    }
  })
  await detail.getByRole('textbox', { name: 'Zone name' }).fill('Loading bay')
  await detail.getByRole('combobox', { name: 'Rule type' }).selectOption('loitering')
  await detail.getByRole('combobox', { name: 'Detection region' }).selectOption('1')
  await detail.getByRole('button', { name: 'Create', exact: true }).click()
  await expect(detail.getByText('Loading bay', { exact: true })).toBeVisible()
  expect(savedZone).toEqual({ name: 'Loading bay', rule_type: 'loitering', polygon: [[0, 0], [0.5, 0], [0.5, 1], [0, 1]] })
})

test('registry health filters retain unknown states and map view retains a camera list', async ({ page }) => {
  await page.goto('/cameras')
  await page.getByRole('button', { name: 'Unknown cameras' }).click()
  await expect(page.getByRole('button', { name: 'Station', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Riverfront', exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: 'All cameras', exact: true }).click()
  await page.getByRole('button', { name: 'Map', exact: true }).click()
  await expect(page.getByRole('region', { name: 'Cameras on this map' })).toBeVisible()
  await expect(page.getByText('3 cameras have no map location.')).toBeVisible()
  await page.getByRole('button', { name: 'Riverfront', exact: true }).click()
  await expect(page.getByRole('dialog', { name: 'Riverfront' })).toBeVisible()
})

test('bulk import and catalogue discovery are direct onboarding paths', async ({ page }) => {
  await page.goto('/cameras')
  await page.getByRole('button', { name: 'Import cameras', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('CSV')
  await page.getByRole('button', { name: 'Close', exact: true }).click()
  await page.getByRole('button', { name: 'Discover cameras', exact: true }).click()
  await expect(page.getByRole('dialog').getByRole('button', { name: 'Sync now' })).toBeVisible()
})

test('monitoring layouts reflow on mobile and support translated dark mode', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/live-wall')
  await expect(page.getByRole('region', { name: 'Camera selection' })).toBeVisible()
  await page.getByRole('button', { name: 'Switch to Dark mode' }).click()
  for (const language of ['en', 'hi', 'gu'] as const) {
    await page.locator('select').filter({ has: page.locator('option[value="gu"]') }).selectOption(language)
    for (const path of ['/live-wall', '/cameras']) {
      await page.goto(path)
      await expect(page.locator('html')).toHaveAttribute('lang', language)
      await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
      await expect(page.getByRole('region', { name: path === '/live-wall' ? monitoringCopy[language].selection : monitoringCopy[language].registry, exact: true })).toBeVisible()
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
      expect(await page.locator('main').innerText()).not.toContain('monitoring:')
    }
  }
})

test('focus mode lets operators choose any selected camera and clear the wall', async ({ page }) => {
  await page.goto('/live-wall')
  await page.getByRole('button', { name: 'Focus view' }).click()
  await page.getByRole('combobox', { name: 'Camera in focus' }).selectOption('east')
  const wall = page.getByRole('region', { name: 'Monitoring wall' })
  await expect(wall.getByRole('button', { name: 'Open details: East Gate' })).toBeVisible()
  await expect(wall.getByRole('button', { name: 'Open details: Riverfront' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Clear selection' }).click()
  await expect(wall.getByText('Choose a camera from the selection panel to start monitoring.')).toBeVisible()
  await page.getByRole('button', { name: 'Select all' }).click()
  await expect(wall.getByRole('button', { name: 'Open details: East Gate' })).toBeVisible()
})

test('manual onboarding submits the selected monitoring profile and shows the real preview result', async ({ page }) => {
  let created: Record<string, unknown> | null = null
  await page.route('**/api/v1/cameras', async (route) => {
    if (route.request().method() === 'POST') {
      created = route.request().postDataJSON()
      await route.fulfill({ json: { ...cameras[0], ...created } })
    } else await route.fulfill({ json: cameras })
  })
  await page.goto('/cameras')
  await page.getByRole('button', { name: 'Add camera', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByRole('textbox', { name: 'Camera name', exact: true }).fill('North Gate')
  await dialog.getByRole('textbox', { name: 'Site', exact: true }).fill('North')
  await dialog.getByRole('button', { name: 'Next', exact: true }).click()
  await dialog.getByRole('textbox', { name: 'Stream link' }).fill('rtsp://camera.local/stream')
  await dialog.getByRole('button', { name: 'Next', exact: true }).click()
  await dialog.getByRole('radio', { name: /Only watch when something moves/ }).check()
  await dialog.getByRole('button', { name: 'Add camera', exact: true }).click()
  await expect(dialog.getByText('North Gate was added')).toBeVisible()
  await expect(dialog.getByText('Relay unavailable')).toBeVisible()
  expect(created).toMatchObject({ camera_id: 'north-gate', name: 'North Gate', site_name: 'North', tier: 'c_motion_gated', profiles: [{ protocol: 'rtsp', url: 'rtsp://camera.local/stream' }] })
})

test('CSV onboarding previews before commit and catalogue discovery calls the real action', async ({ page }) => {
  const imports: string[] = []
  await page.route('**/api/v1/cameras/bulk-import?*', async (route) => {
    const dryRun = new URL(route.request().url()).searchParams.get('dry_run') === 'true'
    imports.push(String(dryRun))
    await route.fulfill({ json: { dry_run: dryRun, total_rows: 1, succeeded: 1, rows: [{ row_number: 1, camera_id: 'north', ok: true }] } })
  })
  await page.goto('/cameras')
  await page.getByRole('button', { name: 'Import cameras', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByLabel('Camera CSV file').setInputFiles({ name: 'cameras.csv', mimeType: 'text/csv', buffer: Buffer.from('camera_id,name\nnorth,North Gate\n') })
  await dialog.getByRole('button', { name: 'Preview (dry run)' }).click()
  await expect(dialog.getByText(/nothing saved yet/)).toBeVisible()
  expect(imports).toEqual(['true'])
  await dialog.getByRole('button', { name: 'Import 1 camera(s)' }).click()
  await expect(dialog.getByText('Import committed — cameras are now in the registry.')).toBeVisible()
  expect(imports).toEqual(['true', 'false'])
  await dialog.getByRole('button', { name: 'Done', exact: true }).click()
  await page.route('**/api/v1/cameras/discover', async (route) => {
    expect(route.request().method()).toBe('POST')
    await route.fulfill({ json: { onboarded: 2 } })
  })
  await page.getByRole('button', { name: 'Discover cameras', exact: true }).click()
  await dialog.getByRole('button', { name: 'Sync now' }).click()
  await expect(dialog.locator('pre')).toContainText('"onboarded": 2')
})

test('offscreen cameras do not resolve streams until the operator scrolls to them', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  const requests: string[] = []
  await page.route('**/api/v1/cameras/*/stream', async (route) => {
    requests.push(new URL(route.request().url()).pathname)
    await route.fulfill({ json: { available: false, hls_url: null, reason: 'Relay unavailable' } })
  })
  await page.goto('/live-wall')
  const wall = page.getByRole('region', { name: 'Monitoring wall' })
  await expect(wall.getByRole('button', { name: 'Open details: East Gate' })).toBeAttached()
  expect(requests).not.toContain('/api/v1/cameras/east/stream')
  await wall.getByRole('button', { name: 'Open details: East Gate' }).scrollIntoViewIfNeeded()
  await expect.poll(() => requests).toContain('/api/v1/cameras/east/stream')
})

test('mobile operators can scroll through the entire wall without clipped feeds', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/live-wall')
  await expect(page.getByRole('region', { name: 'Camera selection' })).toBeVisible()
  await page.mouse.move(250, 740)
  await page.mouse.wheel(0, 2400)
  await expect(page.getByText('Only visible streams play. Select a camera to inspect its connection and zone rules.')).toBeInViewport()
})
