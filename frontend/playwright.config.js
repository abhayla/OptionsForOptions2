// Adapted from abhayla/algochanakya@bf9faf7:playwright.config.js (ADR-047)
// Changed: two viewport projects (390x844, 1280x800), headless, no broker login or storage state, no global setup;
// the base URL is the preview server (the built app, /api proxied). Servers are started by the caller (CI or the
// documented local commands in frontend/README.md); PREVIEW_DOWN_URL is a second preview whose proxy points at a closed
// port, for the unavailable-state check.
import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 30000,
  retries: process.env.CI ? 1 : 0,
  workers: 2,
  reporter: [['list']],
  use: {
    baseURL: process.env.PREVIEW_URL || 'http://127.0.0.1:4173',
    headless: true,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    // Local only: use an already-installed Chromium when the download is blocked. CI installs its own.
    launchOptions: process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {},
  },
  projects: [
    { name: 'mobile-390', use: { browserName: 'chromium', viewport: { width: 390, height: 844 } } },
    { name: 'desktop-1280', use: { browserName: 'chromium', viewport: { width: 1280, height: 800 } } },
  ],
})
