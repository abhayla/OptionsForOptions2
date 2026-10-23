// REQ-015 AC-13 (RD-013): the Settings account block from GET /api/broker/account.
// The server masks the client id (first 2 + last 2 characters) and sends Zerodha's own available margin as a string
// with its read time. This file never computes, rounds, parses or defaults a figure: the margin text is the API string
// itself, and every no-figure state shows its reason. Answer states (standing item d), all fail closed:
//   margin.state 'available' with a non-empty string figure -> 'Rs <figure>' + its read time;
//   'available' without a string figure, any unknown state  -> the read-failed reason (never 0);
//   not_connected / not_offered / empty / busy / session_expired / read_failed -> that reason;
//   the request failed or the body is not an object         -> the could-not-read reason, no id.
export const MARGIN_REASON = Object.freeze({
  not_connected: 'Connect Zerodha to see your available margin.',
  not_offered: 'Available margin is not shown for this account.',
  empty: 'Zerodha did not send an available margin figure.',
  busy: 'Zerodha is busy - try again in a moment.',
  session_expired: 'Your Zerodha login for today has expired. Use Reconnect to see your margin.',
  read_failed: 'Your available margin could not be read from Zerodha.',
})
export const ACCOUNT_UNREADABLE = 'Your Zerodha account details could not be read.'
export const ID_HIDDEN = '*'

function istTime(at) {
  return new Date(at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', dateStyle: 'medium', timeStyle: 'medium' }) + ' IST'
}

/** The masked id as shown (`AB**34`), or null. Built only from the parts the server sends. */
export function maskedId(userId) {
  if (!userId || typeof userId !== 'object' || !Number.isInteger(userId.hidden) || userId.hidden < 1) return null
  const start = typeof userId.start === 'string' ? userId.start : ''
  const end = typeof userId.end === 'string' ? userId.end : ''
  return start + ID_HIDDEN.repeat(userId.hidden) + end
}

/** `{ id, figure, readAt, reason }` for the block: a figure only when Zerodha's answer carried one. */
export function accountView(body) {
  if (!body || typeof body !== 'object' || Array.isArray(body)) {
    return { id: null, figure: null, readAt: null, reason: ACCOUNT_UNREADABLE }
  }
  const id = maskedId(body.user_id)
  const margin = body.margin && typeof body.margin === 'object' ? body.margin : {}
  const figure = margin.available
  if (margin.state === 'available' && typeof figure === 'string' && figure !== '' && margin.read_at) {
    return { id, figure, readAt: istTime(margin.read_at), reason: null }
  }
  const reason = margin.state !== 'available' && MARGIN_REASON[margin.state] ? MARGIN_REASON[margin.state] : MARGIN_REASON.read_failed
  return { id, figure: null, readAt: null, reason }
}
