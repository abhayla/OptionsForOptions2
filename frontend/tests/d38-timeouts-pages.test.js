// D-38 (GC-ICLIVE-D): the plan dialog and the settings page, on a read that hit the client's limit (axios ECONNABORTED):
// the text says it took too long, and what the user picked or typed is not wiped.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

let answers = {}
const TIMEOUT = { message: 'x', parts: null, status: null, code: 'ECONNABORTED' }
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url) => {
    const a = answers[`${method} ${url}`]
    if (a === undefined) return Promise.reject({ message: 'no answer', parts: null, status: 404 })
    return typeof a === 'function' ? a() : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u) => respond('POST', u), put: (u) => respond('PUT', u) } }
})
import AdjustPlanSheet from '@/components/strategy/AdjustPlanSheet.vue'
import SettingsPage from '@/pages/SettingsPage.vue'

const LABELS = { title: "When tracking starts: this strategy's plan", playbook: 'Playbook', target: 'Target', stop: 'Stop', max_adjustments: 'Max adjustments',
  time_exit: 'Time exit', customise: 'Customise triggers', use_as_is: 'Use playbook as is', save: 'Save plan', close: 'Close',
  plan_entry: 'Plan', edit: 'Edit plan', no_plan: 'No plan: nothing is watched for this strategy', set_plan: 'Set plan', hour: 'Hour', minute: 'Minute' }
const PLAYBOOKS = [
  { id: 1, name: 'Iron condor (system)', type: 'ic', type_name: 'Iron condor', is_system: true, draft: false, active: false },
  { id: 9, name: '"Mine"', type: 'ic', type_name: 'Iron condor', is_system: false, draft: false, active: true },
]
const PREFILL_9 = { playbook_id: 9, target: '50', stop: '50', max_adjustments: 2, time_exit: null, target_words: '50 % of max profit', stop_words: '50 % of max loss' }
const SHEET = { strategy_id: 70, type: 'ic', type_name: 'Iron condor', generic: false, generic_text: null, playbooks: PLAYBOOKS, plan: null, prefill: PREFILL_9, labels: LABELS }
const PATH = '/strategies/70/adjustment-plan'
const mounted = []
afterEach(() => { mounted.splice(0).forEach((w) => w.unmount()) })
beforeEach(() => { answers = {} })
const t = (w, id) => w.find(`[data-testid="${id}"]`)

describe('D-38 plan dialog on a timeout', () => {
  it('the first read timing out says the plan took too long, with Retry', async () => {
    answers[`GET ${PATH}`] = () => Promise.reject(TIMEOUT)
    const w = mount(AdjustPlanSheet, { attachTo: document.body, props: { open: true, strategyId: 70 } })
    mounted.push(w)
    await flushPromises()
    expect(t(w, 'plan-sheet-error').text()).toContain('took too long')
    expect(t(w, 'plan-sheet-retry').exists()).toBe(true)
  })

  it('picking another playbook that times out keeps the fields as typed and says it took too long', async () => {
    let n = 0
    answers[`GET ${PATH}`] = () => (n++ === 0 ? Promise.resolve({ data: SHEET }) : Promise.reject(TIMEOUT))
    answers[`GET ${PATH}?playbook_id=1`] = () => Promise.reject(TIMEOUT)
    const w = mount(AdjustPlanSheet, { attachTo: document.body, props: { open: true, strategyId: 70 } })
    mounted.push(w)
    await flushPromises()
    await t(w, 'plan-target').setValue('77')
    await t(w, 'plan-playbook').setValue('1')
    await flushPromises()
    expect(t(w, 'plan-target').exists()).toBe(true) // the form is still there
    expect(t(w, 'plan-target').element.value).toBe('77') // what was typed
    expect(t(w, 'plan-sheet-pick-error').text()).toContain('took too long')
  })
})

describe('D-38 settings page on a timeout', () => {
  it('says the settings took too long, and Try again reads them', async () => {
    let n = 0
    const ok = { groups: [{ name: 'Pricing', settings: [] }], charges: null }
    answers['GET /settings'] = () => (n++ === 0 ? Promise.reject(TIMEOUT) : Promise.resolve({ data: ok }))
    const w = mount(SettingsPage)
    mounted.push(w)
    await flushPromises()
    expect(t(w, 'settings-unavailable').text()).toContain('took too long')
    expect(t(w, 'settings-unavailable').text()).not.toContain('could not be read')
    await t(w, 'settings-retry').trigger('click')
    await flushPromises()
    expect(t(w, 'settings-unavailable').exists()).toBe(false)
  })
})
