// Plan-save-1127 (Lane R; ADR-330 (1), (5); REQ-161 AC-2/AC-3; ADR-016 to ADR-019): the ONE mapping of a plan save attempt to
// exactly one of three outcomes, shared by the builder's AdjustPlanSheet, Settings > Adjustments "Change plan values" and the
// adjustments page's trade rules. No screen decides this on its own.
//   saved         the server's own answer (`value`), and the strategy's save count is marked (a read begun earlier is dropped)
//   refused       a 4xx carrying a catalogue reason: `parts` is the server's reason, shown as it is
//   not_confirmed a 5xx, a timeout, no answer, a 4xx with no catalogue reason, or a 200 the browser cannot read: the one
//                 sentence PLAN_NOT_CONFIRMED_TEXT. The typed values stay, nothing is re-sent, there is no "Try again".
import { NEUTRAL_PARTS } from '@/services/api'
import { markSaved } from '@/lib/planSaveClock'
import { PLAN_NOT_CONFIRMED_TEXT } from '@/lib/sharedStateText'

/** A refusal is a 4xx whose body carried a catalogue message; NEUTRAL_PARTS (the client's stand-in) is never one. */
export const isRefusal = (e) => !!e?.parts && e.parts !== NEUTRAL_PARTS && Number.isInteger(e.status) && e.status >= 400 && e.status < 500

const NOT_CONFIRMED = Object.freeze({ kind: 'not_confirmed', parts: null, text: PLAN_NOT_CONFIRMED_TEXT })

/** The outcome of a save that threw `e`. */
export const failureOf = (e) => (isRefusal(e) ? { kind: 'refused', parts: e.parts, text: e.parts.what_happened } : NOT_CONFIRMED)

/** Run one save attempt (`call()` resolves the server's answer; it is called once, never again).
 *  `opts.readable(value)` false -> not confirmed; `opts.markId` marks that strategy saved (for a call that does not mark itself). */
export async function planSaveResult(call, opts = {}) {
  let value
  try {
    value = await call()
  } catch (e) {
    return failureOf(e)
  }
  if (opts.readable && !opts.readable(value)) return NOT_CONFIRMED
  if (opts.markId !== undefined && opts.markId !== null) markSaved(opts.markId)
  return { kind: 'saved', value, parts: null, text: '' }
}
