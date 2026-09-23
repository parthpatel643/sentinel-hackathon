import { expect, test } from '@playwright/test'
import en from '../src/locales/en/translation.json' with { type: 'json' }
import hi from '../src/locales/hi/translation.json' with { type: 'json' }
import gu from '../src/locales/gu/translation.json' with { type: 'json' }

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    if (!localStorage.getItem('sentinel-language')) localStorage.setItem('sentinel-language', 'en')
    if (!localStorage.getItem('sentinel-theme')) localStorage.setItem('sentinel-theme', 'dark')
    localStorage.setItem('sentinel.auth.token', 'ui-test')
  })
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    const body = path.endsWith('/auth/me')
      ? { id: 'test-user', email: 'operator@example.test', full_name: 'Test Operator', role: 'admin', active: true }
      : path.endsWith('/compliance/integrator')
        ? { rtsp_transport_tcp_forced: true, timing_source: 'pts', backoff: { initial_s: 1, max_s: 30 }, catalogue_driven_discovery: true, codecs_in_use: [], mixed_codec_handling: true, publishing_to_gateway_disabled: true }
        : []
    await route.fulfill({ json: body })
  })
})

test('investigation keeps workspace preferences and labelled navigation available', async ({ page }) => {
  await page.goto('/find-a-vehicle')
  await expect(page.getByRole('navigation', { name: 'Workspace' })).toBeVisible()
  await expect(page.getByRole('combobox', { name: 'Language' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Switch to Light mode' })).toBeVisible()
  await expect(page.getByRole('search', { name: 'Vehicle search' })).toBeVisible()
})

test('mobile navigation opens and closes after choosing a destination', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/find-a-vehicle')
  await page.getByRole('button', { name: 'Open navigation' }).click()
  await page.getByRole('navigation', { name: 'Workspace' }).getByRole('link', { name: 'Cameras', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Cameras', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Open navigation' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

test('overview distinguishes an empty registry from a failed request', async ({ page }) => {
  await page.route('**/api/v1/cameras**', (route) => route.fulfill({ status: 503, json: { detail: 'Unavailable' } }))
  await page.goto('/')
  await expect(page.getByRole('alert').first()).toContainText('Could not refresh')
  await expect(page.getByRole('heading', { name: 'Operations overview' })).toBeVisible()
})

test('camera registry filters real entries by name and status', async ({ page }) => {
  await page.route('**/api/v1/cameras**', (route) => route.fulfill({ json: [
    { camera_id: 'cam-1', name: 'Riverfront', status: 'live', tier: 'T1', location: null, reconnects: 0 },
    { camera_id: 'cam-2', name: 'East Gate', status: 'down', tier: 'T2', location: null, reconnects: 2 },
  ] }))
  await page.goto('/cameras')
  await page.getByRole('textbox', { name: 'Filter cameras by name or ID' }).fill('river')
  await expect(page.getByRole('button', { name: 'Riverfront' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'East Gate' })).toHaveCount(0)
  await page.getByRole('combobox', { name: 'All statuses' }).selectOption('down')
  await expect(page.getByText('No cameras match these filters.')).toBeVisible()
})

test('language and theme persist after a reload', async ({ page }) => {
  await page.goto('/find-a-vehicle')
  await page.getByRole('button', { name: 'Switch to Light mode' }).click()
  await page.getByRole('combobox', { name: 'Language' }).selectOption('gu')
  await page.reload()
  await expect(page.locator('html')).toHaveAttribute('lang', 'gu')
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
  expect(await page.evaluate(() => localStorage.getItem('sentinel-language'))).toBe('gu')
})

for (const language of ['en', 'hi', 'gu']) {
  test(`mobile layouts contain translated content in ${language}`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto('/find-a-vehicle')
    await page.getByRole('combobox', { name: 'Language' }).selectOption(language)
    for (const path of ['/', '/find-a-vehicle', '/cameras', '/alerts', '/live-wall', '/health', '/admin', '/field/lookup', '/field/report', '/field/alerts', '/field/nearby']) {
      await page.goto(path)
      await expect(page.locator('html')).toHaveAttribute('lang', language)
      await expect(page.locator('main')).toBeVisible()
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), path).toBe(true)
      expect(await page.locator('body').innerText()).not.toContain('workspace.')
    }
  })
}

test('login keeps labelled credentials and preferences available on a phone', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ status: 401, json: { detail: 'Unauthorized' } }))
  await page.goto('/')
  await expect(page.getByRole('button', { name: 'Sign in', exact: true })).toBeVisible()
  await expect(page.getByLabel('Email', { exact: true })).toBeVisible()
  await expect(page.getByLabel('Password', { exact: true })).toBeVisible()
  await expect(page.getByRole('combobox', { name: 'Language' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

test('field shell keeps sync state separate from preferences and touch-friendly navigation', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/field/alerts')
  await expect(page.locator('header').getByRole('status')).toBeVisible()
  await expect(page.getByRole('combobox', { name: 'Language' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Switch to Light mode' })).toBeVisible()
  const navLinks = page.getByRole('navigation', { name: 'Sentinel Field' }).getByRole('link')
  await expect(navLinks).toHaveCount(4)
  const minHeights = await navLinks.evaluateAll((links) => links.map((link) => parseFloat(getComputedStyle(link).minHeight)))
  expect(minHeights.every((height) => height >= 60)).toBe(true)
})

test('field lookup exposes a labelled plate form with clear and search actions', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/field/lookup')
  await expect(page.getByRole('heading', { name: 'Look up', exact: true })).toBeVisible()
  const plateInput = page.getByRole('textbox', { name: 'Plate', exact: true })
  await expect(plateInput).toBeVisible()
  await plateInput.fill('GJ 01 AB 1234')
  await expect(page.getByRole('button', { name: 'Clear', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Look up', exact: true })).toBeVisible()
})

test('field nearby presents switchable map and list tabs inside the mobile task area', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.route('**/api/v1/cameras**', (route) => route.fulfill({ json: [
    { camera_id: 'cam-1', name: 'Riverfront', status: 'live', tier: 'T1', location: { lat: 23.02, lon: 72.57 }, reconnects: 0 },
  ] }))
  await page.goto('/field/nearby')
  await expect(page.getByRole('heading', { name: 'Nearby', exact: true })).toBeVisible()
  await expect(page.getByRole('tablist', { name: 'Nearby', exact: true })).toBeVisible()
  await page.getByRole('tab', { name: 'List', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Riverfront', exact: true })).toBeVisible()
})

test('map controls follow language changes without a reload', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('button', { name: en.map.zoomIn, exact: true })).toBeVisible()
    await page.getByRole('combobox', { name: 'Language' }).selectOption('hi')
    await expect(page.getByRole('button', { name: hi.map.zoomIn, exact: true })).toBeVisible()
    await expect(page.getByRole('region', { name: hi.map.title })).toBeVisible()
  })

  test('translated dictionaries retain every key and interpolation', () => {
    function flatten(value: object, prefix = ''): Record<string, string> {
      return Object.fromEntries(Object.entries(value).flatMap(([key, child]) =>
        typeof child === 'string' ? [[`${prefix}${key}`, child]] : Object.entries(flatten(child, `${prefix}${key}.`)),
      ))
    }
    const base = flatten(en)
    for (const dictionary of [hi, gu]) {
      const translated = flatten(dictionary)
      expect(Object.keys(translated).sort()).toEqual(Object.keys(base).sort())
      for (const key of Object.keys(base)) {
        expect(translated[key].trim(), key).not.toBe('')
        expect(translated[key].match(/{{[^}]+}}/g)?.sort() ?? [], key).toEqual(base[key].match(/{{[^}]+}}/g)?.sort() ?? [])
      }
    }
  })

  test('both themes meet text and primary-action contrast thresholds', async ({ page }) => {
    await page.goto('/find-a-vehicle')
    await expect(page.getByRole('heading', { name: 'Find a vehicle', exact: true })).toBeVisible()
    for (const theme of ['dark', 'light']) {
      if (theme === 'light') await page.getByRole('button', { name: 'Switch to Light mode' }).click()
      const ratios = await page.evaluate(() => {
        const style = getComputedStyle(document.documentElement)
        const color = (token: string) => style.getPropertyValue(`--color-${token}`).trim()
        const luminance = (hex: string) => {
          const channels = hex.replace('#', '').match(/../g)!.map((n) => {
            const v = parseInt(n, 16) / 255
            return v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4
          })
          return channels[0] * .2126 + channels[1] * .7152 + channels[2] * .0722
        }
        const contrast = (a: string, b: string) => {
          const x = luminance(color(a)), y = luminance(color(b))
          return (Math.max(x, y) + .05) / (Math.min(x, y) + .05)
        }
        return [
          ...['text-primary', 'text-secondary', 'text-tertiary'].flatMap((text) =>
            ['bg-base', 'bg-raised', 'bg-overlay', 'bg-inset'].map((bg) => ({ pair: `${text}/${bg}`, ratio: contrast(text, bg) })),
          ),
          ...['accent', 'accent-hover'].map((bg) => ({ pair: `on-accent/${bg}`, ratio: contrast('on-accent', bg) })),
        ]
      })
      for (const { pair, ratio } of ratios) expect(ratio, `${theme}: ${pair}`).toBeGreaterThanOrEqual(4.5)
    }
  })

  test('plate search retains timeline, replay, and export actions on mobile', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await page.route('**/api/v1/vehicles/*/route', (route) => route.fulfill({ json: {
      plate_normalised: 'GJ01AB1234', total_sightings: 2,
      first_seen_at: '2026-06-15T10:00:00Z', last_seen_at: '2026-06-15T10:05:00Z',
      points: [
        { camera_id: 'cam-1', camera_name: 'Riverfront', location: { lat: 23.02, lon: 72.57 }, observed_at: '2026-06-15T10:00:00Z', plate_text: 'GJ01AB1234', plate_confidence: .97, match_rung: 'exact', snapshot_uri: null, confirmed: true },
        { camera_id: 'cam-2', camera_name: 'East Gate', location: { lat: 23.04, lon: 72.59 }, observed_at: '2026-06-15T10:05:00Z', plate_text: 'GJ01AB1234', plate_confidence: .88, match_rung: 'ambiguity_class', snapshot_uri: null, confirmed: false },
      ],
    } }))
    await page.goto('/find-a-vehicle')
    await page.locator('#investigation-plate').fill('GJ01AB1234')
    await page.locator('main').getByRole('button', { name: 'Search', exact: true }).click()
    await expect(page.getByText('Riverfront', { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Export report' })).toBeVisible()
    await page.getByRole('button', { name: 'Replay route' }).click()
    await expect(page.getByRole('button', { name: 'Stop', exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Stop', exact: true }).click()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  })
