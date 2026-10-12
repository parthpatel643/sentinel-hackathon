import { expect, test } from '@playwright/test'

const JPEG = Buffer.from('/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA=', 'base64')

const moved = {
  id: 'ce-1', event_id: '01JVIEW0000000000000000001', camera_id: 'river', kind: 'view_shifted',
  shift_pct: 12.3, rotation_deg: 0.2, scale: 1.0, match_ratio: 0.27, has_snapshots: true,
  observed_at: '2026-10-12T05:00:00Z', camera_time: '2026-08-08T15:40:33Z', status: 'new',
  resolved_by: null, restored_at: null, created_at: '2026-10-12T05:00:00Z',
}
const lost = {
  ...moved, id: 'ce-2', event_id: '01JVIEW0000000000000000002', camera_id: 'east', kind: 'view_unrecognised',
  shift_pct: null, rotation_deg: null, scale: null, has_snapshots: false, camera_time: null,
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('sentinel-language', 'en')
    localStorage.setItem('sentinel-theme', 'light')
    localStorage.setItem('sentinel.auth.token', 'ui-test')
  })
})

test('a moved camera is triaged from the alerts page with its remembered view beside the view now', async ({ page }) => {
  const triaged: unknown[] = []
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname
    if (path.endsWith('/auth/me')) return route.fulfill({ json: { id: 'op', email: 'op@example.test', full_name: 'Operator', role: 'admin', active: true } })
    if (path.endsWith('/cameras')) return route.fulfill({ json: [{ camera_id: 'river', name: 'Riverfront', status: 'live' }, { camera_id: 'east', name: 'East Gate', status: 'live' }] })
    if (path.includes('/camera-events/') && path.includes('/snapshot/')) return route.fulfill({ body: JPEG, contentType: 'image/jpeg' })
    if (path.startsWith('/api/v1/camera-events/') && route.request().method() === 'PATCH') {
      triaged.push(route.request().postDataJSON())
      return route.fulfill({ json: { ...moved, status: 'resolved' } })
    }
    if (path.endsWith('/camera-events')) return route.fulfill({ json: url.searchParams.get('status') === 'new' ? [moved, lost] : [] })
    return route.fulfill({ json: [] })
  })

  await page.goto('/alerts?camera_event=ce-1')
  const queue = page.getByRole('region', { name: 'Camera views' })
  await expect(queue).toBeVisible()
  const item = queue.getByRole('listitem').filter({ hasText: 'Riverfront' })
  await expect(item).toContainText('Camera moved')
  await expect(item).toContainText('shifted 12%')
  await expect(item.getByRole('img', { name: 'Remembered view' })).toBeVisible()
  await expect(item.getByRole('img', { name: 'View now' })).toBeVisible()
  const other = queue.getByRole('listitem').filter({ hasText: 'East Gate' })
  await expect(other).toContainText('View not recognised')
  await expect(other).toContainText('Time unknown')
  await item.getByRole('button', { name: 'Resolve' }).click()
  await expect.poll(() => triaged).toEqual([{ status: 'resolved' }])
})

test('a camera moved while the operator is elsewhere is announced on screen', async ({ page }) => {
  let announce = false
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/me')) return route.fulfill({ json: { id: 'op', email: 'op@example.test', full_name: 'Operator', role: 'admin', active: true } })
    if (path.endsWith('/cameras')) return route.fulfill({ json: [{ camera_id: 'river', name: 'Riverfront', status: 'live' }] })
    if (path.endsWith('/events/stream')) {
      // Throttle the client's reconnect loop; deliver the event once the first poll has run.
      await new Promise((resolve) => setTimeout(resolve, 400))
      return route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: announce ? `event: camera_event\ndata: ${JSON.stringify(moved)}\n\n` : '',
      })
    }
    return route.fulfill({ json: [] })
  })
  await page.goto('/cameras')
  await page.waitForTimeout(1500)
  announce = true
  const banner = page.getByRole('region', { name: /alert/i })
  await expect(banner).toContainText('Camera view changed')
  await expect(banner).toContainText('Riverfront: view shifted 12%')
})
