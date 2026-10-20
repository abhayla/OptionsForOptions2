// GC-6 ORDERS-SCREEN (ADR-135, ADR-138 (1), ADR-130) at 1280 and 390 px. GET /api/orders is answered in the browser with
// the shape the route returns (backend routes/orders.py; the route itself is proven against the database in
// tests_app/test_orders_route.py): the owner's real GC-3L order, BUY 65 NIFTY26OCT24000CE filled 65 of 65.
// Kite is never reached: the order book link is read, not clicked.
import { test, expect, type Page } from '@playwright/test'

const LINE = {
  strategy_id: 9, plan_number: 1, action: 'ENTRY', tradingsymbol: 'NIFTY26OCT24000CE', transaction_type: 'BUY',
  ordered_quantity: 65, filled_quantity: 65, state: 'executed', could_not_confirm: false, needs_reconciliation: false,
  message: null, updated_at: '2026-10-19T10:00:00+05:30',
}

async function answerWith(page: Page, orders: unknown[]) {
  await page.route('**/api/orders', (route) =>
    route.fulfill({ json: { read_at: '2026-10-19T10:05:00+05:30', kite_read: 'read', orders } }))
}

async function noSideways(page: Page) {
  const wide = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)
  expect(wide, 'no horizontal scroll').toBe(false)
}

test('a line shows its state and the Open Kite order book link, large enough to tap', async ({ page }) => {
  await answerWith(page, [LINE, { ...LINE, plan_number: 2, action: 'EXIT', transaction_type: 'SELL', state: 'placed', filled_quantity: null }])
  await page.goto('/orders')
  await expect(page.getByTestId('page-title')).toHaveText('Orders')
  const lines = page.getByTestId('order-line')
  await expect(lines).toHaveCount(2)
  await expect(lines.nth(0).getByTestId('order-state')).toHaveText('Executed 65 of 65')
  await expect(lines.nth(0).getByTestId('order-what')).toHaveText('BUY 65 NIFTY26OCT24000CE')
  await expect(lines.nth(1).getByTestId('order-state')).toHaveText('Order placed')
  const link = page.getByRole('link', { name: 'Open Kite order book' })
  await expect(link).toHaveAttribute('href', 'https://kite.zerodha.com/orders')
  const box = await link.boundingBox()
  expect(box?.height).toBeGreaterThanOrEqual(44)
  await noSideways(page)
})

test('the other approved words are spelled exactly', async ({ page }) => {
  await answerWith(page, [{ ...LINE, state: 'not_sent', filled_quantity: null }, { ...LINE, plan_number: 2, state: 'not_executed', filled_quantity: null }])
  await page.goto('/orders')
  await expect(page.getByTestId('order-state')).toHaveText(['Not sent to Zerodha', 'Not executed - see Kite'])
  await noSideways(page)
})

test('no orders: "No orders yet." and Create Strategy', async ({ page }) => {
  await answerWith(page, [])
  await page.goto('/orders')
  await expect(page.getByTestId('empty-state-message')).toHaveText('No orders yet.')
  await expect(page.getByRole('button', { name: 'Create Strategy' })).toBeVisible()
  await expect(page.getByTestId('order-line')).toHaveCount(0)
  await noSideways(page)
})
