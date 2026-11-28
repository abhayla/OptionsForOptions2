// Group A (28 Nov, round 3, Opus review of the round-2 order paths; ADR-016..019): the shared harness of the four group-a tests.
// A mocked api (never a broker or a real order endpoint), the REAL Positions list and the REAL builder page on a paper strategy 1 whose leg 776 holds 4 lots.
// The components are imported INSIDE the functions: the api mock's factory imports this file, so a static import of a component here would wait for the mock (deadlock).
// Each test file mocks '@/services/api' with `apiMock` from here (vi.mock factory: `const h = await import('./helpers/group-a.js'); return { ...actual, default: h.apiMock }`).
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { vi } from 'vitest'
import * as L from '@/lib/unknownLocks'
import REAL from '../fixtures/paper-strategies.json'
import BOOK63 from '../fixtures/paper-book-63.json'

export const calls = []
export const state = { answers: {} }
const respond = (method, url, body) => {
  calls.push({ method, url, body })
  const a = state.answers[`${method} ${url}`]
  if (a === undefined && method === 'GET' && url === '/market/exit-state') return Promise.resolve({ data: { closed: false, sentence: null, next_open_at: null } })
  if (a === undefined && method === 'GET' && url === '/strategies') return Promise.resolve({ data: { strategies: [] } })
  if (a === undefined) return Promise.reject({ message: `unmocked ${method} ${url}`, parts: null, status: null })
  return typeof a === 'function' ? a(body) : Promise.resolve({ data: a })
}
export const apiMock = { get: (u) => respond('GET', u), post: (u, b) => respond('POST', u, b), put: (u, b) => respond('PUT', u, b), patch: (u, b) => respond('PATCH', u, b), delete: (u) => respond('DELETE', u) }

export const clone = (o) => JSON.parse(JSON.stringify(o))
export const ORDERS = '/paper/strategies/1/orders'
export const UNKNOWN = () => Promise.reject({ message: 'x', status: 503, parts: null })
export const LIST = (() => { const d = clone(REAL); d.strategies.find((s) => s.strategy_id === 1).positions.find((p) => p.contract_id === 776).net_quantity = 260; return d })()
export const S1 = LIST.strategies.find((s) => s.strategy_id === 1)
export const BOOK1 = { ...clone(BOOK63), strategy_id: 1, name: '"IC"', underlying: 'NIFTY', positions: clone(S1.positions) }
export const BEFORE = '753:65,776:260,784:-65'
const CONTRACTS = S1.positions.map((p) => ({ contract_id: p.contract_id, exchange_segment: 'NSE_FO', exchange_token: p.contract_id, instrument_type: p.instrument, expiry: p.expiry, strike: p.strike, lot_size: 65, symbol: `NIFTY${p.strike}${p.instrument}` }))
export const listWith = (mod) => { const d = clone(LIST); mod(d.strategies.find((x) => x.strategy_id === 1)); return d }
export const bookWith = (mod) => { const d = clone(BOOK1); mod(d); return d }
export const posts = () => calls.filter((c) => c.method === 'POST' && c.url === ORDERS)

export const mounted = []
export const S = (w) => w.vm.$.setupState
export const t = (w, id) => w.find(`[data-testid="${id}"]`)
export const adv = async (ms) => { await vi.advanceTimersByTimeAsync(ms); await flushPromises() }
export function baseAnswers() {
  state.answers = {
    'GET /paper/strategies': () => Promise.resolve({ data: clone(LIST) }),
    'GET /paper/strategies/1': () => Promise.resolve({ data: clone(BOOK1) }),
    'GET /catalogue/NIFTY/contracts?expiry=2026-10-13': { underlying: 'NIFTY', contracts: CONTRACTS },
    'POST /strategies/outcome': () => new Promise(() => {}),
    'POST /strategies/leg-edit': () => new Promise(() => {}),
    [`POST ${ORDERS}`]: UNKNOWN,
  }
}
export async function showPositions() {
  const PaperStrategies = (await import('@/components/strategy/PaperStrategies.vue')).default
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: PaperStrategies }, { path: '/strategy/builder', component: { template: '<div/>' } }] })
  router.push('/')
  await router.isReady()
  const w = mount(PaperStrategies, { global: { plugins: [router] }, attachTo: document.body })
  mounted.push(w)
  await flushPromises()
  return w
}
export async function showBuilder() {
  const StrategyBuilderPage = (await import('@/pages/StrategyBuilderPage.vue')).default
  const r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await r.push('/strategy/builder?strategy=1')
  await r.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [r], stubs: { PayoffChart: true } }, attachTo: document.body })
  mounted.push(w)
  await flushPromises()
  return w
}
export const drop = (w) => { w.unmount(); mounted.splice(mounted.indexOf(w), 1) }
export async function positionsExit(w) { // select leg 776, open the Exit dialog, press Confirm once
  const box = t(w, 'select-leg-1-776')
  if (!box.element.checked) await box.setValue(true)
  await t(w, 'exit-selected-1').trigger('click')
  await flushPromises()
  const b = t(w, 'paper-confirm-button')
  if (b.exists()) await b.trigger('click')
  await flushPromises()
}
export async function builderExit(w, lots = 2) { // a partial exit of the 4-lot leg 776, one Confirm press
  S(w).exitPaper(776, lots)
  await flushPromises()
  const b = t(w, 'paper-confirm-button')
  if (b.exists()) await b.trigger('click')
  await flushPromises()
}
export const storm = (name = 'ofo.exitUnknown') => globalThis.dispatchEvent(new StorageEvent('storage', { key: name }))
export async function setup() {
  const { resetActiveAlerts } = await import('@/lib/paperAlerts')
  calls.length = 0; resetActiveAlerts(); vi.useFakeTimers(); L.resetExitLocks()
  try { globalThis.localStorage?.clear(); globalThis.sessionStorage?.clear() } catch { /* none */ }
  baseAnswers()
}
export function teardown() {
  mounted.splice(0).forEach((w) => { try { w.unmount() } catch { /* gone */ } })
  vi.useRealTimers(); document.body.innerHTML = ''
}
export const lockNow = () => L.exitLockFor(1)
