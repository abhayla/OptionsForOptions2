// S-11 (owner's 25 Nov notes): "Customise triggers" must not drop the unsaved plan. The sheet's whole form is held in the
// builder-hold store (ADR-329 style, in memory, per strategy) and restored when the sheet for that strategy opens again.
// The held form is the typed text and the server's last answers as they were; nothing is computed in the browser (ADR-008).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { routerKey } from 'vue-router'

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
import PlanEntry from '@/components/strategy/PlanEntry.vue'
import { useBuilderHold } from '@/stores/builderHold'

const LABELS = { title: 'Plan', playbook: 'Playbook', target: 'Target', stop: 'Stop', target_rupees: 'Target (Rs)', stop_rupees: 'Stop (Rs)',
  max_adjustments: 'Max adjustments', time_exit: 'Time exit', time_exit_on: 'On', customise: 'Customise triggers', use_as_is: 'Use as is',
  save: 'Save plan', close: 'Close', plan_entry: 'Plan', edit: 'Edit', set_plan: 'Set plan', no_plan: 'No plan' }
const PLAYBOOKS = [{ id: 9, name: 'Mine', type: 'ic', type_name: 'Iron condor', is_system: false, draft: false, active: true }]
const PREFILL = { playbook_id: 9, target: '50', stop: '50', max_adjustments: 2, time_exit: null, target_words: '', stop_words: '',
  target_source: 'percent', stop_source: 'percent' }
const answer = (id, prefill = PREFILL) => ({ strategy_id: id, type: 'ic', type_name: 'Iron condor', generic: false, generic_text: null,
  playbooks: PLAYBOOKS, plan: null, prefill, labels: LABELS })
const path = (id) => `/strategies/${id}/adjustment-plan`
const STOP = { stop: { percent: '15.38', rupees: '400.00', per_lot: '200.00', words: '15.38 % of max loss', rupee_words: 'Rs 400.00 for the whole trade' }, target: null }
const t = (w, id) => w.find(`[data-testid="${id}"]`)
const mounted = []
let pushed
const router = { push: (u) => { pushed.push(u) } }
afterEach(() => { mounted.splice(0).forEach((w) => w.unmount()) })
beforeEach(() => {
  setActivePinia(createPinia())
  calls.length = 0
  pushed = []
  answers = { [`GET ${path(7)}`]: answer(7), [`GET ${path(8)}`]: answer(8), [`GET ${path(7)}/levels?stop_rupees=400&playbook_id=9`]: STOP }
})
async function sheet(strategyId, extra = {}) {
  const w = mount(AdjustPlanSheet, { attachTo: document.body, props: { open: true, strategyId, ...extra }, global: { provide: { [routerKey]: router } } })
  await flushPromises()
  mounted.push(w)
  return w
}
async function typeAndCustomise(w) {
  await t(w, 'plan-stop-rupees').setValue('400')
  await flushPromises()
  await t(w, 'plan-time').setValue('15:15')
  await t(w, 'plan-time-on').setValue('2026-12-03')
  await t(w, 'plan-customise').trigger('click')
  await flushPromises()
}

describe('S-11: Customise triggers holds the unsaved plan', () => {
  it('owner steps: type rupee stop + time exit, Customise, come back -> everything is there', async () => {
    const w1 = await sheet(7)
    await typeAndCustomise(w1)
    expect(pushed).toEqual(['/strategies/adjustments?trade=7'])
    w1.unmount(); mounted.pop()
    const w2 = await sheet(7)
    expect(t(w2, 'plan-stop-rupees').element.value).toBe('400')
    expect(t(w2, 'plan-stop').element.value).toBe('15.38') // the server's figure from the last levels answer, as it was
    expect(t(w2, 'plan-stop-words').text()).toBe('15.38 % of max loss')
    expect(t(w2, 'plan-time').element.value).toBe('15:15')
    expect(t(w2, 'plan-time-on').element.value).toBe('2026-12-03')
  })

  it('Save after the return sends the same body as before leaving', async () => {
    answers[`PUT ${path(7)}`] = answer(7)
    const w1 = await sheet(7, { edit: true })
    await typeAndCustomise(w1)
    const before = { stop_rupees: '400', time_exit: { at: '15:15', on: '2026-12-03' } }
    w1.unmount(); mounted.pop()
    const w2 = await sheet(7, { edit: true })
    await t(w2, 'plan-save').trigger('click')
    await flushPromises()
    expect(calls.find((c) => c.method === 'PUT').body).toMatchObject({ playbook_id: 9, target: '50', max_adjustments: '2', ...before })
    expect(useBuilderHold().planHeld).toBeNull() // cleared on Save
  })

  it('another strategy restores nothing', async () => {
    const w1 = await sheet(7)
    await typeAndCustomise(w1)
    w1.unmount(); mounted.pop()
    const w8 = await sheet(8)
    expect(t(w8, 'plan-stop-rupees').element.value).toBe('')
    expect(t(w8, 'plan-time').element.value).toBe('')
  })

  it('the plan changed on the server meanwhile: the server plan is shown, the held form is dropped', async () => {
    const w1 = await sheet(7)
    await typeAndCustomise(w1)
    w1.unmount(); mounted.pop()
    answers[`GET ${path(7)}`] = answer(7, { ...PREFILL, target: '60' })
    const w2 = await sheet(7)
    expect(t(w2, 'plan-target').element.value).toBe('60')
    expect(t(w2, 'plan-stop-rupees').element.value).toBe('')
    expect(useBuilderHold().planHeld).toBeNull()
  })

  it('a hold is taken once: closing and reopening shows the server plan', async () => {
    const w1 = await sheet(7)
    await typeAndCustomise(w1)
    w1.unmount(); mounted.pop()
    const w2 = await sheet(7)
    expect(t(w2, 'plan-stop-rupees').element.value).toBe('400')
    w2.unmount(); mounted.pop()
    const w3 = await sheet(7)
    expect(t(w3, 'plan-stop-rupees').element.value).toBe('')
  })

  it('no pinia (storage unavailable): Customise still navigates and the sheet loads as today', async () => {
    setActivePinia(undefined)
    const w1 = await sheet(7)
    await t(w1, 'plan-customise').trigger('click')
    expect(pushed).toEqual(['/strategies/adjustments?trade=7'])
    w1.unmount(); mounted.pop()
    const w2 = await sheet(7)
    expect(t(w2, 'plan-stop').element.value).toBe('50')
  })

  it('PlanEntry reopens the sheet for the strategy that holds a plan', async () => {
    const hold = useBuilderHold()
    hold.holdPlan(7, { base: 'x', form: {} })
    const w = mount(PlanEntry, { attachTo: document.body, props: { strategyId: 7 }, global: { provide: { [routerKey]: router } } })
    mounted.push(w)
    await flushPromises()
    expect(w.findComponent(AdjustPlanSheet).props('open')).toBe(true)
    const w8 = mount(PlanEntry, { attachTo: document.body, props: { strategyId: 8 }, global: { provide: { [routerKey]: router } } })
    mounted.push(w8)
    await flushPromises()
    expect(w8.findComponent(AdjustPlanSheet).props('open')).toBe(false)
  })
})
