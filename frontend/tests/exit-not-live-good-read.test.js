// Lane U hotfix (27 Nov 2026, 15:06-15:12 IST, feed process stopped, API up; trade A-H #209): the builder's paper Exit dialog showed NO not-live
// sentence and Confirm stayed enabled while Home said "Paper P&L paused - prices not live". The gate was true only on a FAILED read.
// Spec basis: ADR-330 exit rule (a blocked control says why, ADR-328 (4)); REQ-109 AC-5 / ADR-322 (3) (a leg with no live price is refused with
// "Prices are not live; try again when they update"; judged per leg); ADR-016..019 (fail closed: a missing field is not live).
// The reply shapes are the server's when the feed is down (ofo_app/routes/paper.py `_figures`: state PAUSED, every open position's
// price_state not 'live', ltp / unbooked / total null, pause_reason prices_not_live), on the builder's book read and the Positions list read.
// ONE rule (lib/usePaperExit.js exitLegsNotLive), read by both dialogs.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'
import { TRACKING_REFRESH_MS } from '@/lib/tracking'
import { exitLegsNotLive } from '@/lib/usePaperExit'
import REAL from './fixtures/paper-book-63.json'
import { withPriceTexts } from './_priceTexts'
import { legacy } from './_paperList'

const NOT_LIVE = 'Prices are not live; try again when they update'
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
const orderPosts = () => calls.filter((c) => c.method === 'POST' && /\/orders$/.test(c.url))
const mounted = []
beforeEach(() => { vi.useFakeTimers() })
afterEach(() => { vi.useRealTimers(); while (mounted.length) mounted.pop().unmount(); document.body.innerHTML = '' })

// ---- the one rule, every answer state --------------------------------------------------------------------------------------------
describe('exitLegsNotLive: the ONE rule (per ticked leg; fail closed)', () => {
  const pos = [{ id: 1, live: true }, { id: 2, live: false }, { id: 3, live: true }]
  it('live: every ticked leg live -> not blocked', () => { expect(exitLegsNotLive('LIVE', pos, [1, 3])).toBe(false) })
  it('not live: one ticked leg not live -> blocked', () => { expect(exitLegsNotLive('LIVE', pos, [1, 2])).toBe(true) })
  it('paused book: judged per ticked leg (ADR-322 (3)): a live-priced leg may exit, the unpriced one may not', () => {
    expect(exitLegsNotLive('PAUSED', pos, [1, 3])).toBe(false)
    expect(exitLegsNotLive('PAUSED', pos, [2])).toBe(true)
  })
  it('not connected: blocked for every leg, whatever the leg flags say', () => { expect(exitLegsNotLive('NOT_CONNECTED', pos, [1])).toBe(true) })
  it('unknown / missing state: blocked (fail closed)', () => {
    expect(exitLegsNotLive(undefined, pos, [1])).toBe(true)
    expect(exitLegsNotLive('WEIRD', pos, [1])).toBe(true)
  })
  it('a ticked leg the read does not list, or whose live flag is not exactly true: blocked', () => {
    expect(exitLegsNotLive('LIVE', pos, [9])).toBe(true)
    expect(exitLegsNotLive('LIVE', [{ id: 1 }], [1])).toBe(true)
    expect(exitLegsNotLive('LIVE', [{ id: 1, live: 'live' }], [1])).toBe(true)
    expect(exitLegsNotLive('LIVE', undefined, [1])).toBe(true)
  })
  it('no ticked legs: nothing to judge (an entry-only dialog is ADR-330 (28)\'s own line)', () => {
    expect(exitLegsNotLive('LIVE', pos, [])).toBe(false)
    expect(exitLegsNotLive('PAUSED', pos, [])).toBe(false)
  })
})

// ---- the builder's book read -------------------------------------------------------------------------------------------------------
const CONTRACTS = REAL.positions.map((p) => ({ contract_id: p.contract_id, exchange_segment: 'NSE_FO', exchange_token: p.contract_id,
  instrument_type: p.instrument, expiry: p.expiry, strike: p.strike, lot_size: 65, symbol: `NIFTY${p.strike}${p.instrument}` }))
const LIVE_BOOK = { ...REAL, strategy_id: 86, name: '"IC"' }
// the server's book with the feed down (`_figures`: state PAUSED / pause_reason prices_not_live; every open position stale, no ltp, no unbooked)
const feedDown = (book, priceState = 'stale') => ({
  ...book, state: 'PAUSED', pause_reason: 'prices_not_live', as_of: '2026-11-27T09:36:00Z', total: null, total_text: null, unbooked: null, unbooked_text: null,
  total_after: null, total_after_text: null,
  positions: book.positions.map((p) => (p.net_quantity === 0 ? p : { ...p, price_state: priceState, ltp: null, ltp_text: null, price_at: null, unbooked: null, unbooked_text: null, total: null, total_text: null })),
})
const NOT_LIVE_BOOK = feedDown(LIVE_BOOK)
const MISSING_FIELD_BOOK = { ...LIVE_BOOK, positions: LIVE_BOOK.positions.map((p) => { const { price_state: _drop, ...rest } = p; return rest }) }
const router = () => createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
async function builder(book = LIVE_BOOK) {
  calls.length = 0
  answers = {
    'GET /strategies': { strategies: [] },
    'POST /paper/strategies/86/orders': LIVE_BOOK,
    'GET /paper/strategies/86': book,
    'GET /catalogue/NIFTY/contracts?expiry=2026-11-03': { underlying: 'NIFTY', contracts: CONTRACTS },
    'POST /strategies/outcome': () => new Promise(() => {}),
    'POST /strategies/leg-edit': () => new Promise(() => {}),
  }
  const r = router()
  await r.push('/strategy/builder?strategy=86')
  await r.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [r], stubs: { PayoffChart: true } }, attachTo: document.body })
  mounted.push(w)
  await flushPromises()
  return w
}
const read = async (book) => { answers['GET /paper/strategies/86'] = book; await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS); await flushPromises() }
const names = (w) => w.vm.$.setupState.paperRows.map((r) => r.text).join(', ')
const confirmOff = (w) => t(w, 'paper-confirm-button').attributes('disabled') !== undefined

describe('builder: the Exit dialog on a GOOD read whose legs are not live (A-H #209, 27 Nov)', () => {
  it('good read not live, Exit all: the dialog shows "<legs>: Prices are not live..." and Confirm is disabled; posting nothing', async () => {
    const w = await builder(NOT_LIVE_BOOK)
    await t(w, 'paper-exit-all').trigger('click')
    await flushPromises()
    expect(t(w, 'paper-confirm').exists()).toBe(true)
    expect(names(w)).not.toBe('')
    expect(t(w, 'paper-error').text()).toBe(`No price for ${names(w)}`) // Lane FJ r3 (TD O-3): every leg without a price is named
    expect(confirmOff(w)).toBe(true)
    await w.vm.$.setupState.confirmPending(w.vm.$.setupState.paperRows) // a Confirm that reaches the page posts nothing
    expect(orderPosts()).toHaveLength(0)
  })

  it('the next good read with prices live: the sentence is gone and Confirm is enabled again', async () => {
    const w = await builder(NOT_LIVE_BOOK)
    await t(w, 'paper-exit-all').trigger('click')
    await flushPromises()
    expect(confirmOff(w)).toBe(true)
    await read(LIVE_BOOK)
    expect(t(w, 'paper-confirm').exists()).toBe(true)
    expect(t(w, 'paper-error').exists()).toBe(false)
    expect(confirmOff(w)).toBe(false)
  })

  it('opened while live, then a good read turns not live: blocked at once, sentence shown, dialog stays', async () => {
    const w = await builder(LIVE_BOOK)
    await t(w, 'paper-exit-all').trigger('click')
    await flushPromises()
    expect(confirmOff(w)).toBe(false)
    await read(NOT_LIVE_BOOK)
    expect(t(w, 'paper-confirm').exists()).toBe(true)
    expect(t(w, 'paper-error').text()).toBe(`No price for ${names(w)}`) // Lane FJ r3 (TD O-3): every leg without a price is named
    expect(confirmOff(w)).toBe(true)
    expect(orderPosts()).toHaveLength(0)
  })

  it('a leg\'s live flag missing from the read (unknown): fail closed, same sentence, Confirm disabled', async () => {
    const w = await builder(MISSING_FIELD_BOOK)
    await t(w, 'paper-exit-all').trigger('click')
    await flushPromises()
    expect(t(w, 'paper-error').text()).toBe(`No price for ${names(w)}`) // Lane FJ r3 (TD O-3): every leg without a price is named
    expect(confirmOff(w)).toBe(true)
  })

  it('state "missing" on the legs reads the same as stale', async () => {
    const w = await builder(feedDown(LIVE_BOOK, 'missing'))
    await t(w, 'paper-exit-all').trigger('click')
    await flushPromises()
    expect(confirmOff(w)).toBe(true)
    expect(t(w, 'paper-error').text()).toMatch(/^No price for /)
  })

  it('a "Review and add" dialog of an ADD only, on a not-live read, is not an Exit: ADR-330 (28) owns its line, Confirm is not blocked by this rule', async () => {
    const w = await builder(NOT_LIVE_BOOK)
    const net = w.vm.$.setupState.paper.net
    w.vm.$.setupState.setLegs(net.map((l, i) => (i === 0 ? { ...l, lots: 9 } : { ...l })))
    await flushPromises()
    await t(w, 'paper-review').trigger('click')
    await flushPromises()
    expect(t(w, 'paper-confirm').exists()).toBe(true)
    expect(w.vm.$.setupState.paperRows.every((r) => r.kind === 'add')).toBe(true)
    expect(t(w, 'paper-error').exists() ? t(w, 'paper-error').text() : '').not.toContain(NOT_LIVE)
  })
})

// ---- the Positions list read ------------------------------------------------------------------------------------------------------
const leg = (i, over = {}) => withPriceTexts({
  leg_index: i, instrument_id: `NSE_FO:${i + 1}`, action: i % 2 ? 'SELL' : 'BUY', instrument: i < 2 ? 'PE' : 'CE',
  strike: `${22300 + i * 100}.00`, expiry: '2026-11-03', quantity: 65, entry_price: '114.25', entry_at: '2026-10-28T05:03:09Z',
  current_price: '113.60', price_state: 'live', price_at: '2026-10-28T11:30:00+05:30', exit_price: null, exited_at: null, ...over,
})
const item = (over = {}, legOver = {}) => withPriceTexts({
  strategy_id: 48, name: '"A-H"', underlying: 'NIFTY', started_at: '2026-10-28T05:03:10Z', state: 'LIVE',
  pause_reason: null, as_of: null, total: '71.50', booked: '0.00', unbooked: '71.50', legs: [leg(0, legOver), leg(1, legOver), leg(2, legOver), leg(3, legOver)], ...over,
})
const LIST_LIVE = { strategies: [item()], answered_at: '2026-10-28T06:00:00Z' }
const LIST_DOWN = { strategies: [item({ state: 'PAUSED', pause_reason: 'prices_not_live', as_of: '2026-10-28T06:00:00Z', total: null, unbooked: null }, { price_state: 'stale', current_price: null })], answered_at: '2026-10-28T06:00:01Z' }
const LIST_NO_FIELD = { strategies: [item({}, { price_state: undefined })], answered_at: '2026-10-28T06:00:01Z' }
const ok = (data) => () => Promise.resolve({ data })
async function positions(list, path = '/positions/current-positions?tab=paper&exit=48') {
  calls.length = 0
  answers = { 'GET /tracking': ok(list) }
  const r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }, { path: '/positions/current-positions', component: { template: '<div/>' } }, { path: '/strategy/builder', component: { template: '<div/>' } }] })
  r.push(path)
  await r.isReady()
  const w = mount(PaperStrategies, { global: { plugins: [r] } })
  mounted.push(w)
  await flushPromises()
  return w
}
const dlg = (w) => w.findComponent(PaperConfirmDialog)
const listRead = async (list) => { answers['GET /tracking'] = ok(list); await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS); await flushPromises() }

describe('Positions: the Exit dialog on a GOOD list read whose legs are not live', () => {
  // Lane FJ r3 (28 Nov, PC O-A-12): a greyed Exit opens no dialog, link included (exit-greyed-no-dialog-r3-fj.test.js); the dialog is blocked only when it was open and a read turned not live
  it('opened while live, then not live, then live again: blocked, then unblocked, the sentence gone', async () => {
    const w = await positions(LIST_LIVE)
    await listRead(LIST_DOWN)
    expect(dlg(w).props('blocked')).toBe(true)
    await listRead(LIST_LIVE)
    expect(dlg(w).props('open')).toBe(true)
    expect(dlg(w).props('blocked')).toBe(false)
    expect(dlg(w).props('error')).toBe('')
  })

  it('opened while live, then a good read turns not live: blocked at once', async () => {
    const w = await positions(LIST_LIVE)
    expect(dlg(w).props('open')).toBe(true)
    expect(dlg(w).props('blocked')).toBe(false)
    await listRead(LIST_DOWN)
    expect(dlg(w).props('open')).toBe(true)
    expect(dlg(w).props('blocked')).toBe(true)
    expect(dlg(w).props('error')).toMatch(/^No price for /)
  })

  it('a leg\'s price_state missing (unknown): fail closed: the link opens the dialog with Confirm off; opened live then unknown it is blocked', async () => {
    const w = await positions(LIST_NO_FIELD)
    expect(dlg(w).props('open')).toBe(true)
    expect(dlg(w).props('blocked')).toBe(true)
    expect(dlg(w).props('error')).toMatch(/^No price for /)
    expect(calls.filter((c) => c.method === 'POST')).toHaveLength(0)
    const v = await positions(LIST_LIVE)
    await listRead(LIST_NO_FIELD)
    expect(dlg(v).props('blocked')).toBe(true)
    expect(dlg(v).props('error')).toMatch(/^No price for /)
  })

  it('doExit called directly (not via the button) while a ticked leg is not live on a GOOD read: no POST, the not-live sentence stays', async () => {
    const w = await positions(LIST_LIVE)
    await listRead(LIST_DOWN)
    expect(dlg(w).props('open')).toBe(true)
    await w.vm.$.setupState.doExit(dlg(w).props('orders'))
    await flushPromises()
    expect(calls.filter((c) => c.method === 'POST')).toHaveLength(0)
    expect(dlg(w).props('error')).toMatch(/^No price for /)
  })

  it('failed read keeps the existing behaviour: no dialog is opened from old prices', async () => {
    calls.length = 0
    answers = { 'GET /tracking': () => Promise.reject({ message: 'x', parts: null, status: 500 }) }
    const r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }, { path: '/positions/current-positions', component: { template: '<div/>' } }] })
    r.push('/positions/current-positions?tab=paper&exit=48')
    await r.isReady()
    const w = mount(PaperStrategies, { global: { plugins: [r] } })
    mounted.push(w)
    await flushPromises()
    expect(dlg(w).props('open')).toBe(false)
  })
})
