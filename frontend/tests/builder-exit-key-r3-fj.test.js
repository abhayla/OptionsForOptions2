// Lane FJ (R3) item 1d, on the builder: the key is the dialog's; a resend of the same orders after an unknown outcome sends the SAME key, a new press after a decided outcome a new one.
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


const bodyKeys = () => orderPosts().map((c) => c.body.client_request_id)
async function exitAgain(w) {
  S(w).exitPaper(OPEN_IDS[0], 1)
  await flushPromises()
  const btn = t(w, 'paper-confirm-button')
  if (btn.exists() && !btn.element.disabled) await btn.trigger('click')
  await flushPromises()
}
describe('item 1d on the builder: one key rule', () => {
  it('an unknown exit, a read sent after the window shows the book unchanged: the resend of the same exit carries the SAME key (the dialog\'s first one)', async () => {
    const w = await unknownExit()
    expect(orderPosts()).toHaveLength(1)
    expect(bodyKeys()[0]).toMatch(/^[0-9a-f-]{36}$/)
    await vi.advanceTimersByTimeAsync(140000) // the re-read loop: a read SENT more than 130 s after the client gave up
    await flushPromises()
    expect(S(w).exitBlocked).toBe(false)
    await exitAgain(w)
    expect(orderPosts()).toHaveLength(2)
    expect(bodyKeys()[1]).toBe(bodyKeys()[0])
  })
  it('a read sent INSIDE the window never frees the lock, however late its answer comes', async () => {
    const w = await unknownExit()
    await vi.advanceTimersByTimeAsync(125000)
    await flushPromises()
    expect(S(w).exitBlocked).toBe(true)
    await exitAgain(w)
    expect(orderPosts()).toHaveLength(1)
  })
  it('a stored exit (book moved) ends the action: the next exit of the same leg gets a NEW key', async () => {
    const w = await unknownExit()
    answers['GET /paper/strategies/86'] = afterExitOf(OPEN_IDS[0])
    await vi.advanceTimersByTimeAsync(6000)
    await flushPromises()
    answers['GET /paper/strategies/86'] = BOOK
    answers['POST /paper/strategies/86/orders'] = () => Promise.resolve({ data: { orders: [{ id: 5 }] } })
    await S(w).openPaperOrderbook()
    await flushPromises()
    await exitAgain(w)
    expect(orderPosts()).toHaveLength(2)
    expect(bodyKeys()[1]).not.toBe(bodyKeys()[0])
  })
})
