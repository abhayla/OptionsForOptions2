// W-120 CORE PROOF (REQ-030 AC-1/AC-2/AC-9; ADR-002): on the Option Chain the user ticks four contracts, chooses Buy or
// Sell on each, presses "Add Selected (4)", and the Strategy Builder opens with exactly those four legs priced by the
// real outcome route on the recorded frames. Runs in CI only (the app-tests job), like leg-picker.spec.ts.
//   - REPLAY_URL: the API in APP_ENV=test + OUTCOME_REPLAY=1. The planned entries the chain cells carry are READ from its
//     real planned-entry route (the recorded NIFTY 13-Oct-2026 tokens 44595/44604/44624/44632 are in the recorded frames);
//     the catalogue stays empty in ofo_test, so the chain socket's rows are assembled here from those real ids and prices
//     and pushed through the page's own socket path (the chain socket needs the stored catalogue, which CI does not fill).
//   - The Builder, the outcome route and the draft link are all real.
import { test, expect, type Page } from '@playwright/test'
import { useQuietLiveSocket } from './support/quiet-live'

useQuietLiveSocket() // the Builder's own live socket stays silent: this proves the REST outcome path

const REPLAY_URL = process.env.REPLAY_URL || 'http://127.0.0.1:4175'
const EXPIRY = '2026-10-13'
const CONTRACTS = [
  { token: 44595, type: 'PE', strike: '22200.00' },
  { token: 44604, type: 'PE', strike: '22400.00' },
  { token: 44624, type: 'CE', strike: '22800.00' },
  { token: 44632, type: 'CE', strike: '23000.00' },
]
const idOf = (token: number) => `NSE_FO:${token}`

async function realCells(page: Page) {
  const res = await page.request.post(`${REPLAY_URL}/api/strategies/planned-entry`, {
    data: { underlying: 'NIFTY', instrument_ids: CONTRACTS.map((c) => idOf(c.token)) },
  })
  expect(res.ok()).toBeTruthy()
  const entries: any[] = (await res.json()).entries
  const cells = new Map<number, any>()
  for (const e of entries) {
    expect(e.planned_entry).not.toBeNull() // the recorded frames price every one of the four
    cells.set(e.exchange_token, {
      instrument_id: idOf(e.exchange_token), ltp: e.planned_entry, bid: null, ask: null, change: null, oi: null, oi_change: null,
      volume: null, health: 'available', at: e.captured_at, permitted: true, unavailable_reason: null,
    })
  }
  return cells
}

async function serveChain(page: Page, cells: Map<number, any>) {
  await page.route('**/api/catalogue/NIFTY/expiries', (r) => r.fulfill({ json: { underlying: 'NIFTY', expiries: [EXPIRY] } }))
  await page.route('**/api/market/chain?*', (r) => r.abort())
  const strikes = [...new Set(CONTRACTS.map((c) => c.strike))].sort()
  const rows = strikes.map((strike) => {
    const side = (type: string) => {
      const c = CONTRACTS.find((x) => x.strike === strike && x.type === type)
      return c ? cells.get(c.token) : null
    }
    return { strike, ce: side('CE'), pe: side('PE') }
  })
  await page.routeWebSocket('**/api/market/chain/live', (ws) => {
    ws.onMessage(() => {
      ws.send(JSON.stringify({
        state: 'LIVE', underlying: 'NIFTY', expiry: EXPIRY, spot: '22600.00', spot_at: [...cells.values()][0].at, spot_health: 'available',
        atm_strike: '22400.00', rows_missing: null, rows, answered_at: [...cells.values()][0].at,
      }))
    })
  })
}

for (const [name, size] of [
  ['desktop', { width: 1280, height: 800 }],
  ['mobile 390', { width: 390, height: 844 }],
] as const) {
  test.describe(name, () => {
    test.use({ viewport: size })

    test('four ticked contracts with explicit Buy/Sell open the Builder with exactly those four legs', async ({ page }, info) => {
      const cells = await realCells(page)
      await serveChain(page, cells)
      await page.goto(`${REPLAY_URL}/market/option-chain`)
      await expect(page.getByTestId('chain-row')).toHaveCount(4)

      const pick = async (strike: string, side: 'ce' | 'pe', action: 'buy' | 'sell') => {
        const row = page.getByTestId('chain-row').filter({ has: page.getByTestId('strike').getByText(strike, { exact: true }) })
        await row.getByTestId(`select-${side}`).check()
        await row.getByTestId(`${action}-${side}`).click()
      }
      await pick('23000', 'ce', 'buy')
      await pick('22800', 'ce', 'sell')
      await pick('22400', 'pe', 'buy')
      await pick('22200', 'pe', 'sell')

      const add = page.getByTestId('add-selected')
      await expect(add).toHaveText('Add Selected (4)')
      await page.screenshot({ path: `screenshots/chain-selection-${info.project.name}.png`, fullPage: true })
      await add.click()

      await expect(page).toHaveURL(/\/strategies\/strategy-builder/)
      await expect(page.getByTestId('page-title')).toHaveText('Strategy Builder')
      await expect(page.getByTestId('leg-row')).toHaveCount(4)
      await expect(page.getByTestId('strategy-builder')).toHaveAttribute('data-state', /computed|stale/)
      const draft = JSON.parse(new URL(page.url()).searchParams.get('draft') as string)
      expect(draft.legs.map((l: any) => [l.instrument_id, l.action, l.lots, l.planned_entry])).toEqual([
        [idOf(44632), 'BUY', 1, cells.get(44632).ltp],
        [idOf(44624), 'SELL', 1, cells.get(44624).ltp],
        [idOf(44604), 'BUY', 1, cells.get(44604).ltp],
        [idOf(44595), 'SELL', 1, cells.get(44595).ltp],
      ])
    })
  })
}
