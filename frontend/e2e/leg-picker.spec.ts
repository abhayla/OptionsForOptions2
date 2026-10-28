// W-068 / REQ-035 AC-8: the leg picker on the Builder page, against the real planned-entry and outcome routes.
// Runs in CI only (the app-tests job). The catalogue stays EMPTY in ofo_test (other tests assert it), so the two
// catalogue GET routes are answered here with the exact response shape of routes/catalogue.py, using the recorded NIFTY
// 13-Oct-2026 contracts (tokens 44595/44604/44624/44632 are in the recorded frames); everything else is real:
//   - REPLAY_URL (API in APP_ENV=test + OUTCOME_REPLAY=1): planned-entry returns the recorded LTP, the outcome is priced.
//   - PREVIEW_URL (plain API, no provider): planned-entry returns null + not_connected, so the leg is unpriced.
import { test, expect, type Page } from '@playwright/test'
import { useQuietLiveSocket } from './support/quiet-live'
import { openAddEdit, openFullTable } from './pages/builder.page'

useQuietLiveSocket() // W-065: these tests prove the REST path; the live socket is held silent

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

// The expiry is chosen once by the caller: saving a leg keeps it (and its contracts), so it is not re-selected here.
async function addLeg(page: Page, type: string, strike: string, action: string) {
  const rows = page.getByTestId('leg-row')
  await openAddEdit(page) // W-192: the add form sits behind Add/Edit once legs exist
  const before = await rows.count()
  await page.getByTestId('pick-type').selectOption(type)
  // wait for the API's strikes: the select is disabled until they arrive
  await expect(page.getByTestId('pick-strike')).toBeEnabled()
  await expect(page.getByTestId('pick-strike').locator(`option[value="${strike}"]`)).toBeAttached()
  await page.getByTestId('pick-strike').selectOption(strike)
  await page.getByTestId('pick-action').selectOption(action)
  await page.getByTestId('add-leg').click()
  // the capture has finished and the form is free for the next leg. 15 s, as in the edit test below: CI #581's trace showed the 4th
  // planned-entry request still unanswered 6 s after it was sent, queued behind a 5.2 s outcome reply on the replay API (late, not
  // lost: tests/leg-picker.test.js "legs added quickly in sequence are all kept" pins that every leg is kept)
  await expect(rows).toHaveCount(before + 1, { timeout: 15_000 })
}

test('four picked legs are priced by the real outcome route on the recorded frames', async ({ page }, info) => {
  await seedCatalogue(page)
  await page.goto(`${REPLAY_URL}/strategy/builder`)
  await openAddEdit(page) // W-195: the picker is the left drawer behind Add/Edit
  await expect(page.getByTestId('strategy-builder')).toHaveAttribute('data-state', 'no-draft')
  await expect(page.getByTestId('pick-strike')).toBeVisible()
  await expect(page.getByTestId('pick-expiry')).toContainText('13 Oct') // REQ-148 AC-2: never raw ISO
  await page.getByTestId('pick-expiry').selectOption('2026-10-13')
  await page.getByTestId('pick-type').selectOption('CE')
  // only the two offered CE strikes are choices
  await expect(page.getByTestId('pick-strike').locator('option:not([value=""])')).toHaveText(['22800', '23000']) // #582 item 7: a strike prints without ".00"; the option VALUE stays '22800.00'
  await addLeg(page, 'CE', '22800.00', 'SELL')
  await addLeg(page, 'CE', '23000.00', 'BUY')
  await addLeg(page, 'PE', '22400.00', 'SELL')
  await addLeg(page, 'PE', '22200.00', 'BUY')
  await expect(page.getByTestId('leg-row')).toHaveCount(4)
  await expect(page.getByTestId('leg-unpriced')).toHaveCount(0)
  await expect(page.getByTestId('strategy-builder')).toHaveAttribute('data-state', 'computed')
  await openFullTable(page) // ADR-194: the full table sits behind the P&L Table tab's Full table switch
  await expect(page.getByTestId('strategy-table')).toBeVisible()
  await page.screenshot({ path: `screenshots/leg-picker-priced-${info.project.name}.png`, fullPage: true })
})

test('edit changes a leg and remove drops it', async ({ page }) => {
  await seedCatalogue(page)
  await page.goto(`${REPLAY_URL}/strategy/builder`)
  await openAddEdit(page) // W-195: the picker is the left drawer behind Add/Edit
  await page.getByTestId('pick-expiry').selectOption('2026-10-13')
  await addLeg(page, 'CE', '22800.00', 'SELL')
  await expect(page.getByTestId('leg-row')).toHaveCount(1)
  await page.getByTestId('edit-leg').click()
  await expect(page.getByTestId('pick-strike')).toHaveValue('22800.00')
  await page.getByTestId('pick-strike').selectOption('23000.00')
  await page.getByTestId('add-leg').click()
  // the edit is done when the picker hands the page back (after the new contract's planned entry is captured, which the
  // replay API answered in 4.5 s in the failing run): only then is the row's contract read
  await expect(page.getByTestId('leg-picker-panel')).toBeHidden({ timeout: 15_000 })
  await expect(page.getByTestId('leg-row')).toHaveCount(1)
  await expect(page.getByTestId('leg-row')).toContainText('NIFTY 13 Oct 23000 CE')
  await expect(page.getByTestId('strategy-builder')).toHaveAttribute('data-state', /computed|stale/)
  await page.getByTestId('remove-leg').click()
  await expect(page.getByTestId('leg-row')).toHaveCount(0)
  await expect(page.getByTestId('strategy-builder')).toHaveAttribute('data-state', 'no-draft')
})

test('without live data the leg is added with no price and the not-connected wording, no numbers', async ({ page }, info) => {
  await seedCatalogue(page)
  await page.goto(`${PLAIN_URL}/strategy/builder`)
  await openAddEdit(page) // W-195: the picker is the left drawer behind Add/Edit
  await page.getByTestId('pick-expiry').selectOption('2026-10-13')
  await addLeg(page, 'CE', '22800.00', 'SELL')
  await expect(page.getByTestId('leg-unpriced')).toHaveText('Draft — Live data not connected')
  await expect(page.getByTestId('strategy-builder')).toHaveAttribute('data-state', 'unpriced')
  for (const id of ['strategy-table', 'payoff-chart', 'summary-cards']) await expect(page.getByTestId(id)).toHaveCount(0)
  await page.screenshot({ path: `screenshots/leg-picker-unpriced-${info.project.name}.png`, fullPage: true })
})

// W-147 / REQ-080: the Strikes tab and the depth popup. Only the two /api/leg-picker reads are answered here (the backend
// reads are proven in tests_app/test_leg_picker_routes.py; this API has no feed in e2e), with the exact shape of
// routes/leg_picker.py StrikesOut / DepthOut using the recorded NIFTY 13-Oct-2026 tokens of CONTRACTS above. The planned-entry
// capture is the REAL route of the plain API: no provider, so each leg comes back unpriced and asks for a reprice.
const NOW = '2026-10-08T09:20:09+05:30'
const pickerCell = (token: number) => ({
  instrument_id: `NSE_FO:${token}`, lot_size: 65, ltp: null, oi: null, iv_percent: null, delta: null, health: 'unavailable', at: null,
})
const STRIKES = {
  state: 'NOT_LIVE', reason: 'NOT_CONNECTED', underlying: 'NIFTY', expiry: '2026-10-13', width: 10, spot: null, spot_at: null,
  centre: 'MIDDLE_STRIKE', atm_strike: null, answered_at: NOW, market_closed: false,
  rows: [
    { strike: '22400.00', is_atm: false, ce: null, pe: pickerCell(44604) },
    { strike: '22800.00', is_atm: false, ce: pickerCell(44624), pe: null },
  ],
}
const DEPTH_NOT_AVAILABLE = {
  state: 'NOT_AVAILABLE', reason: 'NO_SESSION', instrument_id: 'NSE_FO:44624', bids: [], asks: [], day_open: null, day_high: null,
  day_low: null, prev_close: null, last_trade_at: null, day_stats_reason: 'NOT_HELD', read_at: NOW,
}

test('Strikes tab without live data: dashes and the reason, two selected contracts added by Done, depth says not available', async ({ page }) => {
  await seedCatalogue(page)
  await page.route('**/api/leg-picker/strikes**', (r) => r.fulfill({ json: STRIKES }))
  await page.route('**/api/leg-picker/depth**', (r) => r.fulfill({ json: DEPTH_NOT_AVAILABLE }))
  await page.goto(`${PLAIN_URL}/strategy/builder`)
  await openAddEdit(page) // W-195: the picker is the left drawer behind Add/Edit
  await page.getByTestId('pick-expiry').selectOption('2026-10-13')
  await expect(page.getByTestId('strikes-reason')).toHaveText('Live data is not connected, so no prices are shown.')
  await expect(page.getByTestId('strikes-centre')).toContainText('ATM unknown - no live price')
  await expect(page.getByTestId('strike-row')).toHaveCount(2)
  await expect(page.getByTestId('cell-ltp').first()).toHaveText('-')
  await page.getByTestId('cell-pe').getByTestId('cell-sell').click()
  await page.getByTestId('cell-ce').getByTestId('cell-buy').click()
  await page.getByTestId('picker-done').click()
  await expect(page.getByTestId('leg-row')).toHaveCount(2)
  await expect(page.getByTestId('leg-reprice-prompt')).toHaveCount(2)
  await page.getByTestId('depth-icon').first().click()
  await expect(page.getByTestId('depth-unavailable')).toContainText('Depth not available')
  await expect(page.getByTestId('depth-reason')).toHaveText('The broker account is not connected.')
  await expect(page.getByTestId('depth-table')).toHaveCount(0)
  await page.getByTestId('depth-close').click()
  await expect(page.getByTestId('depth-popup')).toHaveCount(0)
})
