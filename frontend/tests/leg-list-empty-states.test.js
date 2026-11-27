// Live test 2026-11-27 10:26 IST (item 11): "Open in builder and prepare basket" of a full exit staged the exits, but the
// leg card said "No legs yet" (prepareApproach -> exitAllPaper -> setLegs([]) left the card with nothing to draw). The card
// now tells four empty answers apart: held legs being exited (rows + the staged exits), still loading, read failed, truly empty.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import LegList from '@/components/strategy/LegList.vue'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import { NO_LEGS_YET, CLOSED_TRADE_TEXT, emptyListKind } from '@/lib/legEdit'
import BOOK from '../../tests/fixtures/paper/strategy-63-roll.json'

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
const never = () => new Promise(() => {})
const HELD = BOOK.positions.filter((p) => p.net_quantity).map((p) => ({ id: `h${p.contract_id}`, contract_id: p.contract_id, underlying: 'NIFTY', instrument_id: `NSE_FO:${p.contract_id}`,
  expiry: p.expiry, instrument_type: p.instrument, strike: p.strike, lot_size: 65, action: p.net_quantity > 0 ? 'BUY' : 'SELL', lots: 1, planned_entry: '10.00' }))

describe('emptyListKind: one answer for an empty leg list', () => {
  it('rows when there are legs; exiting when held legs are staged for exit; loading and failed beat empty; empty otherwise', () => {
    expect(emptyListKind({ legs: [{}], held: HELD, loading: true, failed: true })).toBe('rows')
    expect(emptyListKind({ legs: [], held: HELD, loading: false, failed: false })).toBe('exiting')
    expect(emptyListKind({ legs: [], held: [], loading: true, failed: false })).toBe('loading')
    expect(emptyListKind({ legs: [], held: [], loading: false, failed: true })).toBe('failed')
    expect(emptyListKind({ legs: [], held: [], loading: false, failed: false })).toBe('empty')
  })
})
describe('LegList empty states', () => {
  it('staged exits: the held legs are listed as exiting, never "No legs yet"', () => {
    const w = mount(LegList, { props: { legs: [], heldLegs: HELD } })
    expect(t(w, 'no-legs-text').exists()).toBe(false)
    expect(w.findAll('[data-testid="exiting-leg"]')).toHaveLength(HELD.length)
    expect(t(w, 'exiting-label').exists()).toBe(true)
  })
  it('still loading: the opening card, not "No legs yet"', () => {
    const w = mount(LegList, { props: { legs: [], opening: true } })
    expect(t(w, 'opening-card').exists()).toBe(true)
    expect(w.text()).not.toContain(NO_LEGS_YET)
  })
  it('read failed: no "No legs yet" (the page shows the error line)', () => {
    const w = mount(LegList, { props: { legs: [], failed: true } })
    expect(w.text()).not.toContain(NO_LEGS_YET)
    expect(t(w, 'no-legs-add').exists()).toBe(false)
    expect(t(w, 'exiting-leg').exists()).toBe(false)
  })
  it('truly empty draft: "No legs yet" with Add leg and Pick from Option Chain', () => {
    const w = mount(LegList, { props: { legs: [] } })
    expect(t(w, 'no-legs-text').text()).toBe(NO_LEGS_YET)
    expect(t(w, 'no-legs-add').exists()).toBe(true)
  })
})
describe('the page: Compare -> prepare a full exit', () => {
  beforeEach(() => {
    calls.length = 0
    answers = { 'GET /catalogue/NIFTY/contracts?expiry=2026-11-03': { underlying: 'NIFTY', contracts: BOOK.positions.map((p) => ({ contract_id: p.contract_id, exchange_segment: 'NSE_FO', exchange_token: p.contract_id, instrument_type: p.instrument, expiry: p.expiry, strike: p.strike, lot_size: 65, symbol: `NIFTY${p.strike}${p.instrument}` })) }, 'GET /paper/strategies/63': BOOK, 'GET /strategies': { strategies: [] }, 'POST /strategies/outcome': never, 'POST /strategies/leg-edit': never }
  })
  async function open(query) {
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
    await router.push({ path: '/strategy/builder', query })
    await router.isReady()
    const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true, AdjustCompare: true } } })
    await flushPromises()
    return w
  }
  it('after the exits are staged (confirm list closed) the card shows the held legs and the pending count, not "No legs yet"', async () => {
    const w = await open({ adjust: '63', pick: 'A-04', opp: '41' })
    await w.vm.$.setupState.prepareApproach({ legs: [], suggestionIds: ['41'], basketLegs: 2, exit: true })
    await flushPromises()
    w.vm.$.setupState.userCancelPaperDialog() // the user's own Cancel keeps the staged exits as edits
    await flushPromises()
    const n = w.vm.$.setupState.pendingOrders.length
    expect(n).toBeGreaterThan(0)
    expect(t(w, 'no-legs-text').exists()).toBe(false)
    expect(w.findAll('[data-testid="exiting-leg"]')).toHaveLength(n)
    expect(t(w, 'paper-pending-count').text()).toBe(`${n} pending changes`)
  })
  it('while the strategy read is out: loading, not "No legs yet"; a failed read: the open-error line, not "No legs yet"', async () => {
    answers['GET /paper/strategies/63'] = never
    const w = await open({ strategy: '63' })
    expect(t(w, 'opening-card').exists()).toBe(true)
    expect(t(w, 'no-legs-text').exists()).toBe(false)
    answers['GET /paper/strategies/63'] = () => Promise.reject(new Error('network'))
    const f = await open({ strategy: '63' })
    expect(t(f, 'open-error').exists()).toBe(true)
    expect(t(f, 'no-legs-text').exists()).toBe(false)
  })
})
describe('item 8: a closed (Completed / settled) trade never invites a new leg', () => {
  const CLOSED_BOOK = { ...BOOK, state: 'completed', closed: [{ id: 'c1' }], positions: BOOK.positions.map((p) => ({ ...p, net_quantity: 0 })) }
  const open = async (book, query) => {
    answers = { 'GET /catalogue/NIFTY/contracts?expiry=2026-11-03': { underlying: 'NIFTY', contracts: [] }, 'GET /paper/strategies/63': book, 'GET /strategies': { strategies: [] }, 'POST /strategies/outcome': never, 'POST /strategies/leg-edit': never }
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
    await router.push({ path: '/strategy/builder', query })
    await router.isReady()
    const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true, AdjustCompare: true } } })
    await flushPromises()
    return w
  }
  it('emptyListKind: done:true gives the closed kind; held and rows still win; loading and failed come first', () => {
    expect(emptyListKind({ legs: [], held: [], done: true })).toBe('closed')
    expect(emptyListKind({ legs: [], held: [], loading: true, done: true })).toBe('loading')
    expect(emptyListKind({ legs: [{}], done: true })).toBe('rows')
  })
  it('closed trade: the right side says it is closed, not "Add a leg to start one"', async () => {
    const w = await open(CLOSED_BOOK, { strategy: '63' })
    expect(w.text()).not.toContain('No draft strategy is open')
    expect(w.text()).not.toContain('Add a leg to start one')
    expect(t(w, 'state-closed').text()).toBe(CLOSED_TRADE_TEXT)
  })
  it('a running trade does not show the closed text; a fresh builder keeps "No draft strategy is open"', async () => {
    const run = await open(BOOK, { strategy: '63' })
    expect(t(run, 'state-closed').exists()).toBe(false)
    const fresh = await open(BOOK, {})
    expect(t(fresh, 'state-closed').exists()).toBe(false)
    expect(t(fresh, 'state-no-draft').text()).toBe('No draft strategy is open. Add a leg to start one.')
  })
})
