// W-115 AC-2 / AC-4 / AC-5 (REQ-008): Home overview on the replay preview. The state follows GET /api/strategies (routed
// here to an empty list, then to three drafts); the strip follows the index socket's pushes; no connect control exists.
// Listed and written only: CI runs it. Expected strip text is read from the server's own pushes.
import { test, expect } from '@playwright/test'

const REPLAY_URL = process.env.REPLAY_URL || 'http://127.0.0.1:4175'
const draft = (id: number, underlying: string, updated_at: string) =>
  ({ id, underlying, status: 'draft', revision: 1, created_at: updated_at, updated_at })

test('AC-2: no saved strategies -> Create Strategy, Explore Option Chain, Learn, and a quiet Zerodha line', async ({ page }) => {
  await page.route('**/api/strategies', (route) =>
    route.request().method() === 'GET' ? route.fulfill({ json: { strategies: [] } }) : route.continue())
  await page.goto(`${REPLAY_URL}/home/overview`)
  await expect(page.getByTestId('home')).toHaveAttribute('data-state', 'new')
  await expect(page.getByTestId('home-actions').getByRole('link')).toHaveText(['Create Strategy', 'Explore Option Chain', 'Learn'])
  await expect(page.getByText('Plan your trade. Follow your strategy. Then execute.')).toBeVisible()
  await expect(page.getByTestId('zerodha-line')).toHaveText('Already trade with Zerodha? Connect when ready')
  // AC-5: Home itself offers no control (the shell header's own button, AppHeader.vue, is not part of Home)
  await expect(page.getByTestId('home').getByRole('button')).toHaveCount(0)
})

test('AC-2: three drafts -> My Strategies first, rows newest first', async ({ page }) => {
  await page.route('**/api/strategies', (route) =>
    route.request().method() === 'GET'
      ? route.fulfill({ json: { strategies: [
        draft(1, 'NIFTY', '2026-10-15T10:00:00+05:30'),
        draft(2, 'SENSEX', '2026-10-18T10:00:00+05:30'),
        draft(3, 'NIFTY', '2026-10-17T10:00:00+05:30')] } })
      : route.continue())
  await page.goto(`${REPLAY_URL}/home/overview`)
  await expect(page.getByTestId('home')).toHaveAttribute('data-state', 'has-strategies')
  await expect(page.getByTestId('home-actions').getByRole('link')).toHaveText(['My Strategies', 'Create Strategy'])
  const rows = page.getByTestId('recent-row')
  await expect(rows).toHaveCount(3)
  await expect(rows.first()).toContainText('SENSEX, draft, last saved 18 Oct 2026')
})

test('AC-4: the strip shows NIFTY 50 and SENSEX from the index socket pushes', async ({ page }) => {
  test.setTimeout(60000)
  const pushes: any[] = []
  await page.routeWebSocket('**/api/market/indices/live', (ws) => {
    const server = ws.connectToServer()
    ws.onMessage((m) => server.send(m))
    server.onMessage((m) => {
      pushes.push(JSON.parse(String(m)))
      ws.send(m)
    })
  })
  await page.goto(`${REPLAY_URL}/home/overview`)
  await expect.poll(() => pushes.length, { timeout: 20000 }).toBeGreaterThanOrEqual(2)
  const last = pushes.at(-1)
  const nifty = last.indices.find((r: any) => r.underlying === 'NIFTY')
  await expect(page.getByTestId('strip-NIFTY').getByTestId('strip-value')).toHaveText(nifty.value ?? 'Not available')
  await expect(page.getByTestId('strip-SENSEX')).toBeVisible()
})
