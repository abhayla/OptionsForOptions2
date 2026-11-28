// Lane FJ (R3) item 6 (F6, page half): a refused order prints every part of the server's reply as sent (what happened, impact, what is blocked, next action), not only the first.
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


import SaveDraftBar from '@/components/strategy/SaveDraftBar.vue'
const PARTS = { what_happened: 'NIFTY 13 Oct 22400 PE is the same contract as leg 1.', impact: 'Two legs on one contract would be sent as separate orders.', what_is_blocked: 'Execution.', next_action: 'Edit the strategy so each contract appears in one leg only.' }
const ALL = Object.values(PARTS).join(' ')
describe('item 6 F6: every part of a refusal is printed', () => {
  it('the builder: a refused exit shows all four parts in the dialog', async () => {
    calls.length = 0
    answers = {
      'GET /strategies': { strategies: [] },
      'POST /paper/strategies/86/orders': () => Promise.reject({ status: 422, message: 'x', code: 'gate_duplicate_leg', parts: PARTS }),
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
    expect(t(w, 'paper-error').text()).toBe(ALL)
  })
  it('the builder: a refusal with only some parts prints those, in order; with none, the neutral sentence', async () => {
    const { exitEndText } = await import('@/lib/usePaperExit')
    expect(exitEndText('refused', [], { what_happened: 'A', next_action: 'D' }, 'N')).toBe('A D')
    expect(exitEndText('refused', [], null, 'N')).toBe('N')
  })
  it('Add to Paper (SaveDraftBar): a refused order prints all four parts', async () => {
    answers = { 'GET /strategies': { strategies: [] }, 'POST /paper/strategies/7/orders': () => Promise.reject({ status: 422, message: 'x', parts: PARTS }),
      'GET /market/exit-state': { closed: false, sentence: null, next_open_at: null } }
    const mk = (id) => ({ id, underlying: 'NIFTY', instrument_id: `NSE_FO:${id}`, contract_id: 103, lot_size: 65, action: 'SELL', lots: 1, expiry: '2026-10-13', strike: '22400.00', instrument_type: 'PE', planned_entry: '95.00', captured_at: '2026-10-08T09:20:09+05:30' })
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }] })
    router.push('/')
    await router.isReady()
    const w = mount(SaveDraftBar, { props: { legs: [mk(1), mk(2)], current: { id: 7, revision: 1, name: '"Dup"' } }, global: { plugins: [router] }, attachTo: document.body })
    mounted.push(w)
    await flushPromises()
    await t(w, 'add-to-paper').trigger('click')
    await flushPromises()
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(t(w, 'paper-error').text()).toBe(ALL)
  })
})
