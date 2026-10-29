// W-072 / REQ-039 AC-3 under ADR-086 (core proof): the real Builder page, with legs added from the catalogue routes and a
// priced answer from the real outcome API (replay mode), names each leg by its contract, shows every time as
// "15 Oct 2026, 11:59:59 IST" whatever the browser's zone (the browser here runs in New York), and shows a catalogue error
// with its four labelled parts. No raw instrument id and no ISO time anywhere in the page text.
// As in leg-picker.spec.ts the catalogue GET routes are answered here (the catalogue is empty in the test database).
import { test, expect, type Page } from '@playwright/test'
import { useQuietLiveSocket } from './support/quiet-live'
import { openAddEdit } from './pages/builder.page'

useQuietLiveSocket()
test.use({ timezoneId: 'America/New_York' }) // a browser-zone formatter would show New York time and fail the match below

const REPLAY_URL = process.env.REPLAY_URL || 'http://127.0.0.1:4175'
const c = (token: number, type: string, strike: string, symbol: string) => ({
  exchange_segment: 'NSE_FO', exchange_token: token, instrument_type: type, expiry: '2026-10-13', strike, lot_size: 65, symbol,
})
const CONTRACTS = {
  underlying: 'NIFTY',
  contracts: [
    c(44624, 'CE', '22800.00', 'NIFTY26O1322800CE'),
    c(44632, 'CE', '23000.00', 'NIFTY26O1323000CE'),
  ],
}
const IST_TEXT = /\d{1,2} [A-Z][a-z]{2} \d{4}, \d{2}:\d{2}:\d{2} IST/
const PARTS = {
  what_happened: 'The page or action you asked for is not available here.',
  impact: 'Nothing on this page can be changed until it is available.',
  what_is_blocked: 'This request.',
  next_action: 'Go back to the previous page and choose again.',
}

// GC-UI D-C31: a leg is added only from the strike table, which reads GET /api/leg-picker/strikes. That route reads the
// STORED catalogue on the database clock, where 13-Oct-2026 has expired, so its grid is answered here like the catalogue
// above (same StrikesOut shape as routes/leg_picker.py; no price in it). Prices still come from the real planned-entry route.
const GRID_CELL = (token: number) => ({
  instrument_id: `NSE_FO:${token}`, lot_size: 65, ltp: null, oi: null, iv_percent: null, delta: null, health: 'unavailable', at: null,
})
const GRID = {
  state: 'NOT_LIVE', reason: 'NOT_CONNECTED', underlying: 'NIFTY', expiry: '2026-10-13', width: 10, spot: null, spot_at: null,
  centre: 'MIDDLE_STRIKE', atm_strike: null, answered_at: '2026-10-08T09:20:09+05:30', market_closed: false,
  rows: [
    { strike: '22200.00', is_atm: false, ce: null, pe: GRID_CELL(44595) },
    { strike: '22400.00', is_atm: false, ce: null, pe: GRID_CELL(44604) },
    { strike: '22800.00', is_atm: false, ce: GRID_CELL(44624), pe: null },
    { strike: '23000.00', is_atm: false, ce: GRID_CELL(44632), pe: null },
  ],
}

async function seedCatalogue(page: Page) {
  await page.route('**/api/catalogue/NIFTY/expiries', (r) => r.fulfill({ json: { underlying: 'NIFTY', expiries: ['2026-10-13'] } }))
  await page.route('**/api/catalogue/NIFTY/contracts?expiry=2026-10-13', (r) => r.fulfill({ json: CONTRACTS }))
  await page.route('**/api/leg-picker/strikes**', (r) => r.fulfill({ json: GRID }))
}

async function noRawValues(page: Page) {
  const text = await page.getByTestId('strategy-builder').innerText()
  expect(text).not.toMatch(/[A-Z]+_FO:\d+/)
  expect(text).not.toMatch(/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/)
}

test('legs are named by contract, times are IST words, and no raw id or ISO time is on the page', async ({ page }) => {
  await seedCatalogue(page)
  await page.goto(`${REPLAY_URL}/strategy/builder`)
  await openAddEdit(page) // W-195: the picker is the left drawer behind Add/Edit
  await page.getByTestId('pick-expiry').selectOption('2026-10-13')
  for (const [strike, action] of [['22800.00', 'SELL'], ['23000.00', 'BUY']]) {
    const rows = page.getByTestId('leg-row')
    const before = await rows.count()
    await openAddEdit(page) // W-192: the add form sits behind Add/Edit once legs exist
    // D-C31: B / S on the strike table, then Done
    const cell = page.locator(`[data-testid="strike-row"][data-strike="${strike}"] [data-testid="cell-ce"]`)
    await cell.getByTestId(action === 'BUY' ? 'cell-buy' : 'cell-sell').click()
    await page.getByTestId('picker-done').click()
    await expect(rows).toHaveCount(before + 1)
  }
  await expect(page.getByTestId('strategy-builder')).toHaveAttribute('data-state', 'computed')
  const first = page.getByTestId('leg-row').nth(0)
  await expect(first.getByTestId('leg-name')).toHaveText('NIFTY 13 Oct 22800 CE')
  await expect(page.getByTestId('leg-row').nth(1).getByTestId('leg-name')).toHaveText('NIFTY 13 Oct 23000 CE')
  // the captured time is the API's instant shown in India time, computed here from the raw value kept in data-captured
  const raw = (await first.getAttribute('data-captured')) as string
  expect(raw).toMatch(/^\d{4}-\d{2}-\d{2}T/)
  const parts = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Kolkata', day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' })
    .formatToParts(new Date(raw)).reduce((m: Record<string, string>, p) => ({ ...m, [p.type]: p.value }), {})
  const expected = `${parts.day} ${parts.month} ${parts.year}, ${parts.hour}:${parts.minute}:${parts.second} IST`
  await expect(first.getByTestId('leg-captured')).toHaveText(`captured ${expected}`)
  // REQ-135 AC-3: the footer's 'Priced at' and the summary card's clock are gone; the one 'Prices as of' stamp replaces them
  await expect(page.getByTestId('footer-valuation')).toHaveCount(0)
  await expect(page.getByTestId('summary-cards')).not.toContainText(IST_TEXT)
  await noRawValues(page)
})

test('a catalogue error in the leg picker shows all four parts under their labels', async ({ page }) => {
  await page.route('**/api/catalogue/NIFTY/expiries', (r) => r.fulfill({ status: 404, json: PARTS }))
  await page.goto(`${REPLAY_URL}/strategy/builder`)
  // W-195: the picker is the left drawer; asking to add a leg opens it and its catalogue error is the first thing in it
  await page.getByTestId('no-legs-add').click()
  const err = page.getByTestId('picker-error')
  await expect(err).toBeVisible()
  await expect(err).toBeInViewport()
  await expect(err.getByTestId('picker-error-what')).toHaveText(PARTS.what_happened)
  await expect(err).toContainText(`What this means: ${PARTS.impact}`)
  await expect(err).toContainText(`What is blocked: ${PARTS.what_is_blocked}`)
  await expect(err).toContainText(`What to do next: ${PARTS.next_action}`)
})
