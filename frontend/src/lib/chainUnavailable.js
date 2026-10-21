// W-118-sel part 2 (REQ-030 AC-13/AC-16; ADR-132 (3), ADR-016): the words of a chain cell Zerodha does not permit, in ONE
// place. The server decides (`permitted`, `unavailable_reason` on every chain cell, from Zerodha's own eligibility); the
// browser only shows it. A cell is permitted ONLY when `permitted === true`: a missing field, a string or any other value
// reads as not permitted with the "couldn't check" line (fail closed, never a guess).
export const UNAVAILABLE_LABEL = 'Currently unavailable on Zerodha'
export const REASON_LINES = Object.freeze({
  not_listed: "Not in Zerodha's list today.",
  restricted: 'Zerodha limits trading in this strike.',
  unknown: "We couldn't check with Zerodha. Refresh to try again.",
})

/** True only for a cell the server marked `permitted: true`. */
export const isPermitted = (cell) => !!cell && cell.permitted === true

/** The one reason line for a not-permitted cell (an unrecognised reason reads as "couldn't check"). */
export function reasonLine(cell) {
  const reason = cell?.unavailable_reason
  return typeof reason === 'string' && Object.hasOwn(REASON_LINES, reason) ? REASON_LINES[reason] : REASON_LINES.unknown
}
