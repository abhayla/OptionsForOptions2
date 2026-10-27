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
// jsdom has no canvas; the chart's line colours are tested through pointSigns / segmentColour (GC-BM F-8)
vi.mock('chart.js/auto', () => ({ default: class { destroy() {} } }))
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import { pointSigns, segmentColour } from '@/lib/payoffRegions'
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

describe('item 4: the payoff line is red only over the loss regions, never across the 0.00 plateau (ADR-072)', () => {
  const COLOURS = { profit: 'green', loss: 'red', flat: 'grey' }
  const segments = (points) => {
    const c = segmentColour(pointSigns(points), COLOURS)
    return points.slice(1).map((_, i) => c({ p0DataIndex: i, p1DataIndex: i + 1, chart: null }))
  }
  it('the real condor payoff: loss segments red, the 0.00 plateau grey, no green anywhere', () => {
    const pnl = real.payoff.points.map((p) => p.pnl)
    const seg = segments(real.payoff.points)
    expect(seg).not.toContain('green') // a condor with these quotes has no positive point
    const plateau = seg.map((s, i) => (pnl[i] === '0.00' && pnl[i + 1] === '0.00' ? i : -1)).filter((i) => i >= 0)
    expect(plateau.length).toBeGreaterThan(0)
    for (const i of plateau) expect(seg[i]).toBe('grey') // the plateau between the two loss regions is not on the Loss line
    seg.forEach((s, i) => { if (pnl[i].startsWith('-') || pnl[i + 1].startsWith('-')) expect(s).toBe('red') })
  })
  it('a buy-call payoff: red over the flat loss part up to the break-even point, green from the break-even on', () => {
    const pts = ['-65.00', '-65.00', '0.00', '6435.00', '12935.00'].map((pnl, i) => ({ level: String(i), pnl }))
    expect(segments(pts)).toEqual(['red', 'red', 'green', 'green'])
  })
})
