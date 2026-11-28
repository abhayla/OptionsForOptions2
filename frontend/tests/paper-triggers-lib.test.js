// Modular doors Phase 6 (PLAN 5.6, F7): the one place the paper triggers path, the reply shape check and the armed
// index-exit filter live. PaperStops.vue and TrackingPanel.vue keep their own failure policy and timing.
// Spec basis: REQ-109 AC-8 (the stops panel reads the strategy's triggers).
import { describe, it, expect } from 'vitest'
import { triggersPath, triggerListOf, armedIndexExits } from '@/lib/paperTriggers'

describe('paperTriggers (F7)', () => {
  it('triggersPath names the strategy', () => {
    expect(triggersPath(48)).toBe('/paper/strategies/48/triggers')
  })

  it('triggerListOf returns the array, or null when the reply has none', () => {
    expect(triggerListOf({ triggers: [] })).toEqual([])
    expect(triggerListOf({ triggers: [{ id: 1 }] })).toEqual([{ id: 1 }])
    expect(triggerListOf({})).toBeNull()
    expect(triggerListOf(null)).toBeNull()
    expect(triggerListOf(undefined)).toBeNull()
    expect(triggerListOf({ triggers: 'x' })).toBeNull()
  })

  it('armedIndexExits keeps armed and fired conditional exits, drops cancelled ones and leg stops', () => {
    const list = [
      { id: 1, kind: 'conditional_exit', state: 'armed' },
      { id: 2, kind: 'conditional_exit', state: 'fired' },
      { id: 3, kind: 'conditional_exit', state: 'cancelled' },
      { id: 4, kind: 'leg_stop', state: 'armed' },
      { id: 5, kind: 'leg_stop', state: 'cancelled' },
    ]
    expect(armedIndexExits(list).map((x) => x.id)).toEqual([1, 2])
    expect(armedIndexExits([])).toEqual([])
  })
})
