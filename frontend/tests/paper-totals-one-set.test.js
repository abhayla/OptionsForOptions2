// Lane L (27 Nov, T1-15 / item 1 and 2): the P&L total on Home and the Paper total on Positions are the figure of ONE reply of
// GET /paper/strategies (totals, ADR-008 one engine); the closed-strategies line is tied to the rows of that same reply.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { readPaperList } from '@/lib/paperList'

let paperAnswer
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (url) => {
    if (url === '/strategies') return Promise.resolve({ data: { strategies: [] } })
    if (url === '/alerts/active') return Promise.resolve({ data: { count: 0, alerts: [] } })
    if (url === '/paper/strategies') return Promise.resolve({ data: paperAnswer })
    return Promise.resolve({ data: { state: 'NOT_CONNECTED', answered_at: '2026-11-27T03:50:09+00:00', indices: [] } })
  } } }
})
import HomeOverviewPage from '@/pages/HomeOverviewPage.vue'
import PositionsTotals from '@/components/positions/PositionsTotals.vue'
import { resetActiveAlerts } from '@/lib/paperAlerts'

class FakeSocket { constructor(url) { this.url = url; this.readyState = 0 } send() {} close() { this.readyState = 3 } }
const T = '2026-11-27T10:00:00+05:30'
const row = (id, over = {}) => ({ strategy_id: id, name: `"S${id}"`, underlying: 'NIFTY', state: 'LIVE', status_word: 'Running', positions: [], closed: [], open_count: 1, position_count: 1, total_text: '+10.00', total_after_text: '+9.00', after_charges_reason: null, ...over })
const reply = (rows, totals) => ({ strategies: rows, totals: { total_text: '+25.00', total_after_text: '+22.00', after_charges_reason: null, ...totals }, answered_at: T })
// a priced running trade, a settled trade at its booked result (closed), a settling one (left out, counted)
const MIXED = () => reply(
  [row(1), row(2, { state: 'EXITED', open_count: 0, status_word: 'Completed' }), row(3, { state: 'PAUSED', total_text: null, total_after_text: null, after_charges_reason: 'prices_not_live' })],
  { closed_count: 1, closed_text: 'Includes 1 closed strategy.', left_out_count: 1, left_out_text: '1 strategy left out: its price is not live.' })

beforeEach(() => { resetActiveAlerts(); vi.stubGlobal('WebSocket', FakeSocket) })
afterEach(() => vi.unstubAllGlobals())

async function homeFigure() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/home/overview', component: HomeOverviewPage }, { path: '/:rest(.*)', component: { template: '<div />' } }] })
  router.push('/home/overview'); await router.isReady()
  const w = mount(HomeOverviewPage, { global: { plugins: [router] } })
  await flushPromises()
  return w.get('[data-testid="home-pnl-figure"]').text()
}
function positionsFigure(data) {
  const read = readPaperList(data)
  const w = mount(PositionsTotals, { props: { real: null, paper: { loaded: true, stale: false, totalAfter: read.totals.totalAfter, closedNote: read.totals.closedNote } } })
  return { text: w.get('[data-testid="totals-paper"]').text(), note: w.find('[data-testid="totals-paper-closed-note"]').exists() ? w.get('[data-testid="totals-paper-closed-note"]').text() : null }
}

describe('one reply, one total: Home and Positions show the same figure', () => {
  it('mixed set (priced running + settled + settling): the same text on both, the settling one is counted in the line, not the figure', async () => {
    paperAnswer = MIXED()
    const home = await homeFigure()
    const pos = positionsFigure(MIXED())
    expect(pos.text).toContain('+22.00')
    expect(home).toContain('+22.00')
    expect(pos.note).toBe('Includes 1 closed strategy.')
    expect(readPaperList(MIXED()).totals.leftOut).toBe('1 strategy left out: its price is not live.')
  })
  it('every state of the figure reads the same on both: paused, none priced', async () => {
    paperAnswer = reply([row(3, { state: 'PAUSED', total_text: null, total_after_text: null, after_charges_reason: 'prices_not_live' })],
      { total_text: null, total_after_text: null, after_charges_reason: 'prices_not_live', totals_reason_text: 'Prices are not live' })
    const home = await homeFigure()
    const pos = positionsFigure(paperAnswer)
    expect(home).not.toMatch(/\d/) // no number on Home
    expect(pos.text).not.toMatch(/\d/) // none on Positions
  })
})

describe('the closed-strategies line is tied to the rows of the same reply', () => {
  it('count equals the closed rows: the line stands', () => {
    expect(readPaperList(MIXED()).totals.closedNote).toBe('Includes 1 closed strategy.')
  })
  it('count differs from the closed rows (15 vs 14 on 27 Nov): no line is shown, the mismatch is named for the page', () => {
    const d = MIXED()
    d.totals.closed_count = 2
    d.totals.closed_text = 'Includes 2 closed strategies.'
    const t = readPaperList(d).totals
    expect(t.closedNote).toBe(null)
    expect(t.closedMismatch).toEqual({ server: 2, rows: 1 })
  })
  it('an unreadable row: the rows cannot be counted, so the server line stands as sent', () => {
    const d = MIXED()
    d.strategies.push({ strategy_id: 9 }) // does not read
    expect(readPaperList(d).totals.closedNote).toBe('Includes 1 closed strategy.')
  })
  it('no count sent: the line stands as sent (old reply)', () => {
    const d = MIXED()
    delete d.totals.closed_count
    expect(readPaperList(d).totals.closedNote).toBe('Includes 1 closed strategy.')
  })
})
