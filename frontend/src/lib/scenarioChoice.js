// W-090 (REQ-034 AC-4, AC-6): the user's pick of scenario column and range. The step is the Admin setting per index
// (ADR-042), never the user's. The browser only SENDS the pick and shows what the outcome API returns: it never computes
// a level or a P&L (ADR-008). The server is the authority and refuses a range off its grid (422).
export const VIEWS = [
  { key: 'at_expiry', label: 'At Expiry' },
  { key: 'estimated_now', label: 'Estimated Now' },
]

/** The default pick: At Expiry, the server's own range. */
export const DEFAULT_CHOICE = Object.freeze({ view: 'at_expiry', rangeStart: '', rangeEnd: '' })

/** True for a whole number of index points as typed (digits only, no sign, no decimals), or empty. */
export function isPoints(text) {
  return /^$|^[1-9]\d{0,5}$/.test(String(text).trim())
}

/** The request fields for a pick: only what the user set is sent, so an empty pick is exactly the default request. */
export function choiceFields(choice) {
  const out = choice.view === DEFAULT_CHOICE.view ? {} : { view: choice.view } // At Expiry is the server's default
  if (choice.rangeStart && choice.rangeEnd) {
    out.range_start = String(choice.rangeStart).trim()
    out.range_end = String(choice.rangeEnd).trim()
  }
  return out
}

/** A range needs both ends, or neither. */
export function rangeIsComplete(choice) {
  return !!choice.rangeStart === !!choice.rangeEnd
}

/** True when an outcome answer was made for this pick (a late push of the previous pick is dropped, never shown). */
export function matchesChoice(body, choice) {
  const sc = body?.scenario
  if (!sc) return true // no scenario in the answer (not connected / refused): nothing to compare
  if (sc.view !== choice.view) return false
  const want = choiceFields(choice)
  if (want.range_start && (sc.start !== want.range_start || sc.end !== want.range_end)) return false
  return true
}
