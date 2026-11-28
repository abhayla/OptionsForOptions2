// Lane U2, item 1 (ADR-017, ADR-016..019): after an exit whose outcome is UNKNOWN (503 / no answer) the same exit is never sendable again
// until a re-read of the book has decided it. Spec basis: ADR-017 (never a blind second order), ADR-330 (49). The REAL builder page.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import REAL from './fixtures/paper-book-63.json'
import { legacy } from './_paperList'
import { UNKNOWN_EXIT_WINDOW_MS } from '@/lib/sharedStateText'

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
const afterExitOf = (id) => ({ ...BOOK, positions: BOOK.positions.map((p) => (p.contract_id === id ? { ...p, net_quantity: 0 } : p)) })
const orderPosts = () => calls.filter((c) => c.method === 'POST' && c.url === '/paper/strategies/86/orders')
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
const kindsOf = (os) => (os ?? []).map((o) => [o.kind, o.contract_id])

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

const CHECKING = 'The first exit\'s outcome is not known yet; no second exit is sent until the server\'s answer is known.'
const orderbookGone = () => new Promise(() => {}) // the re-read never answers: the outcome stays unknown, no failed read to hide the bug
const exit1 = async (w, id) => { S(w).exitPaper(id, 1); await flushPromises(); await t(w, 'paper-confirm-button').trigger('click'); await flushPromises() }
const unknownThen = async (readAnswer) => {
  const w = await builder()
  answers['POST /paper/strategies/86/orders'] = () => Promise.reject({ status: 503, message: 'x', parts: null })
  answers['GET /paper/strategies/86'] = readAnswer
  await exit1(w, OPEN_IDS[0])
  return w
}

describe('ADR-017: an unknown-outcome exit is never sent twice', () => {
  it('CORE: unknown, the re-read fails, the 5 s hold lapses, a second Confirm posts nothing and the sentence says it is being checked', async () => {
    const w = await unknownThen(orderbookGone)
    expect(orderPosts()).toHaveLength(1)
    expect(S(w).paperState).toBe('unknown')
    await vi.advanceTimersByTimeAsync(6000)
    await flushPromises()
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeDefined()
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(orderPosts()).toHaveLength(1)
    expect(w.text()).toContain(CHECKING)
  })
  it('Cancel keeps nothing sendable: Review and add and a new Exit click post nothing while unresolved', async () => {
    const w = await unknownThen(orderbookGone)
    await t(w, 'paper-cancel').trigger('click')
    await flushPromises()
    expect(S(w).exitBlocked).toBe(true)
    S(w).exitPaper(OPEN_IDS[0], 1)
    S(w).exitAllPaper()
    S(w).reviewPending(true)
    await flushPromises()
    expect(S(w).paperDialog).toBe(false)
    expect(orderPosts()).toHaveLength(1)
  })
  it('the re-read shows the exit stored: placed note, nothing resent, the lock is gone', async () => {
    const w = await unknownThen(afterExitOf(OPEN_IDS[0]))
    expect(orderPosts()).toHaveLength(1)
    expect(S(w).paper.net.some((l) => l.contract_id === OPEN_IDS[0])).toBe(false)
    expect(S(w).exitBlocked).toBe(false)
  })
  it('the re-read shows the trade unchanged: too early (inside the commit window of the server) it stays locked; after the window the exit is NOT left staged, the lock is gone, a fresh Exit click posts once more', async () => {
    const w = await unknownThen(BOOK)
    expect(S(w).exitBlocked).toBe(true)
    await vi.advanceTimersByTimeAsync(5100)
    await flushPromises()
    expect(S(w).exitBlocked).toBe(true) // Lane Z review F1: 5 s is not enough; the server may still commit (see exit-unknown-window-r2-fb.test.js)
    await vi.advanceTimersByTimeAsync(UNKNOWN_EXIT_WINDOW_MS + 6000)
    await flushPromises()
    expect(orderPosts()).toHaveLength(1)
    expect(kindsOf(S(w).pendingOrders)).toEqual([])
    expect(S(w).exitBlocked).toBe(false)
    answers['POST /paper/strategies/86/orders'] = afterExitOf(OPEN_IDS[0])
    await exit1(w, OPEN_IDS[0])
    expect(orderPosts()).toHaveLength(2)
  })
  it('Exit all unknown + re-read unchanged: nothing staged, Exit all open again; failed re-read: Exit all blocked with the sentence', async () => {
    const w = await builder()
    answers['POST /paper/strategies/86/orders'] = () => Promise.reject({ status: 503, message: 'x', parts: null })
    answers['GET /paper/strategies/86'] = orderbookGone
    S(w).exitAllPaper()
    await flushPromises()
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    S(w).exitAllPaper()
    await flushPromises()
    expect(orderPosts()).toHaveLength(1)
    expect(S(w).exitBlocked).toBe(true)
  })
})

describe('Tier A round 1 findings', () => {
  it('F1: exit, Cancel, Review and add, 503: the second dialog is locked too (the click path does not matter)', async () => {
    const w = await builder()
    answers['POST /paper/strategies/86/orders'] = () => Promise.reject({ status: 503, message: 'x', parts: null })
    answers['GET /paper/strategies/86'] = orderbookGone
    S(w).exitPaper(OPEN_IDS[0], 1)
    await flushPromises()
    await t(w, 'paper-cancel').trigger('click')
    S(w).reviewPending(false)
    await flushPromises()
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    await vi.advanceTimersByTimeAsync(6000)
    await flushPromises()
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(orderPosts()).toHaveLength(1)
    expect(S(w).exitBlocked).toBe(true)
  })
  it('F2: an older read answering after a newer one has been applied never reopens the exited leg', async () => {
    const w = await unknownThen(afterExitOf(OPEN_IDS[0])) // the automatic re-read already decided: stored
    expect(S(w).paper.net.some((l) => l.contract_id === OPEN_IDS[0])).toBe(false)
    let release
    answers['GET /paper/strategies/86'] = () => new Promise((r) => { release = () => r({ data: BOOK }) })
    const pending = S(w).openPaperOrderbook() // started after: newer, so it applies; then an even newer one is applied first
    answers['GET /paper/strategies/86'] = afterExitOf(OPEN_IDS[0])
    await S(w).openPaperOrderbook()
    release()
    await pending
    await flushPromises()
    expect(S(w).paper.net.some((l) => l.contract_id === OPEN_IDS[0])).toBe(false)
  })
  it('F5: unknown with leg 2 staged, the re-read (after the commit window) shows nothing stored: leg 2\'s add is put back, the exit is NOT staged', async () => {
    const w = await builder()
    S(w).setLegs(S(w).paper.net.map((l, i) => (i === 1 ? { ...l, lots: 2 } : { ...l })))
    await flushPromises()
    answers['POST /paper/strategies/86/orders'] = () => Promise.reject({ status: 503, message: 'x', parts: null })
    answers['GET /paper/strategies/86'] = BOOK
    await exit1(w, OPEN_IDS[0])
    await vi.advanceTimersByTimeAsync(UNKNOWN_EXIT_WINDOW_MS + 11000)
    await flushPromises()
    expect(kindsOf(S(w).pendingOrders)).toEqual([['add', OPEN_IDS[1]]])
    expect(S(w).exitBlocked).toBe(false)
  })
})
