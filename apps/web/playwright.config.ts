import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests',
  use: { baseURL: 'http://localhost:5188', headless: true, serviceWorkers: 'block' },
  reporter: 'list',
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1 --port 5188 --strictPort',
    url: 'http://localhost:5188',
    reuseExistingServer: !process.env.CI,
  },
})
