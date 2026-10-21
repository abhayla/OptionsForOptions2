// W-111 (REQ-044 AC-3 part 1; ADR-109 (2); ADR-138 (2)): the Positions pages in a real browser. GET /api/positions is
// answered in the browser with the route's own shape (backend/ofo_app/routes/positions.py: strategy groups of
// strategy-linked contracts plus one outside-lots count; its values are the ADR-109 examples: strategy 1 holds 65 of
// NIFTY26O1923650CE, recorded 2026-10-16, lot 65). What is proven here is what the page SHOWS: quantities per strategy,
// the strategy link, "N outside lots - view on Kite", the catalogue message when the read is refused, and no money or
// order control. Keys are exactly the set asserted by tests_app/test_positions_route.py::
// test_adr110_two_strategies_on_one_contract_one_pending_blocks_both, so a renamed route key fails there.
import { test, expect, type Page } from '@playwright/test'
import { KITE_POSITIONS_URL } from '../src/lib/execute.js'

const SYMBOL = 'NIFTY26O1923650CE'
const READ_AT = '2026-10-16T12:21:04+05:30'

async function answer(page: Page, strategies: object[], outside: number | null, hasOutside: boolean, blocked: number[] = []) {
  await page.route('**/api/positions', (route) => route.fulfill({
    json: { read_at: READ_AT, strategies, has_outside: hasOutside, outside_lots: outside, blocked: blocked.length > 0,
      blocked_strategy_ids: blocked },
  }))
}
const own = (units: number, zerodha: number) => ({ tradingsymbol: SYMBOL, zerodha_units: zerodha, units, pending: false,
  pending_plans: [] })

for (const path of ['/positions/current-positions', '/positions/strategy-linked-positions']) {
  test(`ADR-138 (2) mixed on ${path}: strategy 1 own 65 (Zerodha 130), "1 outside lot - view on Kite", no money word or button`, async ({ page }) => {
    await answer(page, [{ strategy_id: 1, blocked: false, contracts: [own(65, 130)] }], 1, true)
    await page.goto(path)
    const group = page.getByTestId('position-group')
    await expect(group).toHaveAttribute('data-strategy', '1')
    await expect(page.getByTestId('position-row')).toHaveAttribute('data-symbol', SYMBOL)
    await expect(page.getByTestId('position-own-units')).toHaveText('65')
    await expect(page.getByTestId('position-zerodha')).toHaveText('130')
    await expect(page.getByTestId('position-strategy-link')).toHaveAttribute('href', '/strategy/1/execute')
    await expect(page.getByTestId('positions-outside')).toHaveText('1 outside lot - view on Kite')
    await expect(page.getByTestId('positions-outside-kite')).toHaveAttribute('href', KITE_POSITIONS_URL)
    await expect(page.getByTestId('positions-page')).not.toContainText(/P&L|price|margin|₹/i)
    await expect(page.getByTestId('positions-page').getByRole('button')).toHaveCount(0)
  })
}

test('ADR-138 (2): only outside positions show zero rows and the outside count, never the contract', async ({ page }) => {
  await answer(page, [], 1, true)
  await page.goto('/positions/current-positions')
  await expect(page.getByTestId('position-row')).toHaveCount(0)
  await expect(page.getByTestId('positions-outside-count')).toHaveText('1 outside lot')
  await expect(page.getByTestId('positions-page')).not.toContainText(SYMBOL)
  await expect(page.getByTestId('positions-empty')).toHaveCount(0)
})

test('AC-3: the recorded 65 shows no outside line, and Zerodha 0 against own 65 shows the mismatch badge', async ({ page }) => {
  await answer(page, [{ strategy_id: 1, blocked: false, contracts: [own(65, 65)] }], 0, false)
  await page.goto('/positions/strategy-linked-positions')
  await expect(page.getByTestId('position-own-units')).toHaveText('65')
  await expect(page.getByTestId('positions-outside')).toHaveCount(0)
  await page.unroute('**/api/positions')
  await answer(page, [{ strategy_id: 1, blocked: true, contracts: [own(65, 0)] }], 0, false, [1])
  await page.goto('/positions/strategy-linked-positions')
  await expect(page.getByTestId('position-mismatch-badge')).toBeVisible()
  await expect(page.getByTestId('positions-blocked')).toBeVisible()
})

test('AC-3: a refused read shows the catalogue message, not an empty list', async ({ page }) => {
  await page.route('**/api/positions', (route) => route.fulfill({
    status: 409,
    json: { error_class: 'BROKER_AUTHENTICATION', code: 'BROKER_AUTHENTICATION_102',
      what_happened: 'Your Zerodha account is not connected. Connect it to continue.',
      impact: 'Orders cannot be sent to Zerodha.', what_is_blocked: 'Execution of this strategy.',
      next_action: 'Connect your Zerodha account from the account page.', external_text: null },
  }))
  await page.goto('/positions/current-positions')
  await expect(page.getByTestId('positions-page')).toContainText('Your Zerodha account is not connected')
  await expect(page.getByTestId('positions-empty')).toHaveCount(0)
  await expect(page.getByTestId('position-row')).toHaveCount(0)
})

test('ADR-110: a contract with an open plan shows waiting for Check, 65 not yet confirmed, no own units, and the Execute link', async ({ page }) => {
  // A browser mock, not the real route. The pending case is unproven end to end through the real route
  // (work/W-111.md next_action).
  await answer(page, [{ strategy_id: 1, blocked: true, contracts: [{ tradingsymbol: SYMBOL, zerodha_units: 65, units: null,
    pending: true, pending_plans: [1] }] }], 0, false, [1])
  await page.goto('/positions/strategy-linked-positions')
  await expect(page.getByTestId('position-waiting')).toHaveText('Order placed - waiting for Check with Zerodha')
  await expect(page.getByTestId('position-zerodha')).toHaveText('65')
  await expect(page.getByTestId('position-unconfirmed')).toHaveText('not yet confirmed')
  await expect(page.getByTestId('position-strategy-link')).toHaveAttribute('href', '/strategy/1/execute')
  await expect(page.getByTestId('positions-blocked-link')).toHaveAttribute('href', '/strategy/1/execute')
  await expect(page.getByTestId('position-own-units')).toHaveCount(0)
  await expect(page.getByTestId('positions-outside')).toHaveCount(0)
})
