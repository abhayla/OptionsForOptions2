// P10 Wave 2 (ADR-330 (11), (13), ADR-008): the ONE reader of GET /api/strategies/{id}/plan-watch. The reply below is in the exact
// server shape (backend/ofo_app/routes/plan_watch.py PlanWatchOut, tests_app/test_plan_watch.py). The browser computes nothing.
import { describe, it, expect, vi, beforeEach } from 'vitest'

let reply = null
const calls = []
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (url) => { calls.push(url); return reply() } } }
})

import { readPlanWatch, PLAN_WATCH_UNAVAILABLE, PLAN_WATCH_NOT_FOUND } from '@/lib/planWatch'

const line = (over = {}) => ({
  key: 'T-07', kind: 'target', section: 'plan', label: 'Profit target Rs 1,200.00', unit: 'pnl_rupees', fires_at: '1200.00',
  now: '350.00', distance_rs: '850.00', distance_pct: '70.83', state: 'watching', reason: null, ...over,
})
const SERVER = (over = {}) => ({
  strategy_id: 7, as_of: '2026-11-26T05:10:00Z', as_of_text: 'As of 10:40:00 AM IST', plan_state: 'planned', no_plan_text: null,
  armed_heading: null, paused: null, lines: [line()], ...over,
})
const ok = (data) => () => Promise.resolve({ data })
const fail = (e) => () => Promise.reject(e)

beforeEach(() => { calls.length = 0 })

describe('readPlanWatch', () => {
  it('stated: a plan with lines keeps the server text and figures as sent, split by section', async () => {
    reply = ok(SERVER({ armed_heading: 'Armed in the Stops panel', lines: [line(), line({ key: 'ix1', kind: 'index_exit', section: 'armed', label: 'NIFTY at or above 23,400', unit: 'index_points', fires_at: '23400.00', now: '23050.00', distance_rs: '350.00', distance_pct: '1.52' })] }))
    const v = await readPlanWatch(7)
    expect(calls).toEqual(['/strategies/7/plan-watch'])
    expect(v.state).toBe('ok')
    expect(v.planState).toBe('planned')
    expect(v.planLines.map((l) => l.key)).toEqual(['T-07'])
    expect(v.armedLines.map((l) => l.key)).toEqual(['ix1'])
    expect(v.armedHeading).toBe('Armed in the Stops panel')
    expect(v.planLines[0]).toMatchObject({ firesAt: '1200.00', now: '350.00', distanceRs: '850.00', distancePct: '70.83', state: 'watching', unit: 'pnl_rupees' })
    expect(v.asOfText).toBe('As of 10:40:00 AM IST')
  })
  it('absent: no plan prints no_plan_text and still lists the armed triggers under the heading', async () => {
    reply = ok(SERVER({ plan_state: 'no_plan', no_plan_text: 'No plan: nothing is watched for this strategy', armed_heading: 'Armed in the Stops panel', lines: [line({ key: 'ls1', kind: 'leg_stop', section: 'armed', unit: 'option_price' })] }))
    const v = await readPlanWatch(7)
    expect(v.state).toBe('ok')
    expect(v.planState).toBe('no_plan')
    expect(v.noPlanText).toBe('No plan: nothing is watched for this strategy')
    expect(v.planLines).toEqual([])
    expect(v.armedLines).toHaveLength(1)
  })
  it('empty: no plan lines and no armed lines is an ok reply with nothing to list', async () => {
    reply = ok(SERVER({ lines: [] }))
    const v = await readPlanWatch(7)
    expect(v.state).toBe('ok')
    expect(v.planLines).toEqual([])
    expect(v.armedLines).toEqual([])
    expect(v.empty).toBe(true)
  })
  it('a line with now absent keeps null (never 0) and its reason', async () => {
    reply = ok(SERVER({ lines: [line({ now: null, distance_rs: null, distance_pct: null, state: 'paused', reason: 'Prices are not live' })] }))
    const l = (await readPlanWatch(7)).planLines[0]
    expect(l.now).toBeNull()
    expect(l.distanceRs).toBeNull()
    expect(l.distancePct).toBeNull()
    expect(l.reason).toBe('Prices are not live')
  })
  it('the user pause carries its server text', async () => {
    reply = ok(SERVER({ plan_state: 'paused', paused: { until: '1030', text: 'Paused until 10:30' }, lines: [] }))
    const v = await readPlanWatch(7)
    expect(v.planState).toBe('paused')
    expect(v.pausedText).toBe('Paused until 10:30')
  })
  it('not found: a 404 is its own state', async () => {
    reply = fail({ status: 404, message: 'x', parts: null })
    expect(await readPlanWatch(7)).toMatchObject({ state: 'not_found', text: PLAN_WATCH_NOT_FOUND, planLines: [], armedLines: [] })
  })
  it('failed: a failed request uses the server parts text when it sent one, else the neutral text; no lines', async () => {
    reply = fail({ status: 503, message: 'x', parts: { what_happened: 'The check could not run.', impact: 'i', what_is_blocked: 'b', next_action: 'n' } })
    expect(await readPlanWatch(7)).toMatchObject({ state: 'failed', text: 'The check could not run.', planLines: [] })
    reply = fail({ status: null, message: 'network', parts: null })
    expect(await readPlanWatch(7)).toMatchObject({ state: 'failed', text: PLAN_WATCH_UNAVAILABLE })
  })
  it('malformed: an unusable top level reads as unavailable with no lines', async () => {
    const bad = [null, 'x', {}, [], SERVER({ lines: 'no' }), SERVER({ lines: null })]
    for (const b of bad) {
      reply = ok(b)
      expect(await readPlanWatch(7), JSON.stringify(b)).toMatchObject({ state: 'unavailable', text: PLAN_WATCH_UNAVAILABLE, planLines: [], armedLines: [] })
    }
  })
  it('malformed line (Lane R, 27 Nov 2026): the reply is kept and that line reads Not checked with no figures', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    const bad = [
      line({ state: 'maybe' }), line({ section: 'other' }), line({ now: 12 }), line({ label: '' }), null, line({ fires_at: 'abc' }), line({ key: '' }),
    ]
    for (const b of bad) {
      reply = ok(SERVER({ lines: [line({ key: 'T-06' }), b] }))
      const v = await readPlanWatch(7)
      expect(v.state, JSON.stringify(b)).toBe('ok')
      const all = [...v.planLines, ...v.armedLines]
      expect(all, JSON.stringify(b)).toHaveLength(2)
      expect(all.find((l) => l.key === 'T-06').state).toBe('watching')
      expect(all[1]).toMatchObject({ state: 'not_computable', firesAt: null, now: null, distanceRs: null, distancePct: null })
    }
  })
  it('a reply for another strategy is unavailable (an answer for a key no longer shown)', async () => {
    reply = ok(SERVER({ strategy_id: 8 }))
    expect((await readPlanWatch(7)).state).toBe('unavailable')
  })
  it('a superseded request is not an answer', async () => {
    reply = fail({ superseded: true })
    expect((await readPlanWatch(7)).state).toBe('superseded')
  })
})
