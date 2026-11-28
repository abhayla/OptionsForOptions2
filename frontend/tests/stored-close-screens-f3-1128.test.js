// Lane F3 MUST (coordinator 22:15 IST, Opus review of Lane RA2's branch): with no broker session and the market closed the server sends a paper
// book as state LIVE computed from the STORED CLOSE, `as_of` = the close's real time. The screens must print that time WITH ITS DATE beside
// the P&L, never a bare clock: a close from 1 Oct shown on 10 Oct must not read "15:29:58". One named test per screen.
// Real case: stored close 1 Oct 2026 15:29:58 IST (as_of 2026-10-01T09:59:58Z), strategy LIVE, total +3,027.52.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import REAL0 from './fixtures/paper-strategies.json'
import { readPaperList } from '@/lib/paperList'
import PaperBookPanel from '@/components/strategy/PaperBookPanel.vue'
import PositionsTotals from '@/components/positions/PositionsTotals.vue'

let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url) => {
    const a = answers[`${method} ${url}`]
    if (a instanceof Error) return Promise.reject(a)
    return a ? a() : Promise.reject({ message: 'no answer', parts: null, status: null })
  }
  return { ...actual, default: { get: reply('GET'), post: reply('POST') } }
})
import PositionsPage from '@/pages/PositionsPage.vue'
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'
import HomeOverviewPage from '@/pages/HomeOverviewPage.vue'
import { resetActiveAlerts } from '@/lib/paperAlerts'

const CLOSE = '2026-10-01T09:59:58Z'
const OLDER = '2026-09-30T09:59:58Z'
const DATED = 'As of 1 Oct 2026, 15:29:58 IST'
const ok = (data) => () => Promise.resolve({ data })
const clone = (x) => JSON.parse(JSON.stringify(x))
const stored = (asOfs = [CLOSE]) => {
  const d = clone(REAL0)
  const live = d.strategies.find((s) => s.state === 'LIVE')
  d.strategies = asOfs.map((as_of, i) => ({ ...clone(live), strategy_id: 300 + i, name: `S${i}`, state: 'LIVE', as_of }))
  Object.assign(d.totals, { totals_as_of: null })
  return d
}
const t = (w, id) => w.find(`[data-testid="${id}"]`)

describe('stored close: as-of with its date on every screen', () => {
  it('paper list rows (readPaperList): the row line carries the dated time; a total line carries the oldest', () => {
    const r = readPaperList(stored([CLOSE, OLDER]))
    expect(r.groups.map((g) => g.stateText)).toEqual([DATED, 'As of 30 Sep 2026, 15:29:58 IST'])
    expect(r.totals.storedAsOf).toBe('As of 30 Sep 2026, 15:29:58 IST')
  })
  it('paper list: LIVE with no as_of (a live book) prints no as-of line and no total line', () => {
    const r = readPaperList(stored([null]))
    expect(r.groups[0].stateText).toBe('')
    expect(r.totals.storedAsOf).toBe(null)
  })
  it('PaperBookPanel: a LIVE book with as_of says it beside the P&L, with the date', () => {
    const book = { ...clone(REAL0.strategies.find((s) => s.state === 'LIVE')), orders: [], state: 'LIVE', as_of: CLOSE }
    const w = mount(PaperBookPanel, { props: { book, net: [] } })
    expect(t(w, 'book-as-of').text()).toBe(DATED)
  })
  it('PaperBookPanel: a live book (no as_of) prints no stored-close line', () => {
    const book = { ...clone(REAL0.strategies.find((s) => s.state === 'LIVE')), orders: [], state: 'LIVE', as_of: null }
    expect(t(mount(PaperBookPanel, { props: { book, net: [] } }), 'book-as-of').exists()).toBe(false)
  })
  it('Positions totals strip: the Paper P&L card carries the same dated line', () => {
    const w = mount(PositionsTotals, { props: { real: null, paper: { loaded: true, stale: false, totalAfter: { text: '+3,027.52', reason: null, label: '' }, storedAsOf: DATED } } })
    expect(t(w, 'totals-paper-as-of').text()).toBe(DATED)
  })
  it('Positions page: rows and the Paper P&L card show the dated close', async () => {
    answers['GET /paper/strategies'] = ok(stored([CLOSE, OLDER]))
    answers['GET /positions'] = ok({ read_at: null, strategies: [], has_outside: false, outside_lots: 0, blocked: false, blocked_strategy_ids: [], broker_connected: false, real_pnl: { state: 'not_connected', pnl_text: null, reason: null, caption: null, excludes_note: null } })
    answers['GET /features'] = ok({ order_path: 'on' })
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/p', component: PositionsPage, meta: { title: 'T', parent: 'Positions', view: 'current' } }, { path: '/:r(.*)', component: { template: '<div/>' } }] })
    router.push('/p'); await router.isReady()
    const w = mount(PositionsPage, { attachTo: document.body, global: { plugins: [router] } })
    await flushPromises()
    expect(t(w, 'totals-paper-as-of').text()).toBe('As of 30 Sep 2026, 15:29:58 IST')
    expect(w.findAll('[data-testid="paper-state"]').map((n) => n.text())).toContain(DATED)
    w.unmount()
  })
  it('the per-leg price time shows its date when it is not today', async () => {
    const d = stored([CLOSE]); d.strategies[0].positions.forEach((p) => { p.price_at = CLOSE })
    answers['GET /paper/strategies'] = ok(d)
    answers['GET /positions'] = ok({ read_at: null, strategies: [], has_outside: false, outside_lots: 0, blocked: false, blocked_strategy_ids: [], broker_connected: false, real_pnl: { state: 'not_connected', pnl_text: null, reason: null, caption: null, excludes_note: null } })
    answers['GET /features'] = ok({ order_path: 'on' })
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/p', component: PositionsPage, meta: { title: 'T', parent: 'Positions', view: 'current' } }, { path: '/:r(.*)', component: { template: '<div/>' } }] })
    router.push('/p'); await router.isReady()
    const w = mount(PositionsPage, { attachTo: document.body, global: { plugins: [router] } })
    await flushPromises()
    const ats = w.findAll('[data-testid="paper-ltp-at"]').map((n) => n.text())
    expect(ats.length).toBeGreaterThan(0)
    expect(ats.every((x) => x.includes('1 Oct 2026'))).toBe(true)
    w.unmount()
  })
})

describe('stored close on Home', () => {
  beforeEach(() => { resetActiveAlerts(); globalThis.WebSocket = class { constructor() { this.readyState = 0 } send() {} close() {} } })
  it('the Total P&L card carries the oldest dated close', async () => {
    answers['GET /strategies'] = ok({ strategies: [] })
    answers['GET /alerts/active'] = ok({ count: 0, alerts: [] })
    answers['GET /paper/strategies'] = ok(stored([CLOSE, OLDER]))
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/h', component: HomeOverviewPage }, { path: '/:r(.*)', component: { template: '<div/>' } }] })
    router.push('/h'); await router.isReady()
    const w = mount(HomeOverviewPage, { global: { plugins: [router] } })
    await flushPromises()
    expect(t(w, 'home-pnl-as-of').text()).toBe('As of 30 Sep 2026, 15:29:58 IST')
    w.unmount()
  })
})


describe('stored close in the list header totals', () => {
  it('the paper list\'s own totals block shows the oldest dated close under the total', async () => {
    answers['GET /paper/strategies'] = ok(stored([CLOSE, OLDER]))
    answers['GET /features'] = ok({ order_path: 'on' })
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:r(.*)', component: { template: '<div/>' } }] })
    router.push('/x'); await router.isReady()
    const w = mount(PaperStrategies, { attachTo: document.body, global: { plugins: [router] } })
    await flushPromises()
    expect(t(w, 'totals-as-of').text()).toBe('As of 30 Sep 2026, 15:29:58 IST')
    w.unmount()
  })
})

beforeEach(() => { answers = {} })
afterEach(() => { document.body.innerHTML = '' })
