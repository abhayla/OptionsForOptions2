// D-41 (ADR-320 point 5; GC-ICLIVE-E): the Live Strategies card and the My Strategies row show a running trade's P&L from the
// ONE function the Positions page reads (GET /paper/strategies through readPaperList), a dash with "prices not live" when
// paused, and never stay on "Loading": a failed read says so. "Health" is not built (no definition).
// Real case: C1 155 (condor, running), total after charges +3.50 on the Positions Paper tab.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { echoSeq } from './helpers/echoSeq'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { readPaperList } from '@/lib/paperList'

let listAnswer // GET /paper/strategies: an object, or a function returning a promise
let bookAnswer // GET /paper/strategies/155
const rows = [
  { id: 155, underlying: 'NIFTY', status: 'draft', status_word: 'Running', has_order: true, created_at: '2026-11-23T10:00:00+05:30', updated_at: '2026-11-23T10:00:00+05:30' },
  { id: 9, underlying: 'NIFTY', status: 'draft', status_word: 'Draft', has_order: false, created_at: '2026-11-22T10:00:00+05:30', updated_at: '2026-11-22T10:00:00+05:30' },
]
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const get = (url) => {
    if (url === '/strategies') return Promise.resolve({ data: { strategies: rows } })
    if (url === '/features') return Promise.resolve({ data: { order_path: 'on' } })
    if (url === '/paper/strategies') return typeof listAnswer === 'function' ? listAnswer() : Promise.resolve({ data: listAnswer })
    if (/^\/paper\/strategies\/155$/.test(url)) return typeof bookAnswer === 'function' ? bookAnswer() : Promise.resolve({ data: bookAnswer })
    if (/^\/strategies\/9\/legs/.test(url) || /^\/strategies\/9$/.test(url)) return Promise.resolve({ data: { id: 9, legs: [], revision: 1 } })
    if (/^\/catalogue\/NIFTY\/contracts/.test(url)) {
      return Promise.resolve({ data: { contracts: [...Array(40).keys()].map((i) => ({ contract_id: i + 1, exchange_segment: 'NSE_FO', exchange_token: 1001 + i,
        instrument_type: 'PE', expiry: '2026-11-25', strike: '25400.00', lot_size: 65, symbol: `NIFTY${i + 1}` })) } })
    }
    return Promise.reject(new Error(`unmocked get ${url}`))
  }
  return { ...actual, default: { get, post: () => Promise.resolve({ data: {} }), patch: () => Promise.resolve({ data: {} }), delete: () => Promise.resolve({ data: {} }) } }
})
import LiveStrategiesPage from '@/pages/LiveStrategiesPage.vue'
import MyStrategiesPage from '@/pages/MyStrategiesPage.vue'

class FakeSocket {
  static all = []
  constructor(url) { this.url = url; this.sent = []; this.readyState = 0; FakeSocket.all.push(this) }
  send(t) { this.sent.push(t) }
  close() { this.readyState = 3 }
  serverOpen() { this.readyState = 1; this.onopen?.() }
  serverPush(obj) { this.onmessage?.({ data: JSON.stringify(echoSeq(this, obj)) }) }
}

const position = { contract_id: 5, net_quantity: -65, lot_size: 65, contract_text: 'NIFTY 25 Nov 25400 PE', average_text: '88.50', price_state: 'live', ltp_text: '80.00', price_at: '2026-11-23T11:18:00+05:30', booked_text: '+0.00', unbooked_text: '+552.50', total_text: '+552.50' }
const item = (over = {}) => ({ strategy_id: 155, name: null, underlying: 'NIFTY', state: 'LIVE', status_word: 'Running', open_count: 1, position_count: 1, positions: [position],
  total_text: '+9.00', total_after_text: '+3.50', booked_text: '+0.00', unbooked_text: '+9.00', after_charges_reason: null, ...over })
const list = (over) => ({ strategies: [item(over)], totals: null, answered_at: '2026-11-23T11:18:00+05:30' })
const book = () => ({ strategy_id: 155, underlying: 'NIFTY', answered_at: '2026-11-23T11:18:00+05:30', state: 'LIVE', as_of: null, orders: [{ id: 1 }],
  positions: [{ contract_id: 5, net_quantity: -65, average: '88.50', expiry: '2026-11-25' }], max_profit_text: '+2,380.32', max_loss_text: '-4,119.68',
  breakevens_display: ['25,457'], total_after_text: '+3.50', total_text: '+9.00' })
const outcome = () => ({ state: 'COMPUTED', underlying: 'NIFTY', status_label: null, reason: null, output_label: null, spot_level: '25575.00',
  spot_at: '2026-11-23T11:18:00+05:30', answered_at: '2026-11-23T11:18:01+05:30', summary: { max_profit: '1', max_loss: '-1' },
  legs: [{ instrument_id: 'NSE_FO:1005', symbol: 'NIFTY5', action: 'SELL', ltp: '39.15', health: 'available', label: null }] })

const mounted = []
const router = () => createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }, { path: '/strategy/builder', component: { template: '<div/>' } },
  { path: '/strategy/:id/execute', component: { template: '<div/>' } }, { path: '/positions/adjustment-opportunities', component: { template: '<div/>' } }] })
async function mountPage(Page) {
  const r = router()
  r.push('/')
  await r.isReady()
  const w = mount(Page, { global: { plugins: [r] } })
  mounted.push(w)
  await flushPromises()
  FakeSocket.all.forEach((s) => s.serverOpen())
  if (FakeSocket.all[0]) FakeSocket.all[0].serverPush(outcome())
  await flushPromises()
  return w
}
const card = (w) => w.get('[data-strategy-id="155"]')
const rowOf = (w, id) => w.get(`[data-testid="strategy-row"][data-strategy-id="${id}"]`)

beforeEach(() => {
  FakeSocket.all = []
  listAnswer = list()
  bookAnswer = book()
  vi.spyOn(Math, 'random').mockReturnValue(0)
  global.WebSocket = FakeSocket
})
afterEach(() => { while (mounted.length) mounted.pop().unmount(); vi.restoreAllMocks(); vi.useRealTimers() })

describe('D-41 Live card: the P&L is the Positions page figure', () => {
  it('value: the card shows the figure readPaperList gives for the same reply, labelled', async () => {
    const fromPositions = readPaperList(listAnswer).groups[0].totalAfter
    const c = card(await mountPage(LiveStrategiesPage))
    expect(fromPositions.text).toBe('+3.50')
    expect(c.get('[data-testid="live-pnl-figure"]').text()).toBe(fromPositions.text)
    expect(c.get('[data-testid="live-pnl"]').text()).toContain('(after charges)')
  })
  it('paused: a dash and "prices not live", no number', async () => {
    listAnswer = list({ state: 'PAUSED', as_of: '2026-11-23T11:10:00+05:30', total_text: null, total_after_text: null, unbooked_text: null, after_charges_reason: 'prices_not_live' })
    const c = card(await mountPage(LiveStrategiesPage))
    expect(c.get('[data-testid="live-pnl-figure"]').text()).toBe('—')
    expect(c.get('[data-testid="live-pnl"]').text()).toContain('prices not live')
    expect(c.get('[data-testid="live-pnl"]').text()).not.toMatch(/\+3\.50|\+9\.00/)
  })
  it('read failed: the card says the P&L is not available, no figure, no Loading text left', async () => {
    listAnswer = () => Promise.reject(new Error('down'))
    const c = card(await mountPage(LiveStrategiesPage))
    expect(c.get('[data-testid="live-pnl"]').text()).toContain('not available')
    expect(c.find('[data-testid="live-pnl-figure"]').exists()).toBe(false)
    expect(c.text()).not.toContain('Loading')
  })
  it('nothing to show: a running trade absent from the list, and a draft, show no P&L line', async () => {
    listAnswer = { strategies: [], totals: null, answered_at: '2026-11-23T11:18:00+05:30' }
    const w = await mountPage(LiveStrategiesPage)
    expect(card(w).find('[data-testid="live-pnl"]').exists()).toBe(false)
    expect(w.get('[data-strategy-id="9"]').find('[data-testid="live-pnl"]').exists()).toBe(false)
  })
  it('a card whose own read never answers does not stay on Loading: it says it could not load', async () => {
    vi.useFakeTimers()
    bookAnswer = () => new Promise(() => {})
    const w = await mountPage(LiveStrategiesPage)
    expect(card(w).find('[data-testid="live-loading"]').exists()).toBe(true)
    await vi.advanceTimersByTimeAsync(30000)
    await flushPromises()
    expect(card(w).find('[data-testid="live-loading"]').exists()).toBe(false)
    expect(card(w).find('[data-testid="live-error"]').exists()).toBe(true)
  })
})

describe('D-41 My Strategies row: the same figure', () => {
  it('value', async () => {
    const w = await mountPage(MyStrategiesPage)
    expect(rowOf(w, 155).get('[data-testid="row-pnl-figure"]').text()).toBe('+3.50')
    expect(rowOf(w, 155).get('[data-testid="row-pnl"]').text()).toContain('(after charges)')
  })
  it('paused', async () => {
    listAnswer = list({ state: 'PAUSED', as_of: '2026-11-23T11:10:00+05:30', total_text: null, total_after_text: null, unbooked_text: null, after_charges_reason: 'prices_not_live' })
    const w = await mountPage(MyStrategiesPage)
    expect(rowOf(w, 155).get('[data-testid="row-pnl-figure"]').text()).toBe('—')
    expect(rowOf(w, 155).get('[data-testid="row-pnl"]').text()).toContain('prices not live')
  })
  it('read failed: says so, never Loading', async () => {
    listAnswer = () => Promise.reject(new Error('down'))
    const w = await mountPage(MyStrategiesPage)
    expect(rowOf(w, 155).get('[data-testid="row-pnl"]').text()).toContain('not available')
    expect(rowOf(w, 155).text()).not.toContain('Loading')
  })
  it('nothing to show: a draft row and a running row absent from the list have no P&L line', async () => {
    listAnswer = { strategies: [], totals: null, answered_at: '2026-11-23T11:18:00+05:30' }
    const w = await mountPage(MyStrategiesPage)
    expect(rowOf(w, 155).find('[data-testid="row-pnl"]').exists()).toBe(false)
    expect(rowOf(w, 9).find('[data-testid="row-pnl"]').exists()).toBe(false)
  })
})
