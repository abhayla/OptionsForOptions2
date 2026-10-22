// W-132 (REQ-117 AC-1, AC-3, AC-4): a feature asks a NAMED broker flag; it never compares a broker's name or id.
// The server's GET /api/broker/capabilities answers each of the seven flags as true/false. Answer states (standing
// item d, every one fails closed):
//   the flag is exactly `true` in the body        -> on;
//   `false`, absent, any other value ("true", 1)  -> off;
//   a name that is not one of the seven           -> off;
//   body missing / not an object / an array       -> every flag off;
//   request failed (network, 4xx, 5xx, timeout)   -> every flag off (the body becomes {}).
// A flag never loosens a safety gate: the server's checks run the same whatever a flag says (REQ-117 AC-5).
import { ref } from 'vue'
import api from '../services/api'

export const CAPABILITY_NAMES = Object.freeze([
  'basket_page_orders',
  'broker_held_triggers',
  'intraday_product',
  'order_update_stream',
  'funds_read',
  'positions_read',
  'basket_margin_quote',
])

/** Shown where the margin line would be when `basket_margin_quote` is not on. Names no broker. */
export const MARGIN_LINE_HIDDEN_REASON = 'Margin from the broker is not available for this account.'

/** True only when `name` is one of the seven flags and the body states it as exactly `true`. */
export function capabilityOn(body, name) {
  if (!CAPABILITY_NAMES.includes(name)) return false
  if (!body || typeof body !== 'object' || Array.isArray(body)) return false
  return Object.prototype.hasOwnProperty.call(body, name) && body[name] === true
}

let pending = null

/** The one read of the flags, shared by every screen; any failure is `{}` (every flag off), never an error. */
export function fetchCapabilities() {
  if (!pending) {
    pending = Promise.resolve().then(() => api.get('/broker/capabilities')).then(({ data }) => data)
      .catch(() => { pending = null; return {} }) // a failed read is all off now, and is read again next time
  }
  return pending
}

/** Forget the cached read (tests, and a screen that must re-read after the login changes). */
export function resetCapabilities() {
  pending = null
}

/** A ref that is `null` while the read is pending, then the body (or `{}` after a failure). Pass it to
 *  `capabilityOn`; a screen shows a flag-gated feature only when `capabilityOn` answers true. */
export function useCapabilities() {
  const body = ref(null)
  fetchCapabilities().then((value) => { body.value = value })
  return body
}
