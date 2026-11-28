// Lane F2 item 1 (I-197, MUST stop): the builder Plan block of a running trade (A-H strategy 209) printed "Playbook", "Max adjustments",
// "Time exit" but no stop or target figure (FJ second PC list O-R-09 / W-01). Raw body of 209 not seen: shape from the plan sheet's
// own server reading (PlanOut: target, stop, *_words, *_rupees, *_rupee_words). The block now prints the plan's own stop and target
// with units, or the reason none is set, whenever the rule check's lines carry no row for that level.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

let planBody
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: () => Promise.resolve({ data: planBody }), post: () => Promise.reject(new Error('no')), put: () => Promise.reject(new Error('no')) } }
})
import PlanEntry from '@/components/strategy/PlanEntry.vue'

const LABELS = { plan_entry: 'Plan', playbook: 'Playbook', no_plan: 'No plan', max_adjustments: 'Max adjustments', time_exit: 'Time exit',
  stop: 'Stop', target: 'Target', stop_rupees: 'Stop (Rs)', target_rupees: 'Target (Rs)', edit: 'Edit', set_plan: 'Set plan', title: 'Plan', customise: 'c', use_as_is: 'u', save: 's', close: 'x', playbook_label: 'p' }
const PLAN = { playbook_id: 9, playbook_name: 'A-H playbook', target: '50', stop: '15.38', target_words: '50 % of max profit', stop_words: '15.38 % of max loss',
  max_adjustments: 2, time_exit: { hour: 15, minute: 15 }, time_exit_on: null, target_rupees: '1950.00', stop_rupees: '400.00',
  target_rupee_words: 'Rs 1950.00', stop_rupee_words: 'Rs 400.00', changed: [], switched_off: [], accepted_at: '2026-11-27T10:00:00+05:30' }
const body = (plan) => ({ strategy_id: 209, type: 'ic', type_name: 'Iron condor', generic: false, generic_text: null, labels: LABELS,
  playbooks: [{ id: 9, name: 'A-H playbook', is_system: false, draft: false, active: true }], prefill: { playbook_id: 9 }, plan })
const mounted = []
afterEach(() => { mounted.splice(0).forEach((w) => w.unmount()) })
async function card(props, plan = PLAN) {
  planBody = body(plan)
  const w = mount(PlanEntry, { props: { strategyId: 209, checkStatus: 'ok', ...props } })
  mounted.push(w)
  await flushPromises()
  return w
}
const txt = (w, id) => w.find(`[data-testid="${id}"]`)
const PAUSED = { paused: { text: 'The market is closed; nothing is checked now.' }, limits: [{ rule_id: 'T-06', state: 'checked', text: 'x' }], playbook: { source: 'plan' } }

describe('the plan block prints the stop and the target', () => {
  it('check paused (market closed): the plan\'s own stop and target with units', async () => {
    const w = await card({ check: PAUSED })
    expect(txt(w, 'plan-entry-stop').text()).toBe('Stop: 15.38 % (Rs 400.00)')
    expect(txt(w, 'plan-entry-target').text()).toBe('Target: 50 % (Rs 1950.00)')
  })
  it('a check row for the stop is printed once: no second stop line; the target the check did not carry still shows', async () => {
    const check = { limits: [{ rule_id: 'T-06', trigger_id: 'T-06', state: 'checked', text: 'Stop: loss of 15.38 % of max loss (Rs 400.00)' }], playbook: { source: 'plan' } }
    const w = await card({ check })
    expect(txt(w, 'plan-entry-limit-T-06').exists()).toBe(true)
    expect(txt(w, 'plan-entry-stop').exists()).toBe(false)
    expect(txt(w, 'plan-entry-target').text()).toBe('Target: 50 % (Rs 1950.00)')
  })
  it('no target set: the reason, not silence', async () => {
    const w = await card({ check: PAUSED }, { ...PLAN, target: null, target_rupees: null, target_words: null, target_rupee_words: null })
    expect(txt(w, 'plan-entry-target').text()).toBe('No target is set for this trade.')
  })
  it('no stop at all: the reason', async () => {
    const w = await card({ check: PAUSED }, { ...PLAN, stop: null, stop_rupees: null })
    expect(txt(w, 'plan-entry-stop').text()).toBe('No stop is set for this trade.')
  })
  it('only a rupee stop: the rupee figure with its unit', async () => {
    const w = await card({ check: PAUSED }, { ...PLAN, stop: null })
    expect(txt(w, 'plan-entry-stop').text()).toBe('Stop (Rs): Rs 400.00')
  })
  it('check still loading or failed: the plan\'s levels are saved facts and still show; no plan: nothing', async () => {
    const w = await card({ check: null, checkStatus: 'failed' })
    expect(txt(w, 'plan-entry-stop').exists()).toBe(true)
    const none = await card({ check: null, checkStatus: 'failed' }, null)
    expect(txt(none, 'plan-entry-stop').exists()).toBe(false)
    expect(txt(none, 'plan-entry-target').exists()).toBe(false)
  })
})

describe('W-30 (TG2, weekly trade #1, market closed): "Stop: not being checked" keeps the stop\'s stored figure beside the reason', () => {
  const REASON = 'No adjustment opportunity checked: prices stale or missing.'
  const check = (rows) => ({ limits: rows, playbook: { source: 'plan' } })
  const row = (trigger, over = {}) => ({ rule_id: trigger, trigger_id: trigger, state: 'not_checked', reason: REASON, text: `${trigger === 'T-07' ? 'Target' : 'Stop'}: not being checked: ${REASON}`, ...over })
  it('stop 45 % saved (Rs 731.25), market closed: ONE line, the stored figure first, the server\'s reason after it on the same line (coordinator: I-197 re-fix, walker W2 on 28c0e7be6)', async () => {
    const w = await card({ check: check([row('T-06'), row('T-07')]) }, { ...PLAN, stop: '45', stop_rupees: '731.25' })
    expect(txt(w, 'plan-entry-stop').text()).toBe(`Stop: 45 % (Rs 731.25), not being checked: ${REASON}`)
    expect(txt(w, 'plan-entry-target').text()).toBe(`Target: 50 % (Rs 1950.00), not being checked: ${REASON}`)
    expect(txt(w, 'plan-entry-limit-T-06').exists()).toBe(false) // the sentence never replaces the figure and is not printed twice
    expect(txt(w, 'plan-entry-limit-T-07').exists()).toBe(false)
  })
  it('a not-checked row with no reason text: the server\'s own row sentence stays beside the figure', async () => {
    const w = await card({ check: check([row('T-06', { reason: null })]) }, { ...PLAN, stop: '45', stop_rupees: '731.25' })
    expect(txt(w, 'plan-entry-stop').text()).toBe('Stop: 45 % (Rs 731.25)')
    expect(txt(w, 'plan-entry-limit-T-06').text()).toBe(`Stop: not being checked: ${REASON}`)
  })
  it('no stop in the plan and the stop not being checked: the server\'s row line is all there is', async () => {
    const w = await card({ check: check([row('T-06')]) }, { ...PLAN, stop: null, stop_rupees: null })
    expect(txt(w, 'plan-entry-stop').text()).toBe(`No stop is set for this trade.`)
  })
  it('a checked stop row already carries its figure: no second line (unchanged)', async () => {
    const w = await card({ check: check([row('T-06', { state: 'checked', text: 'Stop: loss of 45 % of max loss (Rs 731.25)' })]) }, { ...PLAN, stop: '45', stop_rupees: '731.25' })
    expect(txt(w, 'plan-entry-stop').exists()).toBe(false)
  })
})

