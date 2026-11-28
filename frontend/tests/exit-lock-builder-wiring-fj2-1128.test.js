// Lane F1 (FJ2) I-139 (GitHub 870, 873) page wiring in the BUILDER + I-14: after an exit whose outcome is UNKNOWN the page's Exit stays locked until the page has RE-READ the trade: not released by a timer, by closing the dialog or by a failing read, also in a second tab; the dialog then says the one unknown sentence and offers no retry.
// (harness copied from exit-unknown-remount-r2-fb2.test.js)
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


async function remount() {
  const r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await r.push('/strategy/builder?strategy=86')
  await r.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [r], stubs: { PayoffChart: true } }, attachTo: document.body })
  mounted.push(w)
  await flushPromises()
  return w
}


import { PAPER_UNKNOWN_TEXT } from '@/lib/tracking'
import { dropExitLock, exitLockFor } from '@/lib/unknownLocks'
const TAB_BOOK = () => BOOK
async function secondTab() { return remount() }
const tryExit = async (w) => {
  S(w).exitPaper(OPEN_IDS[0], 1)
  await flushPromises()
  const b = t(w, 'paper-confirm-button')
  if (b.exists()) await b.trigger('click')
  await flushPromises()
}

describe('I-139 builder wiring', () => {
  it('closing the dialog does not release the lock: Cancel, reopen Exit 20 s later, Confirm sends nothing', async () => {
    const w = await unknownExit()
    expect(orderPosts()).toHaveLength(1)
    await t(w, 'paper-cancel').trigger('click')
    await flushPromises()
    await vi.advanceTimersByTimeAsync(20000)
    expect(S(w).exitBlocked).toBe(true)
    await tryExit(w)
    expect(orderPosts()).toHaveLength(1)
  })
  it('a failing book read after the unknown answer and ten minutes of timers: still locked, nothing sent (a timer never releases)', async () => {
    const w = await unknownExit()
    answers['GET /paper/strategies/86'] = () => Promise.reject({ status: 500, message: 'x', parts: null })
    await vi.advanceTimersByTimeAsync(600000)
    expect(S(w).exitBlocked).toBe(true)
    await tryExit(w)
    expect(orderPosts()).toHaveLength(1)
  })
  it('a second tab (the first still open): its Exit is locked and sends nothing', async () => {
    await unknownExit()
    const second = await secondTab()
    expect(S(second).exitBlocked).toBe(true)
    await tryExit(second)
    expect(orderPosts()).toHaveLength(1)
  })
})

describe('I-139 second tab (Lane W2): released by the first tab\'s decision', () => {
  it('the first tab decided (stored) and removed the lock: this tab is released at once, reads the book again, sends nothing', async () => {
    await unknownExit()
    const second = await secondTab()
    expect(S(second).exitBlocked).toBe(true)
    answers['GET /paper/strategies/86'] = afterExitOf(OPEN_IDS[0]) // the book moved: the exit was stored
    dropExitLock(86, exitLockFor(86)) // the first tab decided THIS lock (Lane F1b: it passes the lock it decided, so its decided marker is written) and removed it from the store
    window.dispatchEvent(new StorageEvent('storage', { key: 'ofo.exitUnknown' })) // the browser tells the other tab
    await flushPromises()
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()
    expect(S(second).exitBlocked).toBe(false)
    expect(document.body.textContent).not.toContain('could not confirm')
    expect(orderPosts()).toHaveLength(1)
  })
})

describe('I-14 the unknown-result sentence (builder dialog)', () => {
  it('says the one unknown sentence; no "placed", no "failed", no retry; Confirm stays off', async () => {
    const w = await unknownExit()
    const say = t(w, 'paper-unknown')
    expect(say.exists()).toBe(true)
    expect(say.text()).toContain(PAPER_UNKNOWN_TEXT)
    expect(say.text().replace(PAPER_UNKNOWN_TEXT, '').trim()).toBe('Open Orderbook') // the only thing beside the sentence is the way to read the book
    const text = document.body.textContent
    expect(text).not.toMatch(/placed on paper|Exit placed|failed|could not be sent/i)
    expect(t(w, 'paper-placed').exists()).toBe(false)
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeDefined()
    expect([...document.querySelectorAll('button')].map((b) => b.textContent.trim()).filter((x) => /retry|try again/i.test(x))).toEqual([])
  })
  it('the stored case (I-14 first half, fixed earlier): once the book shows the exit stored, "could not confirm" is gone', async () => {
    const w = await unknownExit()
    answers['GET /paper/strategies/86'] = afterExitOf(OPEN_IDS[0])
    await t(w, 'paper-open-orderbook').trigger('click')
    await flushPromises()
    expect(document.body.textContent).not.toContain('could not confirm')
    expect(S(w).exitBlocked).toBe(false)
    expect(orderPosts()).toHaveLength(1)
  })
})
