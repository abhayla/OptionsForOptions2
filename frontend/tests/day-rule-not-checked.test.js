// GC-IC1 step 10 fix (REQ-159 AC-4): a switched-on day rule whose (kind, action) pair is not in the server's acting list
// is shown as "not checked" with the server's reason, in the plan sheet summary; the browser holds no list of its own.
import { describe, expect, it } from 'vitest'
import { dayRuleNotChecked, labelMaps, summaryLines } from '../src/lib/playbookEditor.js'
import LABELS from './fixtures/playbook-labels.json'

const WHY = 'This day rule is saved and shown, but it is not checked yet.'
const ANSWER = {
  ...LABELS,
  day_acting: [{ when: 'expiry', action: 5 }, { when: 'beforeWeekend', action: 0 }],
  day_not_checked: { what_happened: WHY },
}
const maps = labelMaps(ANSWER)
// The route answer carries the acting list now; "no list loaded" is that same answer without the two keys.
const { day_acting: _acting, day_not_checked: _why, ...NO_LIST } = LABELS

describe('day rules that are not checked', () => {
  it('a switched-on rule outside the acting list carries the server reason; others do not', () => {
    expect(dayRuleNotChecked({ on: true, when: 'afterBreak', action: 2 }, maps)).toBe(WHY)
    expect(dayRuleNotChecked({ on: true, when: 'expiry', action: 5 }, maps)).toBe('')
    expect(dayRuleNotChecked({ on: false, when: 'afterBreak', action: 2 }, maps)).toBe('')
  })

  it('no acting list loaded: nothing is guessed in the browser', () => {
    expect(dayRuleNotChecked({ on: true, when: 'afterBreak', action: 2 }, labelMaps(NO_LIST))).toBe('')
  })

  it('the plan sheet summary marks the not-checked rule with the reason', () => {
    const body = { day_rules: [{ on: true, when: 'afterBreak', at: '09:30', action: 2 }, { on: true, when: 'expiry', at: '14:30', action: 5 }] }
    const days = summaryLines(body, 'Iron condor', 'monthly', maps).find((l) => l.key === 'days').items
    expect(days[0]).toContain(`(${WHY})`)
    expect(days[1]).not.toContain(WHY)
  })
})
