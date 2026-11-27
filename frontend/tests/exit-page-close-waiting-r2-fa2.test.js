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
  const r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
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
const stage = async (w) => { S(w).setLegs(S(w).paper.net.map((l, i) => (i === 1 ? { ...l, lots: 2 } : { ...l }))); await flushPromises() }

// Lane FA2 #873: the page closing the Exit all dialog (the trade changed elsewhere) must forget the waiting change; otherwise a later Cancel or
// Confirm acts on a stale snapshot (restores or discards a change the user has edited since).
describe('#873: page close clears the waiting change of an Exit all', () => {
  it('Exit all with a staged change, the page closes the dialog, nothing is left waiting (the staged change itself is back, unchanged)', async () => {
    const w = await builder()
    await stage(w)
    S(w).exitAllPaper()
    await flushPromises()
    expect(t(w, 'paper-discard-note').exists()).toBe(true)
    w.vm.$.setupState.paperContractsChanged = true // the page closes the dialog
    await flushPromises()
    expect(t(w, 'paper-confirm').exists()).toBe(false)
    expect(S(w).exitAllWaiting).toBeNull()
    expect(S(w).legs.find((l) => l.contract_id === OPEN_IDS[1]).lots).toBe(2)
  })
})
