// Hotfix plan-save-1127 (Lane R, 27 Nov 2026; ADR-330 (1), (5); ADR-016 to ADR-019 spirit: no auto re-send): what the page ends on after
// a plan Save: the server's new value; the server's refusal; or, with no answer in time, ONE sentence and the value as typed.
// A read that started before the save never puts the old value back (trade #209: the stop typed 100 came back as 996.13).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body, config) => {
    calls.push({ method, url, body, config })
    const a = answers[`${method} ${url}`]
    if (a === undefined) return Promise.reject({ message: 'no answer', parts: null, status: 404 })
    return typeof a === 'function' ? a(body) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u, c) => respond('GET', u, undefined, c), post: (u, b, c) => respond('POST', u, b, c), put: (u, b, c) => respond('PUT', u, b, c) } }
})
import AdjustPlanSheet from '@/components/strategy/AdjustPlanSheet.vue'
import PlanEntry from '@/components/strategy/PlanEntry.vue'
import PlanWatch from '@/components/strategy/PlanWatch.vue'
import { PLAN_SAVE_TIMEOUT_MS } from '@/lib/adjustPlan'
import { PLAN_NOT_CONFIRMED_TEXT } from '@/lib/sharedStateText'

const LABELS = {
  title: "When tracking starts: this strategy's plan", playbook: 'Playbook', target: 'Target', stop: 'Stop', stop_rupees: 'Stop (Rs)', max_adjustments: 'Max adjustments',
  time_exit: 'Time exit', customise: 'Customise triggers', use_as_is: 'Use playbook as is', save: 'Save plan', close: 'Close',
  plan_entry: 'Plan', edit: 'Edit plan', no_plan: 'No plan: nothing is watched for this strategy', set_plan: 'Set plan',
}
const PLAYBOOKS = [{ id: 9, name: '"Mine"', type: 'ic', type_name: 'Iron condor', is_system: false, draft: false, active: true }]
const planOf = (stopRupees) => ({ playbook_id: 9, playbook_name: '"Mine"', target: '60', stop: stopRupees, stop_rupees: stopRupees, max_adjustments: 3, time_exit: { hour: 14, minute: 45 } })
const sheetAnswer = (stopRupees) => ({ strategy_id: 70, type: 'ic', type_name: 'Iron condor', generic: false, generic_text: null, playbooks: PLAYBOOKS,
  plan: planOf(stopRupees), prefill: { playbook_id: 9, target: '60', stop: '40', stop_rupees: stopRupees, max_adjustments: 3, time_exit: { hour: 14, minute: 45 }, target_words: '', stop_words: '' }, labels: LABELS })
const PATH = '/strategies/70/adjustment-plan'
const t = (w, id) => w.find(`[data-testid="${id}"]`)
const mounted = []
afterEach(() => { mounted.splice(0).forEach((w) => w.unmount()); vi.useRealTimers() })
beforeEach(() => { calls.length = 0; answers = {} })
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b }); return { promise, resolve, reject } }
async function sheet() {
  const w = mount(AdjustPlanSheet, { attachTo: document.body, props: { open: true, strategyId: 70, edit: true } })
  await flushPromises()
  mounted.push(w)
  return w
}

describe('the save outcome', () => {
  it('a save answered after 9 s shows the value the server answered', async () => {
    answers[`GET ${PATH}`] = sheetAnswer('996.13')
    const slow = deferred()
    answers[`PUT ${PATH}`] = () => slow.promise
    const w = await sheet()
    await t(w, 'plan-stop-rupees').setValue('100')
    await t(w, 'plan-save').trigger('click')
    slow.resolve({ data: sheetAnswer('100.00') }) // the server answered, late
    await flushPromises()
    expect(w.emitted('saved')[0][0].plan.stop).toBe('100.00')
  })

  it('the save carries its own 30 s timeout, set on the request', async () => {
    expect(PLAN_SAVE_TIMEOUT_MS).toBe(30000)
    answers[`GET ${PATH}`] = sheetAnswer('996.13')
    answers[`PUT ${PATH}`] = sheetAnswer('100.00')
    const w = await sheet()
    await t(w, 'plan-save').trigger('click')
    await flushPromises()
    expect(calls.find((c) => c.method === 'PUT').config).toEqual({ timeout: 30000 })
  })

  it('no answer in time: exactly the one sentence, the typed value stays, nothing is sent twice', async () => {
    answers[`GET ${PATH}`] = sheetAnswer('996.13')
    answers[`PUT ${PATH}`] = () => Promise.reject({ message: 'x', code: 'ECONNABORTED', status: null })
    const w = await sheet()
    await t(w, 'plan-stop-rupees').setValue('100')
    await t(w, 'plan-save').trigger('click')
    await flushPromises()
    expect(w.text()).toContain(PLAN_NOT_CONFIRMED_TEXT)
    expect(PLAN_NOT_CONFIRMED_TEXT).toBe('Not confirmed: reload to see whether it was saved.')
    expect(w.text().split(PLAN_NOT_CONFIRMED_TEXT)).toHaveLength(2) // once
    expect(t(w, 'plan-stop-rupees').element.value).toBe('100')
    expect(t(w, 'plan-stop-rupees').element.value).not.toBe('996.13')
    expect(w.emitted('saved')).toBeUndefined()
    expect(calls.filter((c) => c.method === 'PUT')).toHaveLength(1)
  })

  it('a dropped connection (no status, no code) is the same one sentence, with no second send', async () => {
    answers[`GET ${PATH}`] = sheetAnswer('996.13')
    answers[`PUT ${PATH}`] = () => Promise.reject({ message: 'Network Error', status: null })
    const w = await sheet()
    await t(w, 'plan-stop-rupees').setValue('100')
    await t(w, 'plan-save').trigger('click')
    await flushPromises()
    expect(w.text()).toContain(PLAN_NOT_CONFIRMED_TEXT)
    expect(calls.filter((c) => c.method === 'PUT')).toHaveLength(1)
  })

  it('a refusal shows the server reason, not the not-confirmed sentence', async () => {
    answers[`GET ${PATH}`] = sheetAnswer('996.13')
    const parts = { what_happened: 'Prices could not be read in time to check this plan.', impact: 'The plan was not saved.', what_is_blocked: 'Saving this plan.', next_action: 'Try again.' }
    answers[`PUT ${PATH}`] = () => Promise.reject({ message: 'x', status: 422, parts })
    const w = await sheet()
    await t(w, 'plan-save').trigger('click')
    await flushPromises()
    expect(w.text()).toContain('Prices could not be read in time to check this plan.')
    expect(w.text()).not.toContain(PLAN_NOT_CONFIRMED_TEXT)
    expect(t(w, 'plan-stop-rupees').element.value).toBe('996.13') // the refusal changed nothing: the sheet still shows what the server holds
  })
})

describe('a read that started before the save', () => {
  it('the Plan block ends on the saved value when an earlier read answers after the save', async () => {
    const early = deferred()
    let n = 0
    answers[`GET ${PATH}`] = () => (++n === 1 ? early.promise : Promise.resolve({ data: sheetAnswer('996.13') }))
    answers[`PUT ${PATH}`] = sheetAnswer('100.00')
    const entry = mount(PlanEntry, { attachTo: document.body, props: { strategyId: 70, check: null, checkStatus: 'loading' } })
    mounted.push(entry)
    await flushPromises() // the block's own read (#1) is out and unanswered
    // the same strategy's sheet saves meanwhile
    const w = mount(AdjustPlanSheet, { attachTo: document.body, props: { open: true, strategyId: 70, edit: true } })
    mounted.push(w)
    await flushPromises()
    await t(w, 'plan-save').trigger('click')
    await flushPromises()
    entry.vm.$.setupState.read = w.emitted('saved')[0][0] // PlanEntry's @saved handler: read = next
    await flushPromises()
    early.resolve({ data: sheetAnswer('996.13') }) // the earlier read answers last, with the old value
    await flushPromises()
    expect(entry.vm.$.setupState.read.plan.stop).toBe('100.00')
  })

  it('a plan watch answer that began before the save is dropped and a fresh read is made', async () => {
    vi.useFakeTimers()
    const early = deferred()
    let reads = 0
    answers['GET /strategies/70/plan-watch'] = () => {
      reads += 1
      return reads === 1 ? early.promise : Promise.resolve({ data: pw('fires 100') })
    }
    const pw = (label) => ({ strategy_id: 70, plan_state: 'planned', lines: [{ key: 'stop', kind: 'stop', section: 'plan', label, unit: 'pnl_rupees', state: 'watching', fires_at: '-100', now: null, distance_rs: null, distance_pct: null, reason: null }] })
    const box = mount(PlanWatch, { attachTo: document.body, props: { strategyId: 70 } })
    mounted.push(box)
    await flushPromises()
    const { markSaved } = await import('@/lib/planSaveClock')
    markSaved(70) // the save was stored while read #1 is out
    await flushPromises()
    early.resolve({ data: pw('old 996.13') })
    await flushPromises()
    await vi.advanceTimersByTimeAsync(20)
    await flushPromises()
    expect(box.text()).not.toContain('old 996.13')
    expect(reads).toBe(2)
    expect(box.text()).toContain('fires 100')
  })
})
