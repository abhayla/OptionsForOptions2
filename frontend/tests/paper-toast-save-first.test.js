// GC-TP step 3b2, R-6 (live 2026-10-29): after Add to Paper on an UNSAVED strategy (saved first, the URL moves to ?strategy=N) the
// "Added to Paper" toast was not on screen 2 s and 5 s after Confirm. The REAL StrategyBuilderPage, the save-first path end to end:
// unsaved legs -> Add to Paper -> POST /strategies -> route ?strategy=70 -> Confirm -> POST orders -> the toast is there and stays.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import { netLegsFromBook } from '@/lib/paperDrafts'
import { PAPER_ADDED_TEXT } from '@/lib/tracking'
import REAL from './fixtures/paper-book-63.json'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    const a = answers[`${method} ${url}`]
    if (a === undefined) return Promise.reject(new Error(`unmocked ${method} ${url}`))
    return typeof a === 'function' ? a(body) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u, b) => respond('POST', u, b), put: (u, b) => respond('PUT', u, b) } }
})

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const CONTRACTS = REAL.positions.map((p) => ({ contract_id: p.contract_id, exchange_segment: 'NSE_FO', exchange_token: p.contract_id,
  instrument_type: p.instrument, expiry: p.expiry, strike: p.strike, lot_size: 65, symbol: `NIFTY${p.strike}${p.instrument}` }))
// an unsaved plan of the book's 4 open contracts, entries at the book's averages
const PLAN = () => netLegsFromBook(REAL, CONTRACTS).map((l, i) => ({ ...l, id: `leg-${i}`, typed: false, captured_at: REAL.answered_at }))
const BOOK_70 = { ...REAL, strategy_id: 70, name: '"Iron"' }

beforeEach(() => {
  calls.length = 0
  answers = {
    'GET /strategies': { strategies: [] },
    'POST /strategies': { id: 70, revision: 1, name: '"Iron"' },
    'POST /paper/strategies/70/orders': BOOK_70,
    'GET /paper/strategies/70': BOOK_70,
    'GET /catalogue/NIFTY/contracts?expiry=2026-11-03': { underlying: 'NIFTY', contracts: CONTRACTS },
    'POST /strategies/outcome': () => new Promise(() => {}),
    'POST /strategies/leg-edit': () => new Promise(() => {}),
  }
})
afterEach(() => vi.useRealTimers())

describe('R-6: the "Added to Paper" toast after the save-first path', () => {
  it('unsaved -> save -> ?strategy=70 -> Confirm: the toast is on screen at once, at 2 s and at 5 s', async () => {
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }, { path: '/positions/current-positions', component: { template: '<p />' } }] })
    await router.push('/strategy/builder')
    await router.isReady()
    const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true } } })
    await flushPromises()
    w.vm.$.setupState.setLegs(PLAN())
    await flushPromises()
    await t(w, 'add-to-paper').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.strategy).toBe('70') // saved first, the URL names it
    expect(calls.filter((c) => c.method === 'POST' && c.url === '/strategies')).toHaveLength(1)
    vi.useFakeTimers()
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(calls.filter((c) => c.url === '/paper/strategies/70/orders')).toHaveLength(1)
    expect(t(w, 'paper-toast-message').text()).toBe(PAPER_ADDED_TEXT)
    // fixed to the viewport: never inside the left column's own scroll, where it could be in the page but off screen
    expect(t(w, 'paper-toast').attributes('data-placement')).toBe('viewport')
    expect(t(w, 'paper-toast').classes()).toContain('fixed')
    for (const ms of [2000, 3000]) {
      vi.advanceTimersByTime(ms)
      await flushPromises()
      expect(t(w, 'paper-toast').exists(), `after ${ms} ms more`).toBe(true)
    }
    vi.advanceTimersByTime(3500) // 8.5 s: gone
    await flushPromises()
    expect(t(w, 'paper-toast').exists()).toBe(false)
  })
})
