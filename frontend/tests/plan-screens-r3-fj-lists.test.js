// Lane FJ (R3) item 3, the list half. Real cases: a settled trade on Positions printed no Plan watch sentence (UX-A06); a real section with no Zerodha
// session printed "No open Zerodha positions." (fd2: GET /positions answers 200 with broker_connected:false and real_pnl.state "not_connected");
// the Stops box printed nothing of what a leg costs because FC2 passed a map PaperStops never declares (UX-A02); the batch Plan watch answers
// a third item state "not_read" that the reader printed as an error. Spec basis: ADR-330 (13), (56), (58), (64); REQ-049; ADR-008; ADR-003.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import REAL0 from './fixtures/paper-strategies.json'
import { closedFrom } from './_closedRows'

const REAL = { ...REAL0, strategies: REAL0.strategies.map((s) => ({ ...s, closed: closedFrom(s.positions) })) }
const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url, body) => {
    calls.push([method, url, body])
    const a = answers[`${method} ${url}`] ?? (method === 'GET' && url === '/market/exit-state' ? async () => ({ data: { closed: false, sentence: null, next_open_at: null } }) : undefined)
    return a ? a() : Promise.reject({ message: 'no answer', parts: null, status: null })
  }
  return { ...actual, default: { get: reply('GET'), post: reply('POST'), delete: reply('DELETE') } }
})

import PaperStrategies from '@/components/strategy/PaperStrategies.vue'
import PaperStops from '@/components/strategy/PaperStops.vue'
import PlanWatch from '@/components/strategy/PlanWatch.vue'
import PositionsPage from '@/pages/PositionsPage.vue'
import { readPlanWatchBatch, PLAN_WATCH_NOT_READ } from '@/lib/planWatchBatch'
import { resetPlanWatchQueueForTests } from '@/lib/planWatchQueue'
import { PAPER_NO_FIGURE } from '@/lib/paperList'

const ok = (data) => () => Promise.resolve({ data })
const t = (w, id) => w.find(`[data-testid="${id}"]`)
const clone = () => JSON.parse(JSON.stringify(REAL))
async function show(Comp, url = '/p') {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/', component: { template: '<div/>' } },
    { path: '/p', component: Comp, meta: { title: 'T', parent: 'Positions', view: 'current' } },
    { path: '/strategy/builder', component: { template: '<div/>' } },
  ] })
  router.push(url)
  await router.isReady()
  const w = mount(Comp, { global: { plugins: [router] } })
  await flushPromises()
  return w
}
beforeEach(() => { calls.length = 0; answers = {}; resetPlanWatchQueueForTests(); vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] }) })
afterEach(() => vi.useRealTimers())

describe('UX-A06: a settled trade on Positions says it is closed', () => {
  it('the settled row (every leg flat) carries the closed sentence and reads nothing; an open row keeps its watch', async () => {
    answers['GET /paper/strategies'] = ok(REAL)
    const w = await show(PaperStrategies)
    await t(w, 'show-closed').setValue(true)
    await flushPromises()
    const groups = w.findAll('[data-testid="paper-group"]')
    const settled = groups.find((g) => g.attributes('data-strategy') === String(REAL.strategies[0].strategy_id))
    expect(settled).toBeTruthy()
    expect(settled.find('[data-testid="plan-watch"]').exists()).toBe(false) // F2 (W-29 step 57, ADR-330 (57)): no box on a settled row
    const open = groups.find((g) => g.attributes('data-strategy') === String(REAL.strategies[1].strategy_id))
    expect(open.find('[data-testid="plan-watch-closed"]').exists()).toBe(false)
    expect(calls.some((c) => c[1].includes(`plan-watch?strategy_ids=`) && c[1].split('=')[1].split(',').includes(String(REAL.strategies[0].strategy_id)))).toBe(false)
  })
})

describe('UX-A02: what a leg costs now rides the leg (ltpText), never a side map', () => {
  it('Stops gets ltpText per open leg (null when the leg has no live price); the unused map is gone', async () => {
    const book = clone()
    const s = book.strategies[1]
    s.positions.find((p) => p.contract_id === 753).price_state = 'stale'
    s.positions.find((p) => p.contract_id === 753).ltp_text = null
    answers['GET /paper/strategies'] = ok(book)
    answers[`GET /paper/strategies/${s.strategy_id}/triggers`] = ok({ triggers: [] })
    const w = await show(PaperStrategies)
    await t(w, `stops-open-${s.strategy_id}`).trigger('click')
    await flushPromises()
    const stops = w.findComponent(PaperStops)
    expect(stops.props('legs').map((l) => [l.contractId, l.ltpText])).toEqual([['776', '21.70'], ['784', '31.15'], ['753', null]])
    expect(t(w, 'stop-cost-784').text()).toBe('Costs now 31.15')
    expect(t(w, 'stop-cost-753').text()).toBe('Costs now: not priced')
    expect(stops.attributes('current-price-text')).toBeUndefined()
  })
})

describe('fd2: GET /positions with no Zerodha session (200, broker_connected false)', () => {
  const NC = (over = {}) => ({ read_at: null, strategies: [], has_outside: false, outside_lots: 0, blocked: false, blocked_strategy_ids: [], broker_connected: false,
    real_pnl: { state: 'not_connected', pnl_text: null, reason: 'Zerodha is not connected, so real positions and their P&L are not read.', caption: null, excludes_note: null }, ...over })
  it('prints the server reason and a dash for the figure; never "No open Zerodha positions." or a read time', async () => {
    answers['GET /positions'] = ok(NC())
    answers['GET /paper/strategies'] = ok({ strategies: [], totals: null, answered_at: '2026-10-29T05:00:00Z' })
    const w = await show(PositionsPage)
    expect(t(w, 'real-state').attributes('data-state')).toBe('not_connected')
    expect(t(w, 'totals-real').text()).toBe(PAPER_NO_FIGURE)
    expect(t(w, 'totals-real-reason').text()).toBe('Zerodha is not connected, so real positions and their P&L are not read.')
    expect(t(w, 'positions-not-connected').text()).toBe('Zerodha is not connected, so real positions and their P&L are not read.')
    expect(t(w, 'positions-empty').exists()).toBe(false)
    expect(t(w, 'positions-read-at').exists()).toBe(false)
  })
  it('no reason sent: the one plain sentence, never an empty list', async () => {
    answers['GET /positions'] = ok(NC({ real_pnl: { state: 'not_connected', pnl_text: null, reason: null, caption: null, excludes_note: null } }))
    answers['GET /paper/strategies'] = ok({ strategies: [], totals: null, answered_at: '2026-10-29T05:00:00Z' })
    const w = await show(PositionsPage)
    expect(t(w, 'positions-not-connected').text()).toBe('No broker is connected, so no real positions are shown.')
    expect(t(w, 'positions-empty').exists()).toBe(false)
  })
  it('connected (broker_connected true) and an empty list: the empty state stays', async () => {
    answers['GET /positions'] = ok(NC({ broker_connected: true, read_at: '2026-10-29T10:00:00+05:30', real_pnl: { state: 'stated', pnl_text: '0.00', reason: null, caption: null, excludes_note: null } }))
    answers['GET /paper/strategies'] = ok({ strategies: [], totals: null, answered_at: '2026-10-29T05:00:00Z' })
    const w = await show(PositionsPage)
    expect(t(w, 'positions-empty').exists()).toBe(true)
    expect(t(w, 'positions-not-connected').exists()).toBe(false)
  })
  it('broker_connected absent (an old reply): unchanged, the empty state', async () => {
    const { broker_connected: _b, ...old } = NC({ real_pnl: undefined })
    answers['GET /positions'] = ok({ ...old, read_at: '2026-10-29T10:00:00+05:30' })
    answers['GET /paper/strategies'] = ok({ strategies: [], totals: null, answered_at: '2026-10-29T05:00:00Z' })
    const w = await show(PositionsPage)
    expect(t(w, 'positions-not-connected').exists()).toBe(false)
  })
})

describe('fd2: /api/plan-watch item state "not_read"', () => {
  it('the batch reader makes a not_read view with its own plain line, not an error', async () => {
    answers['GET /plan-watch?strategy_ids=7,8'] = ok({ items: [{ strategy_id: 7, state: 'not_read' }, { strategy_id: 8, state: 'refused', status: 500, refusal: null }] })
    const views = await readPlanWatchBatch([7, 8])
    expect(views.get('7').state).toBe('not_read')
    expect(views.get('7').text).toBe(PLAN_WATCH_NOT_READ)
    expect(PLAN_WATCH_NOT_READ).toBe('The plan watch has not been read for this trade.')
    expect(views.get('8').state).toBe('failed')
  })
  it('the box prints that line; with the feed paused it still says "not read" (nothing to resume)', async () => {
    const view = { state: 'not_read', text: PLAN_WATCH_NOT_READ, planState: null, noPlanText: null, armedHeading: null, pausedText: null, asOfText: null, planLines: [], armedLines: [], empty: false }
    const w = mount(PlanWatch, { props: { strategyId: 7, view, compact: true, stale: true } })
    await flushPromises()
    expect(t(w, 'plan-watch-message').text()).toBe('The plan watch has not been read for this trade.')
    w.unmount()
  })
  it('an item with no state field at all stays unavailable (fail closed)', async () => {
    answers['GET /plan-watch?strategy_ids=9'] = ok({ items: [{ strategy_id: 9 }] })
    const views = await readPlanWatchBatch([9])
    expect(views.get('9').state).toBe('failed')
  })
})
