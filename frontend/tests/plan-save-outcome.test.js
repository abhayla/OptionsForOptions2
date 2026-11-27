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
import { PLAN_SAVE_TIMEOUT_MS, readPlan, resetPlan, sendPlan } from '@/lib/adjustPlan'
import { PLAN_NOT_CONFIRMED_TEXT } from '@/lib/sharedStateText'
import { markSaved, saveStamp } from '@/lib/planSaveClock'

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

describe('a save that ends without a 2xx or a 4xx refusal', () => {
  it('a 500 (even with a catalogue message) shows Not confirmed, keeps the typed value and moves no clock', async () => {
    answers[`GET ${PATH}`] = sheetAnswer('996.13')
    const parts = { what_happened: 'The change was not completed.', impact: 'x', what_is_blocked: 'y', next_action: 'z' }
    answers[`PUT ${PATH}`] = () => Promise.reject({ message: 'x', status: 500, parts })
    const w = await sheet()
    const before = saveStamp(70)
    await t(w, 'plan-stop-rupees').setValue('100')
    await t(w, 'plan-save').trigger('click')
    await flushPromises()
    expect(w.text()).toContain(PLAN_NOT_CONFIRMED_TEXT)
    expect(w.text()).not.toContain('The change was not completed.')
    expect(t(w, 'plan-stop-rupees').element.value).toBe('100')
    expect(saveStamp(70)).toBe(before)
    expect(calls.filter((c) => c.method === 'PUT')).toHaveLength(1)
  })
})

describe('a read that started before the save', () => {
  it('through the real @saved wiring: the block shows the saved plan and an earlier levels answer never refills the sheet', async () => {
    const early = deferred()
    answers[`GET ${PATH}`] = sheetAnswer('996.13')
    answers[`GET ${PATH}/levels?stop_rupees=100&playbook_id=9`] = () => early.promise
    answers[`PUT ${PATH}`] = { ...sheetAnswer('100.00'), plan: { ...planOf('100.00'), max_adjustments: 5 } }
    const entry = mount(PlanEntry, { attachTo: document.body, props: { strategyId: 70, check: null, checkStatus: 'loading' } })
    mounted.push(entry)
    await flushPromises()
    expect(t(entry, 'plan-entry-guards').text()).toContain('3')
    await t(entry, 'plan-entry-edit').trigger('click')
    await flushPromises()
    await t(entry, 'plan-stop-rupees').setValue('100') // the levels read for the typed box is now out
    expect(calls.some((c) => c.url === `${PATH}/levels?stop_rupees=100&playbook_id=9`)).toBe(true)
    await t(entry, 'plan-save').trigger('click')
    await flushPromises()
    expect(t(entry, 'plan-entry-guards').text()).toContain('5') // PlanEntry's own @saved handler took the server's answer
    early.resolve({ data: { stop: { percent: '9.99', rupees: '996.13', words: 'old words', rupee_words: 'old rupee words', warning: null }, target: null } })
    await flushPromises()
    expect(t(entry, 'plan-entry-guards').text()).toContain('5')
    expect(entry.text()).not.toContain('old rupee words')
    expect(entry.text()).not.toContain('996.13')
  })

  it('an earlier levels answer that comes after the save does not refill the sheet boxes', async () => {
    const early = deferred()
    answers[`GET ${PATH}`] = sheetAnswer('996.13')
    answers[`GET ${PATH}/levels?stop_rupees=100&playbook_id=9`] = () => early.promise
    answers[`PUT ${PATH}`] = sheetAnswer('100.00')
    const w = await sheet()
    await t(w, 'plan-stop-rupees').setValue('100')
    await t(w, 'plan-save').trigger('click')
    await flushPromises()
    early.resolve({ data: { stop: { percent: '9.99', rupees: '100', words: 'old words', rupee_words: null, warning: null }, target: null } })
    await flushPromises()
    expect(t(w, 'plan-stop').element.value).toBe('40') // not the older answer's 9.99
    expect(w.text()).not.toContain('old words')
  })

  it('a plan watch answer that began before the save is never shown, and the fresh read is', async () => {
    vi.useFakeTimers()
    const early = deferred()
    const fresh = deferred()
    let reads = 0
    const pw = (label) => ({ strategy_id: 70, plan_state: 'planned', lines: [{ key: 'stop', kind: 'stop', section: 'plan', label, unit: 'pnl_rupees', state: 'watching', fires_at: '-100', now: null, distance_rs: null, distance_pct: null, reason: null }] })
    answers['GET /strategies/70/plan-watch'] = () => {
      reads += 1
      return reads === 1 ? early.promise : fresh.promise
    }
    const box = mount(PlanWatch, { attachTo: document.body, props: { strategyId: 70 } })
    mounted.push(box)
    await flushPromises()
    markSaved(70) // the save was stored while read #1 is out
    await flushPromises()
    early.resolve({ data: pw('old 996.13') })
    await flushPromises()
    await vi.advanceTimersByTimeAsync(20)
    await flushPromises()
    expect(box.text()).not.toContain('old 996.13') // the intermediate render: the stale answer was never drawn
    expect(reads).toBe(2)
    fresh.resolve({ data: pw('fires 100') })
    await flushPromises()
    expect(box.text()).toContain('fires 100')
    expect(box.text()).not.toContain('old 996.13')
  })

  it('a save of strategy 70 does not drop the answers of strategy 71', async () => {
    const early = deferred()
    let reads = 0
    answers['GET /strategies/71/plan-watch'] = () => { reads += 1; return early.promise }
    const box = mount(PlanWatch, { attachTo: document.body, props: { strategyId: 71 } })
    mounted.push(box)
    await flushPromises()
    markSaved(70)
    await flushPromises()
    early.resolve({ data: { strategy_id: 71, plan_state: 'planned', lines: [{ key: 'stop', kind: 'stop', section: 'plan', label: 'own 71', unit: 'pnl_rupees', state: 'watching', fires_at: '-50', now: null, distance_rs: null, distance_pct: null, reason: null }] } })
    await flushPromises()
    expect(box.text()).toContain('own 71')
    expect(reads).toBe(1)
  })
})

// plan-save-1127 round 2: the sheet's own cases next to the other two screens'
describe('the sheet: the three sentences and the guards', () => {
  const PARTS = { what_happened: 'Prices could not be read in time to check this plan.', impact: 'x', what_is_blocked: 'y', next_action: 'z' }
  it('a 422 shows the reason, a 200 shows the server value', async () => {
    answers[`GET ${PATH}`] = sheetAnswer('996.13')
    answers[`PUT ${PATH}`] = () => Promise.reject({ message: 'x', status: 422, parts: PARTS })
    const w = await sheet()
    await t(w, 'plan-save').trigger('click')
    await flushPromises()
    expect(w.text()).toContain(PARTS.what_happened)
    answers[`PUT ${PATH}`] = sheetAnswer('100.00')
    await t(w, 'plan-save').trigger('click')
    await flushPromises()
    expect(w.emitted('saved')[0][0].plan.stop).toBe('100.00')
  })

  it('a 4xx with no catalogue reason is Not confirmed', async () => {
    answers[`GET ${PATH}`] = sheetAnswer('996.13')
    answers[`PUT ${PATH}`] = () => Promise.reject({ message: 'x', status: 422, parts: null })
    const w = await sheet()
    await t(w, 'plan-save').trigger('click')
    await flushPromises()
    expect(w.text()).toContain(PLAN_NOT_CONFIRMED_TEXT)
    expect(w.text()).not.toContain('Try again')
  })

  it('a 200 the sheet cannot read after the save is Not confirmed, not "Something went wrong"', async () => {
    answers[`GET ${PATH}`] = sheetAnswer('996.13')
    answers[`PUT ${PATH}`] = { nothing: 'readable' }
    const w = await sheet()
    await t(w, 'plan-save').trigger('click')
    await flushPromises()
    expect(w.text()).toContain(PLAN_NOT_CONFIRMED_TEXT)
    expect(w.text()).not.toContain('Something went wrong')
    expect(w.emitted('saved')).toBeUndefined()
    expect(calls.filter((c) => c.method === 'PUT')).toHaveLength(1)
  })

  it('the load guard: a read that began before a save never puts the old plan back in the sheet', async () => {
    const slow = deferred()
    let reads = 0
    answers[`GET ${PATH}`] = () => { reads += 1; return Promise.resolve({ data: sheetAnswer('996.13') }) }
    answers[`GET ${PATH}?playbook_id=9`] = () => { reads += 1; return slow.promise }
    const w = await sheet()
    const picked = t(w, 'plan-playbook')
    expect(picked.exists()).toBe(true)
    await picked.setValue('9') // a pick: a second read of the sheet is now out
    expect(reads).toBe(2)
    markSaved(70) // a save of this strategy was stored while it is out
    slow.resolve({ data: { ...sheetAnswer('OLD-VALUE'), prefill: { ...sheetAnswer('OLD-VALUE').prefill, stop: 'OLD-VALUE', stop_rupees: 'OLD-VALUE' } } })
    await flushPromises()
    expect(t(w, 'plan-stop-rupees').element.value).toBe('996.13')
    expect(w.html()).not.toContain('OLD-VALUE')
  })
})

describe('PlanEntry: the card keeps loading while the fresh read is out', () => {
  it('a stale read dropped for a save does not clear loading before the fresh read answers', async () => {
    const stale = deferred()
    const fresh = deferred()
    let reads = 0
    answers[`GET ${PATH}`] = () => { reads += 1; return reads === 1 ? stale.promise : fresh.promise }
    const entry = mount(PlanEntry, { attachTo: document.body, props: { strategyId: 70, check: null, checkStatus: 'loading' } })
    mounted.push(entry)
    await flushPromises()
    markSaved(70)
    stale.resolve({ data: sheetAnswer('996.13') })
    await flushPromises()
    expect(reads).toBe(2)
    expect(t(entry, 'plan-entry-loading').exists()).toBe(true) // the fresh read is still out
    fresh.resolve({ data: sheetAnswer('100.00') })
    await flushPromises()
    expect(t(entry, 'plan-entry-loading').exists()).toBe(false)
  })
})

describe('plan-save-1127 round 2: the save count and the generic text', () => {
  const fake = (data) => ({ put: () => Promise.resolve({ data }), post: () => Promise.resolve({ data }) })
  it('sendPlan and resetPlan move the save count only for an answer the browser can read', async () => {
    const before = saveStamp(81)
    await sendPlan(fake({ unreadable: true }), 81, {}, true)
    await resetPlan(fake({ unreadable: true }), 81)
    expect(saveStamp(81)).toBe(before)
    await sendPlan(fake(sheetAnswer('1')), 81, {}, true)
    expect(saveStamp(81)).toBe(before + 1)
    await resetPlan(fake(sheetAnswer('1')), 81)
    expect(saveStamp(81)).toBe(before + 2)
  })

  it('the generic text is read from a plain string, a catalogue object, or null', () => {
    const generic = (text) => readPlan({ generic: true, generic_text: text, labels: {} })
    expect(generic('Nothing to adjust.').text).toBe('Nothing to adjust.')
    expect(generic({ what_happened: 'Nothing to adjust.' }).text).toBe('Nothing to adjust.')
    expect(generic(null).text).toBe('')
    expect(generic(5).text).toBe('')
  })
})
