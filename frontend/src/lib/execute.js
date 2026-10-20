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

/** Catalogue template `gate_market_unconfirmed`, as the server renders it. Shown when the market-status read fails or
 *  the server cannot confirm the market (ADR-119 fail closed): the Execute actions stay disabled. */
export const MARKET_UNCONFIRMED_PARTS = Object.freeze({
  what_happened: 'We could not confirm that the market is open. Execution is paused until it is confirmed.',
  impact: "No order can be placed while the market's status is unknown.",
  what_is_blocked: 'Execution of this strategy.',
  next_action: 'Try again once the market status is shown.',
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

// ---- EXECUTE-REVIEW (S5; docs/design/screens-research-2026-10-19-part2.md A4 + shared rules): the review's fixed texts.
// Each is the design note's wording, character for character. Every figure beside them is a server string.

/** The margin label (REQ-055 AC-1/AC-3: Zerodha's figure is final). */
export const MARGIN_ESTIMATE_LABEL = "planning estimate; Zerodha's figure is authoritative"
/** The sequence note (REQ-056 AC-3; REQ-058 Q238): the engine owns the order; the screen never reorders. */
export const SEQUENCE_NOTE = 'protective buys first; exits buy back shorts first, then sell longs'
/** REQ-036 AC-4. */
export const EVERY_TRADE_NOTE = 'Every trade follows a strategy'
/** Guided level's gloss of the order type (shared rules: "LIMIT (price you set)"). */
export const LIMIT_GLOSS = 'LIMIT (price you set)'

/** "Ready to execute: <n> orders": the count is the server's own order list. */
export function readyText(reply) {
  return `Ready to execute: ${reply.orders.length} orders`
}

/** The one plain first sentence. Only the shape the design note settles is built: two or more orders, every one a BUY, and
 *  a finite worst-case loss the server sent ("You will place 2 buy orders now; worst case loss ₹5,900"). Any other shape
 *  (a sell, an exit, one order, unlimited or unknown loss) returns null: its wording is the owner's call. The count is
 *  the length of the server's order list; the loss is the server's string, untouched. */
export function planSentence(reply) {
  const orders = reply?.orders
  const review = reply?.review
  if (!Array.isArray(orders) || orders.length < 2 || !review) return null
  if (!orders.every((o) => o.transaction_type === 'BUY')) return null
  if (review.max_loss_unlimited || typeof review.max_loss !== 'string' || review.max_loss === '') return null
  return `You will place ${orders.length} buy orders now; worst case loss ₹${review.max_loss}`
}

/** The order type as shown: Guided adds the gloss; every other level shows the server's word. */
export function orderTypeText(orderType, guided) {
  return guided && orderType === 'LIMIT' ? LIMIT_GLOSS : orderType
}
