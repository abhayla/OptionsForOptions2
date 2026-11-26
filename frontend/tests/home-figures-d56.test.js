// D-56 (ADR-320 point 5; GC-ICLIVE-E): Home shows the count of running strategies (the server's status_word, D-28), the unread alert
// count (GET /paper/alerts, D-29) and the total P&L (the Positions total, GET /paper/strategies totals; same paused rule). Each
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
    if (url === '/paper/alerts') return answer(alertsAnswer)
    if (url === '/paper/strategies') return answer(paperAnswer)
    return Promise.resolve({ data: { state: 'NOT_CONNECTED', answered_at: '2026-11-23T03:50:09+00:00', indices: [] } })
  } } }
})
import HomeOverviewPage from '@/pages/HomeOverviewPage.vue'
import { bellCount, openRecords, resetPaperAlerts } from '@/lib/paperAlerts'

class FakeSocket {
  constructor(url) { this.url = url; this.readyState = 0 }
  send() {}
  close() { this.readyState = 3 }
}
const T = '2026-11-23T10:00:00+05:30'
const strat = (id, word) => ({ id, underlying: 'NIFTY', status: 'draft', status_word: word, revision: 1, created_at: T, updated_at: T })
const totals = (over = {}) => ({ total_text: '+14.00', total_after_text: '+12.00', booked_text: '+2.00', unbooked_text: '+12.00', after_charges_reason: null, ...over })
const paper = (t = totals()) => ({ strategies: [], totals: t, answered_at: T })
const alerts = (unread) => ({ unread, alerts: [] })

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
  resetPaperAlerts()
  strategiesAnswer = [strat(1, 'Running'), strat(2, 'Running'), strat(3, 'Draft'), strat(4, 'Completed')]
  alertsAnswer = alerts(3)
  paperAnswer = paper()
  vi.stubGlobal('WebSocket', FakeSocket)
})
afterEach(() => vi.unstubAllGlobals())

describe('D-56 Home: running strategies (the server status_word)', () => {
  it('value: counts the rows whose status_word is Running, not drafts or completed', async () => {
    const w = await mountHome()
    expect(fig(w, 'running')).toBe('2')
    expect(tile(w, 'running')).toContain('Running strategies')
  })
  it('zero: only a draft is saved', async () => {
    strategiesAnswer = [strat(3, 'Draft')]
    expect(fig(await mountHome(), 'running')).toBe('0')
  })
  it('zero: nothing saved', async () => {
    strategiesAnswer = []
    expect(fig(await mountHome(), 'running')).toBe('0')
  })
  it('read failed: says so, no number', async () => {
    strategiesAnswer = new Error('down')
    const w = await mountHome()
    expect(tile(w, 'running')).toContain('Could not be read right now.')
    expect(fig(w, 'running')).toBe('—')
  })
})

describe('D-56 Home: unread alerts (the alert count route)', () => {
  it('value: the server unread number', async () => {
    expect(fig(await mountHome(), 'unread')).toBe('3')
  })
  it('zero', async () => {
    alertsAnswer = alerts(0)
    expect(fig(await mountHome(), 'unread')).toBe('0')
  })
  it('read failed: says so, no number; the other figures stay', async () => {
    alertsAnswer = new Error('down')
    const w = await mountHome()
    expect(tile(w, 'unread')).toContain('Could not be read right now.')
    expect(fig(w, 'unread')).toBe('—')
    expect(fig(w, 'running')).toBe('2')
  })
})

describe('D-56 round 2: Home unread = the bell badge', () => {
  it('with open adjustment records in the store, Home shows the bell number', async () => {
    openRecords.list = [{ id: 1, strategy_id: 1 }, { id: 2, strategy_id: 1 }]
    const w = await mountHome()
    expect(bellCount()).toBe(5)
    expect(fig(w, 'unread')).toBe(String(bellCount()))
    openRecords.list = []
  })
})

describe('D-56 Home: total P&L (the Positions total)', () => {
  it('value: the figure readPaperList gives for the same reply, labelled', async () => {
    const fromPositions = readPaperList(paper()).totals.totalAfter
    const w = await mountHome()
    expect(fromPositions.text).toBe('+12.00')
    expect(fig(w, 'pnl')).toBe(fromPositions.text)
    expect(tile(w, 'pnl')).toContain('(after charges)')
  })
  it('R-06 / N-18: the tile names the figure and carries "(after charges)" exactly once, before and after the figure arrives', async () => {
    const w = await mountHome()
    const label = w.get('[data-testid="home-pnl"] dt').text()
    expect(label).toBe('Total P&L (after charges)')
    expect(tile(w, 'pnl').split('(after charges)')).toHaveLength(2)
  })
  it('zero: a total of nothing is shown as the server wrote it, not as a dash', async () => {
    paperAnswer = paper(totals({ total_text: '+0.00', total_after_text: '+0.00' }))
    expect(fig(await mountHome(), 'pnl')).toBe('+0.00')
  })
  it('paused: a dash and "prices not live", no number', async () => {
    paperAnswer = paper(totals({ total_text: null, total_after_text: null, after_charges_reason: 'prices_not_live', totals_as_of: '2026-11-23T10:00:00+05:30' }))
    const w = await mountHome()
    expect(fig(w, 'pnl')).toBe('—')
    expect(tile(w, 'pnl')).toContain('prices not live')
  })
  it('AC-R06: one paused strategy among six: Home shows the server\'s total over the priced five and its count line', async () => {
    const LINE = '1 strategy left out: its price is not live.'
    paperAnswer = paper(totals({ total_text: '+15,775.80', total_after_text: '+15,775.80', left_out_count: 1, left_out_text: LINE }))
    const w = await mountHome()
    expect(fig(w, 'pnl')).toBe('+15,775.80')
    expect(w.get('[data-testid="home-pnl-left-out"]').text()).toBe(LINE)
    expect(tile(w, 'pnl')).not.toContain('prices not live')
  })
  it('AC-R06: no count line when nothing was left out', async () => {
    const w = await mountHome()
    expect(w.find('[data-testid="home-pnl-left-out"]').exists()).toBe(false)
  })
  it('read failed: says it is not available, no number', async () => {
    paperAnswer = new Error('down')
    const w = await mountHome()
    expect(fig(w, 'pnl')).toBe('—')
    expect(tile(w, 'pnl')).toContain('not available')
  })
  it('no paper trade yet (totals absent): shows a dash, never 0', async () => {
    paperAnswer = { strategies: [], totals: null, answered_at: T }
    const w = await mountHome()
    expect(fig(w, 'pnl')).toBe('—')
  })
})
