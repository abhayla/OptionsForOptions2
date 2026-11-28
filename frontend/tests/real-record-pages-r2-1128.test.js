// Lane R2 item 5 (owner 28 Nov): a stored action on a REAL position is ONE line ("... Not sent to Zerodha. Place it in Kite.") under its row on
// every page that shows the row, and NEVER changes the quantity or the P&L shown (broker is the authority, ADR-016..019; no "if filled" P&L).
// One test per page: Positions, Paper list (a real group), My Strategies, Home. (Live Strategies: real-same-screens-core-r2-1128; Alerts: alerts-real-r2-1128.)
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import FIX from './fixtures/paper-strategies.json'

let positionsReply = null
let strategiesReply = []
let paperReply = null
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: {
    get: (url) => {
      if (url === '/features') return Promise.resolve({ data: { order_path: 'on' } })
      if (url === '/paper/strategies') return Promise.resolve({ data: paperReply ?? { strategies: [], totals: null } })
      if (url === '/strategies') return Promise.resolve({ data: { strategies: strategiesReply } })
      if (url === '/positions') return Promise.resolve({ data: positionsReply })
      return Promise.reject({ status: 404, parts: null })
    }, post: () => Promise.reject({ status: 404 }), delete: () => Promise.reject({ status: 404 }) } }
})
vi.mock('@/stores/settingsValues', () => ({ useSettingsValues: () => ({ waitMs: () => Promise.resolve(60000) }) }))
import PositionsPage from '@/pages/PositionsPage.vue'
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'
import MyStrategiesPage from '@/pages/MyStrategiesPage.vue'
import HomeOverviewPage from '@/pages/HomeOverviewPage.vue'

const NOT_SENT = 'Not sent to Zerodha. Place it in Kite.'
const RECORD = { action: 'exit', stored_at: '2026-11-28T10:32:00+05:30', price: '120.50' }
const LINE = `Exit stored 10:32:00 at 120.50. ${NOT_SENT}`
const router = () => createRouter({ history: createMemoryHistory(), routes: [{ path: '/p', component: { template: '<div/>' }, meta: { title: 'T', parent: 'P', view: 'current' } }, { path: '/:p(.*)*', component: { template: '<div/>' } }] })
async function mountAt(comp, path = '/p') {
  const r = router()
  r.push(path)
  await r.isReady()
  const w = mount(comp, { global: { plugins: [r, createPinia()] } })
  await flushPromises()
  return w
}
beforeEach(() => { setActivePinia(createPinia()); positionsReply = null; strategiesReply = []; paperReply = null })

describe('Positions page', () => {
  const group = (extra = {}) => ({ strategy_id: 12, blocked: false, contracts: [{ tradingsymbol: 'NIFTY26D1625600CE', zerodha_units: '65', units: '65', pending: false, pending_plans: [], pnl_state: 'stated', pnl_text: '+1,234.50' }], ...extra })
  const reply = (g) => ({ read_at: '2026-11-28T10:40:00+05:30', strategies: [g], has_outside: false, outside_lots: 0, blocked: false, blocked_strategy_ids: [] })
  it('the record line sits under the real row; units and P&L text are exactly what they were; none when nothing is stored', async () => {
    positionsReply = reply(group())
    const before = await mountAt(PositionsPage)
    positionsReply = reply(group({ stored_not_sent: true, record: RECORD }))
    const w = await mountAt(PositionsPage)
    expect(w.get('[data-testid="position-record-line"]').text()).toBe(LINE)
    expect(before.find('[data-testid="position-record-line"]').exists()).toBe(false)
    for (const id of ['position-own-units', 'position-zerodha', 'position-pnl']) expect(w.get(`[data-testid="${id}"]`).text()).toBe(before.get(`[data-testid="${id}"]`).text())
    expect(w.get('[data-testid="position-pnl"]').text()).toBe('+1,234.50')
  })
})

describe('Paper list holding a real group', () => {
  const doc = (extra) => { const d = JSON.parse(JSON.stringify(FIX)); Object.assign(d.strategies.find((s) => s.state === 'LIVE'), extra); return d }
  it('tagged REAL with its line and record; Exit and Stops offered; total and quantity text unchanged; unknown kind offers neither', async () => {
    paperReply = doc({ position_kind: 'paper' })
    const base = await mountAt(PaperStrategies)
    paperReply = doc({ position_kind: 'real', stored_not_sent: true, record: RECORD })
    const w = await mountAt(PaperStrategies)
    const g = w.get('[data-testid="paper-group"][data-strategy="1"]')
    expect(g.find('[data-testid="paper-real-tag"]').exists()).toBe(true)
    expect(g.find('[data-testid="paper-tag"]').exists()).toBe(false)
    expect(base.get('[data-testid="paper-group"][data-strategy="1"]').find('[data-testid="paper-real-tag"]').exists()).toBe(false)
    expect(g.get('[data-testid="paper-record-line"]').text()).toBe(LINE)
    expect(g.get('[data-testid="paper-real-line"]').text()).toContain('Real position')
    expect(w.get('[data-testid="paper-banner"]').text()).not.toBe('Paper trades - not real money')
    expect(g.find('[data-testid="stops-open-1"]').exists()).toBe(true)
    expect(g.get('[data-testid="paper-total"]').text()).toBe(base.get('[data-testid="paper-group"][data-strategy="1"] [data-testid="paper-total"]').text())
    expect(g.findAll('[data-testid="paper-qty"]').map((x) => x.text())).toEqual(base.get('[data-testid="paper-group"][data-strategy="1"]').findAll('[data-testid="paper-qty"]').map((x) => x.text()))
    paperReply = doc({ position_kind: 'unknown' })
    const u = await mountAt(PaperStrategies)
    const ug = u.get('[data-testid="paper-group"][data-strategy="1"]')
    expect(ug.find('[data-testid="stops-open-1"]').exists()).toBe(false)
    expect(ug.find('[data-testid="paper-unknown-kind-line"]').exists()).toBe(true)
  })
})

describe('My Strategies and Home', () => {
  const run = (extra = {}) => ({ id: 31, name: '"S31"', underlying: 'NIFTY', status: 'draft', status_word: 'Running', has_order: true, created_at: '2026-11-25T04:00:00Z', updated_at: '2026-11-26T04:00:00Z', can_delete: false, revision: 1, position_kind: 'real', ...extra })
  it('My Strategies: the record line under the real row, the rest of the row unchanged', async () => {
    strategiesReply = [run()]
    const base = await mountAt(MyStrategiesPage)
    strategiesReply = [run({ stored_not_sent: true, record: RECORD })]
    const w = await mountAt(MyStrategiesPage)
    expect(w.get('[data-testid="row-record-line"]').text()).toBe(LINE)
    expect(base.find('[data-testid="row-record-line"]').exists()).toBe(false)
    expect(w.get('[data-testid="strategy-row"]').text().replace(LINE, '').trim()).toBe(base.get('[data-testid="strategy-row"]').text().trim())
  })
  it('Home: the record line under the recent row; the running count is unchanged', async () => {
    strategiesReply = [run()]
    const base = await mountAt(HomeOverviewPage)
    strategiesReply = [run({ stored_not_sent: true, record: RECORD })]
    const w = await mountAt(HomeOverviewPage)
    expect(w.get('[data-testid="recent-record-line"]').text()).toBe(LINE)
    expect(base.find('[data-testid="recent-record-line"]').exists()).toBe(false)
    expect(w.text().replace(LINE, '').replace(/\s+/g, ' ')).toBe(base.text().replace(/\s+/g, ' '))
  })
})
