// S-11 regression (owner's PC 27 Nov 12:42, T3-16 FAIL): after Add to Paper the builder is in Drafts Mode (savedId null), so the
// tracking panel (and its Plan entry) is not drawn and nothing reopened the sheet on return from "Customise triggers". The
// builder's save bar is always drawn, so IT reopens the sheet for the strategy whose form is held (RESULTS-lane-j row N13).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    if (method === 'GET' && url === '/strategies') return Promise.resolve({ data: { strategies: [] } })
    const a = answers[`${method} ${url}`]
    if (a === undefined) return Promise.reject({ message: 'no answer', parts: null, status: 404 })
    return Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u, b) => respond('POST', u, b), put: (u, b) => respond('PUT', u, b) } }
})
import AdjustPlanSheet from '@/components/strategy/AdjustPlanSheet.vue'
import SaveDraftBar from '@/components/strategy/SaveDraftBar.vue'
import { useBuilderHold } from '@/stores/builderHold'

const LABELS = { title: 'Plan', playbook: 'Playbook', target: 'Target', stop: 'Stop', target_rupees: 'Target (Rs)', stop_rupees: 'Stop (Rs)',
  max_adjustments: 'Max adjustments', time_exit: 'Time exit', time_exit_on: 'On', customise: 'Customise triggers', use_as_is: 'Use as is',
  save: 'Save plan', close: 'Close', plan_entry: 'Plan', edit: 'Edit', set_plan: 'Set plan', no_plan: 'No plan' }
const PLAYBOOKS = [{ id: 9, name: 'Mine', type: 'ic', type_name: 'Iron condor', is_system: false, draft: false, active: true }]
const PREFILL = { playbook_id: 9, target: '50', stop: '50', max_adjustments: 2, time_exit: null, target_words: '', stop_words: '', target_source: 'percent', stop_source: 'percent' }
const answer = (id) => ({ strategy_id: id, type: 'ic', type_name: 'Iron condor', generic: false, generic_text: null, playbooks: PLAYBOOKS, plan: null, prefill: PREFILL, labels: LABELS })
const path = (id) => `/strategies/${id}/adjustment-plan`
const STOP = { stop: { percent: '15.38', rupees: '400.00', per_lot: '200.00', words: '15.38 % of max loss', rupee_words: 'Rs 400.00 for the whole trade' }, target: null }
const LEGS = [{ id: 'l1', contract_id: 5, action: 'SELL', lots: 1, lot_size: 65, instrument: 'CE', strike: '22800', expiry: '2026-12-01', underlying: 'NIFTY', planned_entry: '100.00', captured_at: '2026-11-26T09:20:00+05:30', included: true }]
const t = (id) => document.body.querySelector(`[data-testid="${id}"]`)
const setValue = (el, v) => { el.value = v; el.dispatchEvent(new Event('input')) }
const mounted = []
const makeRouter = async () => {
  const r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:p(.*)*', component: { template: '<p />' } }] })
  await r.push('/')
  return r
}
afterEach(() => { mounted.splice(0).forEach((w) => w.unmount()); document.body.innerHTML = '' })
beforeEach(() => {
  setActivePinia(createPinia())
  calls.length = 0
  answers = { [`GET ${path(7)}`]: answer(7), [`GET ${path(8)}`]: answer(8), [`GET ${path(7)}/levels?stop_rupees=400&playbook_id=9`]: STOP }
})
async function bar(props = {}) {
  const r = await makeRouter()
  const w = mount(SaveDraftBar, { props: { legs: LEGS, shownName: 'IC', ...props }, global: { plugins: [r] }, attachTo: document.body })
  mounted.push(w)
  await flushPromises()
  return w
}
/** The user's steps up to leaving the page: the sheet of strategy `id` open, 400 and 15:15 typed, Customise triggers pressed. */
async function typeAndLeave(id, edit = false) {
  const r = await makeRouter()
  const w = mount(AdjustPlanSheet, { attachTo: document.body, props: { open: true, strategyId: id, edit }, global: { plugins: [r] } })
  await flushPromises()
  setValue(t('plan-stop-rupees'), '400')
  await flushPromises()
  setValue(t('plan-time'), '15:15')
  await flushPromises()
  t('plan-customise').click()
  await flushPromises()
  w.unmount() // the builder page is left: everything it drew is gone
  document.body.innerHTML = ''
  expect(useBuilderHold().hasPlan(id)).toBe(true)
}

describe('S-11: back from Customise triggers, the builder reopens the plan sheet by itself', () => {
  it('Drafts Mode (no saved id on the tracking panel): the save bar reopens it with 400 and 15:15', async () => {
    await typeAndLeave(7)
    await bar({ current: null, paperMode: true })
    expect(t('plan-sheet')).not.toBeNull()
    expect(t('plan-stop-rupees').value).toBe('400')
    expect(t('plan-time').value).toBe('15:15')
  })
  it('a running trade that has a plan: the reopened sheet still Saves with PUT, then the hold is gone and the sheet closed', async () => {
    answers[`PUT ${path(7)}`] = answer(7)
    await typeAndLeave(7, true)
    await bar({ current: { id: 7, revision: 1, name: 'x' } })
    expect(t('plan-stop-rupees').value).toBe('400')
    t('plan-save').click()
    await flushPromises()
    const put = calls.find((c) => c.method === 'PUT')
    expect(put.body).toMatchObject({ stop_rupees: '400', time_exit: { at: '15:15' } })
    expect(calls.some((c) => c.method === 'POST')).toBe(false)
    expect(useBuilderHold().planHeld).toBeNull()
    expect(t('plan-sheet')).toBeNull()
  })
  it('nothing held: the builder opens no sheet', async () => {
    await bar({ current: null })
    expect(t('plan-sheet')).toBeNull()
  })
  it('Close (Cancel) clears the hold', async () => {
    await typeAndLeave(7)
    await bar({ current: null })
    t('plan-close').click()
    await flushPromises()
    expect(useBuilderHold().planHeld).toBeNull()
  })
  it('another strategy opened in the sheet shows nothing held and leaves the hold alone', async () => {
    await typeAndLeave(7)
    const w = mount(AdjustPlanSheet, { attachTo: document.body, props: { open: true, strategyId: 8 } })
    mounted.push(w)
    await flushPromises()
    expect(t('plan-stop-rupees').value).toBe('')
    expect(useBuilderHold().hasPlan(7)).toBe(true)
  })
})
