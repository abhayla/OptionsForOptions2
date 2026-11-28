// Lane FC2 (R2, 28 Nov) D-TD-2 / board I-86: every list page, on a failed load, says ONE sentence and has a Retry that asks again.
// With a server message (a refusal) its four parts stay and Retry sits under them. API stand-in: the first N reads fail with no message.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { createPinia } from 'pinia'

let failsLeft = 0
let withParts = null
const calls = []
const FAILING = ['/strategies', '/alerts/active', '/alerts/answered', '/paper/alerts/records', '/positions', '/adjustment-opportunities']
const bodies = {
  '/strategies': { strategies: [] },
  '/alerts/active': { count: 0, alerts: [] },
  '/alerts/answered': { items: [] },
  '/paper/alerts/records': { records: [] },
  '/positions': { read_at: '2026-11-28T03:34:07+05:30', real_pnl: null, strategies: [], has_outside: false, outside_lots: 0, blocked: false, blocked_strategy_ids: [] },
  '/paper/strategies': { strategies: [], totals: null, answered_at: null },
  '/adjustment-opportunities': { groups: [], totals: null, counts: [] },
  '/features': { order_path: 'on' },
}
const reply = (url) => {
  calls.push(url)
  if (FAILING.includes(url) && failsLeft > 0) {
    failsLeft -= 1
    return Promise.reject({ message: 'down', status: withParts ? 409 : null, parts: withParts })
  }
  return url in bodies ? Promise.resolve({ data: bodies[url] }) : Promise.reject({ message: 'no answer', parts: null, status: null })
}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (u) => reply(u), post: (u) => reply(u), delete: (u) => reply(u) } }
})
import LiveStrategiesPage from '@/pages/LiveStrategiesPage.vue'
import AlertsPage from '@/pages/AlertsPage.vue'
import PositionsPage from '@/pages/PositionsPage.vue'
import AdjustmentOpportunitiesPage from '@/pages/AdjustmentOpportunitiesPage.vue'
import HomeOverviewPage from '@/pages/HomeOverviewPage.vue'
import ListLoadFailed from '@/components/common/ListLoadFailed.vue'
import { LIST_FAILED_TEXT } from '@/lib/listFailed'
import { resetActiveAlerts, resetOpenRecords } from '@/lib/paperAlerts'

const FOUR = { what_happened: 'Connect your Zerodha account to continue.', impact: 'i', what_is_blocked: 'b', next_action: 'n' }
const mounted = []
async function open(component, path, extra = {}) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:rest(.*)', meta: { title: 'T', parent: 'P', view: 'current' }, component }] })
  router.push(path)
  await router.isReady()
  const stubs = { IndexStrip: true, PaperStrategies: true, PriceNotice: true, PositionsTotals: true, PlanDoor: true, MonitoringBadge: true }
  const w = mount(component, { ...extra, global: { plugins: [router, createPinia()], stubs } })
  mounted.push(w)
  await flushPromises()
  return w
}
beforeEach(() => { failsLeft = 0; withParts = null; calls.length = 0; resetActiveAlerts(); resetOpenRecords(); vi.useFakeTimers() })
afterEach(() => { mounted.splice(0).forEach((w) => { try { w.unmount() } catch { /* gone */ } }); vi.useRealTimers() })
const count = (u) => calls.filter((c) => c === u).length

describe('ListLoadFailed', () => {
  it('no parts: the shared sentence and Retry', async () => {
    const w = mount(ListLoadFailed, { props: { parts: null, prefix: 'x' } })
    expect(w.get('[data-testid="x-error"]').text()).toBe(LIST_FAILED_TEXT)
    expect(w.get('[data-testid="x-retry"]').text()).toBe('Retry')
    await w.get('[data-testid="x-retry"]').trigger('click')
    expect(w.emitted('retry')).toHaveLength(1)
  })
  it("the server's four parts: kept, with Retry under them", () => {
    const w = mount(ListLoadFailed, { props: { parts: FOUR, prefix: 'x' } })
    expect(w.get('[data-testid="x-what"]').text()).toBe(FOUR.what_happened)
    expect(w.find('[data-testid="x-error"]').exists()).toBe(false)
    expect(w.find('[data-testid="x-retry"]').exists()).toBe(true)
  })
})

const PAGES = [
  ['Live Strategies', LiveStrategiesPage, '/strategies/live-strategies', 'live-list', '/strategies', {}],
  ['Alerts > Active', AlertsPage, '/alerts/active', 'alerts-error', '/alerts/active', {}],
  ['Alerts > History', AlertsPage, '/alerts/history', 'answered-error', '/alerts/answered', {}],
  ['Positions', PositionsPage, '/positions/current-positions', 'positions-error', '/positions', {}],
  ['Adjustment opportunities', AdjustmentOpportunitiesPage, '/positions/adjustment-opportunities', 'opp-error', '/adjustment-opportunities', { props: { client: { get: (u) => reply(u) } } }],
  ['Home', HomeOverviewPage, '/home/overview', 'home-error', '/strategies', { fails: 2 }], // Home's silent alerts read takes the first failure
]
describe.each(PAGES)('%s: failed load', (_n, comp, path, prefix, url, extra) => {
  const { fails = 1, ...mountOpts } = extra
  it('says the shared sentence with a Retry; Retry asks again and the page recovers', async () => {
    failsLeft = fails
    const w = await open(comp, path, mountOpts)
    expect(w.get(`[data-testid="${prefix}-error"]`).text()).toBe(LIST_FAILED_TEXT)
    const before = count(url)
    await w.get(`[data-testid="${prefix}-retry"]`).trigger('click')
    await flushPromises()
    expect(count(url)).toBe(before + 1)
    expect(w.find(`[data-testid="${prefix}-error"]`).exists()).toBe(false)
  })
  it('a server refusal keeps its four parts and still has Retry', async () => {
    failsLeft = fails
    withParts = FOUR
    const w = await open(comp, path, mountOpts)
    expect(w.get(`[data-testid="${prefix}-what"]`).text()).toBe(FOUR.what_happened)
    expect(w.find(`[data-testid="${prefix}-retry"]`).exists()).toBe(true)
  })
})
