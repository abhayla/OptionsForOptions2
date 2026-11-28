// Lane F3 I-201 (T3-09): a dismissed adjustment row said "You dismissed this" with no reason word. Real case: ADJ-02 row T-09
// dismissed with reason "Not relevant" (the server's `detail`); a dismissal made with no reason has `detail` null.
import { describe, it, expect, vi, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

let reply
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: () => Promise.resolve({ data: reply }), post: () => Promise.reject({ parts: null }) } }
})
vi.mock('chart.js/auto', () => ({ default: class { destroy() {} } }))
import AdjustmentOpportunitiesPage from '@/pages/AdjustmentOpportunitiesPage.vue'

const rec = (detail) => ({ id: 3, rule_id: 'T-09', trigger_id: 'T-09', stage: 'Middle', value: '2.7000', threshold: '3.0000', condition: 'A short leg premium falls', shown_at: '2026-10-31T07:47:04Z', outcome: 'dismissed', outcome_text: 'You dismissed this', detail, can_act: false, closed_at: '2026-10-31T08:00:00Z' })
const body = (detail) => ({ groups: [{ group: '1-x', strategy_id: 1, strategy_name: '"S"', shown_at: '2026-10-31T07:47:04Z', label: 'L', summary: null, has_open: false, records: [rec(detail)] }], held: [], counts: [], empty_text: null, dismiss_reasons: [] })
const mounted = []
afterEach(() => { mounted.splice(0).forEach((w) => w.unmount()) })
const outcome = async (detail) => { reply = body(detail); const w = mount(AdjustmentOpportunitiesPage, { global: { stubs: { RouterLink: { props: ['to'], template: '<a><slot /></a>' } } } }); mounted.push(w); await flushPromises(); return w.get('[data-testid="opp-outcome"]').text() }

describe('I-201 dismissed row reason', () => {
  it('the server sent a reason: it is printed beside "You dismissed this"', async () => {
    const t = await outcome('Not relevant')
    expect(t).toContain('You dismissed this'); expect(t).toContain('Not relevant')
  })
  it('no reason sent (dismissed with none): the row says so, plainly', async () => {
    const t = await outcome(null)
    expect(t).toContain('You dismissed this'); expect(t).toContain('No reason given')
  })
  it('blank reason text (ambiguous): treated as none', async () => {
    expect(await outcome('   ')).toContain('No reason given')
  })
})
