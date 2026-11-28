// R2 FC2 (order path): the ONE place a user action gets its request key. Lane FD2's order routes honour `client_request_id`: a repeat of
// the same key places nothing, so a resend of an exit whose outcome was unknown can never place a second order (ADR-016..019).
// One key per user action; the SAME key while the action is resent with the same orders; a new key for any other action.
export const newRequestKey = () => (typeof globalThis.crypto?.randomUUID === 'function'
  ? globalThis.crypto.randomUUID()
  : `k-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}-${Math.random().toString(36).slice(2, 12)}`)

/** The api client with `client_request_id` added to the body of every POST it sends; other calls and the third argument pass through. */
export const withRequestKey = (client, key) => ({ ...client, post: (url, body, cfg) => client.post(url, { ...body, client_request_id: key }, cfg) })

// One store per tab (module scope), so a remount of the screen (Cancel on the Alerts exit door, leaving for the Orderbook) keeps the key of an
// exit whose outcome is still unknown. It is NOT kept across a reload or another tab (listed in RESULTS; Opus review F2).
const held = new Map()
export const resetRequestKeys = () => held.clear()

/**
 * The keys of a screen's pending actions, by name (a strategy id). `keyFor(name, signature, mayReuse)`: the key of the action `signature` names.
 * It is reused only while the last attempt ended UNKNOWN (`markUnknown`), the orders text is the same and the caller says the screen's record of
 * that attempt is still open (`mayReuse`: unknown / not stored, or no record because the screen was mounted again); any other ask is a new action
 * with a new key (Opus review F1: an unknown outcome that a re-read settled as placed must not lend its key to the next exit).
 * `done(name)` ends the action (stored, or refused by the server).
 */
export function useRequestKeys() {
  return {
    keyFor(name, signature, mayReuse = true) {
      const cur = held.get(String(name))
      if (cur && cur.unknown && mayReuse && cur.signature === signature) return cur.key
      const next = { signature, key: newRequestKey(), unknown: false }
      held.set(String(name), next)
      return next.key
    },
    markUnknown(name) { const cur = held.get(String(name)); if (cur) cur.unknown = true },
    done(name) { held.delete(String(name)) },
  }
}
