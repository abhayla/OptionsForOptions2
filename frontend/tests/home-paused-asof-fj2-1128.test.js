// D-56 (ADR-320 point 5; GC-ICLIVE-E): Home shows the count of running strategies (the server's status_word, D-28), the unread alert
// count (GET /alerts/active, ADR-330 (4)) and the total P&L (the Positions total, GET /paper/strategies totals; same paused rule). Each
// figure has its own states: value, paused (P&L only), read failed, zero. A failed read of one figure leaves the others alone.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { readPaperList } from '@/lib/paperList'

let strategiesAnswer // a list, or an Error
let alertsAnswer // an object, or an Error
let paperAnswer // an object, or an Error
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const answer = (a) => (a instanceof Error ? Promise.reject(a) : Promise.resolve({ data: a }))
  return { ...actual, default: { get: (url) => {
    if (url === '/strategies') return strategiesAnswer instanceof Error ? Promise.reject(strategiesAnswer) : Promise.resolve({ data: { strategies: strategiesAnswer } })
    if (url === '/alerts/active') return answer(alertsAnswer)
    if (url === '/paper/strategies') return answer(paperAnswer)
    return Promise.resolve({ data: { state: 'NOT_CONNECTED', answered_at: '2026-11-23T03:50:09+00:00', indices: [] } })
  } } }
})
import HomeOverviewPage from '@/pages/HomeOverviewPage.vue'
import { bellCount, openRecords, resetActiveAlerts } from '@/lib/paperAlerts'

class FakeSocket {
  constructor(url) { this.url = url; this.readyState = 0 }
  send() {}
  close() { this.readyState = 3 }
}
const T = '2026-11-23T10:00:00+05:30'
const strat = (id, word) => ({ id, underlying: 'NIFTY', status: 'draft', status_word: word, revision: 1, created_at: T, updated_at: T })
const totals = (over = {}) => ({ total_text: '+14.00', total_after_text: '+12.00', booked_text: '+2.00', unbooked_text: '+12.00', after_charges_reason: null, ...over })
const paper = (t = totals()) => ({ strategies: [], totals: t, answered_at: T })
const alerts = (count) => ({ count, alerts: Array.from({ length: count }, (_, i) => ({ id: i + 1, strategy_id: 1, kind: 'plan_loss_stop', text: 't', fired_line: 'Fired at 11:02', answers: [] })) })

async function mountHome() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/home/overview', component: HomeOverviewPage }, { path: '/:rest(.*)', component: { template: '<div />' } }] })
  router.push('/home/overview')
  await router.isReady()
  const w = mount(HomeOverviewPage, { global: { plugins: [router] } })
  await flushPromises()
  return w
}
const fig = (w, id) => w.get(`[data-testid="home-${id}-figure"]`).text()
const tile = (w, id) => w.get(`[data-testid="home-${id}"]`).text()


beforeEach(() => {
  resetActiveAlerts()
  strategiesAnswer = [strat(1, 'Running'), strat(2, 'Running')]
  alertsAnswer = alerts(0)
  vi.useFakeTimers()
  globalThis.WebSocket = FakeSocket
})
afterEach(() => { vi.useRealTimers() })

// FJ2 item 1 / T1-20 (Lane TG, 28 Nov): Positions printed "Paper P&L paused - prices not live, as of <time> IST"; Home printed the sentence with no time.
describe('FJ2-1 Home: the paused total carries its as-of time', () => {
  it('server sends no totals_as_of: the answer\'s own time is used', async () => {
    paperAnswer = paper(totals({ total_text: null, total_after_text: null, after_charges_reason: 'prices_not_live' }))
    const w = await mountHome()
    expect(tile(w, 'pnl')).toContain('Paper P&L paused - prices not live, as of ')
  })
  it('server sends totals_as_of: that time', async () => {
    paperAnswer = paper(totals({ total_text: null, total_after_text: null, after_charges_reason: 'prices_not_live', totals_as_of: '2026-11-23T10:00:00+05:30' }))
    const w = await mountHome()
    expect(tile(w, 'pnl')).toContain('Paper P&L paused - prices not live, as of ')
  })
})
