// W-159 / REQ-085 AC-1, AC-2, AC-5 (ADR-185): the warnings area on the Builder page, against the real outcome route on the
// recorded 2026-10-08 frames (API in APP_ENV=test + OUTCOME_REPLAY=1, the replay preview). Runs in CI only (the app-tests job).
// The catalogue stays EMPTY in ofo_test, so the two catalogue GET routes are answered here in the exact shape of
// routes/catalogue.py with NIFTY 19-Oct-2026 contracts whose tokens are in the recorded frames (47417 24900 PE, 47425
// 25000 CE, 47411 24850 PE; each has a live price there); the outcome, its warnings and their texts are the server's.
import { test, expect, type Page } from '@playwright/test'
import { useQuietLiveSocket } from './support/quiet-live'

useQuietLiveSocket() // these tests prove the REST path; the live socket is held silent

const REPLAY_URL = process.env.REPLAY_URL || 'http://127.0.0.1:4175'
const EXPIRY = '2026-10-19'
const c = (token: number, type: string, strike: string, symbol: string) => ({
  exchange_segment: 'NSE_FO', exchange_token: token, instrument_type: type, expiry: EXPIRY, strike, lot_size: 65, symbol,
})
const CONTRACTS = {
  underlying: 'NIFTY',
  contracts: [c(47411, 'PE', '24850.00', 'NIFTY26O1924850PE'), c(47417, 'PE', '24900.00', 'NIFTY26O1924900PE'), c(47425, 'CE', '25000.00', 'NIFTY26O1925000CE')],
}

async function seedCatalogue(page: Page) {
  await page.route('**/api/catalogue/NIFTY/expiries', (r) => r.fulfill({ json: { underlying: 'NIFTY', expiries: [EXPIRY] } }))
  await page.route(`**/api/catalogue/NIFTY/contracts?expiry=${EXPIRY}`, (r) => r.fulfill({ json: CONTRACTS }))
}

async function addLeg(page: Page, type: string, strike: string, action: string) {
  const rows = page.getByTestId('leg-row')
  const before = await rows.count()
  await page.getByTestId('pick-type').selectOption(type)
  await expect(page.getByTestId('pick-strike')).toBeEnabled()
  await expect(page.getByTestId('pick-strike').locator(`option[value="${strike}"]`)).toBeAttached()
  await page.getByTestId('pick-strike').selectOption(strike)
  await page.getByTestId('pick-action').selectOption(action)
  await page.getByTestId('add-leg').click()
  await expect(rows).toHaveCount(before + 1)
}

test('a strangle shows the rising and the falling unhedged warning in the strategy area; the bought put leaves the rising one', async ({ page }, info) => {
  await seedCatalogue(page)
  await page.goto(`${REPLAY_URL}/strategy/builder`)
  await page.getByTestId('pick-expiry').selectOption(EXPIRY)
  await addLeg(page, 'PE', '24900.00', 'SELL')
  await addLeg(page, 'CE', '25000.00', 'SELL')
  await expect(page.getByTestId('strategy-builder')).toHaveAttribute('data-state', /computed|stale/)
  const warnings = page.getByTestId('strategy-warning')
  await expect(warnings).toHaveCount(2)
  await expect(warnings.filter({ hasText: 'rises' })).toHaveCount(1)
  await expect(warnings.filter({ hasText: 'falls' })).toHaveCount(1)
  await expect(page.locator('[data-testid="strategy-warning"][data-code="unhedged_short"]')).toHaveCount(2)
  // ADR-185: no leg row carries an unhedged mark; a leg mark is a liquidity code only
  await expect(page.locator('[data-testid="leg-warning"][data-code="unhedged_short"]')).toHaveCount(0)
  await expect(page.getByTestId('no-warnings')).toHaveCount(0)
  await page.screenshot({ path: `screenshots/strategy-warnings-strangle-${info.project.name}.png`, fullPage: true })

  await addLeg(page, 'PE', '24850.00', 'BUY')
  await expect(warnings).toHaveCount(1)
  await expect(warnings.first()).toContainText('rises')
  await expect(page.locator('[data-testid="leg-warning"][data-code="unhedged_short"]')).toHaveCount(0)
})
