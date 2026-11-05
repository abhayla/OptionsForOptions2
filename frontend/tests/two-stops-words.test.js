// ADR-247 (replaces GC-MU A4's browser table): the stops are worded once, by the server (settings_in_force.stops_of ->
// `stop_words` on GET /api/strategies/{id}/adjustment-plan). The browser shows that text and never builds it from the
// playbook body's guards; the editor's draft preview leaves the stop out.
import { describe, it, expect } from 'vitest'
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
  it('a reply with stop_words and a body with only a max-loss guard shows the server words', async () => {
    const w = mount(PlanEntry, { props: { strategyId: 70 }, global: { stubs: { AdjustPlanSheet: true } } })
    w.vm.read = readPlan(REPLY)
    await flushPromises()
    expect(w.get('[data-testid=plan-entry-guards]').text()).toContain(SERVER_WORDS)
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
