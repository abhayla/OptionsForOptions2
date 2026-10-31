// GC-MU A4 (ADR-230 (4)): the browser plan line and the summary read the same expectation table as the server test
// (tests_app/test_two_stops_words.py): two stops with no combining rule show both values.
import { describe, it, expect } from 'vitest'
import { planLine, summaryLines, labelMaps } from '../src/lib/playbookEditor.js'
import LABELS from './fixtures/playbook-labels.json'
import TABLE from '../../tests/fixtures/stop_words_cases.json'

const t = labelMaps(LABELS).summary
const BODY = { stages: [], looks: [], rules: [], day_rules: [], approaches: { applicable: [] } }

describe('two stops: plan line and summary agree with the server table', () => {
  for (const c of TABLE.cases) {
    it(c.name, () => {
      const line = planLine(c.guards, t)
      if (c.expect === null) { expect(line).toEqual([]); return }
      expect(line[0].text).toBe(`Plan: stop at ${TABLE[c.expect]}.`)
    })
  }
  it('the summary shows both values when the rule is absent', () => {
    const lines = summaryLines({ ...BODY, guards: TABLE.cases[0].guards }, 'Iron condor', 'monthly', labelMaps(LABELS))
    expect(lines.find((l) => l.key === 'plan').text).toBe(`Plan: stop at ${TABLE.either}.`)
  })
})
