// W-089 (REQ-015 AC-4): Settings -> Broker & Market Data shows the four statuses, the last successful sync, Reconnect and
// Disconnect, and the V1 statement that history is not available. The status API is answered in the browser with the
// shapes backend/ofo_app/routes/broker_status.py produces (proven against PostgreSQL in tests_app/test_broker_status_route.py).
import { test, expect, type Page } from '@playwright/test'

const PATH = '/settings/broker-market-data'
const ROWS = ['account_connection', 'live_market_data', 'position_sync', 'order_execution']
const ok = { state: 'connected', fix: null }
const down = (fix: string) => ({ state: 'disconnected', fix })

const CONNECTED = {
  account_connection: ok, live_market_data: ok, position_sync: ok, order_execution: ok,
  last_successful_sync: '2026-10-17T09:05:00Z', historical_data: 'not_available',
}
const PARTIAL = {
  ...CONNECTED,
  live_market_data: { state: 'partial', fix: 'live_feed_off' },
  order_execution: { state: 'partial', fix: 'live_data_not_connected' },
}
const DISCONNECTED = {
  account_connection: down('connect_zerodha'), live_market_data: down('connect_zerodha'),
  position_sync: down('connect_zerodha'), order_execution: down('connect_zerodha'),
  last_successful_sync: null, historical_data: 'not_available',
}

async function serve(page: Page, body: unknown, status = 200) {
  await page.route('**/api/broker/status', (route) => route.fulfill({ status, json: body as object }))
}

test('connected: four Connected rows, the last sync, Reconnect and Disconnect, and the history statement', async ({ page }, info) => {
  await serve(page, CONNECTED)
  await page.goto(PATH)
  for (const key of ROWS) await expect(page.getByTestId(`status-${key}`)).toHaveText('Connected')
  await expect(page.getByTestId('last-sync-time')).toContainText('IST')
  await expect(page.getByTestId('broker-reconnect')).toHaveText('Reconnect Zerodha')
  await expect(page.getByTestId('broker-disconnect')).toBeVisible()
  await expect(page.getByTestId('history-statement')).toContainText('not currently available')
  await page.screenshot({ path: `screenshots/broker-settings-connected-${info.project.name}.png`, fullPage: true })
})

test('partially connected: names what to fix, and never shows Connected for the feed', async ({ page }) => {
  await serve(page, PARTIAL)
  await page.goto(PATH)
  await expect(page.getByTestId('status-live_market_data')).toHaveText('Partially connected')
  await expect(page.getByTestId('fix-live_market_data')).toContainText('switched off on the server')
  await expect(page.getByTestId('status-order_execution')).toHaveText('Partially connected')
  await expect(page.getByTestId('fix-order_execution')).toContainText('live market data')
  await expect(page.getByTestId('fix-account_connection')).toHaveCount(0)
})

test('disconnected: four Disconnected rows with the guide, no sync time, Connect and no Disconnect', async ({ page }, info) => {
  await serve(page, DISCONNECTED)
  await page.goto(PATH)
  for (const key of ROWS) {
    await expect(page.getByTestId(`status-${key}`)).toHaveText('Disconnected')
    await expect(page.getByTestId(`fix-${key}`)).toContainText('Zerodha is not connected')
  }
  await expect(page.getByTestId('last-sync-none')).toBeVisible()
  await expect(page.getByTestId('broker-reconnect')).toHaveText('Connect Zerodha')
  await expect(page.getByTestId('broker-disconnect')).toHaveCount(0)
  await page.screenshot({ path: `screenshots/broker-settings-disconnected-${info.project.name}.png`, fullPage: true })
})

test('Disconnect asks first, then the page reads Disconnected', async ({ page }) => {
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
  await expect(page.getByTestId('status-account_connection')).toHaveText('Disconnected')
})

test('a failed status read shows the unavailable state and no Connected row', async ({ page }) => {
  await serve(page, { detail: 'boom' }, 500)
  await page.goto(PATH)
  await expect(page.getByTestId('broker-unavailable')).toBeVisible()
  await expect(page.getByTestId('broker-rows')).toHaveCount(0)
  await expect(page.getByText('Connected', { exact: true })).toHaveCount(0)
})
