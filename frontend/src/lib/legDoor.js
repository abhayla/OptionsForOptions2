// D-60 (ADR-319, REQ-030 AC-11/AC-12): the ONE door every way of adding or moving a leg passes before it changes the leg
// list. A contract another leg already holds with the same action is asked about (Increase quantity / Keep separate /
// Cancel); the opposite action on the same contract is a second leg, no question. Increase quantity obeys the same lots
// limit as a manual change of lots. Nothing here prices anything or computes a number beyond the lots sum (ADR-008).
import { lotsValid } from '@/lib/legPicker'

/** D-47: said beside the picker's own count when the draft already holds legs (the count is only the picks of this open picker). New text, pending owner read. */
export const DRAFT_HOLDS_TEXT = (n) => `${n} already in the draft`
export const DUP_QUESTION = (name) => `${name} is already in this strategy.`
/** The manual lots edit's own sentence (LegPicker's lots-error), with the served maximum. */
export const lotsRangeText = (max) => `Lots must be a whole number from 1 to ${max ?? 10000}.`

/** Same contract = same instrument id and same action; a leg with no instrument id never matches another. */
export const sameContract = (a, b) => a?.instrument_id != null && a.instrument_id === b?.instrument_id && a.action === b.action

/** ADR-328 (1): the same contract held on the OTHER side (Buy against Sell). A leg with no instrument id never matches. */
export const oppositeContract = (a, b) => a?.instrument_id != null && a.instrument_id === b?.instrument_id && a.action !== b.action

/** ADR-328 (1), new wording on the screen-check list: a move onto a contract held on the other side. */
export const OPPOSITE_QUESTION = (name, heldAction) => `${name} is already in this strategy as a ${heldAction === 'BUY' ? 'Buy' : 'Sell'}.`
export const OPPOSITE_NOTE = 'A Buy and a Sell of one contract cancel each other out.'

/** The legs on screen are still the ones a question was asked about, by content (id, contract, action, lots): an equal-content
 *  refresh keeps the answer, a real replacement means the answer no longer belongs to them (treated as Cancel). */
export function sameLegs(a, b) {
  return Array.isArray(a) && Array.isArray(b) && a.length === b.length
    && a.every((l, i) => l.id === b[i].id && l.instrument_id === b[i].instrument_id && l.action === b[i].action && l.lots === b[i].lots)
}

/** Ask once per incoming leg that a held leg already covers. `ask(heldLeg, kind)` answers 'increase' | 'separate' | 'cancel'
 *  (kind 'same'); with `opposite: 'ask'` (moves, ADR-328 (1)) a leg landing on a contract held on the OTHER side is asked too
 *  (kind 'opposite': 'separate' = Keep both, anything but 'separate' = Cancel); the default `'allow'` adds it silently (a
 *  deliberate add, REQ-030 AC-11). The same-action question comes first. Returns null on Cancel (nothing changes), `{ error }` when an Increase would pass the lots limit (nothing changes), else
 *  `{ legs, kept }`: the held list with its Increases applied and the incoming legs to add as their own rows. */
export async function admitLegs(held, incoming, { ask, maxLots, skipId = null, opposite = 'allow' }) {
  let legs = held
  const kept = []
  for (const x of incoming) {
    const clash = legs.find((l) => l.id !== skipId && sameContract(l, x))
    const against = clash ? null : opposite === 'ask' ? legs.find((l) => l.id !== skipId && oppositeContract(l, x)) : null
    const choice = clash ? await ask(clash, 'same') : against ? await ask(against, 'opposite') : 'separate'
    if (choice === 'cancel' || (against && choice !== 'separate')) return null
    if (choice !== 'increase') { kept.push(x); continue }
    const total = clash.lots + x.lots
    if (!lotsValid(String(total), maxLots)) return { error: lotsRangeText(maxLots) }
    // the server computes lots = base_lots x multiplier (leg_edit.apply_multiplier): the base rises with the lots, or a later
    // multiplier edit would drop the increase
    const base = (clash.base_lots ?? clash.lots) + (x.base_lots ?? x.lots)
    legs = legs.map((l) => (l.id === clash.id ? { ...l, lots: total, base_lots: base } : l))
  }
  return { legs, kept }
}
