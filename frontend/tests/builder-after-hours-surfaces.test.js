// GC-BM step 9 fix round 1 (Tier A finding 1) and ADR-197: every after-hours number on the builder screen sits under the
// ONE market-closed banner ("Market closed. Prices are from <time>.", ADR-177, lib/sharedStateText.js through
// MarketClosedBanner): the page with NO legs (the index answer's market_closed / last_price_at; there is no outcome reply),
// the strike drawer (StrikesOut.market_closed / last_price_at) and the depth popup (DepthOut.market_closed /
// last_price_at). In market hours none of them shows it. ADR-197: a planned entry captured outside market hours is
// captioned as the close with the quote's own time ("Close, 8 Oct 2026, 15:29:58 IST"), never "captured <clock time>".
// The replies are the real route shapes (backend/ofo_app/routes/leg_picker.py StrikesOut / DepthOut, index_push.IndicesOut,
// planned_entry.PlannedEntryOut).
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises, enableAutoUnmount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'

let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    const a = answers[`${method} ${url}`] ?? answers[`${method} ${url.split('?')[0]}`]
    if (a === undefined) return Promise.reject(new Error(`unmocked ${method} ${url}`))
    return typeof a === 'function' ? a(body) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (url) => respond('GET', url), post: (url, body) => respond('POST', url, body) } }
})
class FakeSocket {
  constructor(url) { this.url = url; this.readyState = 0 }
  send() {}
  close() { this.readyState = 3 }
}

import LegPicker from '@/components/strategy/LegPicker.vue'
import LegList from '@/components/strategy/LegList.vue'
import DepthPopup from '@/components/strategy/DepthPopup.vue'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import { marketClosedText } from '@/lib/sharedStateText'
import { capturedCaption } from '@/lib/displayFormat'

const QUOTE_AT = '2026-10-08T15:29:58+05:30' // the quotes' own last-price time (the close)
const AFTER_CLOSE = '2026-10-08T18:00:00+05:30'
const BANNER = marketClosedText('8 Oct 2026, 15:29:58 IST')
const GRID = ['22500.00', '22550.00']
const tok = (i, side) => 44000 + 2 * i + (side === 'pe' ? 1 : 0)
const cell = (i, side) => ({ instrument_id: `NSE_FO:${tok(i, side)}`, lot_size: 65, ltp: '151.30', oi: 3218475,
  iv_percent: '11.34', delta: '0.5730', health: 'stale', at: QUOTE_AT })
const strikesAnswer = (over = {}) => ({
  state: 'LIVE', reason: null, underlying: 'NIFTY', expiry: '2026-10-13', width: 10, spot: '22533.25', spot_at: QUOTE_AT,
  centre: 'LAST_KNOWN_SPOT', atm_strike: '22550.00', answered_at: AFTER_CLOSE, market_closed: true, last_price_at: QUOTE_AT,
  rows: GRID.map((strike, i) => ({ strike, is_atm: strike === '22550.00', ce: cell(i, 'ce'), pe: cell(i, 'pe') })),
  ...over,
})
const catalogue13 = {
  underlying: 'NIFTY',
  contracts: GRID.flatMap((strike, i) => ['ce', 'pe'].map((side) => ({
    contract_id: tok(i, side), exchange_segment: 'NSE_FO', exchange_token: tok(i, side), instrument_type: side.toUpperCase(),
    expiry: '2026-10-13', strike, lot_size: 65, symbol: `NIFTY26OCT${strike}${side.toUpperCase()}`,
  }))),
}
const depthAnswer = (over = {}) => ({
  state: 'AVAILABLE', reason: null, instrument_id: 'NSE_FO:44002',
  bids: [{ price: '151.20', quantity: 650 }], asks: [{ price: '151.40', quantity: 325 }],
  day_open: '140.00', day_high: '160.00', day_low: '135.00', prev_close: '138.00', last_trade_at: QUOTE_AT,
  day_stats_reason: null, read_at: AFTER_CLOSE, market_closed: true, last_price_at: QUOTE_AT, ...over,
})
const indices = (closed) => ({
  state: 'NOT_CONNECTED', answered_at: AFTER_CLOSE, market_closed: closed, last_price_at: closed ? QUOTE_AT : null,
  indices: [{ underlying: 'NIFTY', instrument_id: 'NSE_INDICES:256265', value: '22533.25', at: QUOTE_AT, health: 'stale' },
    { underlying: 'SENSEX', instrument_id: 'BSE_INDICES:265', value: '74000.00', at: QUOTE_AT, health: 'stale' }],
})

enableAutoUnmount(afterEach)
beforeEach(() => {
  setActivePinia(createPinia())
  vi.stubGlobal('WebSocket', FakeSocket)
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  answers = {
    'GET /catalogue/NIFTY/expiries': { underlying: 'NIFTY', expiries: ['2026-10-13'] },
    'GET /catalogue/SENSEX/expiries': { underlying: 'SENSEX', expiries: [] },
    'GET /catalogue/NIFTY/contracts': catalogue13,
    'GET /leg-picker/strikes': strikesAnswer(),
    'GET /leg-picker/depth': depthAnswer(),
  }
})
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks() })

const bannerTexts = (w) => w.findAll('[data-testid="market-closed-text"]').map((b) => b.text())

describe('attack 1: no legs at 18:00, the drawer and the page carry the banner', () => {
  it('the drawer: strike cells priced from the last close sit under the banner with the quotes\' own time', async () => {
    const w = mount(LegPicker, { props: { legs: [], active: true } })
    await flushPromises()
    await w.find('[data-testid="pick-expiry"]').setValue('2026-10-13')
    await flushPromises()
    expect(w.findAll('[data-testid="cell-ltp"]').map((c) => c.text())).toContain('151.30')
    expect(bannerTexts(w)).toEqual([BANNER])
  })

  it('the drawer in market hours: no banner', async () => {
    answers['GET /leg-picker/strikes'] = strikesAnswer({ market_closed: false, last_price_at: null })
    const w = mount(LegPicker, { props: { legs: [], active: true } })
    await flushPromises()
    await w.find('[data-testid="pick-expiry"]').setValue('2026-10-13')
    await flushPromises()
    expect(w.findAll('[data-testid="cell-ltp"]').length).toBeGreaterThan(0)
    expect(bannerTexts(w)).toEqual([])
  })

  async function openEmptyBuilder() {
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
    await router.push('/strategy/builder')
    await router.isReady()
    const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true, LegPicker: true } } })
    await flushPromises()
    return w
  }

  it('the page with no draft shows the banner from the index answer (no outcome reply exists)', async () => {
    answers['GET /api/market/indices'] = indices(true)
    const w = await openEmptyBuilder()
    expect(w.find('[data-testid="strategy-builder"]').attributes('data-state')).toBe('no-draft')
    expect(bannerTexts(w)).toEqual([BANNER])
  })

  it('the page with no draft in market hours: no banner', async () => {
    answers['GET /api/market/indices'] = indices(false)
    const w = await openEmptyBuilder()
    expect(bannerTexts(w)).toEqual([])
  })
})

describe('attack 2: the depth popup', () => {
  it('market_closed true: the held depth is shown under the banner with the quote\'s own time', async () => {
    const w = mount(DepthPopup, { props: { instrumentId: 'NSE_FO:44002', title: 'NIFTY 13 Oct 22500 CE' } })
    await flushPromises()
    expect(w.find('[data-testid="depth-table"]').exists()).toBe(true)
    expect(bannerTexts(w)).toEqual([BANNER])
  })

  it('market_closed false (in hours): no banner', async () => {
    answers['GET /leg-picker/depth'] = depthAnswer({ market_closed: false, last_price_at: null })
    const w = mount(DepthPopup, { props: { instrumentId: 'NSE_FO:44002', title: 'x' } })
    await flushPromises()
    expect(w.find('[data-testid="depth-table"]').exists()).toBe(true)
    expect(bannerTexts(w)).toEqual([])
  })
})

describe('ADR-197: an entry captured after hours is captioned as the close with the quote\'s own time', () => {
  it('capturedCaption: a close entry reads "Close, <quote time>", a live one keeps "captured HH:MM:SS"', () => {
    expect(capturedCaption('2026-10-08T18:55:36+05:30', AFTER_CLOSE, QUOTE_AT)).toBe('Close, 8 Oct 2026, 15:29:58 IST')
    expect(capturedCaption('2026-10-08T11:00:05+05:30', '2026-10-08T11:00:09+05:30')).toBe('captured 11:00:05')
    expect(capturedCaption('2026-10-08T11:00:05+05:30', '2026-10-08T11:00:09+05:30', null)).toBe('captured 11:00:05')
  })

  const leg = (over = {}) => ({
    id: 1, instrument_id: 'NSE_FO:44002', contract_id: 44002, exchange_segment: 'NSE_FO', exchange_token: 44002,
    instrument_type: 'CE', strike: '22500.00', expiry: '2026-10-13', lot_size: 65, symbol: 'NIFTY26OCT22500CE',
    action: 'SELL', lots: 1, planned_entry: '151.30', captured_at: '2026-10-08T18:55:36+05:30', source: 'ltp', ...over,
  })

  it('the leg row (LegList) shows the close caption, never the capture clock time', () => {
    const w = mount(LegList, { props: { legs: [leg({ close_at: QUOTE_AT })] } })
    expect(w.text()).toContain('Close, 8 Oct 2026, 15:29:58 IST')
    expect(w.text()).not.toContain('18:55:36')
  })

  it('the leg row in market hours keeps "captured HH:MM:SS"', () => {
    const w = mount(LegList, { props: { legs: [leg({ captured_at: '2026-10-08T11:00:05+05:30' })] } })
    expect(w.text()).toContain('11:00:05')
    expect(w.text()).not.toContain('Close,')
  })

  it('the drawer copies close_at from the planned-entry reply onto the leg it emits', async () => {
    answers['POST /strategies/planned-entry'] = (body) => Promise.resolve({ data: { answered_at: AFTER_CLOSE,
      entries: body.instrument_ids.map((id) => ({ exchange_segment: 'NSE_FO', exchange_token: Number(id.split(':')[1]),
        planned_entry: '151.30', captured_at: '2026-10-08T18:55:36+05:30', close_at: QUOTE_AT, source: 'ltp', reason_code: null })) } })
    const emitted = []
    const w = mount(LegPicker, { props: { legs: [], active: true, 'onUpdate:legs': (v) => emitted.push(v) } })
    await flushPromises()
    await w.find('[data-testid="pick-expiry"]').setValue('2026-10-13')
    await flushPromises()
    await w.find('[data-testid="strike-row"][data-strike="22500.00"] [data-testid="cell-ce"] [data-testid="cell-sell"]').trigger('click')
    await w.find('[data-testid="picker-done"]').trigger('click')
    await flushPromises()
    expect(emitted.at(-1)[0].close_at).toBe(QUOTE_AT)
  })
})

describe('ADR-197 round 2: the close label survives a leg edit and a draft link', () => {
  const base = { instrument_id: 'NSE_FO:44002', action: 'SELL', lots: 1, planned_entry: '151.30', captured_at: '2026-10-08T18:55:36+05:30' }

  it('a leg-edit request sends each leg\'s close_at back; the reply\'s close_at becomes the leg\'s', async () => {
    const { buildEditRequest, applyEditReply } = await import('@/lib/legEdit')
    const req = buildEditRequest('NIFTY', [{ ...base, close_at: QUOTE_AT }], { control: 'reset_prices' })
    expect(req.legs[0].close_at).toBe(QUOTE_AT)
    const inHours = buildEditRequest('NIFTY', [{ ...base }], { control: 'reset_prices' })
    expect(inHours.legs[0].close_at).toBeNull()
    const recaptured = '2026-10-08T15:29:59+05:30'
    const after = applyEditReply([{ ...base, close_at: QUOTE_AT }], { legs: [{ ...base, captured_at: '2026-10-08T19:00:00+05:30', close_at: recaptured, price_source: 'captured' }] })
    expect(after[0].close_at).toBe(recaptured)
    const live = applyEditReply([{ ...base }], { legs: [{ ...base, close_at: null, price_source: 'captured' }] })
    expect(live[0].close_at).toBeNull()
  })

  it('a draft link reopened later keeps the close label of each leg', async () => {
    answers['POST /strategies/outcome'] = { state: 'NOT_CONNECTED', status_label: 'x', legs: [], underlying: 'NIFTY' }
    answers['GET /api/market/indices'] = indices(true)
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
    await router.push({ path: '/strategy/builder', query: { draft: JSON.stringify({ underlying: 'NIFTY', legs: [{ ...base, close_at: QUOTE_AT }] }) } })
    await router.isReady()
    const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true, LegPicker: true } } })
    await flushPromises()
    expect(w.text()).toContain('Close, 8 Oct 2026, 15:29:58 IST')
    expect(w.text()).not.toContain('captured 18:55:36')
  })
})
