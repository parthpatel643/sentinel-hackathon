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

const alert = (id: string, plate: string, camera: string) => ({
  id, plate_text: plate, camera_id: camera, watchlist_entry_id: 'watch-1', detection_event_id: `det-${id}`,
  match_rung: 'exact', match_confidence: .96, priority_score: .9, status: 'new', sighting_count: 1,
  first_seen_at: '2026-09-23T09:00:00Z', last_seen_at: '2026-09-23T09:10:00Z',
  first_seen_camera_time: '2026-09-23T09:00:00Z', last_seen_camera_time: '2026-09-23T09:10:00Z',
  resolved_by: null, resolution_note: null, created_at: '2026-09-23T09:00:00Z',
})

test('navigation names every destination and counts waiting vehicles, not raw hits', async ({ page }) => {
  await page.route('**/api/v1/alerts**', route => route.fulfill({ json: [alert('a', 'GJ01AB1234', 'cam-1'), alert('b', 'GJ01AB1234', 'cam-1'), alert('c', 'GJ05CD5678', 'cam-1')] }))
  await page.goto('/')
  const nav = page.getByRole('navigation', { name: 'Workspace', exact: true })
  for (const name of ['Overview', 'Live Wall', 'Find a Vehicle', 'Cameras', 'Health', 'Admin']) {
    await expect(nav.getByRole('link', { name, exact: true })).toBeVisible()
  }
  await expect(nav.getByRole('link', { name: /Alerts/ })).toContainText('2')
})

test('watchlist board shows one row per vehicle and opens its sighting pass', async ({ page }) => {
  await page.route('**/api/v1/alerts**', route => route.request().url().endsWith('/clip')
    ? route.fulfill({ status: 404, json: {} })
    : route.fulfill({ json: [alert('a', 'GJ01AB1234', 'cam-1'), alert('b', 'GJ01AB1234', 'cam-1'), alert('c', 'GJ05CD5678', 'cam-1')] }))
  await page.goto('/')
  const board = page.getByRole('region', { name: 'Watchlist board', exact: true })
  await expect(board).toContainText('3hits')
  await expect(board).toContainText('2vehicles')
  await expect(board.getByRole('button', { name: /GJ01AB1234/ })).toHaveCount(1)
  await board.getByRole('button', { name: /GJ05CD5678/ }).click()
  await expect(page.getByRole('region', { name: 'Selected alert' })).toContainText('GJ05CD5678')
})

test('cameras roll up by district with problems first and unlocated cameras kept', async ({ page }) => {
  await page.goto('/')
  const districts = page.getByRole('region', { name: 'Cameras by district', exact: true })
  await expect(districts).toContainText('Ahmedabad')
  await expect(districts).toContainText('No location recorded')
  await expect(districts).toContainText('1 unknown')
})

test('latest reads lead directly into vehicle investigation', async ({ page }) => {
  await page.goto('/')
  const detections = page.getByRole('region', { name: 'Detections', exact: true })
  await detections.getByRole('link', { name: /GJ01AB1234/ }).click()
  await expect(page).toHaveURL(/find-a-vehicle\?plate=GJ01AB1234/)
})

test('failed detection refresh is not shown as an empty healthy stream', async ({ page }) => {
  await page.route('**/api/v1/detections**', route => route.fulfill({ status: 503, json: { detail: 'Unavailable' } }))
  await page.goto('/')
  const detections = page.getByRole('region', { name: 'Detections', exact: true })
  await expect(detections.getByRole('alert')).toBeVisible()
  await expect(detections).not.toContainText('No camera has reported a read yet.')
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
