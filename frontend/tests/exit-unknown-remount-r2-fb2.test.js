// Lane FB2 (coordinator 07:30, F1 second path): the unknown-exit lock survives leaving the builder and coming back (copy of the FB harness).
// Lane FB round 2, Opus review of Lane Z (F1), ADR-017 / ADR-016..019, ADR-330 (58): after an exit whose outcome is UNKNOWN the page never
// says "not stored" and never unlocks Exit on a short timer. The server can still commit later (client timeout 10 s, statement 30 s, pool wait
// 30 s, no idempotency key), so a second partial Exit would commit too (2 of 4 lots twice = 4 lots). Only the server's own answer unlocks:
// the book moved (stored), or the book is read UNCHANGED after the longest commit window has passed. The REAL builder page.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import { UNKNOWN_EXIT_WINDOW_MS } from '@/lib/sharedStateText'
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

beforeEach(() => { vi.useFakeTimers() })
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

describe('F1 second path: leaving the builder and coming back inside the commit window keeps the exit locked', () => {
  it('CORE (2 of 4 lots twice): unknown exit, the page is left and opened again 30 s later with the book unchanged: Exit is still locked, a second partial Exit posts nothing', async () => {
    const first = await unknownExit()
    expect(orderPosts()).toHaveLength(1)
    first.unmount()
    mounted.pop()
    await vi.advanceTimersByTimeAsync(30000)
    const w = await remount()
    expect(S(w).exitBlocked).toBe(true)
    S(w).exitPaper(OPEN_IDS[0], 1)
    await flushPromises()
    const btn = t(w, 'paper-confirm-button')
    if (btn.exists()) await btn.trigger('click')
    await flushPromises()
    expect(orderPosts()).toHaveLength(1)
  })
  it('the server commits late: the reopened page sees the book moved and unlocks (the server answer), still ONE post', async () => {
    const first = await unknownExit()
    first.unmount()
    mounted.pop()
    await vi.advanceTimersByTimeAsync(30000)
    answers['GET /paper/strategies/86'] = afterExitOf(OPEN_IDS[0])
    const w = await remount()
    expect(S(w).exitBlocked).toBe(false)
    expect(orderPosts()).toHaveLength(1)
  })
  it('the book stays unchanged past the whole window: the reopened page unlocks only then', async () => {
    const first = await unknownExit()
    first.unmount()
    mounted.pop()
    await vi.advanceTimersByTimeAsync(UNKNOWN_EXIT_WINDOW_MS + 15000)
    const w = await remount()
    expect(S(w).exitBlocked).toBe(false)
    expect(orderPosts()).toHaveLength(1)
  })
})

describe('Opus review F1: the lock is written BEFORE the post, so a page left while the post is still out is covered too', () => {
  it('CORE: the exit post never answers, the page is left 3 s later and opened again: Exit is locked, a second partial Exit posts nothing', async () => {
    calls.length = 0
    answers = {
      'GET /strategies': { strategies: [] },
      'POST /paper/strategies/86/orders': () => new Promise(() => {}), // still out
      'GET /paper/strategies/86': BOOK,
      'GET /catalogue/NIFTY/contracts?expiry=2026-11-03': { underlying: 'NIFTY', contracts: CONTRACTS },
      'POST /strategies/outcome': () => new Promise(() => {}),
      'POST /strategies/leg-edit': () => new Promise(() => {}),
    }
    const first = await remount()
    S(first).exitPaper(OPEN_IDS[0], 1)
    await flushPromises()
    await t(first, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(orderPosts()).toHaveLength(1)
    first.unmount()
    mounted.pop()
    await vi.advanceTimersByTimeAsync(3000)
    const w = await remount()
    expect(S(w).exitBlocked).toBe(true)
    S(w).exitPaper(OPEN_IDS[0], 1)
    await flushPromises()
    const btn = t(w, 'paper-confirm-button')
    if (btn.exists()) await btn.trigger('click')
    await flushPromises()
    expect(orderPosts()).toHaveLength(1)
  })
  it('a definite refusal (4xx) removes the lock: the exit may be sent again', async () => {
    calls.length = 0
    answers = {
      'GET /strategies': { strategies: [] },
      'POST /paper/strategies/86/orders': () => Promise.reject({ status: 422, message: 'x', parts: null }),
      'GET /paper/strategies/86': BOOK,
      'GET /catalogue/NIFTY/contracts?expiry=2026-11-03': { underlying: 'NIFTY', contracts: CONTRACTS },
      'POST /strategies/outcome': () => new Promise(() => {}),
      'POST /strategies/leg-edit': () => new Promise(() => {}),
    }
    const first = await remount()
    S(first).exitPaper(OPEN_IDS[0], 1)
    await flushPromises()
    await t(first, 'paper-confirm-button').trigger('click')
    await flushPromises()
    first.unmount()
    mounted.pop()
    const w = await remount()
    expect(S(w).exitBlocked).toBe(false)
  })
  it('a decided lock is removed from storage (a stored exit, then a reopened page has nothing left)', async () => {
    const first = await unknownExit()
    answers['GET /paper/strategies/86'] = afterExitOf(OPEN_IDS[0])
    await vi.advanceTimersByTimeAsync(6000)
    await flushPromises()
    expect(S(first).exitBlocked).toBe(false)
    expect(globalThis.sessionStorage.getItem('ofo.exitUnknown') ?? '{}').not.toContain('"86"')
  })
})
