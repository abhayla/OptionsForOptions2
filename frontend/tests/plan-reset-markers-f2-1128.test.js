// Lane F2 (coordinator, D-TG2-1, check T2-19): after "Reset to playbook" the sheet said "Switched on again: triggers.T-01":
// a raw key on the screen. The user reads the trigger's name in plain words (its label in the trade's own rules); an
// unknown key, or rules that cannot be read, shows a plain fallback, never the key.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    const a = answers[`${method} ${url}`]
    if (a === undefined) return Promise.reject({ message: 'no answer', parts: null, status: 404 })
    return Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u, b) => respond('POST', u, b), put: (u, b) => respond('PUT', u, b) } }
})
import AdjustPlanSheet from '@/components/strategy/AdjustPlanSheet.vue'
import { markerNames, MARKER_FALLBACK_TEXT } from '@/lib/adjustPlan'

const LABELS = { title: 'Plan', playbook: 'Playbook', target: 'Target', stop: 'Stop', target_rupees: 'Target (Rs)', stop_rupees: 'Stop (Rs)',
  max_adjustments: 'Max adjustments', time_exit: 'Time exit', time_exit_on: 'On', customise: 'Customise triggers', use_as_is: 'Use as is', save: 'Save plan', close: 'Close',
  reset: 'Reset to playbook', reset_confirm: 'Put the playbook conditions back?', reset_put_back: 'Changed back:', reset_put_back_off: 'Switched on again:', reset_put_back_none: 'Nothing needed putting back.' }
const PLAYBOOKS = [{ id: 9, name: 'Mine', is_system: false, draft: false, active: true }]
const PLAN = { playbook_id: 9, playbook_name: 'Mine', target: '50', stop: '50', max_adjustments: 2, time_exit: null, changed: [], switched_off: [], accepted_at: '2026-11-27T10:00:00+05:30' }
const PREFILL = { playbook_id: 9, target: '50', stop: '50', max_adjustments: 2, time_exit: null }
const SHEET = { strategy_id: 70, type: 'ic', type_name: 'Iron condor', generic: false, generic_text: null, playbooks: PLAYBOOKS, plan: PLAN, prefill: PREFILL, labels: LABELS }
const PATH = '/strategies/70/adjustment-plan'
const NAME = 'Spot within this % of a short strike'
const t = (w, id) => w.find(`[data-testid="${id}"]`)
const mounted = []
afterEach(() => { mounted.splice(0).forEach((w) => w.unmount()) })
beforeEach(() => { calls.length = 0; answers = { [`GET ${PATH}`]: SHEET } })
async function resetWith(reply, rules) {
  answers[`POST ${PATH}/reset`] = { ...SHEET, ...reply }
  if (rules !== undefined) answers[`GET ${PATH}/rules`] = rules
  const w = mount(AdjustPlanSheet, { attachTo: document.body, props: { open: true, strategyId: 70, edit: true } })
  mounted.push(w)
  await flushPromises()
  await t(w, 'plan-reset').trigger('click')
  await t(w, 'plan-reset-yes').trigger('click')
  await flushPromises()
  return w
}

describe('markers after Reset to playbook name the trigger in words', () => {
  it('T-01 switched on again: the trigger\'s label, never "triggers.T-01"', async () => {
    const w = await resetWith({ put_back_off: ['triggers.T-01'] }, { body: { triggers: { 'T-01': { label: NAME } } } })
    const text = t(w, 'plan-reset-markers').text()
    expect(text).toBe(`Switched on again: ${NAME}`)
    expect(text).not.toContain('triggers.')
  })
  it('a changed one: the label too; two keys are joined by commas', async () => {
    const w = await resetWith({ put_back: ['triggers.T-01'], put_back_off: ['triggers.T-02'] },
      { body: { triggers: { 'T-01': { label: NAME }, 'T-02': { label: 'Other rule' } } } })
    const text = t(w, 'plan-reset-markers').text()
    expect(text).toContain(`Changed back: ${NAME}`)
    expect(text).toContain('Switched on again: Other rule')
  })
  it('an unknown key, or a label that is empty: the plain fallback, never the key', async () => {
    const w = await resetWith({ put_back_off: ['triggers.T-77', 'guards.max_adjustments'] }, { body: { triggers: { 'T-01': { label: NAME }, 'T-77': { label: '  ' } } } })
    const text = t(w, 'plan-reset-markers').text()
    expect(text).not.toContain('T-77')
    expect(text).not.toContain('guards.')
    expect(text).toContain(MARKER_FALLBACK_TEXT)
  })
  it('the rules cannot be read: the fallback, never the key', async () => {
    const w = await resetWith({ put_back_off: ['triggers.T-01'] }) // no answer for /rules: 404
    const text = t(w, 'plan-reset-markers').text()
    expect(text).toBe(`Switched on again: ${MARKER_FALLBACK_TEXT}`)
  })
  it('markerNames: one name per key, duplicates of the fallback collapse to one', () => {
    expect(markerNames(['triggers.T-01', 'triggers.T-02'], { 'T-01': NAME })).toEqual([NAME, MARKER_FALLBACK_TEXT])
    expect(markerNames(['triggers.T-08', 'triggers.T-09'], {})).toEqual([MARKER_FALLBACK_TEXT])
    expect(markerNames([], {})).toEqual([])
  })
})
