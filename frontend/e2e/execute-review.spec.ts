// EXECUTE-REVIEW (S5; docs/design/screens-research-2026-10-19-part2.md A4): the Execute review's reading order and fit at
// 1280 and 390 px. The page, the saved legs, the catalogue and the market verdict come from the Execute replay API (CI);
// only the Execute POST is answered here with a two-BUY reply, because the seeded strategy holds ONE order and a second
// real Execute on it is refused while a plan is open (execute-screen.spec.ts spends that one). The real reply's own risk
// block is asserted there. Every figure below is a made-up server string; the expectations are those same strings.
import { test, expect } from '@playwright/test'
import { findClippedElements } from './clipping-check'

const EXECUTE_REPLAY_URL = process.env.EXECUTE_REPLAY_URL || ''

const BASKET = {
  url: 'https://kite.zerodha.com/connect/basket', api_key: 'replay_api_key',
  data: '[{"variety": "regular", "tradingsymbol": "NIFTY26O1923650CE", "exchange": "NFO", "transaction_type": "BUY", "order_type": "LIMIT", "product": "NRML", "price": 3.35, "quantity": 65, "readonly": true, "tag": "Q0001010"}]',
}
const order = (symbol: string, qty: number, price: string, tag: string) => ({
  exchange: 'NFO', tradingsymbol: symbol, transaction_type: 'BUY', order_type: 'LIMIT', product: 'NRML', variety: 'regular',
  quantity: qty, price, readonly: true, tag,
})
const TWO_BUYS = {
  plan_number: 2, tags: ['Q0001010', 'Q0001011'], basket: BASKET,
  orders: [order('NIFTY26O1923650CE', 65, '3.35', 'Q0001010'), order('NIFTY26O1924150PE', 75, '29.90', 'Q0001011')],
  cost: { net_premium: '-2460.25', charges: '310.00', charges_note: null, funds_available: '240000.00', margin_required: '110000.00',
    figures_read_at: '2026-10-16T15:07:20+05:30' },
  review: { max_loss: '5900.00', max_loss_unlimited: false, max_profit: '4100.00', max_profit_unlimited: false },
}

test.describe('Execute review reading order', () => {
  test.skip(!EXECUTE_REPLAY_URL, 'EXECUTE_REPLAY_URL is set only in CI, where the Execute replay API runs')

  test('sentence, margin + charges, max loss / profit, orders, ready; fits the viewport', async ({ page }) => {
    await page.routeWebSocket('**/api/strategies/live', (ws) => {
      ws.onMessage((message) => {
        const body = JSON.parse(String(message))
        ws.send(JSON.stringify({
          state: 'COMPUTED',
          legs: body.legs.map((l: { instrument_id: string, action: string, lots: number, planned_entry: string, captured_at: string }) => ({
            instrument_id: l.instrument_id, symbol: 'NIFTY26O1923650CE', action: l.action, instrument: 'CE', strike: '23650.00',
            expiry: '2026-10-19', lots: l.lots, lot_size: 65, quantity: 65, planned_entry: l.planned_entry,
            captured_at: l.captured_at, ltp: '3.35', iv: null, health: null, label: null,
          })),
        }))
      })
    })
    await page.route('**/api/strategies/1/execute', (route) => route.fulfill({ json: TWO_BUYS }))

    await page.goto(`${EXECUTE_REPLAY_URL}/strategy/1/execute`)
    await page.getByTestId('prepare-entry').click()

    await expect(page.getByTestId('execute-sentence')).toHaveText('You will place 2 orders now (2 buy, 0 sell); worst case loss ₹5,900.00.')
    const seen = await page.locator('[data-testid="execute-screen"] [data-testid]').evaluateAll((els) => els.map((e) => e.getAttribute('data-testid')))
    const at = (id: string) => seen.indexOf(id)
    expect(at('execute-sentence')).toBeGreaterThan(-1)
    for (const [a, b] of [['execute-sentence', 'margin-label'], ['margin-label', 'cost-charges'], ['cost-charges', 'execute-max-loss'],
      ['execute-max-loss', 'execute-orders'], ['execute-orders', 'execute-ready'], ['execute-ready', 'place-on-kite']]) {
      expect(at(a), `${a} before ${b}`).toBeLessThan(at(b))
    }
    await expect(page.getByTestId('margin-label')).toHaveText("planning estimate; Zerodha's figure is authoritative")
    await expect(page.getByTestId('cost-margin')).toHaveText('110000.00')
    await expect(page.getByTestId('cost-funds')).toHaveText('240000.00')
    await expect(page.getByTestId('execute-max-loss')).toHaveText('5900.00')
    await expect(page.getByTestId('execute-max-profit')).toHaveText('4100.00')
    await expect(page.getByTestId('order-seq')).toHaveText(['1', '2'])
    await expect(page.getByTestId('execute-ready')).toHaveText('Ready to execute: 2 orders')

    // the orders block is open on a desktop and starts collapsed on a phone; opening it shows the table
    const phone = (page.viewportSize()?.width ?? 1280) < 640
    await expect(page.getByTestId('execute-orders-block')).toHaveJSProperty('open', !phone)
    if (phone) await page.getByTestId('execute-orders-block').locator('summary').click()
    await expect(page.getByTestId('execute-orders')).toBeVisible()
    expect(await findClippedElements(page)).toEqual([])

    const button = await page.getByTestId('place-on-kite').boundingBox()
    expect(button?.height ?? 0).toBeGreaterThanOrEqual(44)
  })
})
