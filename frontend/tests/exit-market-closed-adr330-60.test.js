// Lane U2, item 2 (ADR-330 (60), ADR-212, ADR-330 (58)): while the market is closed an Exit dialog opens, lists its legs, shows the server's one
// sentence and has Confirm off; builder (per-leg Exit and Exit all) and the dialog component itself (the Positions dialog is the same component).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
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
const OPEN_IDS = BOOK.positions.filter((p) => p.net_quantity !== 0).map((p) => p.contract_id) // [5572, 5587, 5585, 5574]
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


const CLOSED = 'The market is closed. Exits can be placed from 09:15 on Monday 30 Nov.'
const closedAnswer = { closed: true, sentence: CLOSED, next_open_at: '2026-11-30T09:15:00+05:30' }
const marketGets = () => calls.filter((c) => c.method === 'GET' && c.url === '/market/exit-state')

describe('ADR-330 (60): the Exit dialog when the market is closed (builder)', () => {
  it('per-leg Exit: the dialog opens with the leg, the server sentence, Confirm off, nothing posted', async () => {
    const w = await builder()
    answers['GET /market/exit-state'] = closedAnswer
    S(w).exitPaper(OPEN_IDS[0], 1)
    await flushPromises()
    expect(S(w).paperDialog).toBe(true)
    expect(S(w).paperRows).toHaveLength(1)
    expect(t(w, 'paper-market-closed').text()).toBe(CLOSED)
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeDefined()
    await t(w, 'paper-confirm-button').trigger('click')
    expect(orderPosts()).toHaveLength(0)
  })
  it('Exit all: the same line, one row per open leg, Confirm off', async () => {
    const w = await builder()
    answers['GET /market/exit-state'] = closedAnswer
    S(w).exitAllPaper()
    await flushPromises()
    expect(S(w).paperRows).toHaveLength(OPEN_IDS.length)
    expect(t(w, 'paper-market-closed').text()).toBe(CLOSED)
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeDefined()
  })
  it('the market-closed line wins over the not-live line (both legs not live and market closed)', async () => {
    const w = await builder()
    answers['GET /market/exit-state'] = closedAnswer
    S(w).exitPaper(OPEN_IDS[0], 1)
    await flushPromises()
    expect(w.text()).not.toContain('Prices are not live; try again when they update') // inside the dialog's status slot
    expect(t(w, 'paper-status-slot').text()).toBe(CLOSED)
  })
  it('open market: the question is asked once per opening, no market line, Confirm on', async () => {
    const w = await builder()
    S(w).exitPaper(OPEN_IDS[0], 1)
    await flushPromises()
    expect(marketGets()).toHaveLength(1)
    expect(w.find('[data-testid="paper-market-closed"]').exists()).toBe(false)
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeUndefined()
  })
  it('answer states: unreadable (failed), ambiguous (no sentence) and absent each keep Confirm off with the page line', async () => {
    for (const a of [() => Promise.reject(new Error('x')), { closed: true, sentence: null }, { closed: null }, {}]) {
      const w = await builder()
      answers['GET /market/exit-state'] = a
      S(w).exitPaper(OPEN_IDS[0], 1)
      await flushPromises()
      expect(t(w, 'paper-market-closed').text()).toBe('The market status could not be read. Try again in a moment.')
      expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeDefined()
    }
  })
  it('while the market answer is late, Confirm is off and nothing posts (checking)', async () => {
    const w = await builder()
    answers['GET /market/exit-state'] = () => new Promise(() => {})
    S(w).exitPaper(OPEN_IDS[0], 1)
    await flushPromises()
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeDefined()
    await t(w, 'paper-confirm-button').trigger('click')
    expect(orderPosts()).toHaveLength(0)
  })
  it('an entry-only dialog never asks (ADR-330 (60) is the Exit dialog)', async () => {
    const w = await builder()
    S(w).setLegs(S(w).paper.net.map((l, i) => (i === 1 ? { ...l, lots: 2 } : { ...l })))
    await flushPromises()
    S(w).reviewPending(false)
    await flushPromises()
    expect(S(w).paperDialog).toBe(true)
    expect(marketGets()).toHaveLength(0)
  })
})
