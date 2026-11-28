// Lane FJ2 item 9 / O-R-09, W-01 (FJ second PC list): the Plan block of a running trade printed no stop or target figure.
// Real case: tracked trade with a saved plan (playbook "Mine", target 50 % of max profit, stop 25 % of max loss, max adjustments 2): the card showed the playbook and
// the guards only. Wanted: the target and the stop with their units (the server's words), or the plain fact that none is set. The numbers and words are the server's.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

let plan
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (u) => (u === '/strategies/7/adjustment-plan' ? Promise.resolve({ data: ANSWER() }) : Promise.reject({ status: 404, parts: null })) } }
})
import PlanEntry from '@/components/strategy/PlanEntry.vue'

const LABELS = { title: 'Plan', playbook: 'Playbook', target: 'Target', stop: 'Stop', target_rupees: 'Target (Rs)', stop_rupees: 'Stop (Rs)', max_adjustments: 'Max adjustments', time_exit: 'Time exit',
  time_exit_on: 'On', customise: 'Customise', use_as_is: 'Use as is', save: 'Save', close: 'Close', plan_entry: 'Plan', edit: 'Edit', set_plan: 'Set plan', no_plan: 'No plan' }
const PLAYBOOKS = [{ id: 9, name: 'Mine', type: 'ic', type_name: 'Iron condor', is_system: false, draft: false, active: true }]
const PREFILL = { playbook_id: 9, target: '50', stop: '50', max_adjustments: 2, time_exit: null, target_words: '', stop_words: '', target_source: 'percent', stop_source: 'percent' }
const ANSWER = () => ({ strategy_id: 7, type: 'ic', type_name: 'Iron condor', generic: false, generic_text: null, playbooks: PLAYBOOKS, plan, prefill: PREFILL, labels: LABELS })
const PLAN = { playbook_id: 9, playbook_name: 'Mine', target: '50.00', stop: '25.00', target_words: '50.00 % of max profit', stop_words: '25.00 % of max loss', max_adjustments: 2, time_exit: { hour: 15, minute: 15 }, time_exit_on: '' }
const mounted = []
afterEach(() => mounted.splice(0).forEach((w) => w.unmount()))
beforeEach(() => setActivePinia(createPinia()))
const card = async () => {
  const w = mount(PlanEntry, { props: { strategyId: 7, check: null, checkStatus: 'loading' }, attachTo: document.body })
  await flushPromises()
  mounted.push(w)
  return w
}

describe('FJ2-9 O-R-09 the Plan card shows the plan\'s target and stop with units, or says none is set', () => {
  it('plan with both: "Target: 50.00 % of max profit" and "Stop: 25.00 % of max loss" (the server\'s words)', async () => {
    plan = PLAN
    const w = await card()
    expect(w.get('[data-testid="plan-entry-target"]').text()).toBe('Target: 50.00 % of max profit')
    expect(w.get('[data-testid="plan-entry-stop"]').text()).toBe('Stop: 25.00 % of max loss')
  })
  it('the server sent a figure but no words: the figure with its percent unit', async () => {
    plan = { ...PLAN, target_words: '', stop_words: '' }
    const w = await card()
    expect(w.get('[data-testid="plan-entry-target"]').text()).toBe('Target: 50.00 %')
    expect(w.get('[data-testid="plan-entry-stop"]').text()).toBe('Stop: 25.00 %')
  })
  it('no target and no stop in the plan: each says it is not set, never a blank or a 0', async () => {
    plan = { ...PLAN, target: '', stop: '', target_words: '', stop_words: '' }
    const w = await card()
    expect(w.get('[data-testid="plan-entry-target"]').text()).toBe('Target: not set')
    expect(w.get('[data-testid="plan-entry-stop"]').text()).toBe('Stop: not set')
  })
  it('no plan at all: no target / stop lines (the "No plan" line stands)', async () => {
    plan = null
    const w = await card()
    expect(w.find('[data-testid="plan-entry-target"]').exists()).toBe(false)
    expect(w.find('[data-testid="plan-entry-none"]').exists()).toBe(true)
  })
})
