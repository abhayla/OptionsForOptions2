// GC-ADJ2 step 4 (REQ-161 AC-1..AC-4, REQ-158 AC-5): the plan sheet (AdjustPlanSheet), the tracking panel's Plan entry
// (PlanEntry) and the sheet's opening after Add to Paper. The answers have the shape of GET/POST/PUT
// /api/strategies/{id}/adjustment-plan (AdjustmentPlanOut, backend/ofo_app/routes/adjustment_plan.py; the server side is
// proven on the ADJ-02 scenario in tests_app/test_adjustment_plan.py). Every expected string is the answer's own text.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import { netLegsFromBook } from '@/lib/paperDrafts'
import REAL from './fixtures/paper-book-63.json'

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
import PlanEntry from '@/components/strategy/PlanEntry.vue'

const LABELS = {
  title: "When tracking starts: this strategy's plan", playbook: 'Playbook', target: 'Target', stop: 'Stop', max_adjustments: 'Max adjustments',
  time_exit: 'Time exit', customise: 'Customise triggers', use_as_is: 'Use playbook as is', save: 'Save plan', close: 'Close',
  plan_entry: 'Plan', edit: 'Edit plan', no_plan: 'No plan saved yet', hour: 'Hour', minute: 'Minute',
}
const PLAYBOOKS = [
  { id: 1, name: 'Iron condor (system)', type: 'ic', type_name: 'Iron condor', is_system: true, draft: false, active: false },
  { id: 9, name: '"Mine"', type: 'ic', type_name: 'Iron condor', is_system: false, draft: false, active: true },
]
const PREFILL_9 = { playbook_id: 9, target: '50', stop: '50', max_adjustments: 2, time_exit: null }
const sheetAnswer = (over = {}) => ({
  strategy_id: 70, type: 'ic', type_name: 'Iron condor', generic: false, generic_text: null, playbooks: PLAYBOOKS, plan: null,
  prefill: PREFILL_9, labels: LABELS, ...over,
})
const PLAN = { playbook_id: 9, playbook_name: '"Mine"', target: '60', stop: '40', max_adjustments: 3, time_exit: { hour: 14, minute: 45 },
  accepted_at: '2026-11-02T09:30:00+05:30' }
const GENERIC = sheetAnswer({
  type: null, type_name: null, generic: true, playbooks: [], prefill: null,
  generic_text: { what_happened: "No playbook matches this strategy's shape, so only the generic triggers and approaches apply.",
    impact: 'No plan was saved for this strategy.', what_is_blocked: 'Saving a plan.', next_action: 'Close this sheet; the generic triggers and approaches stay on.' },
})
const PATH = '/strategies/70/adjustment-plan'

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const mounted = []
afterEach(() => { mounted.splice(0).forEach((w) => w.unmount()); vi.useRealTimers() })
beforeEach(() => { calls.length = 0; answers = {} })
async function sheet(props = {}) {
  const w = mount(AdjustPlanSheet, { attachTo: document.body, props: { open: true, strategyId: 70, ...props } })
  await flushPromises()
  mounted.push(w)
  return w
}
const inputs = (w) => ({ playbook: t(w, 'plan-playbook').element.value, target: t(w, 'plan-target').element.value,
  stop: t(w, 'plan-stop').element.value, max: t(w, 'plan-max').element.value, time: t(w, 'plan-time').element.value })

describe('REQ-161 AC-1: the sheet is pre-filled from the server', () => {
  it('shows the server labels and the prefill of the active playbook: playbook, target, stop, max adjustments, time exit, Customise triggers', async () => {
    answers[`GET ${PATH}`] = sheetAnswer()
    const w = await sheet()
    expect(calls).toEqual([{ method: 'GET', url: PATH, body: undefined }])
    expect(inputs(w)).toEqual({ playbook: '9', target: '50', stop: '50', max: '2', time: '' })
    expect(t(w, 'plan-sheet-type').text()).toBe('Iron condor')
    expect(t(w, 'plan-use-as-is').text()).toBe('Use playbook as is')
    expect(t(w, 'plan-customise').text()).toBe('Customise triggers')
    expect(w.text()).toContain('Max adjustments')
    expect(document.body.querySelector('[role="dialog"]').getAttribute('aria-label')).toBe(LABELS.title)
  })

  it('a plan the strategy already holds is what the sheet shows (clock as HH:MM)', async () => {
    answers[`GET ${PATH}`] = sheetAnswer({ plan: PLAN, prefill: { playbook_id: 9, target: '60', stop: '40', max_adjustments: 3, time_exit: PLAN.time_exit } })
    const w = await sheet({ edit: true })
    expect(inputs(w)).toEqual({ playbook: '9', target: '60', stop: '40', max: '3', time: '14:45' })
  })
})

describe('REQ-161 AC-2: one click accepts; another playbook refills every field', () => {
  it('Use playbook as is sends the playbook alone (POST) and closes with the saved plan', async () => {
    answers[`GET ${PATH}`] = sheetAnswer()
    answers[`POST ${PATH}`] = sheetAnswer({ plan: PLAN })
    const w = await sheet()
    await t(w, 'plan-use-as-is').trigger('click')
    await flushPromises()
    expect(calls.filter((c) => c.method !== 'GET')).toEqual([{ method: 'POST', url: PATH, body: { playbook_id: 9 } }])
    expect(w.emitted('close')).toHaveLength(1)
    expect(w.emitted('saved')[0][0].plan.target).toBe('60')
  })

  it('picking another playbook reads the server prefill for it and refills target, stop, max adjustments and time exit', async () => {
    answers[`GET ${PATH}`] = sheetAnswer()
    answers[`GET ${PATH}?playbook_id=1`] = sheetAnswer({ prefill: { playbook_id: 1, target: '70', stop: '30', max_adjustments: 4, time_exit: { hour: 9, minute: 5 } } })
    const w = await sheet()
    await t(w, 'plan-playbook').setValue('1')
    await flushPromises()
    expect(calls.map((c) => c.url)).toEqual([PATH, `${PATH}?playbook_id=1`])
    expect(inputs(w)).toEqual({ playbook: '1', target: '70', stop: '30', max: '4', time: '09:05' })
  })

  it('Save sends the typed fields as the server shapes them; a plan already held is edited with PUT', async () => {
    answers[`GET ${PATH}`] = sheetAnswer({ plan: PLAN, prefill: { playbook_id: 9, target: '60', stop: '40', max_adjustments: 3, time_exit: PLAN.time_exit } })
    answers[`PUT ${PATH}`] = sheetAnswer({ plan: { ...PLAN, stop: '35' } })
    const w = await sheet({ edit: true })
    await t(w, 'plan-stop').setValue('35')
    await t(w, 'plan-save').trigger('click')
    await flushPromises()
    expect(calls.filter((c) => c.method !== 'GET')).toEqual([{ method: 'PUT', url: PATH,
      body: { playbook_id: 9, target: '60', stop: '35', max_adjustments: '3', time_exit: '14:45' } }])
    expect(w.emitted('saved')).toHaveLength(1)
  })

  it('a refusal shows the server message naming the field, keeps the sheet open and the typed values', async () => {
    const refused = { message: 'x', status: 422, parts: { what_happened: 'The playbook value max_adjustments is not valid.',
      impact: 'Nothing was saved; your playbooks are as they were.', what_is_blocked: 'Saving this playbook.', next_action: 'Correct that value, then save again.' } }
    answers[`GET ${PATH}`] = sheetAnswer()
    answers[`POST ${PATH}`] = () => Promise.reject(refused)
    const w = await sheet()
    await t(w, 'plan-max').setValue('11')
    await t(w, 'plan-save').trigger('click')
    await flushPromises()
    expect(t(w, 'plan-error').text()).toContain('The playbook value max_adjustments is not valid.')
    expect(w.emitted('close')).toBeUndefined()
    expect(inputs(w).max).toBe('11')
  })
})

describe('REQ-161 AC-4: a shape with no playbook', () => {
  it('shows the server generic text and offers Close only', async () => {
    answers[`GET ${PATH}`] = GENERIC
    const w = await sheet()
    expect(t(w, 'plan-sheet-generic').text()).toBe(GENERIC.generic_text.what_happened)
    expect(t(w, 'plan-use-as-is').exists()).toBe(false)
    expect(t(w, 'plan-save').exists()).toBe(false)
    expect(t(w, 'plan-close').text()).toBe('Close')
    await t(w, 'plan-close').trigger('click')
    expect(w.emitted('close')).toHaveLength(1)
  })

  it('an unreadable or failed read says so plainly and shows no field', async () => {
    answers[`GET ${PATH}`] = { strategy_id: 70 }
    const w = await sheet()
    expect(t(w, 'plan-sheet-error').exists()).toBe(true)
    expect(t(w, 'plan-use-as-is').exists()).toBe(false)
  })
})

describe('REQ-161 AC-3: the Plan entry on the tracking panel', () => {
  const entry = async () => {
    const w = mount(PlanEntry, { attachTo: document.body, props: { strategyId: 70 } })
    await flushPromises()
    mounted.push(w)
    return w
  }

  it('shows the plan\'s playbook name and guards, and Edit reopens the sheet which saves with PUT', async () => {
    answers[`GET ${PATH}`] = sheetAnswer({ plan: PLAN, prefill: { playbook_id: 9, target: '60', stop: '40', max_adjustments: 3, time_exit: PLAN.time_exit } })
    answers[`PUT ${PATH}`] = sheetAnswer({ plan: { ...PLAN, target: '55' } })
    const w = await entry()
    expect(t(w, 'plan-entry-title').text()).toBe('Plan')
    expect(t(w, 'plan-entry-playbook').text()).toBe('Playbook: "Mine"')
    expect(t(w, 'plan-entry-guards').text()).toBe('Target: 60 / Stop: 40 / Max adjustments: 3 / Time exit: 14:45')
    expect(document.body.querySelector('[data-testid="plan-sheet"]')).toBeNull()
    await t(w, 'plan-entry-edit').trigger('click')
    await flushPromises()
    expect(t(w, 'plan-entry-edit').text()).toBe('Edit plan')
    await t(w, 'plan-target').setValue('55')
    await t(w, 'plan-save').trigger('click')
    await flushPromises()
    expect(calls.filter((c) => c.method === 'PUT')).toHaveLength(1)
    expect(t(w, 'plan-entry-guards').text()).toContain('Target: 55')
  })

  it('a strategy without a plan says so and the button opens the sheet to accept one (POST)', async () => {
    answers[`GET ${PATH}`] = sheetAnswer()
    answers[`POST ${PATH}`] = sheetAnswer({ plan: PLAN })
    const w = await entry()
    expect(t(w, 'plan-entry-none').text()).toBe('No plan saved yet')
    await t(w, 'plan-entry-edit').trigger('click')
    await flushPromises()
    await t(w, 'plan-use-as-is').trigger('click')
    await flushPromises()
    expect(calls.filter((c) => c.method === 'POST')).toEqual([{ method: 'POST', url: PATH, body: { playbook_id: 9 } }])
    expect(t(w, 'plan-entry-playbook').text()).toBe('Playbook: "Mine"')
  })

  it('a generic shape shows the server text; a failed read shows nothing', async () => {
    answers[`GET ${PATH}`] = GENERIC
    expect((await entry()).find('[data-testid="plan-entry-generic"]').text()).toBe(GENERIC.generic_text.what_happened)
    mounted.splice(0).forEach((w) => w.unmount())
    answers = {}
    expect((await entry()).find('[data-testid="plan-entry"]').exists()).toBe(false)
  })
})

describe('REQ-161 AC-1: the sheet opens after the paper orders are placed, never after a failed placement', () => {
  const CONTRACTS = REAL.positions.map((p) => ({ contract_id: p.contract_id, exchange_segment: 'NSE_FO', exchange_token: p.contract_id,
    instrument_type: p.instrument, expiry: p.expiry, strike: p.strike, lot_size: 65, symbol: `NIFTY${p.strike}${p.instrument}` }))
  const PLAN_LEGS = () => netLegsFromBook(REAL, CONTRACTS).map((l, i) => ({ ...l, id: `leg-${i}`, typed: false, captured_at: REAL.answered_at }))
  const BOOK_70 = { ...REAL, strategy_id: 70, name: '"Iron"' }
  const builder = async () => {
    answers = {
      'GET /strategies': { strategies: [] }, 'POST /strategies': { id: 70, revision: 1, name: '"Iron"' }, 'GET /paper/strategies/70': BOOK_70,
      'GET /catalogue/NIFTY/contracts?expiry=2026-11-03': { underlying: 'NIFTY', contracts: CONTRACTS },
      'POST /strategies/outcome': () => new Promise(() => {}), 'POST /strategies/leg-edit': () => new Promise(() => {}),
      [`GET ${PATH}`]: sheetAnswer(),
    }
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }, { path: '/positions/current-positions', component: { template: '<p />' } }] })
    await router.push('/strategy/builder')
    await router.isReady()
    const w = mount(StrategyBuilderPage, { attachTo: document.body, global: { plugins: [router], stubs: { PayoffChart: true } } })
    await flushPromises()
    mounted.push(w)
    w.vm.$.setupState.setLegs(PLAN_LEGS())
    await flushPromises()
    await t(w, 'add-to-paper').trigger('click')
    await flushPromises()
    return w
  }

  it('placed: the plan sheet opens for that strategy, pre-filled', async () => {
    const w = await builder()
    answers['POST /paper/strategies/70/orders'] = BOOK_70
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(calls.filter((c) => c.url === PATH)).toHaveLength(1)
    expect(document.body.querySelector('[data-testid="plan-sheet"]')).not.toBeNull()
    expect(document.body.querySelector('[data-testid="plan-target"]').value).toBe('50')
  })

  it('a failed placement never opens the sheet and never reads a plan', async () => {
    const w = await builder()
    answers['POST /paper/strategies/70/orders'] = () => Promise.reject({ message: 'x', status: 409, parts: null })
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(calls.filter((c) => c.url === PATH)).toHaveLength(0)
    expect(document.body.querySelector('[data-testid="plan-sheet"]')).toBeNull()
  })
})
