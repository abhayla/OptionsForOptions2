// P8 page flow (ADR-330 (9), (32); ADR-002, ADR-003): the plan sheet's "Reset to playbook" button. One confirmation (the server's
// sentence, which says the typed levels stay), then POST /strategies/<id>/adjustment-plan/reset; the reply's changed / switched_off
// markers are shown; a refusal (playbook deleted) shows the server's sentence and leaves the sheet as it was. Real case 26 Nov:
// strategy 70 on playbook 9 with a rupee stop typed on the sheet.
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

const CONFIRM = "Reset to playbook puts back this playbook's conditions only. The levels you typed on the sheet (profit target, rupee target, rupee stop, time exit, the adjustment limit) and the plan's settings stay as you set them. Reset the conditions?"
const LABELS = {
  title: "When tracking starts: this strategy's plan", playbook: 'Playbook', target: 'Target', stop: 'Stop', max_adjustments: 'Max adjustments',
  time_exit: 'Time exit', time_exit_on: 'Time exit date (blank = expiry day)', customise: 'Customise triggers', use_as_is: 'Use playbook as is',
  save: 'Save plan', close: 'Close', reset: 'Reset to playbook', reset_confirm: CONFIRM,
  reset_put_back: "Put back to the playbook's values:", reset_put_back_off: 'Switched on again:',
  reset_put_back_none: 'Nothing differed from the playbook, so nothing was put back.',
}
const PLAYBOOKS = [{ id: 9, name: '"Mine"', type: 'ic', type_name: 'Iron condor', is_system: false, draft: false, active: true }]
const PLAN = (over = {}) => ({ playbook_id: 9, playbook_name: '"Mine"', target: '60', stop: '40', max_adjustments: 3, time_exit: null,
  accepted_at: '2026-11-26T09:30:00+05:30', changed: ['triggers.T-01'], switched_off: [], ...over })
const PREFILL = { playbook_id: 9, target: '60', stop: '40', max_adjustments: 3, time_exit: null }
const sheetAnswer = (over = {}) => ({
  strategy_id: 70, type: 'ic', type_name: 'Iron condor', generic: false, generic_text: null, playbooks: PLAYBOOKS, plan: PLAN(),
  prefill: PREFILL, labels: LABELS, ...over,
})
const PATH = '/strategies/70/adjustment-plan'
const RESET = `${PATH}/reset`
const t = (w, id) => w.find(`[data-testid="${id}"]`)
const mounted = []
afterEach(() => { mounted.splice(0).forEach((w) => w.unmount()) })
beforeEach(() => { calls.length = 0; answers = {}; answers['GET /strategies/70/alert-style'] = { style: 'popup' } })
async function sheet(props = { edit: true }) {
  const w = mount(AdjustPlanSheet, { attachTo: document.body, props: { open: true, strategyId: 70, ...props } })
  await flushPromises()
  mounted.push(w)
  return w
}
const posts = () => calls.filter((c) => c.method === 'POST')

describe('P8 Reset to playbook on the plan sheet', () => {
  it('core: the button asks once with the server sentence, and posts nothing before the user confirms', async () => {
    answers[`GET ${PATH}`] = sheetAnswer()
    const w = await sheet()
    expect(t(w, 'plan-reset').text()).toBe('Reset to playbook')
    await t(w, 'plan-reset').trigger('click')
    expect(t(w, 'plan-reset-confirm').text()).toContain(CONFIRM)
    expect(posts()).toHaveLength(0)
  })
  it('Confirm posts the reset once, shows the reply (levels as the server sent them) and the changed marker', async () => {
    answers[`GET ${PATH}`] = sheetAnswer()
    answers[`POST ${RESET}`] = sheetAnswer({ plan: PLAN({ changed: [], switched_off: [] }), put_back: ['triggers.T-02'], put_back_off: ['triggers.T-05'] })
    const w = await sheet()
    await t(w, 'plan-reset').trigger('click')
    await t(w, 'plan-reset-yes').trigger('click')
    await flushPromises()
    expect(posts()).toEqual([{ method: 'POST', url: RESET, body: undefined }])
    expect(t(w, 'plan-reset-markers').text()).toContain("Put back to the playbook's values: a condition of the playbook") // F2 D-TG2-1: never the raw key; no rules answer here
    expect(t(w, 'plan-reset-markers').text()).toContain('Switched on again: a condition of the playbook')
    expect(t(w, 'plan-target').element.value).toBe('60') // the typed levels are the server's, kept
    expect(t(w, 'plan-reset-confirm').exists()).toBe(false)
  })
  it('a reset that put nothing back says so (stated, not blank)', async () => {
    answers[`GET ${PATH}`] = sheetAnswer()
    answers[`POST ${RESET}`] = sheetAnswer({ plan: PLAN({ changed: [], switched_off: [] }) })
    const w = await sheet()
    await t(w, 'plan-reset').trigger('click')
    await t(w, 'plan-reset-yes').trigger('click')
    await flushPromises()
    expect(posts()).toHaveLength(1)
    expect(t(w, 'plan-reset-markers').text()).toBe('Nothing differed from the playbook, so nothing was put back.')
  })
  it('Cancel posts nothing and closes the question', async () => {
    answers[`GET ${PATH}`] = sheetAnswer()
    const w = await sheet()
    await t(w, 'plan-reset').trigger('click')
    await t(w, 'plan-reset-no').trigger('click')
    expect(posts()).toHaveLength(0)
    expect(t(w, 'plan-reset-confirm').exists()).toBe(false)
  })
  it('refused (playbook deleted): the server sentence shows, the sheet stays as it was', async () => {
    answers[`GET ${PATH}`] = sheetAnswer()
    answers[`POST ${RESET}`] = () => Promise.reject({ message: 'x', status: 404,
      parts: { what_happened: 'That playbook was not found.', impact: '', what_is_blocked: '', next_action: '' } })
    const w = await sheet()
    await t(w, 'plan-reset').trigger('click')
    await t(w, 'plan-reset-yes').trigger('click')
    await flushPromises()
    expect(t(w, 'plan-error').text()).toContain('That playbook was not found.')
    expect(t(w, 'plan-target').element.value).toBe('60')
  })
  it('no button when the plan has no playbook (deleted) or there is no plan yet', async () => {
    answers[`GET ${PATH}`] = sheetAnswer({ plan: PLAN({ playbook_id: null, playbook_name: null }) })
    expect(t(await sheet(), 'plan-reset').exists()).toBe(false)
    answers[`GET ${PATH}`] = sheetAnswer({ plan: null })
    expect(t(await sheet({ edit: false }), 'plan-reset').exists()).toBe(false)
  })
  it('the server sent no reset label or sentence: no button (fail closed)', async () => {
    const { reset: _r, reset_confirm: _c, ...bare } = LABELS
    answers[`GET ${PATH}`] = sheetAnswer({ labels: bare })
    expect(t(await sheet(), 'plan-reset').exists()).toBe(false)
  })
})
