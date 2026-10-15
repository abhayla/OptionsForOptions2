// The `draft` link boundary (W-073, #234 item 1; REQ-035 AC-4, ADR-008). Every leg of a draft link is canonicalized ONCE
// here (lots -> a whole number, planned entry -> canonical decimal text, by the same functions the live-push matcher
// uses), so REST, the socket and the matcher all see the same values. A leg that will not canonicalize refuses the whole
// link (fail closed): the page shows the catalogue's input error and sends no request, instead of freezing on a push it
// can never match.
import { canonicalLots, canonicalMoney } from '@/lib/liveMatch'

/** The catalogue template `user_input_request_invalid` (backend/ofo/errors/templates.py), four parts. A test pins this
 *  text to the template, so the two cannot drift apart. */
export const INVALID_LINK_PARTS = Object.freeze({
  what_happened: 'Some of the values sent with this request are missing or not in the expected form.',
  impact: 'The request was not carried out.',
  what_is_blocked: 'This request, until its values are corrected.',
  next_action: 'Check the values you entered and try again.',
})

/** One leg of a draft link in canonical form, or null when it will not canonicalize. A leg with no planned entry (null or
 *  absent) stays valid: it is shown as not connected and never sent (REQ-035 AC-8). */
export function canonicalLeg(l) {
  if (!l || typeof l !== 'object') return null
  if (typeof l.instrument_id !== 'string' || !l.instrument_id) return null
  const lotsText = canonicalLots(l.lots)
  if (lotsText === null) return null
  let planned = null
  if (l.planned_entry !== null && l.planned_entry !== undefined) {
    planned = canonicalMoney(l.planned_entry)
    if (planned === null) return null
  }
  return { ...l, lots: JSON.parse(lotsText), planned_entry: planned }
}

/** The legs of a draft link in canonical form, or null when any leg is refused. */
export function canonicalLegs(rawLegs) {
  if (!Array.isArray(rawLegs)) return null
  const out = rawLegs.map(canonicalLeg)
  return out.every((l) => l !== null) ? out : null
}
