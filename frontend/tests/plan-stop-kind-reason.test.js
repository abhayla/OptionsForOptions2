// F7 (Lane FC, 28 Nov; RESULTS-lane-r3 "To file 5"): when the server cannot show a stop because the expiry kind is not known it sends `stop_kind_reason`
// (a catalogue sentence). The plan sheet prints that sentence where the stop would be; absent or empty = nothing. Spec basis: ADR-330 (9), ADR-003.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

let body = null
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: () => Promise.resolve({ data: body }), post: () => Promise.resolve({ data: body }), put: () => Promise.resolve({ data: body }) } }
})
import AdjustPlanSheet from '@/components/strategy/AdjustPlanSheet.vue'

const LABELS = { title: 'Plan', playbook: 'Playbook', target: 'Target', stop: 'Stop', target_rupees: 'Target (Rs)', stop_rupees: 'Stop (Rs)', max_adjustments: 'Max adjustments',
  time_exit: 'Time exit', customise: 'Customise triggers', use_as_is: 'Use playbook as is', save: 'Save plan', close: 'Close' }
const answer = (over = {}) => ({ strategy_id: 70, type: 'ic', type_name: 'Iron condor', generic: false, generic_text: null, labels: LABELS,
  playbooks: [{ id: 9, name: '"Mine"', type: 'ic', type_name: 'Iron condor', is_system: false, draft: false, active: true }],
  plan: null, prefill: { playbook_id: 9, target: '50', stop: '', max_adjustments: 2, time_exit: null, target_words: '', stop_words: '' }, ...over })
const REASON = { error_class: 'info', code: 'plan_stop_kind_unknown', what_happened: 'The stop is not shown because the expiry kind of this trade is not known.', impact: 'i', what_is_blocked: 'b', next_action: 'n', external_text: 'x' }

const mounted = []
afterEach(() => { mounted.splice(0).forEach((w) => w.unmount()) })
async function sheet() {
  const w = mount(AdjustPlanSheet, { attachTo: document.body, props: { open: true, strategyId: 70 } })
  await flushPromises()
  mounted.push(w)
  return w
}
const why = (w) => w.find('[data-testid="plan-stop-kind-reason"]')

describe('F7 plan sheet shows stop_kind_reason where the stop would be', () => {
  it('stated (catalogue object): the sentence is printed inside the stop field block', async () => {
    body = answer({ stop_kind_reason: REASON })
    const w = await sheet()
    expect(why(w).text()).toBe('The stop is not shown because the expiry kind of this trade is not known.')
    expect(w.get('[data-testid="plan-stop"]').element.closest('label').contains(why(w).element)).toBe(true)
  })
  it('stated (bare string) is printed as given', async () => {
    body = answer({ stop_kind_reason: 'No stop can be shown here.' })
    expect(why(await sheet()).text()).toBe('No stop can be shown here.')
  })
  it('absent: nothing', async () => {
    body = answer()
    expect(why(await sheet()).exists()).toBe(false)
  })
  it('null and empty text: nothing (never an empty line)', async () => {
    body = answer({ stop_kind_reason: null })
    expect(why(await sheet()).exists()).toBe(false)
    body = answer({ stop_kind_reason: { what_happened: '' } })
    expect(why(await sheet()).exists()).toBe(false)
    body = answer({ stop_kind_reason: '' })
    expect(why(await sheet()).exists()).toBe(false)
  })
})
