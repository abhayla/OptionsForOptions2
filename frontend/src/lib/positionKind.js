// ADR-330 (58) and the owner's 28 Nov decision (withdrawing (64)): a REAL position gets the same Exit, Stops, Add and alerts as a paper
// trade, on the same screens. What a real action does is STORE a record in the app; nothing is sent to Zerodha (ADR-281, ADR-016 to
// ADR-019). The tag is the server's `position_kind` (the stored fact). Only exactly 'paper' or 'real' offers the controls; 'unknown',
// 'none', a missing field or any odd word offers none (fail closed, the unknown lock stays).
// The sentences below are proposals, pending owner read (RESULTS "New wording for the owner to read").
import { istClock } from '@/lib/displayFormat'

export const KIND_UNREAD_LINE = 'Cannot tell whether this is a real or a paper position, so Exit and Stops are not shown.' // used only when the server sent no line
export const isRealKind = (row) => row?.position_kind === 'real'
/** The ONE gate of Exit / Stops / Add / the alert's Exit answer: paper or real. Unknown, none, missing and odd words stay locked. */
export const isActionableKind = (row) => row?.position_kind === 'paper' || row?.position_kind === 'real'

/** The line that must be impossible to miss on every screen where a real action is stored. */
export const NOT_SENT_LINE = 'Not sent to Zerodha. Place it in Kite.'
export const REAL_EXIT_DIALOG_TEXT = 'This stores your exit in the app as a record and a reminder. It does not place an order and does not change your Zerodha position. Place it in Kite.'
export const REAL_ADD_DIALOG_TEXT = 'This stores your add in the app as a record and a reminder. It does not place an order and does not change your Zerodha position. Place it in Kite.'
export const REAL_UNKNOWN_TEXT = 'We could not confirm the record was stored. Check the position before trying again.' // no "order", no "Orderbook"
export const REAL_UNKNOWN_AFTER_WINDOW_TEXT = 'The record is still not confirmed. Nothing was sent to Zerodha. Check the position before trying again.'
export const REAL_STORING_TEXT = 'Storing in the app...' // while the post runs; never reads as done, never "placing"
export const REAL_STORED_NOT_REFRESHED_TEXT = 'Stored in the app. Not sent to Zerodha. Place it in Kite. Loading the position again.'
export const REAL_EXIT_STORED_TEXT = 'Exit stored. Not sent to Zerodha. Place it in Kite. This position stays open here until Zerodha shows it closed.'
export const REAL_STOPS_TEXT = 'Stop stored for this real position. When it is reached you get an alert. Nothing is sent to Zerodha. Place the exit in Kite.'
export const REAL_ROW_TEXT = 'Real position. Zerodha shows its quantity and P&L. Exits and stops you store here are not sent. Place them in Kite.'

/** The row's own line for a real position: the server's line when it sent one, else REAL_ROW_TEXT; none for paper and none-kind rows. */
export const rowLineOf = (row) => (isRealKind(row) ? (typeof row.position_kind_text === 'string' && row.position_kind_text.trim() ? row.position_kind_text : REAL_ROW_TEXT) : null)

const ACTION_WORD = { exit: 'Exit', stop: 'Stop', stop_fired: 'Stop reached', add: 'Add', open: 'Open' }
/**
 * The record line under a real row: "Exit stored 10:32:00 at 120.50. Not sent to Zerodha. Place it in Kite."
 * Only when the server says `stored_not_sent: true` and sent a record; the price is the server's text, shown untouched (ADR-008).
 * No P&L is derived from it (a price nobody got would read as a claim). Absent or unreadable parts are left out, never invented;
 * a stored_not_sent row with no readable record still prints the one line.
 */
export function recordLineOf(row) {
  if (row?.stored_not_sent !== true) return null
  const r = row.record
  // R1's contract: the record carries its own one catalogue line; show it as the server sent it
  if (typeof r?.text === 'string' && r.text.trim() && r.text.includes(NOT_SENT_LINE)) return r.text.trim()
  const word = ACTION_WORD[r?.action]
  if (!word) return NOT_SENT_LINE
  const at = r.stored_at ? istClock(r.stored_at) : null
  const price = typeof r.price === 'string' && r.price.trim() ? r.price.trim() : null
  return `${word === 'Stop reached' ? word : `${word} stored`}${at ? ` ${at}` : ''}${price ? ` at ${price}` : ''}. ${NOT_SENT_LINE}`
}
