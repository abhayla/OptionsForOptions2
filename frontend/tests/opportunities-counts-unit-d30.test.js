// D-30 (ADR-320): the counters line is labelled with its unit (conditions) and states the rows beside it, in the server's words.
import { describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import AdjustmentOpportunitiesPage from '@/pages/AdjustmentOpportunitiesPage.vue'

const reply = {
  groups: [{ group: '160-g1', strategy_id: 160, strategy_name: 'C6', shown_at: '2026-11-23T09:01:20Z', label: 'x', summary: null, has_open: false,
    records: [{ id: 1, rule_id: 'R-1', trigger_id: 'T-01', stage: null, value: '0.7293', threshold: '0.75', condition: 'c', shown_at: '2026-11-23T09:01:20Z', outcome: 'lapsed', outcome_text: 'Lapsed', detail: null, can_act: false, closed_at: null }] }],
  held: [], counts: [{ outcome: 'lapsed', text: 'Lapsed', count: 1 }], empty_text: null, dismiss_reasons: [],
  totals: { conditions: 1, rows: 1, text: 'Counters count conditions, not rows. Conditions: 1. Rows: 1. One row can hold several conditions.' },
}
describe('D-30 the counters say their unit', () => {
  it('shows the totals sentence above the counters', async () => {
    const w = mount(AdjustmentOpportunitiesPage, { props: { client: { get: async () => ({ data: reply }) } }, global: { stubs: { RouterLink: true } } })
    await flushPromises()
    expect(w.find('[data-testid="opp-totals"]').text()).toBe(reply.totals.text)
  })
})
