// GC-ICFIX u141-u143 (Issue 5, ADR-304 (3), ADR-296, ADR-305, ADR-003): the trade page re-reads the rule check on the page's
// one refresh rhythm (usePaperRefresh.onData), never flipping to loading on a background read; a failed re-read keeps the last
// lines with a could-not-refresh mark and the old "as of"; every sentence below is the SERVER's text, the browser derives nothing.
// Values are the user test of 13 Nov (strategy 144): the warning showed 2.07 % for 5 minutes while the real figure was 7.46 %.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

let checks = [] // successive answers of GET .../adjustment-check: a value, or an Error to reject with
let checkCalls = 0
let pending = null // when set, the next check read waits for it
const answer = (url) => {
  if (url === '/strategies/7/tracking') return Promise.resolve({ data: TRACK })
  if (url === '/strategies/7/adjustment-check') {
    const a = checks[Math.min(checkCalls, checks.length - 1)]
    checkCalls += 1
    const out = () => (a instanceof Error ? Promise.reject(a) : Promise.resolve({ data: a }))
    return pending ? pending.then(out) : out()
  }
  if (url.startsWith('/strategies/7/adjustment-plan')) return Promise.resolve({ data: PLAN })
  return Promise.reject({ status: 404, parts: null })
}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (u) => answer(u), post: (u) => answer(u), put: (u) => answer(u) } }
})
import TrackingPanel from '@/components/strategy/TrackingPanel.vue'
import PlanEntry from '@/components/strategy/PlanEntry.vue'
import { TRACKING_REFRESH_MS } from '@/lib/tracking'
import { CHECK_STALE_TEXT } from '@/lib/sharedStateText'

let TRACK = { strategy_id: 7, state: 'LIVE', paper_pnl: '195.00', paper_pnl_text: '+195.00', as_of: null, legs: [], detections: [] }
const LABELS = { plan_entry: 'Plan', playbook: 'Playbook', target: 'Target', stop: 'Stop', max_adjustments: 'Max adjustments', time_exit: 'Time exit',
  edit: 'Edit plan', no_plan: 'No plan saved yet: default rules apply', set_plan: 'Set plan' }
const PLAN = { strategy_id: 7, type: 'ic', type_name: 'Iron condor', generic: false, generic_text: null, labels: LABELS, plan: null,
  playbooks: [{ id: 9, name: 'Mine', type: 'ic', type_name: 'Iron condor', is_system: false, draft: false, active: true }], prefill: { playbook_id: 9 } }

const AS_OF_1 = 'As of 01:05:00 PM IST'
const AS_OF_2 = 'As of 01:05:05 PM IST'
const flag = (pct, over = {}) => ({ kind: 'flag', rule_id: 'R-stop', trigger_id: 'T-06', cmp: 'ge', value: pct, threshold: '50.0000', reason: null,
  wording: 'Your rule was triggered', condition: `Loss as % of max loss: ${pct} % (rule 5 %)`, suggestion_id: 11, note: null,
  stop_text: `Stop reached: loss now ₹1,234.00 (${pct} % of max loss); stop line ₹2,980.00 (5 % of max loss); reached at 12:58 IST`, ...over })
const row = (rule_id, text, state = 'checked', over = {}) => ({ rule_id, trigger_id: rule_id, threshold: '40.0000', amount: null, later: [],
  tightened_by: null, state, reason: null, text, after: null, reason_code: null, ...over })
const check = (over = {}) => ({ strategy_id: 7, as_of: '2026-11-13T07:35:00Z', as_of_text: AS_OF_1, strategy_type: 'ic', type_name: 'Iron condor',
  playbook: { source: 'system', id: 1, status: null, draft: false }, stage: { name: null, index: null }, withheld: null, results: [],
  limits: [row('T-07', 'Target: profit of 40 % of max profit, before charges')], paused: null, ...over })

const mounted = []
const t = (w, id) => w.find(`[data-testid="${id}"]`)
async function panel() {
  const w = mount(TrackingPanel, { props: { savedId: 7, legs: [] } })
  mounted.push(w)
  await flushPromises()
  return w
}
const tick = async () => { await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS) }
beforeEach(() => { vi.useFakeTimers(); checks = []; checkCalls = 0; pending = null
  TRACK = { strategy_id: 7, state: 'LIVE', paper_pnl: '195.00', paper_pnl_text: '+195.00', as_of: null, legs: [], detections: [] } })
afterEach(() => { mounted.splice(0).forEach((w) => w.unmount()); vi.useRealTimers() })

describe('the stop warning follows the live check (Issue 5)', () => {
  it('(1) two successive replies, stop value 2.07 then 7.46: the warning changes with no reload', async () => {
    checks = [check({ results: [flag('2.07')] }), check({ results: [flag('7.46')], as_of_text: AS_OF_2 })]
    const w = await panel()
    expect(t(w, 'playbook-flag-condition').text()).toContain('2.07 %')
    await tick()
    expect(checkCalls).toBe(2)
    expect(t(w, 'playbook-flag-condition').text()).toContain('7.46 %')
    expect(t(w, 'playbook-flag-condition').text()).not.toContain('2.07')
  })

  it('(6) the warning carries the loss and the stop line in rupees and percent and the time it fired: the server\'s sentence', async () => {
    checks = [check({ results: [flag('7.46')] })]
    const w = await panel()
    expect(t(w, 'playbook-flag-stop').text()).toBe(
      'Stop reached: loss now ₹1,234.00 (7.46 % of max loss); stop line ₹2,980.00 (5 % of max loss); reached at 12:58 IST')
  })

  it('a flag without the server\'s stop sentence (an older server or a non-stop rule) prints no stop line, never one built here', async () => {
    checks = [check({ results: [flag('7.46', { stop_text: undefined })] })]
    const w = await panel()
    expect(t(w, 'playbook-flag-stop').exists()).toBe(false)
    expect(t(w, 'playbook-flag-condition').exists()).toBe(true)
  })

  it('ADR-296: a stop already true after adjustment 2 is the grey line, never a red warning, and goes red only when it crosses again', async () => {
    const already = { kind: 'already_true', rule_id: 'R-stop', trigger_id: 'T-06', cmp: 'ge', value: '7.4600', threshold: '5.0000', reason: null,
      wording: { what_happened: 'Already true after adjustment 2.' }, condition: 'Loss as % of max loss: 7.46 % (rule 5 %)' }
    checks = [check({ results: [already] }), check({ results: [flag('9.10')] })]
    const w = await panel()
    expect(t(w, 'playbook-already-true').text()).toContain('Already true after adjustment 2')
    expect(t(w, 'playbook-flag').exists()).toBe(false)
    await tick()
    expect(t(w, 'playbook-already-true').exists()).toBe(false)
    expect(t(w, 'playbook-flag').exists()).toBe(true)
  })
})

describe('the plan card follows the live check', () => {
  it('(2) the limit line changes from "40 %" to the tightened "32.0 %...; tightened by 20 % today" between two refreshes', async () => {
    checks = [check(), check({ limits: [row('T-07', 'Target: profit of 32.0 % of max profit, before charges; tightened by 20 % today')], as_of_text: AS_OF_2 })]
    const w = await panel()
    expect(t(w, 'plan-entry-limit-T-07').text()).toBe('Target: profit of 40 % of max profit, before charges')
    await tick()
    expect(t(w, 'plan-entry-limit-T-07').text()).toBe('Target: profit of 32.0 % of max profit, before charges; tightened by 20 % today')
  })

  it('(5) the card and the warning show the check\'s own "As of" time, the server\'s text', async () => {
    checks = [check({ results: [flag('7.46')] }), check({ results: [flag('7.46')], as_of_text: AS_OF_2 })]
    const w = await panel()
    expect(t(w, 'plan-entry-limits-as-of').text()).toBe(AS_OF_1)
    expect(t(w, 'check-as-of').text()).toBe(AS_OF_1)
    await tick()
    expect(t(w, 'plan-entry-limits-as-of').text()).toBe(AS_OF_2)
    expect(t(w, 'check-as-of').text()).toBe(AS_OF_2)
  })

  it('(3) a failed re-read after a good one keeps the old lines, shows the could-not-refresh mark and the old time; (re-read ok again) clears it', async () => {
    checks = [check(), new Error('boom'), check({ limits: [row('T-07', 'Target: profit of 32.0 % of max profit, before charges')], as_of_text: AS_OF_2 })]
    const w = await panel()
    await tick()
    expect(t(w, 'plan-entry-limit-T-07').text()).toBe('Target: profit of 40 % of max profit, before charges')
    expect(t(w, 'plan-entry-limits-as-of').text()).toBe(AS_OF_1)
    expect(t(w, 'plan-entry-limits-stale').text()).toBe(CHECK_STALE_TEXT)
    expect(t(w, 'check-stale').text()).toBe(CHECK_STALE_TEXT)
    expect(t(w, 'plan-entry-limits-loading').exists()).toBe(false)
    expect(t(w, 'plan-entry-limits-error').exists()).toBe(false)
    await tick()
    expect(t(w, 'plan-entry-limits-stale').exists()).toBe(false)
    expect(t(w, 'check-stale').exists()).toBe(false)
    expect(t(w, 'plan-entry-limit-T-07').text()).toContain('32.0 %')
  })

  it('(4) a background re-read never flips the card to its loading state (nor blanks the lines while it is out)', async () => {
    checks = [check(), check({ as_of_text: AS_OF_2 })]
    const w = await panel()
    let release
    pending = new Promise((r) => { release = r })
    await tick()
    expect(checkCalls).toBe(2)
    expect(t(w, 'plan-entry-limits-loading').exists()).toBe(false)
    expect(t(w, 'plan-entry-limit-T-07').exists()).toBe(true)
    release()
    await flushPromises()
    expect(t(w, 'plan-entry-limits-as-of').text()).toBe(AS_OF_2)
  })

  it('first read ok shows the lines; first read fails keeps today\'s could-not-load with Retry (and the background re-read can recover it)', async () => {
    checks = [new Error('down'), check()]
    const w = await panel()
    expect(t(w, 'plan-entry-limits-error').exists()).toBe(true)
    expect(t(w, 'check-stale').exists()).toBe(false)
    await tick()
    expect(t(w, 'plan-entry-limits-error').exists()).toBe(false)
    expect(t(w, 'plan-entry-limit-T-07').exists()).toBe(true)
  })

  it('a reply without as_of_text (an older server): no time shown, no crash, lines still drawn', async () => {
    checks = [check({ as_of_text: undefined, as_of: undefined })]
    const w = await panel()
    expect(t(w, 'plan-entry-limits-as-of').exists()).toBe(false)
    expect(t(w, 'check-as-of').exists()).toBe(false)
    expect(t(w, 'plan-entry-limit-T-07').exists()).toBe(true)
  })

  it('a closed trade (every leg exited): the check is read once and not re-read, as before', async () => {
    TRACK = { ...TRACK, state: 'EXITED', legs: [] }
    checks = [check()]
    const w = await panel()
    await tick()
    await tick()
    if (t(w, 'tracking-view').exists()) expect(checkCalls).toBe(1)
  })
})

describe('the limit states a user can see', () => {
  it('stop not checked: the reason and no number', async () => {
    checks = [check({ limits: [row('T-06', 'Stop: not being checked: Max loss not finite (unlimited or multi-expiry).', 'not_checked', { threshold: null })] })]
    const w = await panel()
    expect(t(w, 'plan-entry-limit-T-06').text()).toBe('Stop: not being checked: Max loss not finite (unlimited or multi-expiry).')
  })

  it('stop already true after adjustment 2: the card line is grey and names the adjustment', async () => {
    const text = 'Stop: loss of 5 % of max loss (₹2,980.00). Already true after adjustment 2: alerts after it clears and crosses again'
    checks = [check({ limits: [row('T-06', text, 'already_true', { after: 2 })] })]
    const w = await panel()
    expect(t(w, 'plan-entry-limit-T-06').text()).toBe(text)
    expect(t(w, 'plan-entry-limit-T-06').classes()).toContain('text-ink-muted')
  })

  it('(5a) an emptied Target says no target is set for this trade, not that the trigger is switched off in the playbook', async () => {
    checks = [check({ limits: [row('T-07', 'Target: no target is set for this trade', 'not_checked', { threshold: null, reason_code: 'target_unset' })] })]
    const w = await panel()
    expect(t(w, 'plan-entry-limit-T-07').text()).toBe('Target: no target is set for this trade')
    expect(w.text()).not.toContain('switched off in this playbook')
  })

  it('paused: the server\'s paused sentence; a paused block without its text is could-not-load, never an object', async () => {
    checks = [check({ limits: [], paused: { until: '1030', text: 'Adjustment checks paused until 10:30.' } })]
    let w = await panel()
    expect(t(w, 'plan-entry-limits-paused').text()).toBe('Adjustment checks paused until 10:30.')
    mounted.splice(0).forEach((x) => x.unmount())
    checkCalls = 0
    checks = [check({ limits: [], paused: { until: '1030' } })]
    w = await panel()
    expect(t(w, 'plan-entry-limits-paused').exists()).toBe(false)
    expect(w.text()).not.toContain('[object Object]')
    expect(t(w, 'plan-entry-limits-error').exists()).toBe(true)
  })

  it('(5b) "No rules are being checked" only where the server says there is no playbook; any other empty list is could-not-load', async () => {
    checks = [check({ limits: [], playbook: { source: 'none', id: null, status: null, draft: false } })]
    let w = await panel()
    expect(t(w, 'plan-entry-limits-none').exists()).toBe(true)
    mounted.splice(0).forEach((x) => x.unmount())
    checkCalls = 0
    checks = [check({ limits: [] })]
    w = await panel()
    expect(t(w, 'plan-entry-limits-none').exists()).toBe(false)
    expect(t(w, 'plan-entry-limits-error').exists()).toBe(true)
  })
})

describe('PlanEntry alone (a parent that passes no stale mark)', () => {
  it('draws its lines and no mark', async () => {
    const w = mount(PlanEntry, { props: { strategyId: 7, check: check(), checkStatus: 'ok' } })
    mounted.push(w)
    await flushPromises()
    expect(t(w, 'plan-entry-limit-T-07').exists()).toBe(true)
    expect(t(w, 'plan-entry-limits-stale').exists()).toBe(false)
  })
})
