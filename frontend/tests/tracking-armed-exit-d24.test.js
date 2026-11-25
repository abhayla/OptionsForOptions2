// GC-ICLIVE D-24 (REQ-109 AC-8, ADR-317): an armed index conditional exit is shown on the builder's tracking panel with its level
// and state. Real 23 Nov case: C7 strategy 161 had 'Above 25,720' armed (the level text is the server's `paper_trigger_level`,
// "25,720"); the panel's Plan block listed only the Target / Stop lines. Every figure below is the server's own string.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

let triggers = null // GET /paper/strategies/161/triggers: a body, or an Error to reject with
let triggerCalls = 0
const answer = (url) => {
  if (url === '/strategies/161/tracking') return Promise.resolve({ data: TRACK })
  if (url === '/strategies/161/adjustment-check') return Promise.resolve({ data: CHECK })
  if (url.startsWith('/strategies/161/adjustment-plan')) return Promise.resolve({ data: PLAN })
  if (url === '/paper/strategies/161/triggers') {
    triggerCalls += 1
    return triggers instanceof Error ? Promise.reject(triggers) : Promise.resolve({ data: triggers })
  }
  return Promise.reject({ status: 404, parts: null })
}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (u) => answer(u), post: (u) => answer(u), put: (u) => answer(u) } }
})
import TrackingPanel from '@/components/strategy/TrackingPanel.vue'

const TRACK = { strategy_id: 161, state: 'LIVE', paper_pnl: '195.00', paper_pnl_text: '+195.00', as_of: null, legs: [], detections: [] }
const LABELS = { plan_entry: 'Plan', playbook: 'Playbook', target: 'Target', stop: 'Stop', max_adjustments: 'Max adjustments', time_exit: 'Time exit',
  edit: 'Edit plan', no_plan: 'No plan saved yet: default rules apply', set_plan: 'Set plan' }
const PLAN = { strategy_id: 161, type: 'ic', type_name: 'Iron condor', generic: false, generic_text: null, labels: LABELS, plan: null,
  playbooks: [{ id: 9, name: 'Mine', type: 'ic', type_name: 'Iron condor', is_system: false, draft: false, active: true }], prefill: { playbook_id: 9 } }
const CHECK = { strategy_id: 161, as_of: '2026-11-23T09:45:00Z', as_of_text: 'As of 03:15:00 PM IST', strategy_type: 'ic', type_name: 'Iron condor',
  playbook: { source: 'system', id: 1, status: null, draft: false }, stage: { name: null, index: null }, withheld: null, results: [], paused: null,
  limits: [{ rule_id: 'T-07', trigger_id: 'T-07', threshold: '40.0000', amount: null, later: [], tightened_by: null, state: 'checked', reason: null,
    text: 'Target: profit of 40 % of max profit, before charges', after: null, reason_code: null }] }
const trig = (over = {}) => ({ id: 31, strategy_id: 161, kind: 'conditional_exit', direction: 'above', level: '25720.00', level_text: '25,720',
  contract_id: null, contract_text: null, underlying: 'NIFTY', state: 'armed', created_at: '2026-11-23T08:00:00Z', fired_at: null, cancelled_at: null,
  set_before_adjustment: false, adjustment_note: null, ...over })

const mounted = []
const t = (w, id) => w.find(`[data-testid="${id}"]`)
async function panel() {
  const w = mount(TrackingPanel, { props: { savedId: 161, legs: [] } })
  mounted.push(w)
  await flushPromises()
  return w
}
beforeEach(() => { triggers = { triggers: [] }; triggerCalls = 0 })
afterEach(() => { mounted.splice(0).forEach((w) => w.unmount()) })

describe('an armed conditional exit is on the tracking panel (D-24)', () => {
  it('C7 161: Above 25,720 armed shows its level and state beside the Target line', async () => {
    triggers = { triggers: [trig()] }
    const w = await panel()
    const line = t(w, 'plan-entry-exit-31').text()
    expect(line).toBe('Conditional exit: all legs exit if the index goes above 25,720. Armed.')
    expect(line).toContain('25,720')
    expect(line).toContain('Armed')
    expect(t(w, 'plan-entry-limit-T-07').exists()).toBe(true) // the rule-based line still stands
  })

  it('both directions, a fired one and a cancelled one: armed and fired are shown, cancelled is not', async () => {
    triggers = { triggers: [trig({ id: 33, direction: 'below', level: '25100.00', level_text: '25,100', state: 'fired', fired_at: '2026-11-23T09:00:00Z' }),
      trig({ id: 32, state: 'cancelled', cancelled_at: '2026-11-23T08:30:00Z' }), trig()] }
    const w = await panel()
    expect(t(w, 'plan-entry-exit-31').text()).toContain('Armed')
    expect(t(w, 'plan-entry-exit-33').text()).toContain('Fired')
    expect(t(w, 'plan-entry-exit-33').text()).toContain('25,100')
    expect(t(w, 'plan-entry-exit-32').exists()).toBe(false)
  })

  it('a leg stop is not an index exit: it is not listed in this block', async () => {
    triggers = { triggers: [trig({ id: 40, kind: 'leg_stop', contract_id: 77, contract_text: 'NIFTY 25400 PE', level_text: '124.50' })] }
    const w = await panel()
    expect(t(w, 'plan-entry-exit-40').exists()).toBe(false)
  })

  it('no exit set: no exit line and no failure line', async () => {
    const w = await panel()
    expect(w.find('[data-testid^="plan-entry-exit-"]').exists()).toBe(false)
    expect(t(w, 'plan-entry-exits-failed').exists()).toBe(false)
  })

  it('an unreadable exits list says so, never "none set"', async () => {
    triggers = new Error('down')
    const w = await panel()
    expect(t(w, 'plan-entry-exits-failed').exists()).toBe(true)
    expect(w.find('[data-testid^="plan-entry-exit-"]').exists()).toBe(false)
  })
})
