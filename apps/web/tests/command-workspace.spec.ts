import { expect, test } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('sentinel.auth.token', 'ui-test')
    localStorage.setItem('sentinel-language', 'en')
    localStorage.setItem('sentinel-theme', 'light')
  })
  await page.route('**/api/v1/**', route => {
    const path = new URL(route.request().url()).pathname
    return route.fulfill({ json: path.endsWith('/auth/me')
      ? { id: 'operator', email: 'operator@example.test', full_name: 'Test Operator', role: 'admin', active: true }
      : path.endsWith('/cameras') ? [
        { camera_id: 'cam-1', name: 'Riverfront', status: 'live', location: { lat: 23.02, lon: 72.57 }, department_name: 'Traffic', reconnects: 0 },
        { camera_id: 'cam-2', name: 'East Gate', status: 'unknown', location: null, department_name: 'Traffic', reconnects: 0 },
      ]
        : path.endsWith('/detections') ? [{
          event_id: 'test-event', camera_id: 'cam-1', plate_text: 'GJ01AB1234', plate_normalised: 'GJ01AB1234',
          plate_confidence: .92, observed_at: '2026-09-23T10:00:00Z', vehicle_class: 'car', snapshot_uri: null,
        }] : [] })
  })
})

test('compact navigation expands without hiding destination labels', async ({ page }) => {
  await page.goto('/')
  const nav = page.getByRole('navigation', { name: 'Workspace', exact: true })
  await expect(nav.getByRole('link', { name: 'Cameras', exact: true })).toBeVisible()
  expect(await page.locator('.workspace-sidebar').evaluate(el => el.getBoundingClientRect().width)).toBeLessThanOrEqual(104)
  await page.getByRole('button', { name: 'Expand navigation' }).click()
  expect(await page.locator('.workspace-sidebar').evaluate(el => el.getBoundingClientRect().width)).toBeGreaterThan(200)
  await page.reload()
  await expect(page.getByRole('button', { name: 'Collapse navigation' })).toBeVisible()
})

test('overview fleet workbench switches to a searchable camera list', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('tab', { name: 'Camera list', exact: true }).click()
  const fleet = page.getByRole('region', { name: 'Camera network', exact: true })
  await expect(fleet.getByRole('button', { name: /Riverfront/ })).toBeVisible()
  await page.getByRole('searchbox', { name: 'Search the camera network' }).fill('east')
  await expect(fleet.getByRole('button', { name: /Riverfront/ })).toHaveCount(0)
  await expect(fleet.getByRole('button', { name: /East Gate/ })).toBeVisible()
  await page.getByRole('searchbox', { name: 'Search the camera network' }).clear()
  await page.getByRole('button', { name: 'Unknown cameras', exact: true }).click()
  await expect(fleet.getByRole('button', { name: /Riverfront/ })).toHaveCount(0)
  await expect(fleet.getByRole('button', { name: /East Gate/ })).toBeVisible()
})

test('recent detections lead directly into vehicle investigation', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('tab', { name: 'Recent detections', exact: true }).click()
  const activity = page.getByRole('region', { name: 'Operational activity', exact: true })
  await activity.getByRole('link', { name: /GJ01AB1234/ }).click()
  await expect(page).toHaveURL(/find-a-vehicle\?plate=GJ01AB1234/)
})

test('failed detection refresh is not shown as an empty healthy stream', async ({ page }) => {
  await page.route('**/api/v1/detections**', route => route.fulfill({ status: 503, json: { detail: 'Unavailable' } }))
  await page.goto('/')
  await page.getByRole('tab', { name: 'Recent detections', exact: true }).click()
  await expect(page.getByRole('region', { name: 'Operational activity', exact: true }).getByRole('alert')).toBeVisible()
})

test('overview view tabs support arrow-key navigation', async ({ page }) => {
  await page.goto('/')
  const mapTab = page.getByRole('tab', { name: 'Map', exact: true })
  await mapTab.focus()
  await page.keyboard.press('ArrowRight')
  await expect(page.getByRole('tab', { name: 'Camera list', exact: true })).toHaveAttribute('aria-selected', 'true')
  await page.getByRole('tab', { name: /Watchlist matches/ }).focus()
  await page.keyboard.press('ArrowRight')
  await expect(page.getByRole('tab', { name: 'Recent detections', exact: true })).toHaveAttribute('aria-selected', 'true')
})

test('login allows inspecting the password without changing its value', async ({ page }) => {
  await page.route('**/api/v1/auth/me', route => route.fulfill({ status: 401, json: { detail: 'Unauthorized' } }))
  await page.goto('/')
  await page.getByLabel('Password', { exact: true }).fill('local-test-value')
  await page.getByRole('button', { name: 'Show password', exact: true }).click()
  await expect(page.getByLabel('Password', { exact: true })).toHaveAttribute('type', 'text')
  await page.getByRole('button', { name: 'Hide password', exact: true }).click()
  await expect(page.getByLabel('Password', { exact: true })).toHaveValue('local-test-value')
  await expect(page.getByLabel('Password', { exact: true })).toHaveAttribute('type', 'password')
})
