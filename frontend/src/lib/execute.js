// The Execute screen's helpers (W-104; REQ-056 AC-1, REQ-073 AC-1/AC-3; ADR-054, ADR-097 (2), ADR-008). Pure functions.
// New file (copy from: none - legacy-reuse row 149's BasketOrderModal builds the basket in the browser; ADR-054 wants
// the server's read-only basket posted byte-for-byte, so nothing of it is copied).
// The browser computes no money here: every amount is a string from the API, shown as given.

/** localStorage key holding the id of the strategy whose basket the owner last sent to Kite (read by the landing page). */
export const LAST_EXECUTED_KEY = 'ofo.lastExecutedStrategy'

/** Shown for a Zerodha figure the Execute reply carries as null (W-102: funds_available / margin_required are optional). */
export const NOT_READ = 'Not available from Zerodha'

/** How long the screen waits for the strategy's live socket to deliver its first live outcome before it gives up. */
export const LIVE_WAIT_MS = 15000

/** Catalogue template `gate_data_unhealthy` (backend/ofo/errors/templates.py) with data_input = leg prices and
 *  state = unavailable, as the server renders it. Shown when the live socket is not live in time: Execute is not called. */
export const NOT_LIVE_PARTS = Object.freeze({
  what_happened: 'Market data needed for execution (leg prices) is unavailable. Execution is paused until it is current.',
  impact: 'Prices, margin and checks could rest on data that does not match the market.',
  what_is_blocked: 'Execution of this strategy.',
  next_action: 'Wait for the data to update, then try again.',
})

/** True when a live push is a live outcome for every leg: the server computed it and labelled no leg (a labelled leg is
 *  stale or not connected). A NOT_CONNECTED or REFUSED push is never live. */
export function isLiveOutcome(push) {
  return !!push && push.state === 'COMPUTED' && Array.isArray(push.legs) && push.legs.length > 0 &&
    push.legs.every((l) => !l.label)
}

/** The one address the basket form may post to: Kite's basket endpoint (backend `basket_post.py`, ADR-054). The browser
 *  never CALLS a broker host (ADR-012); this constant is only compared with the server's url and used as a form target
 *  the owner submits, so the vendor-host lint is disabled for this one line with that reason. */
// eslint-disable-next-line no-restricted-syntax -- ADR-054: the read-only basket's form target, compared, never fetched
export const KITE_BASKET_URL = 'https://kite.zerodha.com/connect/basket'

/** Kite's own order book (the Orders screen's "Open Kite order book" link, ADR-138 (1)): a plain link the owner opens,
 *  never fetched. The one home of this URL; the lint is disabled for this one line with the same reason as above. */
// eslint-disable-next-line no-restricted-syntax -- ADR-138 (1): a link to Kite's order book, opened by the owner, never fetched
export const KITE_ORDER_BOOK_URL = 'https://kite.zerodha.com/orders'

/** The basket form's three values exactly as the Execute reply gives them, or null when the reply's basket is not the
 *  server's `{url, api_key, data}` shape with non-empty strings and exactly KITE_BASKET_URL (fail closed: no form). */
export function basketFields(reply) {
  const b = reply?.basket
  if (!b || typeof b !== 'object') return null
  const keys = Object.keys(b).sort()
  if (keys.join(',') !== 'api_key,data,url') return null
  if (![b.url, b.api_key, b.data].every((v) => typeof v === 'string' && v.length > 0)) return null
  if (b.url !== KITE_BASKET_URL) return null
  return { url: b.url, api_key: b.api_key, data: b.data }
}

/** Remember the strategy whose basket was just sent to Kite. Storage may be unavailable (private mode): never throws. */
export function rememberExecuted(strategyId, storage = globalThis.localStorage) {
  try {
    storage.setItem(LAST_EXECUTED_KEY, String(strategyId))
    return true
  } catch {
    return false
  }
}

/** The stored strategy id as a string of decimal digits (an id, never parsed into a number), or null (nothing stored, unreadable, or storage unavailable). */
export function readLastExecuted(storage = globalThis.localStorage) {
  let raw
  try {
    raw = storage.getItem(LAST_EXECUTED_KEY)
  } catch {
    return null
  }
  if (typeof raw !== 'string' || !/^[1-9]\d{0,17}$/.test(raw)) return null
  return raw
}
