// ADR-330 (64): a real position never gets a paper stop. An old armed paper stop on one comes back as state "not_applicable":
// not live (no armed badge, no Cancel / Keep, no offer to set a new one) and its row reads "Not applicable: real position."
// Unknown or absent state keeps today's behaviour. Real case: none in 30 days; the row below is the route's documented shape.
import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

let list = []
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (u) => (u.endsWith('/triggers') ? Promise.resolve({ data: { triggers: list } }) : Promise.reject({ status: 404, parts: null })), post: () => Promise.reject({ status: 404 }), delete: () => Promise.reject({ status: 404 }) } }
})
import PaperStops from '@/components/strategy/PaperStops.vue'
import PlanEntry from '@/components/strategy/PlanEntry.vue'
import { NOT_APPLICABLE_REAL_TEXT, armedIndexExits, legStopsGone } from '@/lib/paperTriggers'

const SENTENCE = 'Not applicable: real position.'
const trig = (over = {}) => ({ id: 7, strategy_id: 48, kind: 'leg_stop', direction: 'below', level: '100.00', level_text: '100.00', contract_id: 'C1',
  contract_text: 'NIFTY 24500 CE', underlying: 'NIFTY', state: 'armed', created_at: '2026-11-20T05:00:00Z', fired_at: null, cancelled_at: null,
  set_before_adjustment: true, adjustment_note: 'n', ...over })

describe('not_applicable stop on a real position (ADR-330 (64))', () => {
  it('the sentence is the one the coordinator named', () => { expect(NOT_APPLICABLE_REAL_TEXT).toBe(SENTENCE) })

  it('PaperStops: the row reads the sentence only, no state badge, no Cancel, no Keep', async () => {
    list = [trig({ state: 'not_applicable' })]
    const w = mount(PaperStops, { props: { strategyId: 48, underlying: 'NIFTY', legs: [] } })
    await flushPromises()
    const row = w.get('[data-testid="trigger-row"]')
    expect(row.text()).toBe(SENTENCE)
    expect(w.find('[data-testid="trigger-state"]').exists()).toBe(false)
    expect(w.find('[data-testid="trigger-cancel-7"]').exists()).toBe(false)
    expect(w.find('[data-testid="trigger-keep-7"]').exists()).toBe(false)
    w.unmount()
  })

  it('PaperStops: an armed row and a row with no state keep today\'s behaviour', async () => {
    list = [trig({ id: 8 }), trig({ id: 9, state: undefined })]
    const w = mount(PaperStops, { props: { strategyId: 48, underlying: 'NIFTY', legs: [] } })
    await flushPromises()
    expect(w.get('[data-trigger-id="8"] [data-testid="trigger-state"]').text()).toBe('armed')
    expect(w.find('[data-testid="trigger-cancel-8"]').exists()).toBe(true)
    expect(w.get('[data-trigger-id="9"]').text()).not.toContain(SENTENCE)
    w.unmount()
  })

  it('PlanEntry (tracking panel exit line): the line is the sentence, not "Armed"', () => {
    const exits = armedIndexExits([trig({ id: 5, kind: 'conditional_exit', state: 'not_applicable' }), trig({ id: 6, kind: 'conditional_exit', level_text: '25,720', direction: 'above' })])
    const w = mount(PlanEntry, { props: { strategyId: 48, exits, check: null } })
    expect(w.get('[data-testid="plan-entry-exit-5"]').text()).toBe(SENTENCE)
    expect(w.get('[data-testid="plan-entry-exit-6"]').text()).toContain('Armed.')
    w.unmount()
  })

  it('legStopsGone: an armed stop that came back not_applicable is not "gone", so no offer to set a new one', () => {
    expect(legStopsGone([trig()], [trig({ state: 'not_applicable' })])).toEqual([])
    expect(legStopsGone([trig()], [trig({ state: 'fired' })])).toEqual([7])
  })
})
