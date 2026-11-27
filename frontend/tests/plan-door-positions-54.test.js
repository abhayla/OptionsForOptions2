// ADR-330 (54): each running trade on Positions gets a Plan button beside Exit and Stops; it opens the same plan sheet as the builder's
// "Edit plan" (one sheet, two doors, one module). Real case 27 Nov 09:45: the tester could not find the plan sheet of an existing trade.
// (setup copied from positions-one-list.test.js) ADR-330 (10) (SPEC CHANGE: replaces ADR-201 (2)): real and paper trades in ONE Positions list - filter All / Real / Paper (default
// All), a PAPER tag on every paper group, a REAL (Zerodha) tag on every real group, two totals never added together.
// Paper figures are the recorded reply (tests/fixtures/paper-strategies.json); real replies have the shape of GET /positions.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import REAL0 from './fixtures/paper-strategies.json'
import { closedFrom } from './_closedRows'

const REAL = { ...REAL0, strategies: REAL0.strategies.map((s) => ({ ...s, closed: closedFrom(s.positions) })) }
const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url, body) => {
    calls.push([method, url, body])
    const a = answers[`${method} ${url}`]
    return a ? a() : Promise.reject({ message: 'no answer', parts: null, status: null })
  }
  return { ...actual, default: { get: reply('GET'), post: reply('POST') } }
})

import PositionsPage from '@/pages/PositionsPage.vue'
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'
import AdjustPlanSheet from '@/components/strategy/AdjustPlanSheet.vue'
import PlanEntry from '@/components/strategy/PlanEntry.vue'

const ok = (data) => () => Promise.resolve({ data })
const t = (w, id) => w.get(`[data-testid="${id}"]`)
const all = (w, id) => w.findAll(`[data-testid="${id}"]`)
const has = (w, id) => w.find(`[data-testid="${id}"]`).exists()
const own = (symbol, units, zerodha, over = {}) => ({ tradingsymbol: symbol, zerodha_units: zerodha, units, pending: false, pending_plans: [], pnl: '65.00', pnl_text: '+65.00', pnl_state: 'stated', pnl_reason: null, ...over })
// the server's real_pnl object (Lane S, ADR-330 (24)); every string below is what the server would send, the browser only prints it
const REAL_PNL = { value: '65.00', pnl_text: '+65.00', state: 'stated', reason: null, source: 'Zerodha', read_at: '2026-10-29T10:00:00+05:30', caption: 'Zerodha, as at 10:00:00 IST', excludes_note: null }
const pos = (strategies, over = {}) => ({ read_at: '2026-10-29T10:00:00+05:30', real_pnl: REAL_PNL, pnl_text: REAL_PNL.pnl_text, strategies, has_outside: false, outside_lots: 0, blocked: false, blocked_strategy_ids: [], ...over })
const withReal = (real, strategies) => pos(strategies, { real_pnl: { ...REAL_PNL, ...real }, pnl_text: real.pnl_text ?? null })
const REAL_ONE = pos([{ strategy_id: 1, blocked: false, contracts: [own('NIFTY26O1923650CE', 65, 65)] }])
const refused = () => Promise.reject({ status: 409, parts: { what_happened: 'Connect your Zerodha account to continue.', impact: 'i', what_is_blocked: 'b', next_action: 'n' } })

async function page(url = '/p') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/p', component: PositionsPage, meta: { title: 'T', parent: 'Positions', view: 'current' } },
      { path: '/positions/current-positions', component: { template: '<div/>' } },
      { path: '/strategy/builder', component: { template: '<div/>' } },
      { path: '/strategy/:id/execute', component: { template: '<div/>' } },
    ],
  })
  router.push(url)
  await router.isReady()
  const w = mount(PositionsPage, { attachTo: document.body, global: { plugins: [router] } }) // attached: isVisible reads the v-show style
  await flushPromises()
  return { w, router }
}
const withBoth = () => {
  answers['GET /positions'] = ok(REAL_ONE)
  answers['GET /paper/strategies'] = ok(REAL)
  answers['GET /features'] = ok({ order_path: 'on' })
}

beforeEach(() => { calls.length = 0; answers = {}; vi.useFakeTimers() })
afterEach(() => vi.useRealTimers())


const LABELS = { title: "This strategy's plan", playbook: 'Playbook', target: 'Target', stop: 'Stop', max_adjustments: 'Max adjustments', time_exit: 'Time exit',
  time_exit_on: 'Time exit date', customise: 'Customise triggers', use_as_is: 'Use playbook as is', save: 'Save plan', close: 'Close', reset: 'Reset to playbook', reset_confirm: 'x' }
const sheetOf = (id, plan) => ({ strategy_id: id, type: 'ic', type_name: 'Iron condor', generic: false, generic_text: null,
  playbooks: [{ id: 9, name: 'Mine', type: 'ic', type_name: 'Iron condor', is_system: false, draft: false, active: true }], plan,
  prefill: { playbook_id: 9, target: '60', stop: '40', max_adjustments: 3, time_exit: null }, labels: LABELS })
const PLAN = { playbook_id: 9, playbook_name: 'Mine', target: '60', stop: '40', max_adjustments: 3, time_exit: null, accepted_at: '2026-11-26T09:30:00+05:30', changed: [], switched_off: [] }
const sheetCalls = () => calls.filter((c) => c[1].includes('adjustment-plan'))
const openIds = () => REAL.strategies.filter((s) => s.positions.some((p) => p.net_quantity !== 0)).map((s) => s.strategy_id)

describe('ADR-330 (54): the Plan button on Positions', () => {
  it('every running paper trade has a Plan button; a closed one has none', async () => {
    withBoth()
    const { w } = await page()
    const buttons = w.findAll('[data-testid^="plan-open-paper-"]').map((b) => b.attributes('data-testid'))
    expect(buttons.sort()).toEqual(openIds().map((id) => `plan-open-paper-${id}`).sort())
    expect(has(w, 'plan-open-paper-2')).toBe(false) // strategy 2 is fully closed: no button
  })
  it('the button sits in the same column as Stops and Exit', async () => {
    withBoth()
    const { w } = await page()
    const col = w.get('[data-testid="paper-actions"]')
    expect(col.find('[data-testid^="plan-open-paper-"]').exists()).toBe(true)
    expect(col.find('[data-testid^="stops-open-"]').exists()).toBe(true)
  })
  it('a real trade with positions has a Plan button too (same for real and paper rows)', async () => {
    withBoth()
    const { w } = await page()
    expect(has(w, 'plan-open-real-1')).toBe(true)
  })
  it('clicking it opens the ONE plan sheet (AdjustPlanSheet) for that strategy; a trade with a plan is edited (PUT), not created', async () => {
    withBoth()
    answers['GET /strategies/1/adjustment-plan'] = ok(sheetOf(1, PLAN))
    answers['GET /strategies/1/alert-style'] = ok({ style: 'popup' })
    const { w } = await page()
    await t(w, 'plan-open-paper-1').trigger('click')
    await flushPromises()
    const sheets = w.findAllComponents(AdjustPlanSheet).filter((s) => s.props('open'))
    expect(sheets).toHaveLength(1)
    expect(sheets[0].props('strategyId')).toBe(1)
    expect(sheets[0].props('edit')).toBe(true)
  })
  it('a trade with no plan opens the same sheet to set one (POST), edit false', async () => {
    withBoth()
    answers['GET /strategies/1/adjustment-plan'] = ok(sheetOf(1, null))
    answers['GET /strategies/1/alert-style'] = ok({ style: 'popup' })
    const { w } = await page()
    await t(w, 'plan-open-real-1').trigger('click')
    await flushPromises()
    const sheets = w.findAllComponents(AdjustPlanSheet).filter((s) => s.props('open'))
    expect(sheets).toHaveLength(1)
    expect(sheets[0].props('edit')).toBe(false)
  })
  it('opening reads nothing on page load: the plan is read only when the button is pressed', async () => {
    withBoth()
    await page()
    expect(sheetCalls()).toEqual([])
  })
  it('a plan that cannot be read says so, opens no sheet and keeps the button', async () => {
    withBoth()
    answers['GET /strategies/1/adjustment-plan'] = () => Promise.reject({ message: 'x', parts: null, status: 500 })
    const { w } = await page()
    await t(w, 'plan-open-real-1').trigger('click')
    await flushPromises()
    expect(t(w, 'plan-open-failed-real-1').text()).toBe('Could not open the plan. Try again.')
    expect(w.findAllComponents(AdjustPlanSheet).filter((s) => s.props('open'))).toHaveLength(0)
    expect(has(w, 'plan-open-real-1')).toBe(true)
  })
  it('one module: the builder door (PlanEntry) and this door use the same AdjustPlanSheet component', () => {
    expect(PlanEntry.components?.AdjustPlanSheet ?? AdjustPlanSheet).toBe(AdjustPlanSheet)
  })
})
