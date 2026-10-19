// W-119 core proof (REQ-024 AC-2/AC-8, REQ-026; ADR-008): Guided -> objective -> expiry -> cards -> Open in Builder,
// at 1280 and 390 px, against the real strategy-templates, planned-entry and outcome routes (APP_ENV=test +
// OUTCOME_REPLAY=1 serves the recorded frames). Runs in CI only. As in leg-picker.spec.ts the catalogue stays empty in
// ofo_test, so the two catalogue GETs are answered with the recorded NIFTY 13-Oct-2026 contracts, and the index level is
// answered as 22800 (ATM 22800, step 200 on these strikes: the catalogue's Cash Secured Put, SELL 22400 PE, fits).
// The card numbers are asserted against the outcome route's own answer for the card's legs, never hand-typed.
import { test, expect, type Page } from '@playwright/test'
import { useQuietLiveSocket } from './support/quiet-live'

useQuietLiveSocket()

const REPLAY_URL = process.env.REPLAY_URL || 'http://127.0.0.1:4175'
const c = (token: number, type: string, strike: string, symbol: string) => ({
  contract_id: token, exchange_segment: 'NSE_FO', exchange_token: token, instrument_type: type, expiry: '2026-10-13', strike,
  lot_size: 65, symbol,
})
const CONTRACTS = { underlying: 'NIFTY', contracts: [
  c(44595, 'PE', '22200.00', 'NIFTY26O1322200PE'), c(44604, 'PE', '22400.00', 'NIFTY26O1322400PE'),
  c(44624, 'CE', '22800.00', 'NIFTY26O1322800CE'), c(44632, 'CE', '23000.00', 'NIFTY26O1323000CE'),
] }

async function seed(page: Page) {
  await page.route('**/api/catalogue/NIFTY/expiries', (r) => r.fulfill({ json: { underlying: 'NIFTY', expiries: ['2026-10-13'] } }))
  await page.route('**/api/catalogue/NIFTY/contracts?expiry=2026-10-13', (r) => r.fulfill({ json: CONTRACTS }))
  await page.route('**/api/market/indices', (r) => r.fulfill({ json: { state: 'LIVE', answered_at: '2026-10-13T09:20:00+05:30',
    indices: [{ underlying: 'NIFTY', instrument_id: null, value: '22800.00', at: null, health: 'available' }] } }))
}

// The 1280 px and 390 px runs come from the config's desktop-1280 and mobile-390 projects.
{
  test('create strategy guided flow: cards carry the engine\'s numbers and open in the Builder', async ({ page, request }) => {
    await seed(page)
    await page.goto(`${REPLAY_URL}/strategies/create-strategy`)
    await expect(page.getByTestId('page-title')).toHaveText('Create Strategy')
    await page.getByTestId('path-guided').click()
    await expect(page.getByTestId('step-indicator')).toHaveText('Step 1 of 4')
    await expect(page.getByTestId('step-back')).toBeVisible()
    await page.locator('[data-testid="objective"][data-key="know"]').click()
    await page.getByTestId('pick-expiry').selectOption('2026-10-13')
    await page.getByTestId('show-strategies').click()
    const card = page.locator('[data-testid="strategy-card"][data-template-id="cash_secured_put"]')
    await expect(card.getByTestId('card-max-loss')).toBeVisible()

    const legs = JSON.parse((await card.getAttribute('data-legs')) || '[]')
    expect(legs.map((l: { instrument_id: string; action: string }) => [l.instrument_id, l.action])).toEqual([['NSE_FO:44604', 'SELL']])
    const answer = await (await request.post(`${REPLAY_URL}/api/strategies/outcome`, { data: { underlying: 'NIFTY', ux_level: 'guided',
      legs: legs.map((l: Record<string, unknown>) => ({ instrument_id: l.instrument_id, action: l.action, lots: l.lots,
        planned_entry: l.planned_entry, captured_at: l.captured_at })) } })).json()
    const s = answer.summary
    await expect(card.getByTestId('card-max-profit')).toHaveText(s.max_profit_unlimited ? 'Unlimited' : String(s.max_profit))
    await expect(card.getByTestId('card-max-loss')).toHaveText(s.max_loss_unlimited ? 'Unlimited' : String(s.max_loss))
    await expect(card.getByTestId('card-breakevens')).toHaveText(s.breakevens.join(', ') || '—')

    await card.getByTestId('open-in-builder').click()
    await expect(page).toHaveURL(/\/strategy\/builder\?/)
    await expect(page.getByTestId('leg-row')).toHaveCount(1)
  })
}
