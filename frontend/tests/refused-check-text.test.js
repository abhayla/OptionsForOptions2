// GC-ICFIX screen defect (ADR-003, REQ-109 AC-5): prices stale -> the trade page printed the server's whole error object
// (`{ "error_class": ..., "code": "USER_INPUT_149", ...}`) and, later, the generic "Something went wrong". A refusal shows the
// server's own sentence once; a failure with no usable body shows the existing could-not-load / could-not-refresh state.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

let checks = [] // successive answers of GET .../adjustment-check: a value, or {reject: <axios-shaped error>}
let checkCalls = 0
let trackAnswer = null // when set, the tracking read answers with it (a value or {reject})
const answer = (url) => {
  const out = (a) => (a && a.reject ? Promise.reject(mapError(a.reject)) : Promise.resolve({ data: a }))
  if (url === '/strategies/7/tracking') return out(trackAnswer ?? TRACK)
  if (url === '/strategies/7/adjustment-check') { const a = checks[Math.min(checkCalls, checks.length - 1)]; checkCalls += 1; return out(a) }
  if (url.startsWith('/strategies/7/adjustment-plan')) return Promise.resolve({ data: PLAN })
  if (url === '/strategies/7/adjustment-history') return out(trackAnswer)
  return Promise.reject({ status: 404, parts: null })
}
const holder = vi.hoisted(() => ({ mapError: null }))
const mapError = (e) => holder.mapError(e)
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  holder.mapError = actual.mapError
  return { ...actual, default: { get: (u) => answer(u), post: (u) => answer(u), put: (u) => answer(u) } }
})
import TrackingPanel from '@/components/strategy/TrackingPanel.vue'
import AdjustSteps from '@/components/strategy/AdjustSteps.vue'
import { TRACKING_REFRESH_MS } from '@/lib/tracking'
import { CHECK_STALE_TEXT, LIMITS_LOAD_FAILED_TEXT } from '@/lib/sharedStateText'
import { NEUTRAL_PARTS } from '@/services/api'

const TRACK = { strategy_id: 7, state: 'LIVE', paper_pnl: '195.00', paper_pnl_text: '+195.00', as_of: null, legs: [], detections: [] }
const LABELS = { plan_entry: 'Plan', playbook: 'Playbook', target: 'Target', stop: 'Stop', max_adjustments: 'Max adjustments', time_exit: 'Time exit',
  edit: 'Edit plan', no_plan: 'No plan saved yet: default rules apply', set_plan: 'Set plan' }
const PLAN = { strategy_id: 7, type: 'ic', type_name: 'Iron condor', generic: false, generic_text: null, labels: LABELS, plan: null,
  playbooks: [{ id: 9, name: 'Mine', type: 'ic', type_name: 'Iron condor', is_system: false, draft: false, active: true }], prefill: { playbook_id: 9 } }

const SENTENCE = 'No adjustment opportunity checked: prices stale or missing.'
const BODY = { error_class: 'USER_INPUT', code: 'USER_INPUT_149', what_happened: SENTENCE,
  impact: 'No rule was checked, so no adjustment is offered.', what_is_blocked: 'The rule check.', next_action: 'Wait for live prices.' }
const refused = (data = BODY) => ({ reject: { response: { status: 409, data } } })
const row = (rule_id, text, state = 'checked') => ({ rule_id, trigger_id: rule_id, threshold: null, amount: null, later: [], tightened_by: null, state, reason: null,
  text, after: null, reason_code: null })
const check = (over = {}) => ({ strategy_id: 7, as_of: '2026-11-13T07:35:00Z', as_of_text: 'As of 01:05:00 PM IST', strategy_type: 'ic', type_name: 'Iron condor',
  playbook: { source: 'system', id: 1, status: null, draft: false }, stage: { name: null, index: null }, withheld: null, results: [],
  limits: [row('T-07', 'Target: profit of 40 % of max profit, before charges')], paused: null, ...over })
const NEVER = ['error_class', 'USER_INPUT_149', '{', '[object Object]', 'Something went wrong']

const mounted = []
const t = (w, id) => w.find(`[data-testid="${id}"]`)
async function panel() {
  const w = mount(TrackingPanel, { props: { savedId: 7, legs: [] } })
  mounted.push(w)
  await flushPromises()
  return w
}
const noRaw = (w) => NEVER.forEach((s) => expect(w.text()).not.toContain(s))
beforeEach(() => { vi.useFakeTimers(); checks = []; checkCalls = 0; trackAnswer = null })
afterEach(() => { mounted.splice(0).forEach((w) => w.unmount()); vi.useRealTimers() })

describe('a refused rule check shows the server\'s sentence, never the object', () => {
  it('(1) a 200 check whose withheld note is the error object (prices stale): the page shows the sentence only', async () => {
    checks = [check({ withheld: BODY, limits: [row('T-07', 'Target: not being checked: prices stale or missing.', 'not_checked')] })]
    const w = await panel()
    expect(t(w, 'check-withheld').text()).toBe(SENTENCE)
    noRaw(w)
    expect(t(w, 'plan-entry-limit-T-07').text()).toBe('Target: not being checked: prices stale or missing.') // (4) the plan card
  })

  it('(1b) a withheld object with no usable sentence prints nothing, never the object', async () => {
    checks = [check({ withheld: { code: 'USER_INPUT_149' } })]
    const w = await panel()
    expect(t(w, 'check-withheld').exists()).toBe(false)
    noRaw(w)
  })

  it('(2) the FIRST check read refused (409 + body): the plan card says the server\'s sentence, not could-not-load, no raw text', async () => {
    checks = [refused()]
    const w = await panel()
    expect(t(w, 'plan-entry-limits-refused').text()).toBe(SENTENCE)
    expect(w.text()).not.toContain(LIMITS_LOAD_FAILED_TEXT)
    noRaw(w)
  })

  it('(3) a background re-read refused after a good read: last lines stay; ONE mark = could-not-refresh + the sentence', async () => {
    checks = [check(), refused()]
    const w = await panel()
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    expect(t(w, 'plan-entry-limit-T-07').text()).toBe('Target: profit of 40 % of max profit, before charges')
    expect(t(w, 'check-stale').text()).toBe(`${CHECK_STALE_TEXT} ${SENTENCE}`)
    expect(t(w, 'plan-entry-limits-stale').text()).toBe(`${CHECK_STALE_TEXT} ${SENTENCE}`)
    expect(w.findAll('[data-testid="check-stale"]').length).toBe(1)
    noRaw(w)
  })

  it('(5) a refusal with an empty or malformed body is the could-not-load state, no raw text', async () => {
    for (const data of ['', null, '<html>502</html>', { detail: 'x' }]) {
      checkCalls = 0
      checks = [refused(data)]
      const w = await panel()
      expect(t(w, 'plan-entry-limits-error').text()).toBe(LIMITS_LOAD_FAILED_TEXT)
      expect(t(w, 'plan-entry-limits-refused').exists()).toBe(false)
      noRaw(w)
      w.unmount(); mounted.pop()
    }
  })
})

describe('the other reads on the trade page never say "Something went wrong"', () => {
  it('(6a) the tracking read timing out (no body): the existing could-not-get-an-answer sentence', async () => {
    trackAnswer = { reject: { code: 'ECONNABORTED' } }
    const w = await panel()
    expect(t(w, 'tracking-error').text()).toBe(NEUTRAL_PARTS.what_happened)
    noRaw(w)
  })

  it('(6a2) the tracking read refused with the server\'s sentence shows that sentence', async () => {
    trackAnswer = refused()
    const w = await panel()
    expect(t(w, 'tracking-error').text()).toBe(SENTENCE)
    noRaw(w)
  })

  it('(6b) the adjustment history read with no body: the same sentence', async () => {
    trackAnswer = { reject: { code: 'ECONNABORTED' } }
    const w = mount(AdjustSteps, { props: { strategyId: 7 } })
    mounted.push(w)
    const d = w.find('details')
    d.element.open = true
    await d.trigger('toggle')
    await flushPromises()
    expect(t(w, 'steps-error').text()).toBe(NEUTRAL_PARTS.what_happened)
  })
})
