// W-111 (REQ-044 AC-3 part 1; ADR-109 (2)): the Positions pages in a real browser. GET /api/positions is answered in the
// browser with the route's own shape (backend/ofo_app/routes/positions.py; its values are the ADR-109 examples: strategy 1
// holds 65 of NIFTY26O1923650CE, recorded 2026-10-16). What is proven here is what the page SHOWS: quantities, the
// strategy link, outside lots apart, the catalogue message when the read is refused, and no money or order control.
import { test, expect, type Page } from '@playwright/test'

const SYMBOL = 'NIFTY26O1923650CE'
const READ_AT = '2026-10-16T12:21:04+05:30'

async function answer(page: Page, zerodha: number, outside: number, blocked = false) {
  await page.route('**/api/positions', (route) => route.fulfill({
    json: {
      read_at: READ_AT, blocked,
      contracts: [{ tradingsymbol: SYMBOL, zerodha_units: zerodha, outside_units: outside, blocked, own_units: 65,
        own: [{ strategy_id: 1, units: 65, blocked }] }],
    },
  }))
}

test('AC-3: Current positions shows 130 at Zerodha, 65 in strategies, 65 outside, with no money word or order button', async ({ page }) => {
  await answer(page, 130, 65)
  await page.goto('/positions/current-positions')
  const row = page.getByTestId('position-row')
  await expect(row).toHaveAttribute('data-symbol', SYMBOL)
  await expect(page.getByTestId('position-zerodha')).toHaveText('130')
  await expect(page.getByTestId('position-own')).toHaveText('65')
  await expect(page.getByTestId('position-outside')).toHaveText('65')
  await expect(page.getByTestId('positions-page')).not.toContainText(/P&L|price|margin|₹/i)
  await expect(page.getByTestId('positions-page').getByRole('button')).toHaveCount(0)
})

test('AC-3: Strategy-linked positions shows the own 65 with a link to the strategy and the outside 65 apart', async ({ page }) => {
  await answer(page, 130, 65)
  await page.goto('/positions/strategy-linked-positions')
  await expect(page.getByTestId('position-own-units')).toHaveText('65')
  await expect(page.getByTestId('position-strategy-link')).toHaveAttribute('href', '/strategy/1/execute')
  await expect(page.getByTestId('position-outside-lots')).toContainText('Not part of any strategy: 65 units')
})

test('AC-3: the recorded 65 shows no outside lots and Zerodha 0 against own 65 shows blocked', async ({ page }) => {
  await answer(page, 65, 0)
  await page.goto('/positions/strategy-linked-positions')
  await expect(page.getByTestId('position-own-units')).toHaveText('65')
  await expect(page.getByTestId('position-outside-lots')).toHaveCount(0)
  await page.unroute('**/api/positions')
  await answer(page, 0, 0, true)
  await page.goto('/positions/strategy-linked-positions')
  await expect(page.getByTestId('position-own-blocked')).toBeVisible()
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
