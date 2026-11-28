// GC-ICLIVE-F F4, round 1 (owner's screen check 25 Nov, head 5d9b53ca): D-18 (each panel's leg price carries its own quote
// time: the tracking panel and the Positions Paper row; Escape closes the depth popover) and D-44 (the Stops form and list sit
// side by side from lg up). jsdom has no layout, so the layout is tested as class names and structure.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

const calls = []
let answers = {}
import { legacy } from './_paperList'
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url, body) => {
    calls.push([method, url, body])
    const a = answers[`${method} ${url}`] ?? legacy(answers, method, url)
    return a ? a() : Promise.reject({ message: 'no answer', parts: null, status: null })
  }
  return { ...actual, default: { get: reply('GET'), post: reply('POST'), delete: reply('DELETE') } }
})

import { withPriceTexts } from './_priceTexts'
import TrackingPanel from '@/components/strategy/TrackingPanel.vue'
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'
import PaperStops from '@/components/strategy/PaperStops.vue'
import DepthPopup from '@/components/strategy/DepthPopup.vue'
import { QUOTE_TIME_UNAVAILABLE_TEXT } from '@/lib/sharedStateText'

const t = (w, id) => w.get(`[data-testid="${id}"]`)
const ok = (data) => () => Promise.resolve({ data })
beforeEach(() => { calls.length = 0; answers = {} })

const trackLegs = withPriceTexts([
  { instrument_id: 'NSE_FO:44624', action: 'SELL', instrument: 'CE', strike: '26000.00', entry_price: '39.15', current_price: '45.15', price_state: 'live',
    price_at: '2026-11-25T15:09:28+05:30', expiry: '2026-12-01', quantity: 65, exit_price: null },
  { instrument_id: 'NSE_FO:44604', action: 'SELL', instrument: 'PE', strike: '25400.00', entry_price: '82.75', current_price: '80.00', price_state: 'live',
    price_at: null, expiry: '2026-12-01', quantity: 65, exit_price: null },
  { instrument_id: 'NSE_FO:44605', action: 'BUY', instrument: 'PE', strike: '25300.00', entry_price: '10.00', current_price: null, price_state: 'stale',
    price_at: '2026-11-25T15:09:00+05:30', expiry: '2026-12-01', quantity: 65, exit_price: null },
])
const trackBody = { strategy_id: 7, state: 'LIVE', paper_pnl: '195.00', paper_pnl_text: '+195.00', as_of: null, legs: trackLegs, detections: [] }

describe('D-18: the tracking panel prints each leg its own quote time beside its price', () => {
  it('a live leg shows its own time, a live leg with none says "time not available", a leg with no price shows none', async () => {
    answers['GET /strategies/7/tracking'] = ok(trackBody)
    const w = mount(TrackingPanel, { props: { savedId: 7, legs: [] } })
    await flushPromises()
    const rows = w.findAll('[data-testid="tracking-leg"]')
    expect(rows[0].get('[data-testid="tracking-leg-ltp"]').text()).toBe('45.15')
    expect(rows[0].get('[data-testid="tracking-leg-quote-at"]').text()).toBe('15:09:28')
    expect(rows[1].get('[data-testid="tracking-leg-quote-at"]').text()).toBe(QUOTE_TIME_UNAVAILABLE_TEXT)
    expect(QUOTE_TIME_UNAVAILABLE_TEXT).toBe('time not available')
    expect(rows[2].find('[data-testid="tracking-leg-quote-at"]').exists()).toBe(false)
  })
})

const pleg = (i, over = {}) => withPriceTexts({
  leg_index: i, instrument_id: String(5000 + i), action: i % 2 ? 'SELL' : 'BUY', instrument: i < 2 ? 'PE' : 'CE',
  strike: `${22300 + i * 100}.00`, expiry: '2026-11-03', quantity: 65, entry_price: '114.25', entry_at: '2026-10-28T05:03:09Z',
  current_price: '113.60', price_state: 'live', price_at: '2026-11-25T15:09:28+05:30', exit_price: null, exited_at: null, ...over,
})
const item = (legs) => withPriceTexts({ strategy_id: 48, name: '"GCTP IC"', underlying: 'NIFTY', started_at: '2026-10-28T05:03:10Z', state: 'LIVE',
  pause_reason: null, as_of: null, total: '71.50', booked: '0.00', unbooked: '71.50', legs })
async function openPaper(legs) {
  answers['GET /tracking'] = ok({ strategies: [item(legs)], answered_at: '2026-11-25T09:40:00Z' })
  answers['GET /paper/strategies/48/triggers'] = ok({ triggers: [] })
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }, { path: '/strategy/builder', component: { template: '<div/>' } }] })
  router.push('/')
  await router.isReady()
  const w = mount(PaperStrategies, { global: { plugins: [router] } })
  await flushPromises()
  return w
}

describe('D-18: the Positions > Paper row prints the quote time of its price', () => {
  it('each open row with a price shows that leg\'s own time (with its date when not today, F3 MUST); none sent says "time not available"', async () => {
    const w = await openPaper([pleg(0), pleg(1, { price_at: null })])
    const at = w.findAll('[data-testid="paper-ltp-at"]').map((x) => x.text())
    expect(at).toEqual(['25 Nov 2026, 15:09:28 IST', QUOTE_TIME_UNAVAILABLE_TEXT])
  })
  it('a row with no live price shows no time', async () => {
    const w = await openPaper([pleg(0, { price_state: 'stale', current_price: null })])
    expect(w.find('[data-testid="paper-ltp-at"]').exists()).toBe(false)
  })
})

describe('D-18: Escape closes the depth popover', () => {
  it('Escape pressed anywhere on the page emits close, and the listener is removed on unmount', async () => {
    answers['GET /leg-picker/depth?instrument_id=NSE_FO%3A44002'] = ok({ state: 'NOT_AVAILABLE', reason: 'NOT_STREAMING', bids: [], asks: [] })
    const w = mount(DepthPopup, { props: { instrumentId: 'NSE_FO:44002', title: 'x' }, attachTo: document.body })
    await flushPromises()
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    const events = w.emitted('close')
    expect(events).toHaveLength(1)
    w.unmount()
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    expect(events).toHaveLength(1)
  })
})

describe('D-44: the Stops form and the list sit side by side from lg up', () => {
  it('a two-column grid at lg, the form column first and the list column second', async () => {
    answers['GET /paper/strategies/9/triggers'] = ok({ triggers: [] })
    const w = mount(PaperStops, { props: { strategyId: 9, underlying: 'NIFTY', legs: [{ index: 0, label: 'NIFTY 3 Nov 22300 PE', contractId: 5000 }] } })
    await flushPromises()
    const grid = t(w, 'stops-columns')
    expect(grid.classes()).toEqual(expect.arrayContaining(['grid', 'lg:grid-cols-2']))
    expect(grid.classes()).not.toContain('grid-cols-2')
    const [first, second] = Array.from(grid.element.children)
    expect(first.getAttribute('data-testid')).toBe('stops-form')
    expect(second.getAttribute('data-testid')).toBe('stops-list')
    expect(first.querySelector('[data-testid="conditional-exit"]')).not.toBeNull()
    expect(first.querySelector('[data-testid="leg-stops"]')).not.toBeNull()
    expect(second.querySelector('[data-testid="triggers"]')).not.toBeNull()
    expect(first.querySelector('[data-testid="triggers"]')).toBeNull()
  })
})
