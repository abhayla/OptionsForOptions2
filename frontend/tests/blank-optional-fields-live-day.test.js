// Gap 6 of the 27 Nov live test day (Lane Q2): a good server answer with EVERY optional text blank or null still renders.
// Live: GET /plan-watch answered 200 with a blank optional text, the reader (lib/planWatch.js) took the whole answer for
// unreadable and the box said "not available". One shared walker (`blankVariants`) builds, from a good answer, the answers a
// server may legally send for its optional text fields (null, "", "   ", absent), one field at a time and all at once; each
// page reader below must still read every variant as a good answer.
// Readers covered: lib/planWatch.js (parsePlanWatch) and lib/paperList.js (readPaperList, on the recorded route replies of
// tests/fixtures/paper-list-r19b). To add a reader: add one `describe` below with its good answer and its optional-text keys.
// Spec basis: REQ-049 AC-4 (a screen says data is stale or unavailable, only when it is), ADR-330 (13).
import { describe, it, expect } from 'vitest'
import { parsePlanWatch } from '@/lib/planWatch'
import { readPaperList } from '@/lib/paperList'
import PAUSED from './fixtures/paper-list-r19b/paused.json'

const BLANKS = [null, '', '   ', undefined] // undefined = the key is absent

/** Every answer with ONE key of `keys` blanked (each value of BLANKS), plus one with ALL of them blanked (each value). */
export function blankVariants(good, keys) {
  const out = []
  const set = (data, path, value) => {
    const parts = path.split('.')
    let node = data
    for (const p of parts.slice(0, -1)) node = Array.isArray(node) ? node[Number(p)] : node[p]
    const last = parts[parts.length - 1]
    if (value === undefined) delete node[last]
    else node[last] = value
  }
  for (const value of BLANKS) {
    for (const key of keys) {
      const data = JSON.parse(JSON.stringify(good))
      set(data, key, value)
      out.push({ name: `${key} = ${JSON.stringify(value) ?? 'absent'}`, data })
    }
    const all = JSON.parse(JSON.stringify(good))
    for (const key of keys) set(all, key, value)
    out.push({ name: `every optional text = ${JSON.stringify(value) ?? 'absent'}`, data: all })
  }
  return out
}

const line = (over = {}) => ({
  key: 'T-07', kind: 'target', section: 'plan', label: 'Profit target', unit: 'pnl_rupees', fires_at: '1200.00',
  now: '350.00', distance_rs: '850.00', distance_pct: '70.83', state: 'watching', reason: 'Not checked: the price is not fresh.', ...over,
})
const GOOD_WATCH = {
  strategy_id: 7, as_of: '2026-11-27T05:10:00Z', as_of_text: 'As of 10:40:00 AM IST', plan_state: 'planned',
  no_plan_text: 'No plan', armed_heading: 'Armed in the Stops panel', paused: null,
  lines: [line(), line({ key: 'trigger-3', kind: 'index_exit', section: 'armed', label: 'NIFTY at or above 24000', unit: 'index_points', state: 'paused', now: null, distance_rs: null, distance_pct: null })],
}
const WATCH_OPTIONAL = ['no_plan_text', 'armed_heading', 'as_of_text', 'lines.0.reason', 'lines.1.reason']

describe('lib/planWatch.js: blank optional texts still read as a good answer', () => {
  // "" and "   " were dropped as unreadable before hotfix/plan-watch-load-1127 (9d39c82f); it reads them, so the strict
  // expected-failure marks (`it.fails`) were deleted, as this comment said to (Lane M3, merge of plan-save).
  for (const v of blankVariants(GOOD_WATCH, WATCH_OPTIONAL)) {
    it(v.name, () => {
      const view = parsePlanWatch(v.data, 7)
      expect(view, 'a good 200 with a blank optional text must not be taken for unreadable').not.toBeNull()
      expect(view.state).toBe('ok')
      expect(view.planLines.map((l) => l.key)).toEqual(['T-07'])
      expect(view.armedLines.map((l) => l.key)).toEqual(['trigger-3'])
      // the figures are untouched by a blank text: a missing `now` stays null (never 0)
      expect(view.armedLines[0].now).toBeNull()
    })
  }
  it('a blank text is never shown as a sentence (it reads as absent)', () => {
    const d = JSON.parse(JSON.stringify(GOOD_WATCH))
    d.as_of_text = '   '
    d.lines[0].reason = ''
    const view = parsePlanWatch(d, 7)
    expect(view.asOfText).toBeNull()
    expect(view.planLines[0].reason).toBeNull()
  })
  it('the no-plan sentence is the server\'s: a no_plan answer with no sentence is still refused (fail closed)', () => {
    const d = { ...JSON.parse(JSON.stringify(GOOD_WATCH)), plan_state: 'no_plan', no_plan_text: '   ' }
    expect(parsePlanWatch(d, 7)).toBeNull()
  })
})

// every `*_text` key of a recorded strategy and of its totals, found by walking the real reply
const textKeys = (node, prefix = '', out = []) => {
  if (Array.isArray(node)) node.forEach((x, i) => textKeys(x, prefix ? `${prefix}.${i}` : String(i), out))
  else if (node && typeof node === 'object') {
    for (const [k, v] of Object.entries(node)) {
      const path = prefix ? `${prefix}.${k}` : k
      if (k.endsWith('_text') && (typeof v === 'string' || v === null)) out.push(path)
      else textKeys(v, path, out)
    }
  }
  return out
}

describe('lib/paperList.js: blank optional texts on the recorded paused reply still read', () => {
  const keys = textKeys(PAUSED).filter((k) => !k.endsWith('contract_text')) // the contract's name is required, not optional
  it('the recorded reply has optional texts to blank', () => expect(keys.length).toBeGreaterThan(0))
  for (const v of blankVariants(PAUSED, keys)) {
    it(v.name, () => {
      const list = readPaperList(v.data)
      expect(list).not.toBeNull()
      expect(list.groups.every((g) => g.readable)).toBe(true)
    })
  }
})
