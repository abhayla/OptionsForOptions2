// Lane FC3 (28 Nov 2026), screens of the plan: the tracking panel's rule line, a real trade's exits, the margin "Checked at",
// Plan watch on a closed trade and with the feed paused, the monitoring badge's date. Spec basis: ADR-330 (56), (58); REQ-115; ADR-003.
// Real cases: UX-SW6 builder #209 (17 identical "Rule not checked" lines), UX-B13 ("Checked at Time not available"), UX-A06/A09 (Plan watch
// "not available"), issue #880 ("since 10:12" with no day).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const calls = []
let CHECK = null
let REAL = { triggers: [] }
const answer = (url) => {
  calls.push(url)
  if (url === '/strategies/7/tracking') return Promise.resolve({ data: { strategy_id: 7, state: 'LIVE', paper_pnl: '195.00', paper_pnl_text: '+195.00', as_of: null, legs: [], detections: [] } })
  if (url === '/strategies/7/adjustment-check') return Promise.resolve({ data: CHECK })
  if (url === '/paper/strategies/7/triggers') return Promise.resolve({ data: { triggers: [] } })
  if (url === '/real/strategies/7/triggers') return REAL instanceof Error ? Promise.reject(REAL) : Promise.resolve({ data: REAL })
  if (url === '/strategies/7/plan-watch') return Promise.reject({ status: 500, parts: null })
  return Promise.reject({ status: 404, parts: null })
}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (u) => answer(u), post: (u) => answer(u), put: (u) => answer(u) } }
})
import TrackingPanel from '@/components/strategy/TrackingPanel.vue'
import MarginLine from '@/components/strategy/MarginLine.vue'
import PlanWatch from '@/components/strategy/PlanWatch.vue'
import MonitoringBadge from '@/components/common/MonitoringBadge.vue'
import { resetPlanWatchQueueForTests } from '@/lib/planWatchQueue'

const STALE = 'No adjustment opportunity checked: prices stale or missing'
const nc = (i, reason = STALE) => ({ kind: 'not_checked', rule_id: `R-${i}`, trigger_id: `T-${i}`, cmp: null, value: null, threshold: null, reason,
  wording: null, condition: null, stop_text: null, fired_at: null })
const check = (results) => ({ strategy_id: 7, as_of: '2026-11-13T08:45:00Z', as_of_text: 'As of 14:15:00 IST', strategy_type: 'ic', type_name: 'Iron condor',
  playbook: { source: 'system', id: 1, status: null, draft: false }, stage: { name: null, index: null }, withheld: null, results, limits: [], paused: null })
const t = (w, id) => w.find(`[data-testid="${id}"]`)
const all = (w, id) => w.findAll(`[data-testid="${id}"]`)
const mounted = []
async function panel(results, props = {}) {
  CHECK = check(results)
  const w = mount(TrackingPanel, { props: { savedId: 7, legs: [], ...props } })
  mounted.push(w)
  await flushPromises()
  return w
}
beforeEach(() => { REAL = { triggers: [] }; calls.length = 0; resetPlanWatchQueueForTests() })
afterEach(() => { mounted.splice(0).forEach((w) => w.unmount()) })

describe('UX-SW6: the rules not checked, one line per reason', () => {
  it('17 rules with one reason: one line with the count and the reason; the 17 behind an expand', async () => {
    const w = await panel(Array.from({ length: 17 }, (_, i) => nc(i)))
    expect(all(w, 'rules-not-checked')).toHaveLength(0)
    expect(all(w, 'rules-not-checked-group')).toHaveLength(1)
    expect(t(w, 'rules-not-checked-group').text()).toContain(`17 rules not checked: ${STALE}`)
    expect(all(w, 'rules-not-checked-item')).toHaveLength(17)
    expect(t(w, 'rules-not-checked-list').element.tagName).toBe('DETAILS') // the list is behind an expand
  })
  it('mixed reasons: grouped by reason; a reason with one rule keeps the one-rule sentence', async () => {
    const rs = [...[0, 1, 2].map((i) => nc(i)), ...[3, 4].map((i) => nc(i, 'The index price is missing.')), nc(5, 'Greeks are not read yet.')]
    const w = await panel(rs)
    const groups = all(w, 'rules-not-checked-group').map((g) => g.find('[data-testid="rules-not-checked-summary"]').text())
    expect(groups).toEqual([`3 rules not checked: ${STALE}`, '2 rules not checked: The index price is missing.'])
    expect(all(w, 'rules-not-checked').map((n) => n.text())).toEqual(['Rule not checked: Greeks are not read yet.'])
  })
  it('two rules, one reason: still one line with the count 2', async () => {
    const w = await panel([nc(0), nc(1)])
    expect(t(w, 'rules-not-checked-summary').text()).toBe(`2 rules not checked: ${STALE}`)
  })
  it('one rule: the one-rule sentence, no group', async () => {
    const w = await panel([nc(0)])
    expect(t(w, 'rules-not-checked').text()).toBe(`Rule not checked: ${STALE}`)
    expect(all(w, 'rules-not-checked-group')).toHaveLength(0)
  })
})

describe('item 2: a real trade never calls the paper exits route and never says "none"', () => {
  it('tradeMode real: reads the REAL route (never the paper one) and prints its armed exit', async () => {
    REAL = { triggers: [{ id: 31, strategy_id: 7, kind: 'conditional_exit', direction: 'above', level_text: '25,720', state: 'armed' }] }
    const w = await panel([], { tradeMode: 'real' })
    expect(calls).toContain('/real/strategies/7/triggers')
    expect(calls).not.toContain('/paper/strategies/7/triggers')
    expect(t(w, 'plan-entry-exit-31').text()).toContain('25,720')
    expect(t(w, 'plan-entry-exits-real-unreadable').exists()).toBe(false)
  })
  it('tradeMode real, an empty answer: nothing printed about exits; the sentence is not shown', async () => {
    const w = await panel([], { tradeMode: 'real' })
    expect(t(w, 'plan-entry-exits-real-unreadable').exists()).toBe(false)
  })
  it('tradeMode real, the read fails: the sentence "cannot be read here yet", never "none"', async () => {
    REAL = Object.assign(new Error('x'), { status: 500, parts: null })
    const w = await panel([], { tradeMode: 'real' })
    expect(t(w, 'plan-entry-exits-real-unreadable').text()).toBe('Exits of a real-mode trade cannot be read here yet.')
  })
  it('paper (the default): the paper route is read, no real-mode line', async () => {
    const w = await panel([])
    expect(calls).toContain('/paper/strategies/7/triggers')
    expect(t(w, 'plan-entry-exits-real-unreadable').exists()).toBe(false)
  })
})

describe('UX-B13: no "Checked at" line when the time cannot be read', () => {
  const MARGIN = (checked_at) => ({ state: 'CHECKED', needed: '7065.50', available: '671.50', reason: 'ok', checked_at, shortfall: false })
  const hint = async (w) => {
    const h = w.find('[data-testid="figure-hint"][data-figure="margin_available"]')
    await h.find('[data-testid="figure-hint-mark"]').trigger('click')
    return h.find('[data-testid="figure-hint-text"]').text()
  }
  it('a readable time keeps the line', async () => {
    const w = mount(MarginLine, { props: { margin: MARGIN('2026-10-16T06:38:52Z'), capabilities: { basket_margin_quote: true } } })
    expect(await hint(w)).toContain('Checked at 16 Oct 2026, 12:08:52 IST')
  })
  it('an unreadable time prints no "Checked at" and never "Time not available"', async () => {
    const w = mount(MarginLine, { props: { margin: MARGIN('not a time'), capabilities: { basket_margin_quote: true } } })
    const text = await hint(w)
    expect(text).not.toContain('Checked at')
    expect(text).not.toContain('Time not available')
  })
})

describe('UX-A06 / UX-A09: Plan watch on a closed trade and with the feed paused', () => {
  it('a closed trade: the calm fact, nothing is read', async () => {
    const w = mount(PlanWatch, { props: { strategyId: 7, closed: true } })
    mounted.push(w)
    await flushPromises()
    expect(w.find('[data-testid="plan-watch"]').exists()).toBe(false) // F2 (W-29 step 57, ADR-330 (57)): no box, no sentence
    expect(calls).not.toContain('/strategies/7/plan-watch')
  })
  it('the read failed while prices are paused: prices are not live and the check resumes with them, not an error', async () => {
    const w = mount(PlanWatch, { props: { strategyId: 7, stale: true } })
    mounted.push(w)
    await flushPromises()
    expect(t(w, 'plan-watch-message').text()).toBe('The plan watch is paused while the feed has no live prices. It resumes with them.')
    expect(w.text()).not.toContain('not available')
  })
  it('the read failed with prices live: the old sentence stays', async () => {
    const w = mount(PlanWatch, { props: { strategyId: 7 } })
    mounted.push(w)
    await flushPromises()
    expect(t(w, 'plan-watch-message').text()).toContain('not available')
  })
})

describe('Lane FB: no loading line while the builder outcome is loading', () => {
  it('outcomeLoading hides the first-read loading line; without it the line stays', async () => {
    const a = mount(PlanWatch, { props: { strategyId: 7, view: null, outcomeLoading: true } })
    const b = mount(PlanWatch, { props: { strategyId: 7, view: null } })
    mounted.push(a, b)
    await flushPromises()
    expect(t(a, 'plan-watch-loading').exists()).toBe(false)
    expect(t(b, 'plan-watch-loading').text()).toBe('Loading the rule check...')
  })
})

describe('issue #880: the monitoring badge names the day when it is not today', () => {
  const entry = (since_at) => ({ strategy_id: 7, watch_state: 'paused', reason: 'workers_down', badge_text: 'Monitoring paused', health_text: 'Health unknown',
    reason_text: 'Not being watched: no worker has reported in the last 2 minutes.', since_text: 'Since 10:12', since_at })
  const nowIso = () => new Date().toISOString()
  it('since an earlier day: the date comes with the time', () => {
    const w = mount(MonitoringBadge, { props: { entry: entry('2026-11-20T04:42:00Z') } })
    expect(t(w, 'monitoring-since').text()).toBe('Since 10:12, 20 Nov 2026')
  })
  it('since today: the server sentence untouched', () => {
    const w = mount(MonitoringBadge, { props: { entry: entry(nowIso()) } })
    expect(t(w, 'monitoring-since').text()).toBe('Since 10:12')
  })
  it('since_at missing or unreadable: the server sentence untouched', () => {
    expect(t(mount(MonitoringBadge, { props: { entry: entry(null) } }), 'monitoring-since').text()).toBe('Since 10:12')
    expect(t(mount(MonitoringBadge, { props: { entry: entry('garbage') } }), 'monitoring-since').text()).toBe('Since 10:12')
  })
  it('the FD2 entry: expiry_kind_unknown prints its badge and reason with no code change', () => {
    const e = { strategy_id: 41, watch_state: 'paused', reason: 'expiry_kind_unknown', badge_text: 'Monitoring paused', health_text: 'Health unknown',
      reason_text: 'Every exit rule is not checked because whether this trade expires weekly or monthly is not known.', since_text: null }
    const w = mount(MonitoringBadge, { props: { entry: e } })
    expect(t(w, 'monitoring-paused').text()).toContain('Monitoring paused')
    expect(t(w, 'monitoring-reason').text()).toBe(e.reason_text)
  })
})
