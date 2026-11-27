// Lane H (REQ-049 AC-4): readPlanWatchBatch asks ONCE for the whole list and gives each id the view readPlanWatch would
// (ok / not_found / failed / unavailable); one refused row never hides the others; a failed request fails every id.
import { describe, it, expect, vi, beforeEach } from 'vitest'

const get = vi.fn()
vi.mock('@/services/api', () => ({ default: { get: (...a) => get(...a) }, NEUTRAL_PARTS: { neutral: true } }))
import { readPlanWatchBatch } from '@/lib/planWatchBatch'

const WATCH = (id) => ({
  strategy_id: id, as_of: '2026-11-27T10:00:00+05:30', as_of_text: 'As of 10:00', plan_state: 'planned', no_plan_text: null,
  armed_heading: null, paused: null,
  lines: [{ key: 'T-07', kind: 'target', section: 'plan', label: 'Target', unit: 'pnl_rupees', fires_at: '1000.00', now: '400.00', distance_rs: '600.00', distance_pct: '60.00', state: 'watching', reason: null }],
})

beforeEach(() => { get.mockReset() })

describe('readPlanWatchBatch', () => {
  it('makes ONE request for every row and keeps one bad row from the others', async () => {
    get.mockResolvedValue({ data: { as_of: null, items: [
      { strategy_id: 1, state: 'ok', watch: WATCH(1), refusal: null, status: null },
      { strategy_id: 2, state: 'refused', watch: null, refusal: { what_happened: 'Plan watch is busy.' }, status: 409 },
      { strategy_id: 3, state: 'refused', watch: null, refusal: { what_happened: 'x' }, status: 404 },
    ] } })
    const views = await readPlanWatchBatch([1, 2, 3, 1])
    expect(get).toHaveBeenCalledTimes(1)
    expect(get.mock.calls[0][0]).toBe('/plan-watch?strategy_ids=1,2,3')
    expect(views.get('1').state).toBe('ok')
    expect(views.get('1').planLines[0].key).toBe('T-07')
    expect(views.get('2')).toMatchObject({ state: 'failed', text: 'Plan watch is busy.' })
    expect(views.get('3').state).toBe('not_found')
  })
  it('a row the reply does not carry, or carries unreadable, is unavailable', async () => {
    get.mockResolvedValue({ data: { as_of: null, items: [{ strategy_id: 1, state: 'ok', watch: { strategy_id: 1 } }] } })
    const views = await readPlanWatchBatch([1, 2])
    expect(views.get('1').state).toBe('unavailable')
    expect(views.get('2').state).toBe('unavailable')
  })
  it('a failed request gives every id a failed view and never throws', async () => {
    get.mockImplementation(async () => { throw Object.assign(new Error('x'), { parts: { what_happened: 'The server took too long.' } }) })
    const views = await readPlanWatchBatch([4, 5])
    expect([...views.values()].map((v) => v.state)).toEqual(['failed', 'failed'])
    expect(views.get('4').text).toBe('The server took too long.')
    expect(views.get('4').planLines).toEqual([])
  })
})
