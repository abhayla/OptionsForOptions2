// Lane U2, item 3 (ADR-330 (59), ADR-330 (58), ADR-016..019): Exit all while a change is staged and not sent is not blocked; the dialog says the change
// will be discarded, Cancel gives it back unchanged, Confirm posts only the exits and then says it was discarded; an unknown outcome neither sends nor loses it.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import REAL from './fixtures/paper-book-63.json'
import { legacy } from './_paperList'

const calls = []
let answers = {}
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
const OPEN_IDS = BOOK.positions.filter((p) => p.net_quantity !== 0).map((p) => p.contract_id) // [5572, 5587, 5585, 5574]
const orderPosts = () => calls.filter((c) => c.method === 'POST' && c.url === '/paper/strategies/86/orders')
let router = null
const mounted = []
async function builder(query = '?strategy=86', book = BOOK) {
  calls.length = 0
  answers = {
    'GET /strategies': { strategies: [] },
    'POST /paper/strategies/86/orders': book,
    'GET /paper/strategies/86': book,
    'GET /catalogue/NIFTY/contracts?expiry=2026-11-03': { underlying: 'NIFTY', contracts: CONTRACTS },
    'POST /strategies/outcome': () => new Promise(() => {}),
    'POST /strategies/leg-edit': () => new Promise(() => {}),
  }
  const r = router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await r.push(`/strategy/builder${query}`)
  await r.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [r], stubs: { PayoffChart: true } }, attachTo: document.body })
  mounted.push(w)
  await flushPromises()
  return w
}
const S = (w) => w.vm.$.setupState

beforeEach(() => { vi.useFakeTimers() })
afterEach(() => {
  vi.useRealTimers()
  while (mounted.length) mounted.pop().unmount()
  document.body.innerHTML = ''
})


beforeEach(() => { vi.useFakeTimers() })
afterEach(() => {
  vi.useRealTimers()
  while (mounted.length) mounted.pop().unmount()
  document.body.innerHTML = ''
})



const exit1 = async (w) => { await t(w, 'paper-confirm-button').trigger('click'); await flushPromises() }
const stage = async (w) => { S(w).setLegs(S(w).paper.net.map((l, i) => (i === 1 ? { ...l, lots: 2 } : { ...l }))); await flushPromises() }
const allGone = { ...BOOK, positions: BOOK.positions.map((p) => ({ ...p, net_quantity: 0 })) }
const lotsOf = (w, id) => S(w).legs.find((l) => l.contract_id === id)?.lots

describe('ADR-330 (59): Exit all with a staged change', () => {
  it('not blocked: the dialog holds the exits, says the change will be discarded, naming the leg', async () => {
    const w = await builder()
    await stage(w)
    S(w).exitAllPaper()
    await flushPromises()
    expect(S(w).paperDialog).toBe(true)
    expect(S(w).paperRows).toHaveLength(OPEN_IDS.length)
    const note = t(w, 'paper-discard-note').text()
    expect(note).toMatch(/^Exit all closes every open leg\. The change waiting on .+ is not sent and will be discarded\.$/)
  })
  it('Cancel gives the staged change back exactly: leg 2 still 2 lots, one pending add, no exit staged, nothing posted', async () => {
    const w = await builder()
    await stage(w)
    const before = JSON.stringify(S(w).legs)
    S(w).exitAllPaper()
    await flushPromises()
    await t(w, 'paper-cancel').trigger('click')
    await flushPromises()
    expect(JSON.stringify(S(w).legs)).toBe(before)
    expect(S(w).pendingOrders.map((o) => [o.kind, o.contract_id])).toEqual([['add', OPEN_IDS[1]]])
    expect(orderPosts()).toHaveLength(0)
  })
  it('Confirm posts only the exits (no acted / basket / approach), then says the change was discarded', async () => {
    const w = await builder('?strategy=86&acted=7&basket=4&approach=A-24')
    await stage(w)
    answers['POST /paper/strategies/86/orders'] = allGone
    answers['GET /paper/strategies/86'] = allGone
    S(w).exitAllPaper()
    await flushPromises()
    await exit1(w)
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()
    expect(orderPosts()).toHaveLength(1)
    expect(orderPosts()[0].body.orders.every((o) => o.kind === 'exit')).toBe(true)
    expect(orderPosts()[0].body.orders).toHaveLength(OPEN_IDS.length)
    expect(Object.keys(orderPosts()[0].body).sort()).toEqual(['client_request_id', 'orders'])
    expect(t(w, 'staged-not-kept').text()).toMatch(/^The change waiting on .+ was discarded\.$/)
    expect(S(w).pendingOrders).toEqual([])
    expect(router.currentRoute.value.query.acted).toBeUndefined() // the discarded change's acted / basket / approach do not outlive it
    expect(router.currentRoute.value.query.basket).toBeUndefined()
  })
  it('a refusal (4xx) then Cancel: the staged change comes back exactly', async () => {
    const w = await builder()
    await stage(w)
    const before = JSON.stringify(S(w).legs)
    answers['POST /paper/strategies/86/orders'] = () => Promise.reject({ status: 422, message: 'x', parts: null })
    S(w).exitAllPaper()
    await flushPromises()
    await exit1(w)
    await t(w, 'paper-cancel').trigger('click')
    await flushPromises()
    expect(JSON.stringify(S(w).legs)).toBe(before)
  })
  it('no staged change: no discard sentence in the dialog (nothing to discard)', async () => {
    const w = await builder()
    S(w).exitAllPaper()
    await flushPromises()
    expect(w.find('[data-testid="paper-discard-note"]').exists()).toBe(false)
  })
  it('unknown outcome: nothing is sent twice, the staged change is kept and the sentence says so; a re-read that shows nothing stored gives it back unchanged', async () => {
    const w = await builder()
    await stage(w)
    answers['POST /paper/strategies/86/orders'] = () => Promise.reject({ status: 503, message: 'x', parts: null })
    answers['GET /paper/strategies/86'] = () => new Promise(() => {})
    S(w).exitAllPaper()
    await flushPromises()
    await exit1(w)
    expect(orderPosts()).toHaveLength(1)
    expect(t(w, 'staged-not-kept').text()).toMatch(/^The change waiting on .+ was not sent; it is kept until the exit's outcome is known\.$/)
    answers['GET /paper/strategies/86'] = BOOK
    await vi.advanceTimersByTimeAsync(131000) // the user comes back later; not-stored needs a read SENT after the server's commit window + margin (Lane Z review F1; Lane FJ: 130 s)
    await S(w).openPaperOrderbook()
    await flushPromises()
    expect(S(w).exitBlocked).toBe(false)
    expect(lotsOf(w, OPEN_IDS[1])).toBe(2)
    expect(t(w, 'staged-not-kept').text()).toMatch(/is back, unchanged\.$/)
  })
  it('unknown outcome, the re-read shows the exits stored: the change is discarded and the screen says so', async () => {
    const w = await builder()
    await stage(w)
    answers['POST /paper/strategies/86/orders'] = () => Promise.reject({ status: 503, message: 'x', parts: null })
    answers['GET /paper/strategies/86'] = allGone
    S(w).exitAllPaper()
    await flushPromises()
    await exit1(w)
    await flushPromises()
    expect(orderPosts()).toHaveLength(1)
    expect(t(w, 'staged-not-kept').text()).toMatch(/was discarded\.$/)
    expect(S(w).pendingOrders).toEqual([])
  })
})
