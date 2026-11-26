// ADR-330 (5) / S-12: the plan sheet's rupee box beside each percent box. Typing in one box asks the server
// (GET .../adjustment-plan/levels) and fills the other box and the hints from the reply; the browser computes nothing;
// Save sends only the box last edited of each pair.
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
import { saveBody, formOf } from '@/lib/adjustPlan'

const LABELS = { title: 'Plan', playbook: 'Playbook', target: 'Target', stop: 'Stop', target_rupees: 'Target (Rs)', stop_rupees: 'Stop (Rs)',
  max_adjustments: 'Max adjustments', time_exit: 'Time exit', customise: 'Customise triggers', use_as_is: 'Use as is', save: 'Save plan', close: 'Close' }
const PLAYBOOKS = [{ id: 9, name: 'Mine', type: 'ic', type_name: 'Iron condor', is_system: false, draft: false, active: true }]
const PREFILL = { playbook_id: 9, target: '50', stop: '50', max_adjustments: 2, time_exit: null, target_words: '', stop_words: '',
  target_source: 'percent', stop_source: 'percent' }
const ANSWER = { strategy_id: 70, type: 'ic', type_name: 'Iron condor', generic: false, generic_text: null, playbooks: PLAYBOOKS,
  plan: null, prefill: PREFILL, labels: LABELS }
const PATH = '/strategies/70/adjustment-plan'
const t = (w, id) => w.find(`[data-testid="${id}"]`)
const mounted = []
afterEach(() => { mounted.splice(0).forEach((w) => w.unmount()) })
beforeEach(() => { calls.length = 0; answers = { [`GET ${PATH}`]: ANSWER } })
async function sheet() {
  const w = mount(AdjustPlanSheet, { attachTo: document.body, props: { open: true, strategyId: 70 } })
  await flushPromises()
  mounted.push(w)
  return w
}

describe('typed percents: the hints and the rupee boxes come from the network reply', () => {
  it('typed 25.7 and 15.4 -> two levels reads; hints and rupee boxes are the server\'s words', async () => {
    answers[`GET ${PATH}/levels?target=25.7&playbook_id=9`] = { target: { percent: '25.70', rupees: '1002.30', per_lot: '501.15', words: '25.70 % of max profit',
      rupee_words: 'Rs 1002.30 for the whole trade (Rs 501.15 per lot), before charges' }, stop: null }
    answers[`GET ${PATH}/levels?stop=15.4&playbook_id=9`] = { stop: { percent: '15.40', rupees: '400.40', per_lot: '200.20', words: '15.40 % of max loss',
      rupee_words: 'Rs 400.40 for the whole trade (Rs 200.20 per lot), before charges' }, target: null }
    const w = await sheet()
    await t(w, 'plan-target').setValue('25.7')
    await t(w, 'plan-stop').setValue('15.4')
    await flushPromises()
    expect(calls.filter((c) => c.url.includes('/levels')).map((c) => c.url)).toEqual([`${PATH}/levels?target=25.7&playbook_id=9`, `${PATH}/levels?stop=15.4&playbook_id=9`])
    expect(t(w, 'plan-target-words').text()).toBe('25.70 % of max profit')
    expect(t(w, 'plan-target-rupees').element.value).toBe('1002.30')
    expect(t(w, 'plan-target-rupee-words').text()).toBe('Rs 1002.30 for the whole trade (Rs 501.15 per lot), before charges')
    expect(t(w, 'plan-stop-words').text()).toBe('15.40 % of max loss')
    expect(t(w, 'plan-stop-rupees').element.value).toBe('400.40')
  })

  it('a rupee box typed fills the percent box from the reply, and Save sends only the rupee box', async () => {
    answers[`GET ${PATH}/levels?stop_rupees=400&playbook_id=9`] = { target: null, stop: { percent: '15.38', rupees: '400.00', per_lot: '200.00',
      words: '15.38 % of max loss', rupee_words: 'Rs 400.00 for the whole trade (Rs 200.00 per lot), before charges' } }
    answers[`PUT ${PATH}`] = ANSWER
    const w = await sheet()
    await w.setProps({ edit: true })
    await t(w, 'plan-stop-rupees').setValue('400')
    await flushPromises()
    expect(calls.some((c) => c.url === `${PATH}/levels?stop_rupees=400&playbook_id=9`)).toBe(true)
    expect(t(w, 'plan-stop').element.value).toBe('15.38')
    await t(w, 'plan-save').trigger('click')
    await flushPromises()
    const put = calls.find((c) => c.method === 'PUT')
    expect(put.body.stop_rupees).toBe('400')
    expect('stop' in put.body).toBe(false)
  })

  it('a level the server refuses shows no figure beside it', async () => {
    const w = await sheet()
    await t(w, 'plan-target').setValue('abc')
    await flushPromises()
    expect(t(w, 'plan-target-rupees').element.value).toBe('')
  })
})

describe('saveBody: of each pair only the last edited box', () => {
  const base = { ...formOf(PREFILL), playbookId: 9 }
  it('percent last: target sent, no target_rupees', () => {
    const b = saveBody({ ...base, target: '30', targetRupees: '1170.00', targetLast: 'percent' })
    expect(b.target).toBe('30')
    expect('target_rupees' in b).toBe(false)
  })
  it('rupees last: target_rupees sent, no percent target', () => {
    const b = saveBody({ ...base, target: '25.64', targetRupees: '1000', targetLast: 'rupees' })
    expect(b.target_rupees).toBe('1000')
    expect('target' in b).toBe(false)
  })
  it('a saved rupee stop left untouched is not sent', () => {
    const b = saveBody({ ...base, stop: '15.38', stopRupees: '400.00', stopRupeesShown: '400.00', stopLast: 'rupees' })
    expect('stop' in b || 'stop_rupees' in b).toBe(false)
  })
})
