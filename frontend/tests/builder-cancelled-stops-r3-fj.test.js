// Lane FJ (R3) item 2 (review F3, page half): the stops a move cancelled, from the order reply alone, printed in the page's stop-offer block after the dialog has closed.
// (copy of the FB2 harness; first line of the file it came from: Lane FB2 (coordinator 07:30, F1 second path): the unknown-exit lock survives leaving the builder and coming back (copy of the FB harness).
// Lane FB round 2, Opus review of Lane Z (F1), ADR-017 / ADR-016..019, ADR-330 (58): after an exit whose outcome is UNKNOWN the page never
// says "not stored" and never unlocks Exit on a short timer. The server can still commit later (client timeout 10 s, statement 30 s, pool wait
// 30 s, no idempotency key), so a second partial Exit would commit too (2 of 4 lots twice = 4 lots). Only the server's own answer unlocks:
// the book moved (stored), or the book is read UNCHANGED after the longest commit window has passed. The REAL builder page.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import { resetExitLocks } from '@/lib/unknownLocks'
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
const OPEN = BOOK.positions.filter((p) => p.net_quantity !== 0)
const OPEN_IDS = OPEN.map((p) => p.contract_id)
const afterExitOf = (id) => ({ ...BOOK, positions: BOOK.positions.map((p) => (p.contract_id === id ? { ...p, net_quantity: 0 } : p)) })
const orderPosts = () => calls.filter((c) => c.method === 'POST' && c.url === '/paper/strategies/86/orders')
const S = (w) => w.vm.$.setupState
const mounted = []

beforeEach(() => { vi.useFakeTimers(); globalThis.localStorage?.clear(); resetExitLocks() }) // Lane FJ: the lock is kept in the browser (localStorage), not the tab
afterEach(() => { vi.useRealTimers(); while (mounted.length) mounted.pop().unmount(); document.body.innerHTML = '' })

async function unknownExit() {
  calls.length = 0
  answers = {
    'GET /strategies': { strategies: [] },
    'POST /paper/strategies/86/orders': () => Promise.reject({ status: 503, message: 'x', parts: null }), // no answer: unknown
    'GET /paper/strategies/86': BOOK, // the book is read, unchanged (the server has not committed YET)
    'GET /catalogue/NIFTY/contracts?expiry=2026-11-03': { underlying: 'NIFTY', contracts: CONTRACTS },
    'POST /strategies/outcome': () => new Promise(() => {}),
    'POST /strategies/leg-edit': () => new Promise(() => {}),
  }
  const r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await r.push('/strategy/builder?strategy=86')
  await r.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [r], stubs: { PayoffChart: true } }, attachTo: document.body })
  mounted.push(w)
  await flushPromises()
  S(w).exitPaper(OPEN_IDS[0], 1) // a PARTIAL exit: 1 lot of the leg
  await flushPromises()
  await t(w, 'paper-confirm-button').trigger('click')
  await flushPromises()
  return w
}


async function remount() {
  const r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await r.push('/strategy/builder?strategy=86')
  await r.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [r], stubs: { PayoffChart: true } }, attachTo: document.body })
  mounted.push(w)
  await flushPromises()
  return w
}



async function exitWith(reply) {
  calls.length = 0
  answers = {
    'GET /strategies': { strategies: [] },
    'POST /paper/strategies/86/orders': () => Promise.resolve({ data: reply }),
    'GET /paper/strategies/86': BOOK,
    'GET /catalogue/NIFTY/contracts?expiry=2026-11-03': { underlying: 'NIFTY', contracts: CONTRACTS },
    'POST /strategies/outcome': () => new Promise(() => {}),
    'POST /strategies/leg-edit': () => new Promise(() => {}),
  }
  const r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await r.push('/strategy/builder?strategy=86')
  await r.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [r], stubs: { PayoffChart: true } }, attachTo: document.body })
  mounted.push(w)
  await flushPromises()
  S(w).exitPaper(OPEN_IDS[0], 1)
  await flushPromises()
  await t(w, 'paper-confirm-button').trigger('click')
  await vi.advanceTimersByTimeAsync(3000)
  await flushPromises()
  return w
}
const UNREADABLE = 'The stop on the old leg may have been cancelled, and the new leg has no stop until you set one.'
describe('item 2: the stops a move cancelled', () => {
  it('the reply lists a stop: the stop-offer block prints the past-tense line with its level', async () => {
    const w = await exitWith({ orders: [{ id: 5 }], cancelled_stops: [{ leg: 'NIFTY 22650 PE', contract: 5, level: '120.00' }] })
    expect(orderPosts()).toHaveLength(1)
    expect(t(w, 'stop-offer-cancelled').text()).toBe('The stop on NIFTY 22650 PE (level 120.00) was removed with the move; set a new one on the new leg.')
    expect(t(w, 'stop-offer-reply-unreadable').exists()).toBe(false)
  })
  it('an entry without a level drops the level part', async () => {
    const w = await exitWith({ orders: [{ id: 5 }], cancelled_stops: [{ leg: 'NIFTY 22650 PE', contract: 5 }] })
    expect(t(w, 'stop-offer-cancelled').text()).toBe('The stop on NIFTY 22650 PE was removed with the move; set a new one on the new leg.')
  })
  it('an empty list (no stop was cancelled) and an absent key say nothing', async () => {
    const a = await exitWith({ orders: [{ id: 5 }], cancelled_stops: [] })
    expect(t(a, 'stop-offer').exists()).toBe(false)
    mounted.splice(0).forEach((x) => x.unmount()); document.body.innerHTML = ''
    const b = await exitWith({ orders: [{ id: 5 }] })
    expect(t(b, 'stop-offer').exists()).toBe(false)
  })
  it('a 2xx reply that is not an object: the unreadable sentence (fail closed), no stop line', async () => {
    const w = await exitWith('ok')
    expect(t(w, 'stop-offer-reply-unreadable').text()).toBe(UNREADABLE)
    expect(t(w, 'stop-offer-cancelled').exists()).toBe(false)
  })
  it('a new dialog starts with no word about stops; "Not now" removes the lines', async () => {
    const w = await exitWith({ orders: [{ id: 5 }], cancelled_stops: [{ leg: 'NIFTY 22650 PE', level: '120.00' }] })
    expect(t(w, 'stop-offer-cancelled').exists()).toBe(true)
    S(w).exitPaper(OPEN_IDS[1], 1)
    await flushPromises()
    expect(t(w, 'stop-offer').exists()).toBe(false)
  })
})
