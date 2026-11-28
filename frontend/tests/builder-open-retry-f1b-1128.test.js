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
const mounted = []

beforeEach(() => { vi.useFakeTimers(); globalThis.localStorage?.clear() }) // Lane FJ: the lock is kept in the browser (localStorage), not the tab
afterEach(() => { vi.useRealTimers(); while (mounted.length) mounted.pop().unmount(); document.body.innerHTML = '' })

// Lane F1b batch 2, board item I-86 (cloud walker, Lane W2): the builder shows the "could not load" sentence for a strategy that cannot be opened but has NO Retry button (9 of 10 pages have one).
// Real case: builder at /strategy/builder?strategy=86 with the API stopped: open-error is shown, nothing to press. A not-found strategy keeps its own door (Open My Strategies), no Retry.
async function openBuilder() {
  const r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await r.push('/strategy/builder?strategy=86')
  await r.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [r], stubs: { PayoffChart: true } }, attachTo: document.body })
  mounted.push(w)
  await flushPromises()
  return w
}
const baseAnswers = () => ({
  'GET /strategies': { strategies: [] },
  'GET /catalogue/NIFTY/contracts?expiry=2026-11-03': { underlying: 'NIFTY', contracts: CONTRACTS },
  'POST /strategies/outcome': () => new Promise(() => {}),
  'POST /strategies/leg-edit': () => new Promise(() => {}),
})
describe('I-86 builder: Retry after a failed open', () => {
  it('a failed read of the strategy shows the sentence AND a Retry button; Retry reads again and the sentence goes', async () => {
    calls.length = 0
    answers = { ...baseAnswers(), 'GET /paper/strategies/86': () => Promise.reject({ status: 500, message: 'down', parts: null }) }
    const w = await openBuilder()
    expect(t(w, 'open-error').exists()).toBe(true)
    expect(t(w, 'open-error-retry').exists()).toBe(true)
    const reads = () => calls.filter((c) => c.method === 'GET' && c.url === '/paper/strategies/86').length
    const before = reads()
    answers['GET /paper/strategies/86'] = BOOK
    await t(w, 'open-error-retry').trigger('click')
    await flushPromises()
    expect(reads()).toBeGreaterThan(before)
    expect(t(w, 'open-error').exists()).toBe(false)
    expect(t(w, 'open-error-retry').exists()).toBe(false)
  })
  it('a second failure keeps the sentence and the Retry (it stays usable)', async () => {
    calls.length = 0
    answers = { ...baseAnswers(), 'GET /paper/strategies/86': () => Promise.reject({ status: 500, message: 'down', parts: null }) }
    const w = await openBuilder()
    await t(w, 'open-error-retry').trigger('click')
    await flushPromises()
    expect(t(w, 'open-error').exists()).toBe(true)
    expect(t(w, 'open-error-retry').exists()).toBe(true)
  })
  it('a strategy that is not found keeps its own door (Open My Strategies) and shows no Retry', async () => {
    calls.length = 0
    answers = { ...baseAnswers(), 'GET /paper/strategies/86': () => Promise.reject({ status: 404, message: 'nf', error_code: 'STRATEGY_VALIDATION_523', parts: { what_happened: 'Strategy not found.', impact: 'i', blocked: 'b', next_action: 'n' } }), 'GET /strategies/86': () => Promise.reject({ status: 404, message: 'nf', error_code: 'STRATEGY_VALIDATION_523', parts: { what_happened: 'Strategy not found.', impact: 'i', blocked: 'b', next_action: 'n' } }) }
    const w = await openBuilder()
    expect(t(w, 'open-error').exists()).toBe(true)
    expect(t(w, 'open-error-retry').exists()).toBe(false)
  })
})
