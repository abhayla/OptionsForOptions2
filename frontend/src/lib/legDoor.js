// D-60 (ADR-319, REQ-030 AC-11/AC-12): the ONE door every way of adding or moving a leg passes before it changes the leg
// list. A contract another leg already holds with the same action is asked about (Increase quantity / Keep separate /
// Cancel); the opposite action on the same contract is a second leg, no question. Increase quantity obeys the same lots
// limit as a manual change of lots. Nothing here prices anything or computes a number beyond the lots sum (ADR-008).
import { lotsValid } from '@/lib/legPicker'

export const DUP_QUESTION = (name) => `${name} is already in this strategy.`
/** The manual lots edit's own sentence (LegPicker's lots-error), with the served maximum. */
export const lotsRangeText = (max) => `Lots must be a whole number from 1 to ${max ?? 10000}.`

/** Same contract = same instrument id and same action; a leg with no instrument id never matches another. */
export const sameContract = (a, b) => a?.instrument_id != null && a.instrument_id === b?.instrument_id && a.action === b.action

/** Ask once per incoming leg that a held leg already covers. `ask(heldLeg)` answers 'increase' | 'separate' | 'cancel'.
 *  Returns null on Cancel (nothing changes), `{ error }` when an Increase would pass the lots limit (nothing changes), else
 *  `{ legs, kept }`: the held list with its Increases applied and the incoming legs to add as their own rows. */
export async function admitLegs(held, incoming, { ask, maxLots, skipId = null }) {
  let legs = held
  const kept = []
  for (const x of incoming) {
    const clash = legs.find((l) => l.id !== skipId && sameContract(l, x))
    const choice = clash ? await ask(clash) : 'separate'
    if (choice === 'cancel') return null
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
