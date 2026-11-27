// Lane R (27 Nov 2026, AX-14): a server catalogue text field (CatalogueText) is a sentence, null or an error object. The one helper
// (lib/serverText) and the readers that use it: lib/planWatch (reason, label, as_of_text, ...), lib/playbookEditor `said`
// (the adjustment-check reader; used by TrackingPanel and sharedStateText). AdjustSteps is covered in adjust-steps.test.js.
import { describe, it, expect, vi } from 'vitest'

vi.mock('@/services/api', async (importActual) => ({ ...(await importActual()), default: { get: () => Promise.resolve({ data: globalThis.__reply }) } }))

import { serverNextAction, serverSentence, serverSentenceOrEmpty } from '@/lib/serverText'
import { said } from '@/lib/playbookEditor'
import { ruleNotCheckedText } from '@/lib/sharedStateText'
import { readPlanWatch } from '@/lib/planWatch'

const OBJ = { error_class: 'USER_INPUT', code: 'USER_INPUT_151', what_happened: 'Spot is not available.', impact: 'i', what_is_blocked: 'b', next_action: 'Wait for the spot.', external_text: null }
const FORMS = { string: ['Spot is not available.', 'Spot is not available.'], object: [OBJ, 'Spot is not available.'], null: [null, null] }

describe('serverText', () => {
  for (const [name, [input, sentence]] of Object.entries(FORMS)) {
    it(`${name}: sentence ${JSON.stringify(sentence)}`, () => {
      expect(serverSentence(input)).toBe(sentence)
      expect(serverSentenceOrEmpty(input)).toBe(sentence ?? '')
      expect(serverNextAction(input)).toBe(name === 'object' ? 'Wait for the spot.' : null)
    })
  }
  it('absent and blank are none; a number, an array or an object with no sentence are unreadable (undefined)', () => {
    expect(serverSentence(undefined)).toBeNull()
    expect(serverSentence('  ')).toBeNull()
    expect([serverSentence(5), serverSentence([]), serverSentence({ code: 'x' })]).toEqual([undefined, undefined, undefined])
  })
})

describe('every changed reader reads all three forms', () => {
  for (const [name, [input, sentence]] of Object.entries(FORMS)) {
    it(`said / ruleNotCheckedText (adjustment check): ${name}`, () => {
      expect(said(input)).toBe(sentence ?? '')
      expect(ruleNotCheckedText(input)).toBe(sentence ? `Rule not checked: ${sentence}` : 'Rule not checked')
    })
    it(`readPlanWatch: reason, label and the texts as ${name}`, async () => {
      globalThis.__reply = {
        strategy_id: 7, as_of: '2026-11-27T09:00:00Z', as_of_text: input ?? 'As of 02:30 PM IST', plan_state: 'planned', no_plan_text: null, armed_heading: input, paused: null,
        lines: [{ key: 'a', kind: 'rule', section: 'plan', label: input ?? 'Rule a', unit: 'rule_unit', fires_at: null, now: null, distance_rs: null, distance_pct: null, state: 'not_computable', reason: input }],
      }
      const v = await readPlanWatch(7)
      expect(v.state).toBe('ok')
      expect(v.planLines).toHaveLength(1)
      expect(v.planLines[0]).toMatchObject({ state: 'not_computable', reason: sentence, reasonNext: name === 'object' ? 'Wait for the spot.' : null, label: sentence ?? 'Rule a' })
    })
  }
})
