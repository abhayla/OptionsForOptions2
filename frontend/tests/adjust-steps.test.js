// GC-ADJ2 step 6 (REQ-163 AC-1..AC-3): the history section shows the server's rows and totals as given; the browser
// computes nothing. The reply below has the shape of GET /api/strategies/{id}/adjustment-history for scenario ADJ-13.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const calls = []
let reply
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (url) => { calls.push(url); return reply() } } }
})

import AdjustSteps from '@/components/strategy/AdjustSteps.vue'

const order = (side, text, price) => ({ side, contract_text: text, quantity: 130, price, price_text: price, kind: 'open' })
const row = (over) => ({
  step: 'entry', number: null, at: '2026-10-28T08:00:00+05:30', orders: [order('BUY', 'NIFTY 22400 PE', '10.45')],
  cash: '1202.50', cash_text: '+1,202.50', booked: '0.00', booked_text: '0.00', booked_pending: null, charges: null,
  rule_id: null, why_text: 'Your own change', fill: 'paper', fill_text: 'Paper - not sent to Zerodha', ...over,
})
const totals = (over = {}) => ({
  pnl: '-2015.00', pnl_text: '-2,015.00', booked: '962.00', booked_text: '+962.00', open_pnl: '-2977.00',
  open_pnl_text: '-2,977.00', credit: '5141.50', credit_text: '+5,141.50', premium_left: '7156.50',
  premium_left_text: '+7,156.50', prices_reason: null, prices_reason_text: null, adjustments_used: 1, adjustments_max: 2,
  max_reason: null, max_reason_text: null, charges: '80.00', charges_text: 'Charges 80.00', charges_reason: null,
  charges_reason_text: null, ...over,
})
const body = (t = totals(), rows = [row(), row({ step: 'adjustment', number: 1, booked: '962.00', booked_text: '+962.00', cash_text: '-240.50' })]) =>
  ({ strategy_id: 7, fill_column_text: 'Zerodha', rows, totals: t })
const tid = (w, id) => w.get(`[data-testid="${id}"]`)

async function open(b) {
  reply = () => Promise.resolve({ data: b })
  const w = mount(AdjustSteps, { props: { strategyId: 7 } })
  const d = tid(w, 'adjust-steps')
  d.element.open = true
  await d.trigger('toggle')
  await flushPromises()
  return w
}

beforeEach(() => { calls.length = 0 })

describe('AdjustSteps', () => {
  it('reads nothing until opened, then once from the history route', async () => {
    reply = () => Promise.resolve({ data: body() })
    const w = mount(AdjustSteps, { props: { strategyId: 7 } })
    await flushPromises()
    expect(calls).toEqual([])
    expect(tid(w, 'adjust-steps').text()).toContain('Adjustment history')
    await open(body())
    expect(calls).toEqual(['/strategies/7/adjustment-history'])
  })

  it('AC-1: rows with step, orders, cash, booked, why and the paper label, in the mockup columns', async () => {
    const w = await open(body())
    expect(w.findAll('th').map((x) => x.text())).toEqual(['When', 'Step', 'Orders', 'Cash', 'Booked', 'Why', 'Zerodha'])
    const rows = w.findAll('[data-testid="steps-row"]')
    expect(rows).toHaveLength(2)
    expect(rows.map((r) => r.get('[data-testid="steps-step"]').text())).toEqual(['Entry', 'Adjustment 1'])
    expect(rows[1].get('[data-testid="steps-booked"]').text()).toBe('+962.00')
    expect(rows[1].get('[data-testid="steps-cash"]').text()).toBe('-240.50')
    expect(rows[0].get('[data-testid="steps-order"]').text()).toBe('B NIFTY 22400 PE x 130 @ 10.45')
    expect(rows.map((r) => r.get('[data-testid="steps-why"]').text())).toEqual(['Your own change', 'Your own change'])
    expect(rows.map((r) => r.get('[data-testid="steps-fill"]').text())).toEqual(['Paper - not sent to Zerodha', 'Paper - not sent to Zerodha'])
  })

  it('AC-2: totals tiles are the server texts as given', async () => {
    const w = await open(body())
    expect(tid(w, 'steps-total-pnl').text()).toContain('-2,015.00')
    expect(tid(w, 'steps-total-booked').text()).toContain('+962.00')
    expect(tid(w, 'steps-total-open').text()).toContain('-2,977.00')
    expect(tid(w, 'steps-total-credit').text()).toContain('+5,141.50')
    expect(tid(w, 'steps-total-left').text()).toContain('+7,156.50')
    expect(tid(w, 'steps-total-used').text()).toContain('1 of 2')
    expect(tid(w, 'steps-total-charges').text()).toContain('Charges 80.00')
  })

  it('AC-3: a pending row shows pending and its fill state', async () => {
    const pending = row({ step: 'adjustment', number: 1, booked: null, booked_text: null, booked_pending: 'pending', fill: 'unconfirmed', fill_text: 'Not yet confirmed by Zerodha' })
    const w = await open(body(totals(), [row(), pending]))
    const r = w.findAll('[data-testid="steps-row"]')[1]
    expect(r.get('[data-testid="steps-booked"]').text()).toBe('pending')
    expect(r.get('[data-testid="steps-fill"]').text()).toBe('Not yet confirmed by Zerodha')
  })

  it('missing prices and no plan maximum: a dash with the server reason, booked still shown', async () => {
    const t = totals({ pnl: null, pnl_text: null, open_pnl: null, open_pnl_text: null, premium_left: null, premium_left_text: null,
      prices_reason: 'prices_not_live', prices_reason_text: 'Prices are not live.', open_reason: 'prices',
      open_reason_text: 'Prices are not live.', premium_reason: 'net_long_premium', premium_reason_text: 'No premium to earn (net long premium).', adjustments_max: null,
      max_reason: 'no_plan_max', max_reason_text: 'No plan maximum is set for this strategy.' })
    const w = await open(body(t))
    expect(tid(w, 'steps-total-open').text()).toContain('-')
    expect(tid(w, 'steps-reason-open').text()).toBe('Prices are not live.')
    expect(tid(w, 'steps-reason-pnl').text()).toBe('Prices are not live.')
    expect(tid(w, 'steps-reason-left').text()).toBe('No premium to earn (net long premium).')
    expect(tid(w, 'steps-total-booked').text()).toContain('+962.00')
    expect(tid(w, 'steps-total-used').text()).toContain('1 of -')
    expect(tid(w, 'steps-reason-used').text()).toBe('No plan maximum is set for this strategy.')
  })

  it('the table scrolls in its own container (phone width)', async () => {
    const w = await open(body())
    expect(tid(w, 'steps-scroll').classes()).toContain('overflow-x-auto')
  })

  it('a failed read shows the reason and no figure', async () => {
    reply = () => Promise.reject({ parts: { what_happened: 'Not available.' } })
    const w = mount(AdjustSteps, { props: { strategyId: 7 } })
    const d = tid(w, 'adjust-steps')
    d.element.open = true
    await d.trigger('toggle')
    await flushPromises()
    expect(tid(w, 'steps-error').text()).toBe('Not available.')
    expect(w.find('[data-testid="steps-totals"]').exists()).toBe(false)
  })
})
