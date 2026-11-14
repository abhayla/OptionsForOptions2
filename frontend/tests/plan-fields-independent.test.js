// GC-ICFIX issue 15 (u271; ADR-245, ADR-252, ADR-305): in the plan box typing in one field changes only that field; picking a
// playbook refills the fields AND says so in one line; reopening a saved plan shows the saved values and no note.
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
    return typeof a === 'function' ? a(body) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u, b) => respond('POST', u, b), put: (u, b) => respond('PUT', u, b) } }
})
import AdjustPlanSheet from '@/components/strategy/AdjustPlanSheet.vue'
import PlanEntry from '@/components/strategy/PlanEntry.vue'
import { PLAN_REFILLED_TEXT } from '@/lib/sharedStateText'

const LABELS = {
  title: "When tracking starts: this strategy's plan", playbook: 'Playbook', target: 'Target', stop: 'Stop', max_adjustments: 'Max adjustments',
  time_exit: 'Time exit', customise: 'Customise triggers', use_as_is: 'Use playbook as is', save: 'Save plan', close: 'Close',
  plan_entry: 'Plan', edit: 'Edit plan', no_plan: 'No plan saved yet: default rules apply', set_plan: 'Set plan',
}
const PLAYBOOKS = [
  { id: 1, name: 'Iron condor (system)', type: 'ic', type_name: 'Iron condor', is_system: true, draft: false, active: false },
  { id: 9, name: '"Mine"', type: 'ic', type_name: 'Iron condor', is_system: false, draft: false, active: true },
]
const PREFILL_9 = { playbook_id: 9, target: '50', stop: '50', max_adjustments: 2, time_exit: null, target_words: '', stop_words: '' }
const PREFILL_1 = { playbook_id: 1, target: '70', stop: '30', max_adjustments: 4, time_exit: { hour: 9, minute: 5 }, target_words: '', stop_words: '' }
const sheetAnswer = (over = {}) => ({ strategy_id: 70, type: 'ic', type_name: 'Iron condor', generic: false, generic_text: null,
  playbooks: PLAYBOOKS, plan: null, prefill: PREFILL_9, labels: LABELS, ...over })
const PLAN = { playbook_id: 9, playbook_name: '"Mine"', target: '60', stop: '40', max_adjustments: 3, time_exit: { hour: 14, minute: 45 } }
const PATH = '/strategies/70/adjustment-plan'

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const mounted = []
afterEach(() => { mounted.splice(0).forEach((w) => w.unmount()) })
beforeEach(() => { calls.length = 0; answers = {} })
async function sheet(props = {}) {
  const w = mount(AdjustPlanSheet, { attachTo: document.body, props: { open: true, strategyId: 70, ...props } })
  await flushPromises()
  mounted.push(w)
  return w
}
const inputs = (w) => ({ playbook: t(w, 'plan-playbook').element.value, target: t(w, 'plan-target').element.value,
  stop: t(w, 'plan-stop').element.value, max: t(w, 'plan-max').element.value, time: t(w, 'plan-time').element.value })

describe('typing in one field changes only that field', () => {
  it('stop typed, then Target typed: the stop and every other field stay as typed, no read is made', async () => {
    answers[`GET ${PATH}`] = sheetAnswer()
    const w = await sheet()
    await t(w, 'plan-max').setValue('3')
    await t(w, 'plan-stop').setValue('35')
    await t(w, 'plan-target').setValue('20')
    await flushPromises()
    expect(inputs(w)).toEqual({ playbook: '9', target: '20', stop: '35', max: '3', time: '' })
    expect(calls.filter((c) => c.url === PATH)).toHaveLength(1)
  })

  it('Target emptied (ADR-305: no target alert) leaves the other fields and is sent as ""', async () => {
    answers[`GET ${PATH}`] = sheetAnswer()
    answers[`POST ${PATH}`] = sheetAnswer({ plan: PLAN })
    const w = await sheet()
    await t(w, 'plan-stop').setValue('35')
    await t(w, 'plan-target').setValue('')
    await t(w, 'plan-save').trigger('click')
    await flushPromises()
    expect(calls.find((c) => c.method === 'POST').body).toEqual({ playbook_id: 9, target: '', stop: '35', max_adjustments: '2' })
  })

  it('the parent re-rendering with the same props (a panel refresh while the box is open) keeps what was typed', async () => {
    answers[`GET ${PATH}`] = sheetAnswer()
    const w = await sheet()
    await t(w, 'plan-stop').setValue('35')
    await w.setProps({ open: true, strategyId: 70, edit: false })
    await t(w, 'plan-target').setValue('20')
    await flushPromises()
    expect(inputs(w)).toMatchObject({ target: '20', stop: '35' })
    expect(calls.filter((c) => c.url === PATH)).toHaveLength(1)
  })

  it('the plan card re-reading its rule check while the box is open keeps what was typed', async () => {
    answers[`GET ${PATH}`] = sheetAnswer({ plan: PLAN, prefill: { playbook_id: 9, target: '60', stop: '40', max_adjustments: 3, time_exit: PLAN.time_exit } })
    const w = mount(PlanEntry, { attachTo: document.body, props: { strategyId: 70, check: null, checkStatus: 'loading' } })
    await flushPromises()
    mounted.push(w)
    await t(w, 'plan-entry-edit').trigger('click')
    await flushPromises()
    await t(w, 'plan-stop').setValue('35')
    await w.setProps({ check: { limits: [], playbook: { source: 'none' } }, checkStatus: 'ok' })
    await t(w, 'plan-target').setValue('20')
    await flushPromises()
    expect(inputs(w)).toMatchObject({ target: '20', stop: '35', max: '3', time: '14:45' })
  })
})

describe('picking a playbook refills the fields and says so in one line', () => {
  it('refilled from the playbook: every field, plus the note naming the playbook', async () => {
    answers[`GET ${PATH}`] = sheetAnswer()
    answers[`GET ${PATH}?playbook_id=1`] = sheetAnswer({ prefill: PREFILL_1 })
    const w = await sheet()
    expect(t(w, 'plan-refilled').exists()).toBe(false)
    await t(w, 'plan-stop').setValue('35')
    await t(w, 'plan-playbook').setValue('1')
    await flushPromises()
    expect(inputs(w)).toEqual({ playbook: '1', target: '70', stop: '30', max: '4', time: '09:05' })
    expect(t(w, 'plan-refilled').text()).toBe(PLAN_REFILLED_TEXT('Iron condor (system)'))
  })

  it('a pick whose read fails shows the could-not-load state and no refilled note', async () => {
    answers[`GET ${PATH}`] = sheetAnswer()
    answers[`GET ${PATH}?playbook_id=1`] = () => Promise.reject({ message: 'x', parts: null, status: 503 })
    const w = await sheet()
    await t(w, 'plan-playbook').setValue('1')
    await flushPromises()
    expect(t(w, 'plan-sheet-error').exists()).toBe(true)
    expect(t(w, 'plan-refilled').exists()).toBe(false)
  })

  it('reopening a saved plan shows the saved values and no note', async () => {
    answers[`GET ${PATH}`] = sheetAnswer({ plan: PLAN, prefill: { playbook_id: 9, target: '60', stop: '40', max_adjustments: 3, time_exit: PLAN.time_exit } })
    const w = await sheet({ edit: true })
    expect(inputs(w)).toEqual({ playbook: '9', target: '60', stop: '40', max: '3', time: '14:45' })
    expect(t(w, 'plan-refilled').exists()).toBe(false)
  })

  it('closing and reopening after a pick shows no note', async () => {
    answers[`GET ${PATH}`] = sheetAnswer()
    answers[`GET ${PATH}?playbook_id=1`] = sheetAnswer({ prefill: PREFILL_1 })
    const w = await sheet()
    await t(w, 'plan-playbook').setValue('1')
    await flushPromises()
    await w.setProps({ open: false })
    await w.setProps({ open: true })
    await flushPromises()
    expect(t(w, 'plan-refilled').exists()).toBe(false)
  })
})
