// Lane FJ2 item 5 (28 Nov 2026), D-TG-4 / W-14. Real case: Lane TG, plan sheet: Stop typed 9 (%), then Stop (Rs) typed 500; the sheet saved "Stop 9 %" beside
// "Stop (Rs) 500" (500 is 3.44 %) with no message. Cause: when the levels read answers with no figure for the level (`stop: null`), the sheet left the OLD box value
// beside the new one (an error already cleared it). Fail closed: no figure from the server = no figure shown. Same path for the Target / Target (Rs) pair (TG did not run it).
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

const LABELS = { title: 'Plan', playbook: 'Playbook', target: 'Target', stop: 'Stop', target_rupees: 'Target (Rs)', stop_rupees: 'Stop (Rs)',
  max_adjustments: 'Max adjustments', time_exit: 'Time exit', customise: 'Customise triggers', use_as_is: 'Use as is', save: 'Save plan', close: 'Close' }
const PLAYBOOKS = [{ id: 9, name: 'Mine', type: 'ic', type_name: 'Iron condor', is_system: false, draft: false, active: true }]
const PREFILL = { playbook_id: 9, target: '50', stop: '50', max_adjustments: 2, time_exit: null, target_words: '', stop_words: '', target_source: 'percent', stop_source: 'percent' }
const ANSWER = { strategy_id: 70, type: 'ic', type_name: 'Iron condor', generic: false, generic_text: null, playbooks: PLAYBOOKS, plan: null, prefill: PREFILL, labels: LABELS }
const PATH = '/strategies/70/adjustment-plan'
const t = (w, id) => w.find(`[data-testid="${id}"]`)
const mounted = []
afterEach(() => { mounted.splice(0).forEach((w) => w.unmount()) })
beforeEach(() => { calls.length = 0; answers = { [`GET ${PATH}`]: ANSWER, [`PUT ${PATH}`]: ANSWER } })
async function sheet() {
  const w = mount(AdjustPlanSheet, { attachTo: document.body, props: { open: true, strategyId: 70, edit: true } })
  await flushPromises()
  mounted.push(w)
  return w
}

describe('FJ2-5 a pair whose other box the server cannot fill is not left showing the old value', () => {
  for (const [level, pct, rs] of [['stop', 'plan-stop', 'plan-stop-rupees'], ['target', 'plan-target', 'plan-target-rupees']]) {
    it(`${level}: % typed 9, then Rs typed 500, the levels read answers no figure: the % box is cleared and Save sends only the Rs box`, async () => {
      answers[`GET ${PATH}/levels?${level}=9&playbook_id=9`] = { target: null, stop: null, [level]: { percent: '9.00', rupees: '1309.00', per_lot: '654.50', words: '9.00 %', rupee_words: 'Rs 1309.00' } }
      answers[`GET ${PATH}/levels?${level}_rupees=500&playbook_id=9`] = { target: null, stop: null }
      const w = await sheet()
      await t(w, pct).setValue('9')
      await flushPromises()
      expect(t(w, rs).element.value).toBe('1309.00')
      await t(w, rs).setValue('500')
      await flushPromises()
      expect(t(w, pct).element.value).toBe('') // was "9" (stale) beside Rs 500
      await t(w, 'plan-save').trigger('click')
      await flushPromises()
      const put = calls.find((c) => c.method === 'PUT')
      expect(put.body[`${level}_rupees`]).toBe('500')
      expect(level in put.body).toBe(false)
    })
  }
})
