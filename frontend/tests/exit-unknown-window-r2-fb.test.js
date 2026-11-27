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
const LOTS = (OPEN[0].net_quantity < 0 ? -OPEN[0].net_quantity : OPEN[0].net_quantity) / 65 // lots held on the first leg
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

describe('F1: an unknown exit is not unlocked by a short timer', () => {
  it('CORE (the 2-of-4-lots case): unknown, book unchanged 5 s later, 30 s later: still locked, no "not stored", a second partial Exit posts nothing; then the server commits late: the book shows it, ONE post in all', async () => {
    expect(LOTS).toBeGreaterThanOrEqual(1)
    const w = await unknownExit()
    expect(orderPosts()).toHaveLength(1)
    await vi.advanceTimersByTimeAsync(5100)
    await flushPromises()
    expect(S(w).exitBlocked).toBe(true)
    expect(w.text()).not.toContain('was not stored')
    S(w).exitPaper(OPEN_IDS[0], 1) // the second partial Exit the old code allowed here
    await flushPromises()
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeDefined() // the open dialog stays locked, too
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(orderPosts()).toHaveLength(1)
    await vi.advanceTimersByTimeAsync(25000)
    await flushPromises()
    expect(S(w).exitBlocked).toBe(true) // 30 s after: still inside the server's longest commit window
    expect(orderPosts()).toHaveLength(1)
    answers['GET /paper/strategies/86'] = afterExitOf(OPEN_IDS[0]) // the server committed late (pool wait + statement)
    await vi.advanceTimersByTimeAsync(6000)
    await flushPromises()
    expect(S(w).exitBlocked).toBe(false) // the server's own answer (the book moved) unlocks it
    expect(S(w).paper.net.some((l) => l.contract_id === OPEN_IDS[0])).toBe(false)
    expect(orderPosts()).toHaveLength(1)
  })
  it('the book stays unchanged for the whole commit window: only then, on a read taken after it, is the exit "not stored" and Exit open again', async () => {
    const w = await unknownExit()
    await vi.advanceTimersByTimeAsync(UNKNOWN_EXIT_WINDOW_MS - 2000)
    await flushPromises()
    expect(S(w).exitBlocked).toBe(true)
    await vi.advanceTimersByTimeAsync(12000)
    await flushPromises()
    expect(S(w).exitBlocked).toBe(false)
    expect(orderPosts()).toHaveLength(1)
  })
  it('the window is longer than the server\'s longest commit (pool wait 30 s + statement 30 s)', () => {
    expect(UNKNOWN_EXIT_WINDOW_MS).toBeGreaterThan(60000)
  })
})
