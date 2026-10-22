// W-127 (REQ-084 AC-1..AC-4, AC-6; REQ-034 AC-6): the user's what-if inputs. They live in component state only: never
// saved with the strategy, never part of a draft link. The browser only SENDS them as typed text; the server clamps,
// refuses and answers (ADR-008). No number is parsed or computed here.
export const DEFAULT_WHATIF = Object.freeze({ targetLevel: '', targetTime: '', ivOffset: '' })

/** True for a whole number of index points as typed, or empty (the server's POINTS_PATTERN). */
export function isLevelText(text) {
  return /^$|^[1-9]\d{0,5}$/.test(String(text).trim())
}

/** True for volatility points in steps of 0.1 as typed ("2.0", "-1.5"), or empty. */
export function isOffsetText(text) {
  return /^$|^-?\d{1,2}\.\d$/.test(String(text).trim())
}

/** The request fields for the inputs: only what the user set is sent, so an empty pick is exactly the default request. */
export function whatifFields(w) {
  const out = {}
  if (w.targetLevel) out.target_level = String(w.targetLevel).trim()
  if (w.targetTime) out.target_time = w.targetTime
  if (w.ivOffset) out.iv_offset = String(w.ivOffset).trim()
  return out
}

/** True when nothing is set (all three controls at their Reset state). */
export function whatifIsDefault(w) {
  return !w.targetLevel && !w.targetTime && !w.ivOffset
}

/**
 * True when an answer was made for these inputs. A late push of the previous inputs is dropped, never drawn
 * ("two quick edits: the older reply never draws"). The level and time are clamped by the server, so only the IV offset
 * (echoed as sent) is compared; an answer without a what-if block has nothing to compare.
 */
export function matchesWhatif(body, w) {
  const block = body?.whatif
  if (!block) return true
  return block.iv_offset === (w.ivOffset ? String(w.ivOffset).trim() : '0.0')
}

// The server's times carry the IST offset; a datetime-local box shows the first 16 characters (YYYY-MM-DDTHH:MM) of the
// server's own string, and a typed value goes back with the same offset. String handling only.
export const IST_OFFSET = '+05:30'
export const toLocalInput = (iso) => (iso ? String(iso).slice(0, 16) : '')
export const fromLocalInput = (value) => (value ? `${value}:00${IST_OFFSET}` : '')
