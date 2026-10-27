// Issue 297 items 1 and 4 (REQ-067 AC-4, ADR-072, ADR-086). The answer is the real push recorded from the live
// websocket on 2026-10-16 (iron condor, 4 legs with no live quote; ofo-kite-ticks/2026-10-16/outcome).
import { describe, expect, it, vi } from 'vitest'
import { expiryWithDays, strikeLabel } from '@/lib/displayFormat'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

let apiAnswer = null
// the read control's answer: the legs as sent, with the strike, type and expiry the server names (REQ-076 AC-8)
let readReply = () => null
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: () => Promise.reject(new Error('unmocked get')), post: (url, body) => Promise.resolve({ data: url === '/strategies/leg-edit' ? readReply(body) : apiAnswer }) } }
})
// jsdom has no canvas; the chart's lines are tested through payoffRegions
vi.mock('chart.js/auto', () => ({ default: class { destroy() {} } }))
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import { payoffRegions } from '@/lib/payoffRegions'
import real from './fixtures/outcome-condor-no-quote.json'

readReply = (body) => ({ legs: body.legs.map((l) => { const r = real.legs.find((x) => x.instrument_id === l.instrument_id)
  return { ...l, instrument: r.instrument, strike: r.strike, expiry: r.expiry, price_source: 'captured', hedge: false, block: null } }),
  shape: null, shape_name: null, outcome: null })
const DRAFT = { underlying: 'NIFTY', legs: real.legs.map((l) => ({ instrument_id: l.instrument_id, action: l.action, lots: l.lots,
  planned_entry: l.planned_entry, captured_at: l.captured_at })) }

async function openPage() {
  apiAnswer = real
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await router.push({ path: '/strategy/builder', query: { draft: JSON.stringify(DRAFT) } })
  await router.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [router] } })
  await flushPromises()
  return w
}
const texts = (w, id) => w.findAll(`[data-testid="${id}"]`).map((e) => e.text())

describe('item 1: a leg opened from a link is named once the catalogue answer is in', () => {
  it('the one leg list rows name each contract (expiry, strike, type), never "Contract details not available"', async () => {
    // Fix round 3: the picker's own list (with its "leg-name" text) is gone from the Builder (one list, REQ-076 AC-1); the
    // contract is now named by the row's own parts. The mock answers every POST with the recorded outcome, so the read
    // control's reply is made leg-edit shaped here (the recorded legs, as the server names them).
    const w = await openPage()
    const rows = w.findAll('[data-testid="leg-row"]')
    expect(rows).toHaveLength(4)
    expect(rows.map((r) => [r.find('[data-testid="leg-expiry"]').text(), r.find('[data-testid="leg-strike"]').text(), r.find('[data-testid="leg-type"]').text()]))
      .toEqual(real.legs.map((l) => [expiryWithDays(l.expiry, l.days_to_expiry), strikeLabel(l.strike), l.instrument]))
    expect(w.text()).not.toContain('Contract details not available')
    w.unmount()
  })
  it('each leg notice is printed once, under its contract name, with no raw trading symbol', async () => {
    const w = await openPage()
    expect(texts(w, 'stale-leg')).toEqual(['NIFTY 19 Oct 22800 PE: no live quote', 'NIFTY 19 Oct 22950 PE: no live quote',
      'NIFTY 19 Oct 23250 CE: no live quote', 'NIFTY 19 Oct 23400 CE: no live quote'])
    w.unmount()
  })
})

describe('item 4: the payoff chart draws each line only over its own region (ADR-072)', () => {
  it('the real condor payoff: Loss is drawn over the loss regions, not across the 0.00 plateau; Profit nowhere', () => {
    const pnl = real.payoff.points.map((p) => p.pnl)
    const { loss, profit } = payoffRegions(real.payoff.points)
    expect(profit.some(Boolean)).toBe(false) // a condor with these quotes has no positive point
    const interior = pnl.map((v, i) => (v === '0.00' && pnl[i - 1] === '0.00' && pnl[i + 1] === '0.00' ? i : -1)).filter((i) => i >= 0)
    expect(interior.length).toBeGreaterThan(0)
    for (const i of interior) expect(loss[i]).toBe(false) // the plateau between the two loss regions is not on the Loss line
    pnl.forEach((v, i) => { if (v.startsWith('-')) expect(loss[i]).toBe(true) })
  })
  it('a buy-call payoff: Loss over the flat loss part and the break-even point, Profit from the break-even on', () => {
    const pts = ['-65.00', '-65.00', '0.00', '6435.00', '12935.00'].map((pnl, i) => ({ level: String(i), pnl }))
    expect(payoffRegions(pts)).toEqual({ loss: [true, true, true, false, false], profit: [false, false, true, true, true] })
  })
})
