// R2 FC2 (order path): the ONE place a user action gets its request key. Lane FD2's order routes honour `client_request_id`: a repeat of
// the same key places nothing, so a resend of an exit whose outcome was unknown can never place a second order (ADR-016..019).
// One key per user action; the SAME key while the action is resent with the same orders; a new key for any other action.
export const newRequestKey = () => (typeof globalThis.crypto?.randomUUID === 'function'
  ? globalThis.crypto.randomUUID()
  : `k-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}-${Math.random().toString(36).slice(2, 12)}`)

/** The api client with `client_request_id` added to the body of every POST it sends; other calls and the third argument pass through. */
export const withRequestKey = (client, key) => ({ ...client, post: (url, body, cfg) => client.post(url, { ...body, client_request_id: key }, cfg) })

/**
 * The keys of a screen's pending actions, by name (a strategy id). `keyFor(name, signature)`: the key of the action `signature` names
 * (its orders as text); asked again with the same signature it is the same key, with another signature a new one. `done(name)` ends the
 * action (stored, or refused by the server): the next ask is a new key. An unknown outcome is NOT done: the resend keeps its key.
 */
export function useRequestKeys() {
  const held = new Map()
  return {
    keyFor(name, signature) {
      const cur = held.get(String(name))
      if (cur && cur.signature === signature) return cur.key
      const next = { signature, key: newRequestKey() }
      held.set(String(name), next)
      return next.key
    },
    done(name) { held.delete(String(name)) },
  }
}
