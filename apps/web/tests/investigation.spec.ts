import { expect, test } from '@playwright/test'
import type { Alert, VehicleRoute } from '../src/lib/types'
import { investigationCopy } from '../src/locales/investigation'

const vehicleRoute: VehicleRoute = {
  plate_normalised: 'GJ01AB1234', total_sightings: 2,
  first_seen_at: '2026-09-23T09:00:00Z', last_seen_at: '2026-09-23T09:10:00Z',
  points: [
    { camera_id: 'river', camera_name: 'Riverfront', location: { lat: 23.02, lon: 72.57 }, camera_time: '2026-09-23T09:00:00Z', plate_text: 'GJ01AB1234', plate_confidence: .96, match_rung: 'exact', snapshot_uri: null, confirmed: true },
    { camera_id: 'gate', camera_name: 'East Gate', location: null, camera_time: '2026-09-23T09:10:00Z', plate_text: 'GJ01A81234', plate_confidence: .74, match_rung: 'ambiguity_class', snapshot_uri: null, confirmed: false },
  ],
  untimed: [],
}
const alertFixture = (id: string, plate: string, priority: number): Alert => ({
  id, plate_text: plate, camera_id: `camera-${id}`,
  watchlist_entry_id: 'watch-1', detection_event_id: 'detection-1', match_rung: 'exact', match_confidence: .96,
  priority_score: priority, status: 'new', sighting_count: 2,
  first_seen_at: '2026-09-23T09:00:00Z', last_seen_at: '2026-09-23T09:10:00Z',
  first_seen_camera_time: '2026-06-13T15:30:00Z', last_seen_camera_time: null,
  resolved_by: null, resolution_note: null, created_at: '2026-09-23T09:00:00Z',
})

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('sentinel.auth.token', 'ui-test')
    if (!localStorage.getItem('sentinel-language')) localStorage.setItem('sentinel-language', 'en')
    if (!localStorage.getItem('sentinel-theme')) localStorage.setItem('sentinel-theme', 'light')
  })
  await page.route('**/api/v1/**', (route) => {
    const path = new URL(route.request().url()).pathname
    return route.fulfill({ json: path.endsWith('/auth/me')
      ? { id: 'operator', email: 'operator@example.test', full_name: 'Test Operator', role: 'admin', active: true }
      : path.endsWith('/route') ? vehicleRoute : [] })
  })
})

test('investigation starts with a persistent query console and useful guidance', async ({ page }) => {
  await page.goto('/find-a-vehicle')
  const search = page.getByRole('search', { name: 'Investigation query' })
  await expect(search.getByRole('textbox', { name: 'Registration plate' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Build a vehicle movement trail' })).toBeVisible()
  await search.getByRole('textbox').fill('GJ01AB1234')
  await search.getByRole('button', { name: 'Search', exact: true }).click()
  await expect(page).toHaveURL(/plate=GJ01AB1234/)
  await expect(page.getByRole('region', { name: 'Movement workbench' })).toBeVisible()
  await expect(search.getByRole('textbox')).toHaveValue('GJ01AB1234')
})

test('timeline selection reveals evidence and explains unmapped sightings', async ({ page }) => {
  await page.goto('/find-a-vehicle?plate=GJ01AB1234')
  await page.getByRole('button', { name: /East Gate/ }).click()
  const evidence = page.getByRole('region', { name: 'Sighting evidence' })
  await expect(evidence).toContainText('East Gate')
  await expect(evidence).toContainText('No snapshot was attached to this sighting.')
  await expect(evidence).toContainText('Location unavailable')
  await expect(page.getByRole('button', { name: 'Replay route' })).toBeDisabled()
  await expect(page.getByText('2 sightings in loaded results')).toBeVisible()
})

test('alert triage filters the loaded queue and applies actions only to the selected alert', async ({ page }) => {
  let alerts = [alertFixture('one', 'GJ01AB1234', .9), alertFixture('two', 'GJ05CD5678', .3)]
  await page.route('**/api/v1/alerts**', (route) => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/clip')) return route.fulfill({ status: 404, json: { detail: 'No clip' } })
    if (route.request().method() === 'PATCH') {
      const { status } = route.request().postDataJSON() as { status: Alert['status'] }
      alerts = alerts.map((alert) => url.pathname.endsWith(alert.id) ? { ...alert, status } : alert)
      return route.fulfill({ json: alerts.find((alert) => url.pathname.endsWith(alert.id)) })
    }
    return route.fulfill({ json: alerts.filter((alert) => !url.searchParams.get('status') || alert.status === url.searchParams.get('status')) })
  })
  await page.goto('/alerts')
  const queue = page.getByRole('region', { name: 'Alert queue', exact: true })
  const details = page.getByRole('region', { name: 'Selected alert' })
  await queue.getByRole('button', { name: /GJ05CD5678/ }).click()
  await expect(details).toContainText('GJ05CD5678')
  await expect(details.getByRole('link', { name: 'Investigate vehicle' })).toHaveAttribute('href', '/find-a-vehicle?plate=GJ05CD5678')
  await page.getByRole('textbox', { name: 'Filter by plate or camera' }).fill('GJ01')
  await expect(queue.getByRole('button', { name: /GJ05/ })).toHaveCount(0)
  await expect(details).toContainText('GJ01AB1234')
  await details.getByRole('button', { name: 'Acknowledge', exact: true }).click()
  await expect(queue.getByRole('button', { name: /GJ01/ })).toHaveCount(0)
  await expect(page.getByText('No alerts match these filters.')).toBeVisible()
})

test('triage action errors retain the selected alert and allow retry', async ({ page }) => {
  await page.route('**/api/v1/alerts**', (route) => route.fulfill(
    route.request().method() === 'PATCH'
      ? { status: 503, json: { detail: 'Unavailable' } }
      : route.request().url().endsWith('/clip')
        ? { status: 404, json: {} }
        : { json: [alertFixture('one', 'GJ01AB1234', .9)] },
  ))
  await page.goto('/alerts')
  const details = page.getByRole('region', { name: 'Selected alert' })
  await details.getByRole('button', { name: 'Resolve', exact: true }).click()
  await expect(details.getByRole('alert')).toContainText('Could not update this alert')
  await expect(details.getByRole('button', { name: 'Resolve', exact: true })).toBeEnabled()
})

test('investigation and triage workspaces fit a phone without horizontal scrolling', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  for (const path of ['/find-a-vehicle', '/find-a-vehicle?plate=GJ01AB1234', '/alerts']) {
    await page.goto(path)
    await expect(page.locator('main h1')).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), path).toBe(true)
  }
})

test('route replay cancels when a new plate replaces the current investigation', async ({ page }) => {
  await page.route('**/api/v1/vehicles/GJ01AB1234/route', (route) => route.fulfill({ json: {
    ...vehicleRoute, points: vehicleRoute.points.map((point, index) => ({ ...point, location: { lat: 23.02 + index * .01, lon: 72.57 + index * .01 } })),
  } }))
  await page.goto('/find-a-vehicle?plate=GJ01AB1234')
  await page.getByRole('button', { name: 'Replay route', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Stop', exact: true })).toBeVisible()
  const query = page.getByRole('search', { name: 'Investigation query' })
  await query.getByRole('textbox').fill('GJ05CD5678')
  await query.getByRole('button', { name: 'Search', exact: true }).click()
  await expect(page).toHaveURL(/plate=GJ05CD5678/)
  await expect(page.getByRole('button', { name: 'Stop', exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Replay route', exact: true })).toBeDisabled()
})

test('failed vehicle searches retry and preserve report export', async ({ page }) => {
  await page.route('**/api/v1/vehicles/*/route', (route) => route.fulfill({ status: 503, json: { detail: 'Search unavailable' } }))
  await page.goto('/find-a-vehicle?plate=GJ01AB1234')
  await expect(page.getByRole('alert')).toContainText('Search unavailable')
  await page.route('**/api/v1/vehicles/*/route', (route) => route.fulfill({ json: vehicleRoute }))
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(page.getByRole('region', { name: 'Movement workbench' })).toBeVisible()
  await page.route('**/movement-report', (route) => route.fulfill({ body: 'test-report', contentType: 'application/pdf', headers: { 'Content-Disposition': 'attachment; filename="movement.pdf"', 'Access-Control-Expose-Headers': 'Content-Disposition' } }))
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export report', exact: true }).click()
  expect((await download).suggestedFilename()).toBe('movement.pdf')
})

test('an empty investigation still supports arming a BOLO', async ({ page }) => {
  await page.route('**/api/v1/vehicles/*/route', (route) => route.fulfill({ json: { ...vehicleRoute, total_sightings: 0, points: [] } }))
  let requestedPlate: string | undefined
  await page.route('**/api/v1/bolo', (route) => {
    requestedPlate = (route.request().postDataJSON() as { plate: string }).plate
    return route.fulfill({ json: { retro_alerts_created: 0, retro_sightings_found: 0, watchlist_entry: {} } })
  })
  await page.goto('/find-a-vehicle?plate=GJ01AB1234')
  await page.getByRole('button', { name: 'Watch for this vehicle', exact: true }).click()
  await expect.poll(() => requestedPlate).toBe('GJ01AB1234')
})

test('arming a plate that is already watched says so instead of claiming a new watch', async ({ page }) => {
  await page.route('**/api/v1/vehicles/*/route', (route) => route.fulfill({ json: { ...vehicleRoute, total_sightings: 0, points: [] } }))
  await page.route('**/api/v1/bolo', (route) => route.fulfill({ json: { retro_alerts_created: 0, retro_sightings_found: 3, already_armed: true, watchlist_entry: {} } }))
  await page.goto('/find-a-vehicle?plate=GJ01AB1234')
  await page.getByRole('button', { name: 'Watch for this vehicle', exact: true }).click()
  await expect(page.getByText('GJ01AB1234 is already being watched — no duplicate alerts were created')).toBeVisible()
})

test('loaded alert counts and selection respond to severity filters', async ({ page }) => {
  await page.route('**/api/v1/alerts**', (route) => route.fulfill(route.request().url().endsWith('/clip')
    ? { status: 404, json: {} }
    : { json: [alertFixture('one', 'GJ01AB1234', .9), alertFixture('two', 'GJ05CD5678', .3)] }))
  await page.goto('/alerts')
  await page.getByRole('combobox', { name: 'Severity', exact: true }).selectOption('medium')
  await expect(page.getByRole('region', { name: 'Alert queue', exact: true })).toContainText('1 of 2 loaded')
  await expect(page.getByRole('region', { name: 'Selected alert' })).toContainText('GJ05CD5678')
})

test('overview alert links select the requested alert while retaining queue selection', async ({ page }) => {
  await page.route('**/api/v1/alerts**', (route) => route.fulfill(route.request().url().endsWith('/clip')
    ? { status: 404, json: {} }
    : { json: [alertFixture('one', 'GJ01AB1234', .9), alertFixture('two', 'GJ05CD5678', .3)] }))
  await page.goto('/alerts?alert=two')
  const details = page.getByRole('region', { name: 'Selected alert' })
  const queue = page.getByRole('region', { name: 'Alert queue', exact: true })
  await expect(details).toContainText('GJ05CD5678')
  await expect(queue.getByRole('button', { name: /GJ05CD5678/ })).toHaveAttribute('aria-pressed', 'true')
  await queue.getByRole('button', { name: /GJ01AB1234/ }).click()
  await expect(details).toContainText('GJ01AB1234')
  await page.goto('/alerts?alert=not-loaded')
  await expect(details).toContainText('GJ01AB1234')
})

test('failed queue refresh does not claim there are no alerts and supports retry', async ({ page }) => {
  await page.goto('/alerts')
  await expect(page.getByText('No alerts here.')).toBeVisible()
  await page.route('**/api/v1/alerts**', (route) => route.fulfill({ status: 503, json: { detail: 'Unavailable' } }))
  await page.getByRole('button', { name: 'Refresh queue' }).click()
  await expect(page.getByRole('alert')).toBeVisible()
  await expect(page.getByText('No alerts here.')).toHaveCount(0)
  await page.route('**/api/v1/alerts**', (route) => route.fulfill(route.request().url().endsWith('/clip')
    ? { status: 404, json: {} } : { json: [alertFixture('one', 'GJ01AB1234', .9)] }))
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(page.getByRole('region', { name: 'Selected alert' })).toContainText('GJ01AB1234')
})

test('localized workspaces retain content and fit both themes on a phone', async ({ page }) => {
  test.setTimeout(120_000)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.route('**/api/v1/alerts**', (route) => route.fulfill(route.request().url().endsWith('/clip')
    ? { status: 404, json: {} } : { json: [alertFixture('one', 'GJ01AB1234', .9)] }))
  for (const language of ['en', 'hi', 'gu'] as const) {
    for (const theme of ['light', 'dark']) {
      await page.goto('/find-a-vehicle', { waitUntil: 'domcontentloaded' })
      await page.evaluate(({ language, theme }) => {
        localStorage.setItem('sentinel-language', language)
        localStorage.setItem('sentinel-theme', theme)
      }, { language, theme })
      for (const path of ['/find-a-vehicle?plate=GJ01AB1234', '/alerts']) {
        await page.goto(path, { waitUntil: 'domcontentloaded' })
        await expect(page.locator('html')).toHaveAttribute('data-theme', theme)
        if (path === '/alerts') await expect(page.getByRole('region', { name: investigationCopy[language].selectedAlert, exact: true })).toBeVisible()
        else await expect(page.getByRole('heading', { name: investigationCopy[language].movementMap, exact: true })).toBeVisible()
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
        expect(await page.locator('main').innerText()).not.toMatch(/investigation:|workspace\./)
      }
    }
  }
})

test('a sighting whose camera clock was unreadable is listed off the timeline as time unknown', async ({ page }) => {
  await page.route('**/api/v1/vehicles/GJ01AB1234/route', (route) => route.fulfill({ json: {
    ...vehicleRoute, total_sightings: 3,
    untimed: [{ camera_id: 'janpath', camera_name: 'Janpath', location: null, camera_time: null, plate_text: 'GJ01AB1234', plate_confidence: .9, match_rung: 'exact', snapshot_uri: null, confirmed: true }],
  } }))
  await page.goto('/find-a-vehicle?plate=GJ01AB1234')
  const untimed = page.getByRole('region', { name: 'Seen here — camera clock unreadable' })
  await expect(untimed).toBeVisible()
  await untimed.getByRole('button', { name: /Janpath/ }).click()
  const evidence = page.getByRole('region', { name: 'Sighting evidence' })
  await expect(evidence.getByRole('heading', { name: 'Janpath' })).toBeVisible()
  await expect(evidence).toContainText('Time unknown — camera clock unreadable')
})

test('alert times are the camera clock, or unknown', async ({ page }) => {
  await page.route('**/api/v1/alerts**', (route) => route.fulfill({ json: [alertFixture('a1', 'GJ01AB1234', .9)] }))
  await page.goto('/alerts')
  await expect(page.getByText('Time unknown — camera clock unreadable', { exact: true }).first()).toBeVisible()
  await expect(page.getByText(/Jun 13|13 Jun/).first()).toBeVisible()
})

test('repeat sightings at one camera share a pin, and the route marks its start and latest stop', async ({ page }) => {
  const at = (camera_id: string, lat: number, lon: number, time: string) => ({
    camera_id, camera_name: camera_id, location: { lat, lon }, camera_time: time, plate_text: 'GJ01AB1234',
    plate_confidence: .95, match_rung: 'exact' as const, snapshot_uri: null, confirmed: true,
  })
  await page.route('**/api/v1/vehicles/GJ01AB1234/route', (route) => route.fulfill({ json: {
    ...vehicleRoute, total_sightings: 4,
    points: [
      at('paldi', 23.0134, 72.5589, '2026-06-13T15:02:00Z'),
      at('bridge', 23.03, 72.58, '2026-06-13T15:18:00Z'),
      at('bridge', 23.03, 72.58, '2026-06-13T15:24:00Z'),
      at('adalaj', 23.1667, 72.5833, '2026-06-13T15:58:00Z'),
    ],
  } }))
  await page.goto('/find-a-vehicle?plate=GJ01AB1234')
  const pins = page.locator('.iw-map .map-marker')
  await expect(pins).toHaveCount(3)
  await expect(pins.filter({ hasText: '2·3' })).toHaveCount(1)
  await expect(page.locator('.iw-map .map-marker-chip')).toHaveText(['Start', 'Latest'])
})
