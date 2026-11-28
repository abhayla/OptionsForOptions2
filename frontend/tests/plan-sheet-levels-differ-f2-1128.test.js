// Lane F2 item 2 (I-208, D-TG-4): the plan sheet saved "Stop 9 %" beside "Stop (Rs) 500" (500 is 3.44 % of the base) with no
// message. Cause: Save sent only the box last edited, so the server never saw the second box. When the server could not
// work out the other box (no levels reply), both boxes hold what the user typed: both are sent and the server names the clash.
// Same for Target / Target (Rs). A box the server filled in is never sent beside the typed one.
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
    if (a && a.__reject) return Promise.reject(a.__reject)
    return Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u, b) => respond('POST', u, b), put: (u, b) => respond('PUT', u, b) } }
})
import AdjustPlanSheet from '@/components/strategy/AdjustPlanSheet.vue'

const LABELS = { title: 'Plan', playbook: 'Playbook', target: 'Target', stop: 'Stop', target_rupees: 'Target (Rs)', stop_rupees: 'Stop (Rs)',
  max_adjustments: 'Max adjustments', time_exit: 'Time exit', customise: 'Customise triggers', use_as_is: 'Use as is', save: 'Save plan', close: 'Close' }
const PLAYBOOKS = [{ id: 9, name: 'Mine', type: 'ic', type_name: 'Iron condor', is_system: false, draft: false, active: true }]
const PREFILL = { playbook_id: 9, target: '50', stop: '50', max_adjustments: 2, time_exit: null, target_words: '', stop_words: '',
  target_source: 'percent', stop_source: 'percent' }
const ANSWER = { strategy_id: 70, type: 'ic', type_name: 'Iron condor', generic: false, generic_text: null, playbooks: PLAYBOOKS,
  plan: null, prefill: PREFILL, labels: LABELS }
const PATH = '/strategies/70/adjustment-plan'
const NONE = { target: null, stop: null }
const t = (w, id) => w.find(`[data-testid="${id}"]`)
const mounted = []
afterEach(() => { mounted.splice(0).forEach((w) => w.unmount()) })
beforeEach(() => { calls.length = 0; answers = { [`GET ${PATH}`]: ANSWER } })
async function sheet() {
  const w = mount(AdjustPlanSheet, { attachTo: document.body, props: { open: true, strategyId: 70, edit: true } })
  await flushPromises()
  mounted.push(w)
  return w
}
const refusal = (what) => ({ __reject: { message: 'x', status: 422, parts: { what_happened: what, what_to_do: 'Change one of them.' } } })

describe('both boxes of a pair typed, the server could not fill either: both are sent and the server names the clash', () => {
  it('Stop 9 % beside Stop (Rs) 500 -> "Stop and Stop (Rs) show different values." and the typed values stay', async () => {
    answers[`GET ${PATH}/levels?stop=9&playbook_id=9`] = NONE
    answers[`GET ${PATH}/levels?stop_rupees=500&playbook_id=9`] = NONE
    answers[`PUT ${PATH}`] = refusal('Stop and Stop (Rs) show different values.')
    const w = await sheet()
    await t(w, 'plan-stop').setValue('9')
    await flushPromises()
    await t(w, 'plan-stop-rupees').setValue('500')
    await flushPromises()
    await t(w, 'plan-save').trigger('click')
    await flushPromises()
    const put = calls.find((c) => c.method === 'PUT')
    expect(put.body.stop).toBe('9')
    expect(put.body.stop_rupees).toBe('500')
    expect(t(w, 'plan-error').text()).toContain('Stop and Stop (Rs) show different values.')
    expect(t(w, 'plan-stop').element.value).toBe('9')
    expect(t(w, 'plan-stop-rupees').element.value).toBe('500')
  })

  it('Target 30 % beside Target (Rs) 900 -> "Target and Target (Rs) show different values."', async () => {
    answers[`GET ${PATH}/levels?target=30&playbook_id=9`] = NONE
    answers[`GET ${PATH}/levels?target_rupees=900&playbook_id=9`] = NONE
    answers[`PUT ${PATH}`] = refusal('Target and Target (Rs) show different values.')
    const w = await sheet()
    await t(w, 'plan-target').setValue('30')
    await flushPromises()
    await t(w, 'plan-target-rupees').setValue('900')
    await flushPromises()
    await t(w, 'plan-save').trigger('click')
    await flushPromises()
    const put = calls.find((c) => c.method === 'PUT')
    expect(put.body.target).toBe('30')
    expect(put.body.target_rupees).toBe('900')
    expect(t(w, 'plan-error').text()).toContain('Target and Target (Rs) show different values.')
  })
})

describe('a box the server filled in is never sent beside the typed one (unchanged rule)', () => {
  it('Stop (Rs) 400 typed, percent filled from the reply: only stop_rupees is sent', async () => {
    answers[`GET ${PATH}/levels?stop_rupees=400&playbook_id=9`] = { target: null, stop: { percent: '15.38', rupees: '400.00', per_lot: '200.00',
      words: '15.38 % of max loss', rupee_words: 'Rs 400.00', warning: null } }
    answers[`PUT ${PATH}`] = ANSWER
    const w = await sheet()
    await t(w, 'plan-stop-rupees').setValue('400')
    await flushPromises()
    expect(t(w, 'plan-stop').element.value).toBe('15.38')
    await t(w, 'plan-save').trigger('click')
    await flushPromises()
    const put = calls.find((c) => c.method === 'PUT')
    expect(put.body.stop_rupees).toBe('400')
    expect('stop' in put.body).toBe(false)
  })

  it('percent typed then rupee box typed, the server fills the percent from the rupee: rupee only', async () => {
    answers[`GET ${PATH}/levels?stop=9&playbook_id=9`] = NONE
    answers[`GET ${PATH}/levels?stop_rupees=500&playbook_id=9`] = { target: null, stop: { percent: '3.44', rupees: '500.00', per_lot: null,
      words: '3.44 % of max loss', rupee_words: 'Rs 500.00', warning: null } }
    answers[`PUT ${PATH}`] = ANSWER
    const w = await sheet()
    await t(w, 'plan-stop').setValue('9')
    await flushPromises()
    await t(w, 'plan-stop-rupees').setValue('500')
    await flushPromises()
    await t(w, 'plan-save').trigger('click')
    await flushPromises()
    const put = calls.find((c) => c.method === 'PUT')
    expect(put.body.stop_rupees).toBe('500')
    expect('stop' in put.body).toBe(false)
  })
})
