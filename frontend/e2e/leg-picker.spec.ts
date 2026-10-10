// W-068 / REQ-035 AC-8: the leg picker on the Builder page, against the real planned-entry and outcome routes.
// Runs in CI only (the app-tests job). The catalogue stays EMPTY in ofo_test (other tests assert it), so the two
// catalogue GET routes are answered here with the exact response shape of routes/catalogue.py, using the recorded NIFTY
// 13-Oct-2026 contracts (tokens 44595/44604/44624/44632 are in the recorded frames); everything else is real:
//   - REPLAY_URL (API in APP_ENV=test + OUTCOME_REPLAY=1): planned-entry returns the recorded LTP, the outcome is priced.
//   - PREVIEW_URL (plain API, no provider): planned-entry returns null + not_connected, so the leg is unpriced.
import { test, expect, type Page } from '@playwright/test'

const REPLAY_URL = process.env.REPLAY_URL || 'http://127.0.0.1:4175'
const PLAIN_URL = process.env.PREVIEW_URL || 'http://127.0.0.1:4173'
const c = (token: number, type: string, strike: string, symbol: string) => ({
  exchange_segment: 'NSE_FO', exchange_token: token, instrument_type: type, expiry: '2026-10-13', strike, lot_size: 65, symbol,
})
const CONTRACTS = {
  underlying: 'NIFTY',
  contracts: [
    c(44595, 'PE', '22200.00', 'NIFTY26O1322200PE'),
    c(44604, 'PE', '22400.00', 'NIFTY26O1322400PE'),
    c(44624, 'CE', '22800.00', 'NIFTY26O1322800CE'),
    c(44632, 'CE', '23000.00', 'NIFTY26O1323000CE'),
  ],
}

async function seedCatalogue(page: Page) {
  await page.route('**/api/catalogue/NIFTY/expiries', (r) => r.fulfill({ json: { underlying: 'NIFTY', expiries: ['2026-10-13'] } }))
  await page.route('**/api/catalogue/NIFTY/contracts?expiry=2026-10-13', (r) => r.fulfill({ json: CONTRACTS }))
}

async function addLeg(page: Page, type: string, strike: string, action: string) {
  await page.getByTestId('pick-expiry').selectOption('2026-10-13')
  await page.getByTestId('pick-type').selectOption(type)
  // wait for the API's strikes: the select is disabled until they arrive
  await expect(page.getByTestId('pick-strike')).toBeEnabled()
  await expect(page.getByTestId('pick-strike').locator(`option[value="${strike}"]`)).toBeAttached()
  await page.getByTestId('pick-strike').selectOption(strike)
  await page.getByTestId('pick-action').selectOption(action)
  await page.getByTestId('add-leg').click()
}

test('four picked legs are priced by the real outcome route on the recorded frames', async ({ page }, info) => {
  await seedCatalogue(page)
  await page.goto(`${REPLAY_URL}/strategy/builder`)
  await expect(page.getByTestId('strategy-builder')).toHaveAttribute('data-state', 'no-draft')
  await expect(page.getByTestId('pick-strike')).toBeVisible()
  await expect(page.getByTestId('pick-expiry')).toContainText('2026-10-13')
  await page.getByTestId('pick-expiry').selectOption('2026-10-13')
  await page.getByTestId('pick-type').selectOption('CE')
  // only the two offered CE strikes are choices
  await expect(page.getByTestId('pick-strike').locator('option:not([value=""])')).toHaveText(['22800.00', '23000.00'])
  await addLeg(page, 'CE', '22800.00', 'SELL')
  await addLeg(page, 'CE', '23000.00', 'BUY')
  await addLeg(page, 'PE', '22400.00', 'SELL')
  await addLeg(page, 'PE', '22200.00', 'BUY')
  await expect(page.getByTestId('leg-row')).toHaveCount(4)
  await expect(page.getByTestId('leg-unpriced')).toHaveCount(0)
  await expect(page.getByTestId('strategy-builder')).toHaveAttribute('data-state', 'computed')
  await expect(page.getByTestId('strategy-table')).toBeVisible()
  await page.screenshot({ path: `screenshots/leg-picker-priced-${info.project.name}.png`, fullPage: true })
})

test('edit changes a leg and remove drops it', async ({ page }) => {
  await seedCatalogue(page)
  await page.goto(`${REPLAY_URL}/strategy/builder`)
  await page.getByTestId('pick-expiry').selectOption('2026-10-13')
  await addLeg(page, 'CE', '22800.00', 'SELL')
  await expect(page.getByTestId('leg-row')).toHaveCount(1)
  await page.getByTestId('edit-leg').click()
  await expect(page.getByTestId('pick-strike')).toHaveValue('22800.00')
  await page.getByTestId('pick-strike').selectOption('23000.00')
  await page.getByTestId('add-leg').click()
  await expect(page.getByTestId('leg-row')).toHaveCount(1)
  await expect(page.getByTestId('leg-row')).toContainText('NIFTY26O1323000CE')
  await page.getByTestId('remove-leg').click()
  await expect(page.getByTestId('leg-row')).toHaveCount(0)
  await expect(page.getByTestId('strategy-builder')).toHaveAttribute('data-state', 'no-draft')
})

test('without live data the leg is added with no price and the not-connected wording, no numbers', async ({ page }, info) => {
  await seedCatalogue(page)
  await page.goto(`${PLAIN_URL}/strategy/builder`)
  await page.getByTestId('pick-expiry').selectOption('2026-10-13')
  await addLeg(page, 'CE', '22800.00', 'SELL')
  await expect(page.getByTestId('leg-unpriced')).toHaveText('Draft - Live data not connected')
  await expect(page.getByTestId('strategy-builder')).toHaveAttribute('data-state', 'unpriced')
  for (const id of ['strategy-table', 'payoff-chart', 'summary-cards']) await expect(page.getByTestId(id)).toHaveCount(0)
  await page.screenshot({ path: `screenshots/leg-picker-unpriced-${info.project.name}.png`, fullPage: true })
})
