// ADR-247 (replaces GC-MU A4's browser table): the stops are worded once, by the server (settings_in_force.stops_of ->
// `stop_words` on GET /api/strategies/{id}/adjustment-plan). The browser shows that text and never builds it from the
// playbook body's guards; the editor's draft preview leaves the stop out.
import { describe, it, expect, vi } from 'vitest'

// the card reads its plan itself (GC-ICFIX u112): the reply below is what the mocked read answers
vi.mock('@/services/api', () => ({ default: { get: () => Promise.resolve({ data: globalThis.__PLAN_REPLY }) } }))
import { mount, flushPromises } from '@vue/test-utils'
import { planLine, summaryLines, labelMaps } from '../src/lib/playbookEditor.js'
import { readPlan } from '../src/lib/adjustPlan.js'
import PlanEntry from '../src/components/strategy/PlanEntry.vue'
import LABELS from './fixtures/playbook-labels.json'

const SERVER_WORDS = '50 % of max loss or 2x the credit received, whichever comes first'
const t = labelMaps(LABELS).summary
const BODY = { stages: [], looks: [], rules: [], day_rules: [], approaches: { applicable: [] } }
const REPLY = {
  strategy_id: 70, type: 'ic', type_name: 'Iron condor', generic: false, generic_text: null, prefill: { playbook_id: 9 },
  playbooks: [{ id: 9, name: 'Mine', type: 'ic', type_name: 'Iron condor', is_system: false, draft: false, active: true }],
  labels: { plan_entry: 'Plan', playbook: 'Playbook', target: 'Target', stop: 'Stop', max_adjustments: 'Max', time_exit: 'Exit', edit: 'Edit', no_plan: 'none' },
  plan: { playbook_id: 9, playbook_name: 'Mine', target: '50', stop: '50', stop_words: SERVER_WORDS, max_adjustments: 2, time_exit: null },
}

describe('the plan stop line is the server words, never a browser reading of the guards', () => {
  it('the card words each stop once, from the rule check\'s rows; the plan\'s own stop words are not repeated beside them', async () => {
    globalThis.__PLAN_REPLY = REPLY
    const limits = [{ rule_id: 'T-06', text: 'Stop: loss of 50 % of max loss (₹11,948.52)', state: 'checked' },
      { rule_id: 'credit_stop', text: 'Stop: loss of 2 x credit (₹17,836.00), whichever comes first', state: 'checked' }]
    const w = mount(PlanEntry, { props: { strategyId: 70, checkStatus: 'ok', check: { limits, paused: null, playbook: { source: 'plan' } } },
      global: { stubs: { AdjustPlanSheet: true } } })
    await flushPromises()
    expect(w.text()).toContain('Stop: loss of 2 x credit (₹17,836.00), whichever comes first')
    expect(w.text()).not.toContain(SERVER_WORDS)
    // the editor's preview of a body holding only a max-loss guard words no stop of its own
    const body = { ...BODY, guards: { stop_line_pct_of_max_loss: '50' } }
    expect(summaryLines(body, 'Iron condor', 'monthly', labelMaps(LABELS)).find((l) => l.key === 'plan')).toBeUndefined()
    expect(planLine(body.guards, t)).toEqual([])
  })
  it('no stop words in the reply: nothing is invented', () => {
    const r = readPlan({ ...REPLY, plan: { playbook_id: 9, stop: '50' } })
    expect(r.plan.stopWords).toBe('')
  })
  it('the editor preview never words a stop, whatever the guards hold', () => {
    for (const g of [{ stop_line_pct_of_margin: '20' }, { stop_line_pct_of_max_loss: '50', stop_line_pct_of_margin: '20' },
      { stop_line_pct_of_max_loss: '50', stop_line_rule: 'whichever comes first' }]) {
      expect(planLine({ ...g, max_adjustments: 2 }, t)[0].text).toBe('Plan: at most 2 adjustments.')
    }
  })
})
