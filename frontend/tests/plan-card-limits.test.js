// GC-ICFIX u113 round 3, slice 2 (ADR-304 (3), ADR-295, ADR-296): the plan card's limit lines are the rule check's own `limits`
// rows (`text` is the server's sentence); the browser derives nothing. Rows below are the real ones from the evaluator
// (tests_app/test_limits_now.py): iron condor weekly early stage, T-06 off, strangle expiry day 13:00, unlimited max loss,
// a not_checked row that still carries numbers, already_true.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

let planReply = null
const calls = []
vi.mock('@/services/api', () => ({ default: { get: (u) => { calls.push(u); return Promise.resolve({ data: planReply }) } } }))
import PlanEntry from '@/components/strategy/PlanEntry.vue'

const LABELS = { plan_entry: 'Plan', playbook: 'Playbook', target: 'Target', stop: 'Stop', max_adjustments: 'Max adjustments', time_exit: 'Time exit',
  edit: 'Edit plan', no_plan: 'No plan saved yet: default rules apply', set_plan: 'Set plan' }
const PLAN = { playbook_id: 9, playbook_name: '"Mine"', target: '50', stop: '50', stop_words: '50 % of max loss or 2x the credit received, whichever comes first',
  max_adjustments: 3, time_exit: { hour: 14, minute: 45 } }
const reply = (plan) => ({ strategy_id: 70, type: 'ic', type_name: 'Iron condor', generic: false, generic_text: null, labels: LABELS, plan,
  playbooks: [{ id: 9, name: 'Mine', type: 'ic', type_name: 'Iron condor', is_system: false, draft: false, active: true }], prefill: { playbook_id: 9 } })

const T07 = 'Target: profit of 50 % of max profit, before charges; 80 % nearer expiry'
const T06 = 'Stop: loss of 50 % of max loss (₹11,948.52); 40 % nearer expiry'
const CREDIT = 'Stop: loss of 2 x credit (₹17,836.00), whichever comes first'
const row = (rule_id, text, state = 'checked', over = {}) => ({ rule_id, trigger_id: rule_id, threshold: '50.0000', amount: null, later: [], tightened_by: null,
  state, reason: null, text, ...over })
const check = (limits, over = {}) => ({ strategy_id: 70, strategy_type: 'ic', playbook: { source: 'system', id: 1, status: null, draft: false },
  results: [], limits, paused: null, ...over })
const IC_ROWS = [row('T-07', T07), row('T-06', T06), row('credit_stop', CREDIT)]

const mounted = []
afterEach(() => { mounted.splice(0).forEach((w) => w.unmount()) })
beforeEach(() => { calls.length = 0; planReply = reply(null) })
const t = (w, id) => w.find(`[data-testid="${id}"]`)
async function card(props = {}, plan = null) {
  planReply = reply(plan)
  const w = mount(PlanEntry, { attachTo: document.body, props: { strategyId: 70, ...props } })
  await flushPromises()
  mounted.push(w)
  return w
}
const lines = (w) => w.findAll('[data-testid^="plan-entry-limit-"]').map((x) => x.text())

describe('the no-plan card: the rule check\'s own limit lines, nothing derived in the browser', () => {
  it('iron condor early stage: the server sentences in order, "No plan saved yet", Set plan', async () => {
    const w = await card({ check: check(IC_ROWS), checkStatus: 'ok' })
    expect(t(w, 'plan-entry-none').text()).toBe('No plan saved yet: default rules apply')
    expect(lines(w)).toEqual([T07, T06, CREDIT])
    expect(t(w, 'plan-entry-edit').text()).toBe('Set plan')
  })

  it('the card never prints a number the rows do not carry (the plan read holds no rules block any more)', async () => {
    const w = await card({ check: check([row('T-07', 'Target: profit of 64 % of max profit, before charges; tightened by 20 % today')]), checkStatus: 'ok' })
    expect(w.text()).toContain('64 %')
    expect(w.text()).not.toContain('50 % of max profit')
  })

  it('T-06 off: the percent stop says why it is not checked, and the credit stop stands alone', async () => {
    const off = row('T-06', 'Stop: not being checked: The stop value saved in the playbook cannot be read.', 'not_checked', { threshold: null })
    const w = await card({ check: check([row('T-07', T07), off, row('credit_stop', 'Stop: loss of 2 x credit (₹17,836.00)')]), checkStatus: 'ok' })
    expect(lines(w)[1]).toBe('Stop: not being checked: The stop value saved in the playbook cannot be read.')
    expect(lines(w)[2]).not.toContain('whichever')
  })

  it('a not_checked row that still carries numbers: the card shows the sentence (the reason), never the 50 / 11948.52', async () => {
    const bad = row('T-06', 'Stop: not being checked: The leg prices do not fit together.', 'not_checked', { threshold: '50.0000', amount: '11948.52', reason: { what_happened: 'x' } })
    const w = await card({ check: check([bad]), checkStatus: 'ok' })
    expect(lines(w)).toEqual(['Stop: not being checked: The leg prices do not fit together.'])
    expect(w.text()).not.toContain('11948.52')
    expect(w.text()).not.toContain('11,948')
  })

  it('unlimited max loss: Stop not being checked with its reason', async () => {
    const w = await card({ check: check([row('T-07', 'Target: profit of 80 % of max profit, before charges'),
      row('T-06', 'Stop: not being checked: Max loss not finite (unlimited or multi-expiry).', 'not_checked', { threshold: null })]), checkStatus: 'ok' })
    expect(lines(w)[1]).toBe('Stop: not being checked: Max loss not finite (unlimited or multi-expiry).')
  })

  it('already_true: the line stays, grey, with no red warning', async () => {
    const txt = 'Target: profit of 50 % of max profit, before charges. Already true: alerts after it clears and crosses again'
    const w = await card({ check: check([row('T-07', txt, 'already_true')]), checkStatus: 'ok' })
    const el = t(w, 'plan-entry-limit-T-07')
    expect(el.text()).toBe(txt)
    expect(el.classes()).toContain('text-ink-muted')
    expect(el.classes().join(' ')).not.toMatch(/red|danger|warn/)
  })
})

describe('the plan-present card: its content with the limit lines in place of Target / Stop', () => {
  it('shows playbook, the limit lines, then Max adjustments and Time exit; the plan\'s own stop words are not repeated', async () => {
    const w = await card({ check: check(IC_ROWS), checkStatus: 'ok' }, PLAN)
    expect(t(w, 'plan-entry-playbook').text()).toBe('Playbook: "Mine"')
    expect(lines(w)).toEqual([T07, T06, CREDIT])
    expect(t(w, 'plan-entry-guards').text()).toBe('Max adjustments: 3 / Time exit: 14:45')
    expect(w.text()).not.toContain('2x the credit received')
    expect(t(w, 'plan-entry-edit').text()).toBe('Edit plan')
  })
})

describe('every answer state of the check read has a visible result', () => {
  it('not yet read: says loading, no numbers', async () => {
    const w = await card({ check: null, checkStatus: 'loading' })
    expect(t(w, 'plan-entry-limits-loading').exists()).toBe(true)
    expect(lines(w)).toEqual([])
  })

  it('read failed: could-not-load with Retry, never stale numbers; Retry asks the owner of the read', async () => {
    const w = await card({ check: check(IC_ROWS), checkStatus: 'failed' })
    expect(t(w, 'plan-entry-limits-error').exists()).toBe(true)
    expect(t(w, 'plan-entry-limits-retry').text()).toBe('Retry')
    expect(lines(w)).toEqual([])
    expect(w.text()).not.toContain('50 % of')
    await t(w, 'plan-entry-limits-retry').trigger('click')
    expect(w.emitted('retry-check')).toHaveLength(1)
  })

  it('an ok status with no reply is also could-not-load', async () => {
    const w = await card({ check: null, checkStatus: 'ok' })
    expect(t(w, 'plan-entry-limits-error').exists()).toBe(true)
  })

  it('limits empty and paused: the check\'s own paused words, no numbers', async () => {
    const w = await card({ check: check([], { paused: { until: '1030', text: 'Adjustment checks paused until 10:30.' } }), checkStatus: 'ok' })
    expect(t(w, 'plan-entry-limits-paused').text()).toBe('Adjustment checks paused until 10:30.')
    expect(lines(w)).toEqual([])
  })

  it('limits empty and no playbook: says no rules are being checked', async () => {
    const w = await card({ check: check([], { playbook: { source: 'none', id: null, status: null, draft: false } }), checkStatus: 'ok' })
    expect(t(w, 'plan-entry-limits-none').text()).toBe('No rules are being checked for this trade')
  })

  it('a row with an unknown state fails closed for that line only', async () => {
    const w = await card({ check: check([row('T-07', T07), row('T-06', T06, 'weird')]), checkStatus: 'ok' })
    expect(lines(w)[0]).toBe(T07)
    expect(t(w, 'plan-entry-limit-T-06-error').exists()).toBe(true)
    expect(w.text()).not.toContain('11,948.52')
  })

  it('a row without its sentence fails closed the same way', async () => {
    const w = await card({ check: check([row('T-07', null)]), checkStatus: 'ok' })
    expect(t(w, 'plan-entry-limit-T-07-error').exists()).toBe(true)
  })

  it('the card reads the plan once and never asks for the check itself (one read, owned by the panel)', async () => {
    await card({ check: check(IC_ROWS), checkStatus: 'ok' })
    expect(calls).toEqual(['/strategies/70/adjustment-plan'])
  })
})
