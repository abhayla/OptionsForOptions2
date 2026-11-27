// B6 item 2 (#730; ADR-328 (4), D-05): the "Review and add" dialog of other edits is built from the net on screen. When the book read (the
// page's real poll, not a set flag) finds other open contracts than the shown ones, the dialog closes and its Confirm posts nothing, with the
// sentence the Exit handlers already use; an unchanged trade posts as before. Spec basis: ADR-328 (4), ADR-008.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'
import { netLegsFromBook } from '@/lib/paperDrafts'
import { TRACKING_REFRESH_MS } from '@/lib/tracking'
import { pausedText } from '@/lib/priceState'
import REAL from './fixtures/paper-book-63.json'
import { withPriceTexts } from './_priceTexts'
import { legacy } from './_paperList'

const NOT_LIVE = 'Prices are not live; try again when they update'
const CHANGED = 'This trade changed elsewhere. Reload to see the current legs.'
const DASH = '—'

const calls = []
let answers = {}
const spy = vi.hoisted(() => ({ addToPaper: vi.fn() }))
vi.mock('@/lib/tracking', async (importActual) => {
  const actual = await importActual()
  return { ...actual, addToPaper: (...a) => { spy.addToPaper(...a); return actual.addToPaper(...a) } }
})
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    const a = answers[`${method} ${url}`] ?? legacy(answers, method, url)
    if (a === undefined || a === null) return Promise.reject(new Error(`unmocked ${method} ${url}`))
    return typeof a === 'function' ? a(body) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u, b) => respond('POST', u, b), put: (u, b) => respond('PUT', u, b), patch: (u, b) => respond('PATCH', u, b) } }
})

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const all = (w, id) => w.findAll(`[data-testid="${id}"]`)
const texts = (w, id) => all(w, id).map((x) => x.text())
const CONTRACTS = REAL.positions.map((p) => ({ contract_id: p.contract_id, exchange_segment: 'NSE_FO', exchange_token: p.contract_id,
  instrument_type: p.instrument, expiry: p.expiry, strike: p.strike, lot_size: 65, symbol: `NIFTY${p.strike}${p.instrument}` }))
const BOOK = { ...REAL, strategy_id: 86, name: '"IC"' }
const FAIL_503 = () => Promise.reject({ status: 503, message: 'x', parts: null })
const orderPosts = () => calls.filter((c) => c.method === 'POST' && c.url === '/paper/strategies/86/orders')
const mounted = []

const router = () => createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }, { path: '/positions/current-positions', component: { template: '<p />' } }] })
async function builder() {
  calls.length = 0
  answers = {
    'GET /strategies': { strategies: [] },
    'POST /paper/strategies/86/orders': BOOK,
    'GET /paper/strategies/86': BOOK,
    'GET /catalogue/NIFTY/contracts?expiry=2026-11-03': { underlying: 'NIFTY', contracts: CONTRACTS },
    'POST /strategies/outcome': () => new Promise(() => {}),
    'POST /strategies/leg-edit': () => new Promise(() => {}),
  }
  const r = router()
  await r.push('/strategy/builder?strategy=86')
  await r.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [r], stubs: { PayoffChart: true } }, attachTo: document.body })
  mounted.push(w)
  await flushPromises()
  return w
}
const tick = async () => { await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS); await flushPromises() }
// a "Review and add" dialog of an edit that only ADDS (lots of the first leg set to 9): not an Exit dialog
async function reviewAdd(w) {
  const net = w.vm.$.setupState.paper.net
  w.vm.$.setupState.setLegs(net.map((l, i) => (i === 0 ? { ...l, lots: 9 } : { ...l })))
  await flushPromises()
  await t(w, 'paper-review').trigger('click')
  await flushPromises()
  expect(t(w, 'paper-confirm').exists()).toBe(true)
}

beforeEach(() => { vi.useFakeTimers(); spy.addToPaper.mockClear() })
afterEach(() => {
  vi.useRealTimers()
  while (mounted.length) mounted.pop().unmount()
  document.body.innerHTML = ''
})

const CHANGED_BOOK = { ...BOOK, positions: BOOK.positions.map((p, i) => (i === 0 ? { ...p, net_quantity: p.net_quantity * 2 } : p)) }

describe('#730: a Review and add dialog is refused once the book read finds the trade changed in another tab', () => {
  it('changed after the dialog opened: it closes, Confirm posts nothing (api POST not called), the existing sentence is shown', async () => {
    const w = await builder()
    await reviewAdd(w)
    const rows = w.vm.$.setupState.paperRows
    answers['GET /paper/strategies/86'] = CHANGED_BOOK
    await tick()
    expect(t(w, 'paper-confirm').exists()).toBe(false)
    await w.vm.$.setupState.confirmPending(rows)
    await flushPromises()
    expect(orderPosts()).toHaveLength(0)
    expect(spy.addToPaper).not.toHaveBeenCalled()
    expect(t(w, 'paper-exit-reason').text()).toBe(CHANGED)
    expect(t(w, 'book-contracts-changed').exists()).toBe(true)
  })
  it('changed before the click: the Review and add button is refused too, no dialog opens, nothing is posted', async () => {
    const w = await builder()
    const net = w.vm.$.setupState.paper.net
    w.vm.$.setupState.setLegs(net.map((l, i) => (i === 0 ? { ...l, lots: 9 } : { ...l })))
    await flushPromises()
    answers['GET /paper/strategies/86'] = CHANGED_BOOK
    await tick()
    w.vm.$.setupState.reviewPending()
    await flushPromises()
    expect(t(w, 'paper-confirm').exists()).toBe(false)
    expect(orderPosts()).toHaveLength(0)
    expect(t(w, 'paper-exit-reason').text()).toBe(CHANGED)
  })
  it('unchanged contracts: the dialog stays open through a poll and Confirm posts the order as today', async () => {
    const w = await builder()
    await reviewAdd(w)
    await tick()
    expect(t(w, 'paper-confirm').exists()).toBe(true)
    if (t(w, 'paper-not-live-ack').exists()) await t(w, 'paper-not-live-ack').setValue(true) // ADR-330 (28): this page's prices are not live (no outcome reply)
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(orderPosts()).toHaveLength(1)
    expect(spy.addToPaper).toHaveBeenCalledTimes(1)
  })
})
