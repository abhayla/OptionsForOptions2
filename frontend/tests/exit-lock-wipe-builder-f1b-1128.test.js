// Lane F1b item 1 (Opus review, builder half): adoptForeignLock must not release when the lock merely VANISHED from the store (site data cleared: lock and request key both gone).
// Real case (FJ2 W2, 28 Nov): unknown exit of strategy 86 (503), storage wiped, Exit pressed again inside the window: a second order under a new key. Pin: no second POST; a deciding read releases.
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

beforeEach(() => { vi.useFakeTimers(); globalThis.localStorage?.clear() }) // Lane FJ: the lock is kept in the browser (localStorage), not the tab
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

const tryExit = async (w) => {
  S(w).exitPaper(OPEN_IDS[0], 1)
  await flushPromises()
  const b = t(w, 'paper-confirm-button')
  if (b.exists()) await b.trigger('click')
  await flushPromises()
}
const wipe = async () => { globalThis.localStorage.clear(); window.dispatchEvent(new StorageEvent('storage', { key: null })); await flushPromises() }

describe('F1b item 1: a wiped store is not a decision (builder, adoptForeignLock)', () => {
  it('unknown exit, storage wiped, book unchanged: Exit stays locked and a second Confirm sends nothing', async () => {
    const w = await unknownExit()
    expect(orderPosts()).toHaveLength(1)
    await wipe()
    await vi.advanceTimersByTimeAsync(6000)
    expect(S(w).exitBlocked).toBe(true)
    await tryExit(w)
    expect(orderPosts()).toHaveLength(1)
  })
  it('the wiped store, then the book shows the exit stored: released by that read, still nothing sent', async () => {
    const w = await unknownExit()
    await wipe()
    answers['GET /paper/strategies/86'] = afterExitOf(OPEN_IDS[0])
    await vi.advanceTimersByTimeAsync(6000)
    await flushPromises()
    expect(S(w).exitBlocked).toBe(false)
    expect(orderPosts()).toHaveLength(1)
  })
  it('the wiped store, an unchanged book past the window: decided "not stored" (never a permanent lock from a wipe)', async () => {
    const w = await unknownExit()
    await wipe()
    await vi.advanceTimersByTimeAsync(UNKNOWN_EXIT_WINDOW_MS + 20000)
    await flushPromises()
    expect(S(w).exitBlocked).toBe(false)
  })
})
