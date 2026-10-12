import { defineConfig } from '@playwright/test'

const port = process.env.SENTINEL_TEST_PORT ?? '5188'

export default defineConfig({
  testDir: './tests',
  use: { baseURL: `http://localhost:${port}`, headless: true, serviceWorkers: 'block' },
  reporter: 'list',
  webServer: {
    command: `npm run dev -- --host 127.0.0.1 --port ${port} --strictPort`,
    url: `http://localhost:${port}`,
    reuseExistingServer: !process.env.CI,
  },
})
