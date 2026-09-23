import { expect, test } from '@playwright/test'
import { managementCopy } from '../src/locales/management'

const compliance = {
  rtsp_transport_tcp_forced: true, timing_source: 'pts',
  backoff: { initial_s: 1, max_s: 30 }, catalogue_driven_discovery: false,
  codecs_in_use: ['h264'], mixed_codec_handling: true, publishing_to_gateway_disabled: true,
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    if (!localStorage.getItem('sentinel-language')) localStorage.setItem('sentinel-language', 'en')
    if (!localStorage.getItem('sentinel-theme')) localStorage.setItem('sentinel-theme', 'light')
    localStorage.setItem('sentinel.auth.token', 'management-test')
  })
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    const body = path.endsWith('/auth/me')
      ? { id: 'admin-1', email: 'admin@example.test', full_name: 'Test Admin', role: 'admin', active: true }
      : path.endsWith('/auth/users')
        ? [{ id: 'operator-1', email: 'officer@example.test', full_name: 'River Officer', role: 'operator', active: true }]
        : path.endsWith('/compliance/integrator') ? compliance
          : path.endsWith('/admin/retention-preview') ? { detections_affected: 12, clips_affected: 2, clips_bytes_affected: 2048 }
            : []
    await route.fulfill({ json: body })
  })
})

test('administration is a navigable management hub with list-first access management', async ({ page }) => {
  await page.goto('/admin')
  await expect(page.getByRole('heading', { name: 'Access & accountability' })).toBeVisible()
  const nav = page.getByRole('navigation', { name: 'Administration sections' })
  await expect(nav.getByRole('button')).toHaveCount(5)
  await expect(page.getByText('River Officer', { exact: true })).toBeVisible()
  await expect(page.getByRole('textbox', { name: 'Full name', exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: 'Add user', exact: true }).click()
  await expect(page.getByRole('textbox', { name: 'Full name', exact: true })).toBeVisible()
  await expect(page.getByRole('combobox', { name: 'Role', exact: true })).toBeVisible()
  await nav.getByRole('button', { name: 'Retention & privacy', exact: true }).click()
  await expect(page.getByRole('region', { name: 'Deletion preview' })).toContainText('12')
  await expect(page.getByRole('slider', { name: 'Detection reads' })).toBeVisible()
})

test('compliance workbench groups checks and filters attention without inventing health', async ({ page }) => {
  await page.goto('/health')
  await expect(page.getByRole('heading', { name: 'Compliance workbench' })).toBeVisible()
  await expect(page.getByRole('region', { name: 'Compliance summary' })).toContainText('5')
  await expect(page.getByRole('heading', { name: 'Transport & timing' })).toBeVisible()
  await page.getByRole('button', { name: 'Needs attention', exact: true }).click()
  await expect(page.locator('[data-check-result="fail"]')).toHaveCount(1)
  await expect(page.locator('[data-check-result="pass"]')).toHaveCount(0)
  await page.route('**/api/v1/compliance/integrator', (route) => route.fulfill({ status: 503, json: { detail: 'Unavailable' } }))
  await page.getByRole('button', { name: 'Refresh checks' }).click()
  await expect(page.getByRole('region', { name: 'Compliance summary' })).toContainText('Not available')
})

test('changing retention periods invalidates the old deletion confirmation', async ({ page }) => {
  await page.goto('/admin')
  await page.getByRole('navigation', { name: 'Administration sections' }).getByRole('button', { name: 'Retention & privacy', exact: true }).click()
  await page.getByRole('button', { name: 'Delete now', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Yes, delete permanently' })).toBeVisible()
  await page.getByRole('slider', { name: 'Detection reads' }).focus()
  await page.keyboard.press('ArrowRight')
  await expect(page.getByRole('button', { name: 'Yes, delete permanently' })).toHaveCount(0)
})

test('administrator controls preserve create, role changes, integration checks and audit verification', async ({ page }) => {
  await page.goto('/admin')
  const roleRequest = page.waitForRequest((request) => request.method() === 'PATCH' && request.url().includes('/auth/users/operator-1'))
  await page.getByRole('button', { name: 'Make admin', exact: true }).click()
  expect((await roleRequest).postDataJSON()).toEqual({ role: 'admin' })
  await page.getByRole('button', { name: 'Add user', exact: true }).click()
  await page.getByRole('textbox', { name: 'Full name', exact: true }).fill('New Officer')
  await page.getByRole('textbox', { name: 'Email', exact: true }).fill('new@example.test')
  await page.getByLabel('Password', { exact: true }).fill('test-password')
  const createRequest = page.waitForRequest((request) => request.method() === 'POST' && request.url().endsWith('/auth/users'))
  await page.getByRole('button', { name: 'Add user', exact: true }).click()
  expect((await createRequest).postDataJSON()).toMatchObject({ full_name: 'New Officer', email: 'new@example.test', role: 'operator' })
  const nav = page.getByRole('navigation', { name: 'Administration sections' })
  await nav.getByRole('button', { name: 'Integrations', exact: true }).click()
  await expect(page.getByText('No integration providers were returned.')).toBeVisible()
  await page.route('**/api/v1/admin/audit-log/verify', (route) => route.fulfill({ json: { intact: true, rows_checked: 3 } }))
  await nav.getByRole('button', { name: 'Audit log', exact: true }).click()
  await page.getByRole('button', { name: 'Verify integrity', exact: true }).click()
  await expect(page.getByText('Chain intact — 3 row(s) verified.', { exact: true })).toBeVisible()
})

test('mobile field lookup leads with a focused plate task and preserves verdict workflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.route('**/api/v1/field/lookup/**', (route) => route.fulfill({ json: {
    plate_normalised: 'GJ01AB1234', status: 'clear', last_seen_at: null, last_seen_camera_name: null,
  } }))
  await page.goto('/field/lookup')
  await expect(page.getByRole('region', { name: 'Plate check' })).toBeVisible()
  await expect(page.getByText('Live lookup requires a connection. Reports can be saved offline.')).toBeVisible()
  const links = page.getByRole('navigation', { name: 'Sentinel Field' }).getByRole('link')
  expect((await links.evaluateAll((items) => items.map((item) => item.getBoundingClientRect().height))).every((height) => height >= 60)).toBe(true)
  await page.getByRole('textbox', { name: 'Plate', exact: true }).fill('gj01ab1234')
  await page.getByRole('button', { name: 'Look up', exact: true }).click()
  await expect(page.getByRole('status').filter({ hasText: 'GJ01AB1234' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Report this vehicle' })).toBeVisible()
})

test('sighting report groups evidence and saves to the existing offline queue', async ({ page }) => {
  await page.route('**/api/v1/field/sightings', (route) => route.abort())
  await page.goto('/field/report')
  await expect(page.getByRole('group', { name: 'Vehicle details' })).toBeVisible()
  await expect(page.getByRole('group', { name: 'Supporting evidence' })).toBeVisible()
  await page.getByRole('textbox', { name: 'Plate', exact: true }).fill('GJ01AB1234')
  await page.getByRole('button', { name: 'Submit sighting', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Report queued' })).toBeVisible()
  await expect(page.locator('header').getByRole('status')).toContainText('1')
})

test('field alerts expose severity and retain successful acknowledgement', async ({ page }) => {
  await page.route('**/api/v1/alerts**', (route) => route.fulfill({ json: route.request().method() === 'PATCH' ? {} : [{
    id: 'alert-1', plate_text: 'GJ01AB1234', camera_id: 'cam-1', priority_score: .9, status: 'new',
    last_seen_at: '2026-09-23T10:00:00Z',
  }] }))
  await page.goto('/field/alerts')
  await expect(page.getByRole('region', { name: 'Alert queue' })).toBeVisible()
  await page.getByRole('button', { name: /GJ01AB1234/ }).click()
  await page.getByRole('button', { name: 'Acknowledge', exact: true }).click()
  await expect(page.getByRole('status').filter({ hasText: 'Alert acknowledged.' })).toBeVisible()
})

test('nearby camera list offers filtering and explains unavailable location', async ({ page }) => {
  await page.route('**/api/v1/cameras', (route) => route.fulfill({ json: [
    { camera_id: 'cam-1', name: 'Riverfront', status: 'live', location: { lat: 23.02, lon: 72.57 } },
    { camera_id: 'cam-2', name: 'East Gate', status: 'down', location: { lat: 23.04, lon: 72.59 } },
  ] }))
  await page.goto('/field/nearby')
  await expect(page.getByText('Distances appear when your location is available.')).toBeVisible()
  await page.getByRole('tab', { name: 'List', exact: true }).click()
  await page.getByRole('searchbox', { name: 'Find a nearby camera' }).fill('river')
  await expect(page.getByRole('button', { name: 'Riverfront', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'East Gate', exact: true })).toHaveCount(0)
})

test('nearby tabs support Home, End and arrow-key activation with roving focus', async ({ page }) => {
  await page.goto('/field/nearby')
  const map = page.getByRole('tab', { name: 'Map', exact: true })
  const list = page.getByRole('tab', { name: 'List', exact: true })
  await map.focus()
  await page.keyboard.press('End')
  await expect(list).toBeFocused()
  await expect(list).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByRole('tabpanel', { name: 'List', exact: true })).toBeVisible()
  await page.keyboard.press('Home')
  await expect(map).toBeFocused()
  await expect(map).toHaveAttribute('tabindex', '0')
  await expect(list).toHaveAttribute('tabindex', '-1')
  await page.keyboard.press('ArrowLeft')
  await expect(list).toBeFocused()
  await page.keyboard.press('ArrowRight')
  await expect(map).toBeFocused()
  await expect(page.getByRole('tabpanel', { name: 'Map', exact: true })).toBeVisible()
})

test('management translations have complete key and interpolation parity', () => {
  expect(Object.keys(managementCopy.en).length).toBeGreaterThan(10)
  for (const dictionary of [managementCopy.hi, managementCopy.gu]) {
    expect(Object.keys(dictionary).sort()).toEqual(Object.keys(managementCopy.en).sort())
    for (const [key, value] of Object.entries(managementCopy.en)) {
      const translated = dictionary[key as keyof typeof dictionary]
      expect(translated).toBeTruthy()
      expect(translated.match(/{{[^}]+}}/g)?.sort() ?? []).toEqual(value.match(/{{[^}]+}}/g)?.sort() ?? [])
    }
  }
})

test('management and field surfaces fit mobile in both themes and all languages', async ({ page }) => {
  test.setTimeout(120000)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/field/lookup')
  for (const language of ['en', 'hi', 'gu']) {
    for (const theme of ['light', 'dark']) {
      await page.evaluate(({ language, theme }) => {
        localStorage.setItem('sentinel-language', language)
        localStorage.setItem('sentinel-theme', theme)
      }, { language, theme })
      for (const path of ['/admin', '/health', '/field/lookup', '/field/report', '/field/alerts', '/field/nearby']) {
        await page.goto(path)
        await expect(page.locator('main')).toBeVisible()
        await expect(page.locator('html')).toHaveAttribute('lang', language)
        await expect(page.locator('html')).toHaveAttribute('data-theme', theme)
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${path} ${language} ${theme}`).toBe(true)
        expect(await page.locator('body').innerText()).not.toContain('management:')
        expect(await page.locator('body').innerText()).not.toContain('management.')
      }
    }
  }
})
