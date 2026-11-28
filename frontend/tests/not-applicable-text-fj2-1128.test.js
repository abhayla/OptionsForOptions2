// Lane FJ2 item 2 (28 Nov 2026). Real case: Lane Z2's fourth review F1 / FJ hand-over 3: a not_applicable row carrying the server's own
// `not_applicable_text` ("Not applicable: the position is real.") still printed the constant "Not applicable: real position.".
// Rule: the server's text when it sent one; the constant only as the fallback (absent, empty, not a string).
import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

let list = []
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (u) => (u.endsWith('/triggers') ? Promise.resolve({ data: { triggers: list } }) : Promise.reject({ status: 404, parts: null })), post: () => Promise.reject({ status: 404 }), delete: () => Promise.reject({ status: 404 }) } }
})
import PaperStops from '@/components/strategy/PaperStops.vue'
import PlanEntry from '@/components/strategy/PlanEntry.vue'
import { NOT_APPLICABLE_TEXT, armedIndexExits, notApplicableTextOf } from '@/lib/paperTriggers'

const OTHER = 'Not applicable: this trade is real, so no paper stop applies.'
const trig = (over = {}) => ({ id: 7, strategy_id: 48, kind: 'leg_stop', direction: 'below', level: '100.00', level_text: '100.00', contract_id: 'C1',
  contract_text: 'NIFTY 24500 CE', underlying: 'NIFTY', state: 'not_applicable', created_at: '2026-11-20T05:00:00Z', fired_at: null, cancelled_at: null, ...over })

describe('FJ2-2 the server\'s not_applicable_text', () => {
  it('helper: server text, else the constant (absent, empty, blank, not a string)', () => {
    expect(notApplicableTextOf({ not_applicable_text: OTHER })).toBe(OTHER)
    for (const v of [undefined, null, '', '   ', 5, {}]) expect(notApplicableTextOf({ not_applicable_text: v })).toBe(NOT_APPLICABLE_TEXT)
    expect(notApplicableTextOf(null)).toBe(NOT_APPLICABLE_TEXT)
  })
  it('PaperStops row prints the server text; a row without one prints the constant', async () => {
    list = [trig({ not_applicable_text: OTHER }), trig({ id: 8 })]
    const w = mount(PaperStops, { props: { strategyId: 48, underlying: 'NIFTY', legs: [] } })
    await flushPromises()
    expect(w.get('[data-trigger-id="7"]').text()).toBe(OTHER)
    expect(w.get('[data-trigger-id="8"]').text()).toBe(NOT_APPLICABLE_TEXT)
    w.unmount()
  })
  it('PlanEntry exit line prints the server text; a row without one prints the constant', () => {
    const exits = armedIndexExits([trig({ id: 5, kind: 'conditional_exit', not_applicable_text: OTHER }), trig({ id: 6, kind: 'conditional_exit' })])
    const w = mount(PlanEntry, { props: { strategyId: 48, exits, check: null } })
    expect(w.get('[data-testid="plan-entry-exit-5"]').text()).toBe(OTHER)
    expect(w.get('[data-testid="plan-entry-exit-6"]').text()).toBe(NOT_APPLICABLE_TEXT)
    w.unmount()
  })
})
