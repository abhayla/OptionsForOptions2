// Lane R N-04 / N-05 (owner screen findings 26 Nov 2026), on top of D-05 builder half + ADR-328 (4): the builder's Exit buttons obey the same rule as Positions.
// Spec basis: REQ-109 AC-4 (Exit all and a per-leg exit share one confirm list), AC-5 / ADR-322 (3) (no exit from old prices:
// "Prices are not live; try again when they update"), ADR-328 (4) (an Exit built from an old net is refused: "This trade
// changed elsewhere. Reload to see the current legs."). The REAL page, the REAL book fixture (strategy 63 as answered live).
// States per rule: stated (good read), failed (503 on the book read), changed (the contracts differ from the shown ones), both,
// then the next good read / reload (ambiguous -> stated). A "Review and add" dialog of other edits is not an Exit dialog.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import { TRACKING_REFRESH_MS } from '@/lib/tracking'
import REAL from './fixtures/paper-book-63.json'
import { legacy } from './_paperList'

const NOT_LIVE = 'Prices are not live; try again when they update'
const CHANGED = 'This trade changed elsewhere. Reload to see the current legs.'

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
const CONTRACTS = REAL.positions.map((p) => ({ contract_id: p.contract_id, exchange_segment: 'NSE_FO', exchange_token: p.contract_id,
  instrument_type: p.instrument, expiry: p.expiry, strike: p.strike, lot_size: 65, symbol: `NIFTY${p.strike}${p.instrument}` }))
const BOOK = { ...REAL, strategy_id: 86, name: '"IC"' }
const FAIL_503 = () => Promise.reject({ status: 503, message: 'x', parts: null })
const orderPosts = () => calls.filter((c) => c.method === 'POST' && c.url.startsWith('/paper/') && c.url.endsWith('/orders'))
const mounted = []
const router = () => createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
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
const failRead = async () => { answers['GET /paper/strategies/86'] = FAIL_503; await tick() }
const setMark = async (w, v) => { w.vm.$.setupState.paperContractsChanged = v; await flushPromises() }
const S = (w) => w.vm.$.setupState
const snap = (w) => JSON.parse(JSON.stringify(S(w).legs))

beforeEach(() => { vi.useFakeTimers() })
afterEach(() => {
  vi.useRealTimers()
  while (mounted.length) mounted.pop().unmount()
  document.body.innerHTML = ''
})

describe('N-04 / N-05: an Exit dialog the PAGE closes drops its staged exits, like the user\'s Cancel', () => {
  it('(a) per-leg Exit clicked, then the book read fails: dialog closed, pending orders and legs as before the click', async () => {
    const w = await builder()
    const legsBefore = snap(w)
    const pendingBefore = S(w).pendingOrders.length
    await w.findAll('[data-testid="net-exit"]')[1].trigger('click')
    await flushPromises()
    expect(t(w, 'paper-confirm').exists()).toBe(true)
    expect(S(w).pendingOrders.length).toBe(pendingBefore + 1)
    await failRead()
    expect(t(w, 'paper-confirm').exists()).toBe(false)
    expect(S(w).pendingOrders.length).toBe(pendingBefore)
    expect(snap(w)).toEqual(legsBefore)
    expect(t(w, 'paper-review').exists()).toBe(false)
    expect(orderPosts()).toHaveLength(0)
  })

  it('(b) Exit all clicked, then the contracts changed elsewhere: dialog closed, 0 staged exits, legs back (no "No legs yet")', async () => {
    const w = await builder()
    const legsBefore = snap(w)
    await t(w, 'paper-exit-all').trigger('click')
    await flushPromises()
    expect(S(w).pendingOrders.length).toBe(4)
    await setMark(w, true)
    expect(t(w, 'paper-confirm').exists()).toBe(false)
    expect(S(w).pendingOrders.length).toBe(0)
    expect(snap(w)).toEqual(legsBefore)
    expect(t(w, 'paper-pending-count').text()).toBe('0 pending changes')
    expect(orderPosts()).toHaveLength(0)
  })

  it('(b2) Confirm arriving in the same tick as the block: nothing posted, staged exits dropped', async () => {
    const w = await builder()
    await t(w, 'paper-exit-all').trigger('click')
    await flushPromises()
    const rows = S(w).paperRows
    S(w).paperContractsChanged = true
    await S(w).confirmPending(rows)
    await flushPromises()
    expect(orderPosts()).toHaveLength(0)
    expect(S(w).pendingOrders.length).toBe(0)
  })

  it('(c) failed read: "Review and add" of an add-only edit has the disabled attribute and a click posts nothing', async () => {
    const w = await builder()
    S(w).setLegs(S(w).paper.net.map((l, i) => (i === 0 ? { ...l, lots: 9 } : { ...l })))
    await flushPromises()
    expect(t(w, 'paper-review').attributes('disabled')).toBeUndefined()
    await failRead()
    expect(t(w, 'paper-review').attributes('disabled')).toBeDefined()
    await t(w, 'paper-review').trigger('click')
    await flushPromises()
    expect(t(w, 'paper-confirm').exists()).toBe(false)
    expect(orderPosts()).toHaveLength(0)
    expect(t(w, 'paper-exit-reason').text()).toBe(NOT_LIVE)
  })

  it('(c) changed elsewhere: "Review and add" has the disabled attribute, a click posts nothing, the sentence is shown', async () => {
    const w = await builder()
    S(w).setLegs(S(w).paper.net.map((l, i) => (i === 0 ? { ...l, lots: 9 } : { ...l })))
    await flushPromises()
    await setMark(w, true)
    expect(t(w, 'paper-review').attributes('disabled')).toBeDefined()
    await t(w, 'paper-review').trigger('click')
    S(w).reviewPending()
    await flushPromises()
    expect(t(w, 'paper-confirm').exists()).toBe(false)
    expect(orderPosts()).toHaveLength(0)
    expect(t(w, 'paper-exit-reason').text()).toBe(CHANGED)
  })

  it('(d) the user\'s Cancel on an Exit dialog drops the staged exit (same function the page uses)', async () => {
    const w = await builder()
    const legsBefore = snap(w)
    await t(w, 'paper-exit-all').trigger('click')
    await flushPromises()
    await t(w, 'paper-cancel').trigger('click')
    await flushPromises()
    expect(t(w, 'paper-confirm').exists()).toBe(false)
    expect(S(w).pendingOrders.length).toBe(0)
    expect(snap(w)).toEqual(legsBefore)
  })

  it('(d2) Cancel of a "Review and add" dialog of adds keeps the user\'s edit (only Exit edits are dropped)', async () => {
    const w = await builder()
    S(w).setLegs(S(w).paper.net.map((l, i) => (i === 0 ? { ...l, lots: 9 } : { ...l })))
    await flushPromises()
    await t(w, 'paper-review').trigger('click')
    await flushPromises()
    await t(w, 'paper-cancel').trigger('click')
    await flushPromises()
    expect(S(w).pendingOrders.length).toBe(1)
  })
})

describe('Tier A review round 2: the staged exit is dropped, the user\'s own edits stay; a blocked Confirm posts nothing; a POST in flight cannot be cancelled', () => {
  const removeFirst = (w) => S(w).setLegs(S(w).legs.slice(1))
  const lots9 = (w) => S(w).setLegs(S(w).paper.net.map((l, i) => (i === 0 ? { ...l, lots: 9 } : { ...l })))
  const exitLeg = async (w, i) => { S(w).exitPaper(S(w).paper.net[i].contract_id, 1); await flushPromises() }

  it('F1 A1: a lot change, then a per-leg Exit on another leg, then Cancel: the lot change stays (1 pending)', async () => {
    const w = await builder()
    lots9(w)
    await flushPromises()
    expect(S(w).pendingOrders.length).toBe(1)
    await exitLeg(w, 2)
    expect(S(w).pendingOrders.length).toBe(2)
    expect(t(w, 'paper-confirm').exists()).toBe(true)
    await t(w, 'paper-cancel').trigger('click')
    await flushPromises()
    expect(S(w).pendingOrders.length).toBe(1)
    expect(S(w).legs[0].lots).toBe(9)
  })

  it('F1 A2: a leg removed, then a per-leg Exit, then the read fails: the removal stays (1 pending)', async () => {
    const w = await builder()
    removeFirst(w)
    await flushPromises()
    expect(S(w).pendingOrders.length).toBe(1)
    await exitLeg(w, 2)
    expect(t(w, 'paper-confirm').exists()).toBe(true)
    await failRead()
    expect(t(w, 'paper-confirm').exists()).toBe(false)
    expect(S(w).pendingOrders.length).toBe(1)
  })

  it('F2 A3: a leg removed, Review and add open, the trade changes elsewhere: dialog closes, Confirm posts nothing, the edit stays', async () => {
    const w = await builder()
    removeFirst(w)
    await flushPromises()
    await t(w, 'paper-review').trigger('click')
    await flushPromises()
    expect(t(w, 'paper-confirm').exists()).toBe(true)
    const rows = S(w).paperRows
    await setMark(w, true)
    expect(t(w, 'paper-confirm').exists()).toBe(false)
    await S(w).confirmPending(rows)
    await flushPromises()
    expect(orderPosts()).toHaveLength(0)
    expect(S(w).pendingOrders.length).toBe(1)
  })

  it('F2 A3b: Confirm in the same tick as the mark, on a Review and add dialog: nothing posted, edit kept', async () => {
    const w = await builder()
    removeFirst(w)
    await flushPromises()
    await t(w, 'paper-review').trigger('click')
    await flushPromises()
    const rows = S(w).paperRows
    S(w).paperContractsChanged = true
    await S(w).confirmPending(rows)
    await flushPromises()
    expect(orderPosts()).toHaveLength(0)
    expect(S(w).pendingOrders.length).toBe(1)
  })

  it('F3 A6: Confirm (POST pending), Cancel, then the POST fails 503: the dialog stays and shows the unknown-outcome text', async () => {
    const w = await builder()
    let fail
    answers['POST /paper/strategies/86/orders'] = () => new Promise((_, rej) => { fail = rej })
    await t(w, 'paper-exit-all').trigger('click')
    await flushPromises()
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(S(w).paperBusy).toBe(true)
    await t(w, 'paper-cancel').trigger('click')
    await flushPromises()
    expect(t(w, 'paper-confirm').exists()).toBe(true)
    expect(S(w).pendingOrders.length).toBe(4)
    fail({ status: 503, message: 'x', parts: null })
    await flushPromises()
    expect(t(w, 'paper-unknown').exists()).toBe(true)
    expect(t(w, 'paper-confirm').exists()).toBe(true)
  })

  it('F4 A9: POST 201 then the re-read fails, Close: the legs stay as they were (nothing restored over stored orders)', async () => {
    const w = await builder()
    await t(w, 'paper-exit-all').trigger('click')
    await flushPromises()
    answers['GET /paper/strategies/86'] = FAIL_503
    await t(w, 'paper-confirm-button').trigger('click')
    await vi.advanceTimersByTimeAsync(100) // the first re-read failed, the next try is 400 ms away: the dialog says it was placed
    await flushPromises()
    expect(orderPosts()).toHaveLength(1)
    expect(t(w, 'paper-placed').exists()).toBe(true)
    await t(w, 'paper-cancel').trigger('click')
    await flushPromises()
    expect(S(w).legs).toEqual([])
  })
})
