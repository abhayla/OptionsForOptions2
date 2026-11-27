// #753 round 3 / ADR-330 (45): the request the plan sheet sends says whether the user CHOSE a playbook (a new acceptance)
// or only edited levels. The page edits an existing plan with PUT (PlanEntry :edit="!!read.plan"), so the choice rides
// as `accept: true`; a pure edit never carries it. Server side: tests_app/test_plan_accept_routes.py.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { asIsBody, formOf, saveBody } from '../src/lib/adjustPlan.js'

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

const LABELS = { title: 'Plan', playbook: 'Playbook', target: 'Target', stop: 'Stop', max_adjustments: 'Max adjustments', time_exit: 'Time exit',
  time_exit_on: 'Date', customise: 'Customise triggers', use_as_is: 'Use playbook as is', save: 'Save plan', close: 'Close', hour: 'Hour', minute: 'Minute' }
const PLAYBOOKS = [
  { id: 1, name: 'Iron condor (system)', type: 'ic', type_name: 'Iron condor', is_system: true, draft: false, active: false },
  { id: 9, name: '"Mine"', type: 'ic', type_name: 'Iron condor', is_system: false, draft: false, active: true },
]
const PREFILL_9 = { playbook_id: 9, target: '60', stop: '40', max_adjustments: 3, time_exit: { hour: 14, minute: 45 } }
const PLAN = { playbook_id: 9, playbook_name: '"Mine"', target: '60', stop: '40', max_adjustments: 3, time_exit: { hour: 14, minute: 45 },
  accepted_at: '2026-11-02T09:30:00+05:30' }
const sheetAnswer = (over = {}) => ({ strategy_id: 70, type: 'ic', type_name: 'Iron condor', generic: false, generic_text: null, playbooks: PLAYBOOKS,
  plan: PLAN, prefill: PREFILL_9, labels: LABELS, ...over })
const PATH = '/strategies/70/adjustment-plan'
const t = (w, id) => w.find(`[data-testid="${id}"]`)
const mounted = []
afterEach(() => { mounted.splice(0).forEach((w) => w.unmount()) })
beforeEach(() => { calls.length = 0; answers = {} })
async function sheet(props = {}) {
  const w = mount(AdjustPlanSheet, { attachTo: document.body, props: { open: true, strategyId: 70, edit: true, ...props } })
  await flushPromises()
  mounted.push(w)
  return w
}
const writes = () => calls.filter((c) => c.method !== 'GET')

describe('the body helpers', () => {
  it('Use as is always carries accept; Save carries it only when the user picked a playbook', () => {
    expect(asIsBody(9)).toEqual({ playbook_id: 9, accept: true })
    const form = formOf({ playbook_id: 3, target: '60', stop: '50', max_adjustments: 2 })
    expect(saveBody(form).accept).toBeUndefined()
    expect(saveBody(form, false).accept).toBeUndefined()
    expect(saveBody(form, true).accept).toBe(true)
  })
})

describe('the requests the plan sheet sends on an existing plan (edit = PUT)', () => {
  it('a level edit with no pick sends no accept (never stamps)', async () => {
    answers[`GET ${PATH}`] = sheetAnswer()
    answers[`PUT ${PATH}`] = sheetAnswer()
    const w = await sheet()
    await t(w, 'plan-target').setValue('55')
    await t(w, 'plan-save').trigger('click')
    await flushPromises()
    expect(writes()).toHaveLength(1)
    expect(writes()[0].method).toBe('PUT')
    expect(writes()[0].body).toMatchObject({ playbook_id: 9, target: '55' })
    expect(writes()[0].body).not.toHaveProperty('accept')
  })

  it('picking another playbook then Save sends PUT with accept: true', async () => {
    answers[`GET ${PATH}`] = sheetAnswer()
    answers[`GET ${PATH}?playbook_id=1`] = sheetAnswer({ prefill: { playbook_id: 1, target: '70', stop: '30', max_adjustments: 4, time_exit: { hour: 9, minute: 5 } } })
    answers[`PUT ${PATH}`] = sheetAnswer()
    const w = await sheet()
    await t(w, 'plan-playbook').setValue('1')
    await flushPromises()
    await t(w, 'plan-save').trigger('click')
    await flushPromises()
    expect(writes()).toHaveLength(1)
    expect(writes()[0].method).toBe('PUT')
    expect(writes()[0].body).toMatchObject({ playbook_id: 1, accept: true })
  })

  it('a pick that failed to load sends no accept on the later Save', async () => {
    answers[`GET ${PATH}`] = sheetAnswer()
    answers[`PUT ${PATH}`] = sheetAnswer()
    const w = await sheet()
    await t(w, 'plan-playbook').setValue('1') // no answer for the pick: the read fails, the sheet stays as it was
    await flushPromises()
    await t(w, 'plan-save').trigger('click')
    await flushPromises()
    expect(writes()[0].body).not.toHaveProperty('accept')
  })

  it('Use playbook as is sends PUT with the playbook and accept: true', async () => {
    answers[`GET ${PATH}`] = sheetAnswer()
    answers[`PUT ${PATH}`] = sheetAnswer()
    const w = await sheet()
    await t(w, 'plan-use-as-is').trigger('click')
    await flushPromises()
    expect(writes()).toEqual([{ method: 'PUT', url: PATH, body: { playbook_id: 9, accept: true } }])
  })

  it('a level typed after a pick asks the preview with accept=true (the preview reads the body the save will)', async () => {
    answers[`GET ${PATH}`] = sheetAnswer()
    answers[`GET ${PATH}?playbook_id=1`] = sheetAnswer({ prefill: { playbook_id: 1, target: '70', stop: '30', max_adjustments: 4, time_exit: null } })
    const w = await sheet()
    await t(w, 'plan-playbook').setValue('1')
    await flushPromises()
    await t(w, 'plan-stop').setValue('35')
    await flushPromises()
    const preview = calls.filter((c) => c.url.includes('/levels')).map((c) => c.url)
    expect(preview).toHaveLength(1)
    expect(preview[0]).toContain('playbook_id=1')
    expect(preview[0]).toContain('accept=true')
  })

  it('a level typed with no pick asks the preview without accept', async () => {
    answers[`GET ${PATH}`] = sheetAnswer()
    const w = await sheet()
    await t(w, 'plan-stop').setValue('35')
    await flushPromises()
    const preview = calls.filter((c) => c.url.includes('/levels')).map((c) => c.url)
    expect(preview).toHaveLength(1)
    expect(preview[0]).not.toContain('accept')
  })
})
