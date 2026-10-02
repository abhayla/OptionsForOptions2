// W-054 core proof: browser -> Vite preview proxy (/api) -> FastAPI -> PostgreSQL, visible on /health-status.
// PREVIEW_URL serves the build with the proxy pointed at the real API; PREVIEW_DOWN_URL serves it with the proxy
// pointed at a closed port. CI starts both (see .github/workflows/app-tests.yml).
import { test, expect } from '@playwright/test'

const DOWN_URL = process.env.PREVIEW_DOWN_URL || 'http://127.0.0.1:4174'

test('the health page shows the live database status from the real backend', async ({ page }, info) => {
  const apiCalls: string[] = []
  page.on('request', (r) => {
    const u = new URL(r.url())
    if (u.pathname.startsWith('/api')) apiCalls.push(u.origin + u.pathname)
  })
  await page.goto('/health-status')
  await expect(page.getByTestId('health-database')).toHaveText('database: ok')
  await expect(page.getByTestId('health-status')).toHaveAttribute('data-state', 'ok')
  // ADR-012: the only call is same-origin /api/health
  expect(apiCalls).toEqual([new URL(page.url()).origin + '/api/health'])
  await page.screenshot({ path: `screenshots/health-ok-${info.project.name}.png`, fullPage: true })
})

test('the health page shows the unavailable state when the API is unreachable', async ({ page }, info) => {
  await page.goto(`${DOWN_URL}/health-status`)
  await expect(page.getByTestId('health-unavailable')).toHaveText('Status unavailable')
  await expect(page.getByTestId('health-status')).toHaveAttribute('data-state', 'unavailable')
  await expect(page.getByTestId('health-database')).toHaveCount(0)
  await page.screenshot({ path: `screenshots/health-unavailable-${info.project.name}.png`, fullPage: true })
})
