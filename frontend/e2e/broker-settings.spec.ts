// W-089 + GC-6 ZERODHA-CONN (REQ-015 AC-4, ADR-138 (5)): Settings -> Broker & Market Data shows one state, Connected or
// Reconnect, the last successful sync, Reconnect and Disconnect, and the V1 statement that history is not available. The
// status API is answered in the browser with the shapes backend/ofo_app/routes/broker_status.py produces (proven against
// PostgreSQL in tests_app/test_broker_status_route.py).
import { test, expect, type Page } from '@playwright/test'

const PATH = '/settings/broker-market-data'
const ok = { state: 'connected', fix: null }
const down = (fix: string) => ({ state: 'disconnected', fix })

const CONNECTED = {
  account_connection: ok, live_market_data: ok, position_sync: ok, order_execution: ok,
  last_successful_sync: '2026-10-17T09:05:00Z', historical_data: 'not_available',
}
const DISCONNECTED = {
  account_connection: down('connect_zerodha'), live_market_data: down('connect_zerodha'),
  position_sync: down('connect_zerodha'), order_execution: down('connect_zerodha'),
  last_successful_sync: null, historical_data: 'not_available',
}

async function serve(page: Page, body: unknown, status = 200) {
  await page.route('**/api/broker/status', (route) => route.fulfill({ status, json: body as object }))
}

test('connected: one Connected state, the last sync, Reconnect and Disconnect, and the history statement', async ({ page }, info) => {
  await serve(page, CONNECTED)
  await page.goto(PATH)
  await expect(page.getByTestId('connection-state')).toHaveText('Connected')
  await expect(page.getByTestId('last-sync-time')).toContainText('IST')
  await expect(page.getByTestId('broker-reconnect')).toHaveText('Reconnect Zerodha')
  await expect(page.getByTestId('broker-disconnect')).toBeVisible()
  await expect(page.getByTestId('history-statement')).toContainText('not currently available')
  await expect(page.getByText('Partially connected')).toHaveCount(0)
  await page.screenshot({ path: `screenshots/broker-settings-connected-${info.project.name}.png`, fullPage: true })
})

test('a live account with a feature not ready is still one Connected state', async ({ page }) => {
  await serve(page, { ...CONNECTED, live_market_data: { state: 'partial', fix: 'live_feed_off' } })
  await page.goto(PATH)
  await expect(page.getByTestId('connection-state')).toHaveText('Connected')
  await expect(page.getByText('Partially connected')).toHaveCount(0)
})

test('not connected: Reconnect with the guide, no sync time, no Disconnect', async ({ page }, info) => {
  await serve(page, DISCONNECTED)
  await page.goto(PATH)
  await expect(page.getByTestId('connection-state')).toHaveText('Reconnect')
  await expect(page.getByTestId('reconnect-help')).toContainText('We never ask for your password, PIN or OTP')
  await expect(page.getByTestId('last-sync-none')).toBeVisible()
  await expect(page.getByTestId('broker-reconnect')).toHaveText('Reconnect')
  await expect(page.getByTestId('broker-disconnect')).toHaveCount(0)
  await page.screenshot({ path: `screenshots/broker-settings-disconnected-${info.project.name}.png`, fullPage: true })
})

test('Disconnect asks first, then the page reads Reconnect', async ({ page }) => {
  let ended = false
  await page.route('**/api/broker/status', (route) => route.fulfill({ json: ended ? DISCONNECTED : CONNECTED }))
  await page.route('**/api/broker/disconnect', (route) => {
    expect(route.request().method()).toBe('POST')
    ended = true
    return route.fulfill({ json: { disconnected: true } })
  })
  await page.goto(PATH)
  await page.getByTestId('broker-disconnect').click()
  await expect(page.getByTestId('disconnect-confirm')).toContainText('keeps your strategies, history, entitlements and account')
  await page.getByTestId('disconnect-no').click()
  await expect(page.getByTestId('disconnect-confirm')).toHaveCount(0)
  expect(ended).toBe(false)
  await page.getByTestId('broker-disconnect').click()
  await page.getByTestId('disconnect-yes').click()
  await expect(page.getByTestId('connection-state')).toHaveText('Reconnect')
})

test('a failed status read shows the unavailable state and no Connected state', async ({ page }) => {
  await serve(page, { detail: 'boom' }, 500)
  await page.goto(PATH)
  await expect(page.getByTestId('broker-unavailable')).toBeVisible()
  await expect(page.getByTestId('connection-state')).toHaveCount(0)
  await expect(page.getByText('Connected', { exact: true })).toHaveCount(0)
})
