// W-151 (REQ-119 AC-2, AC-3, AC-4): the ONE newest-wins rule for every request kind of the browser (outcome, leg-edit,
// execute). Copied from the rule the Sensibull study records (ARCHITECTURE.md:81, bundle-findings.md:104/:360: every edit
// sends a request id; after the await the client compares its own counter and drops an older reply as STALE_REQUEST).
// Per kind a counter: `next(kind)` returns the new seq and an AbortController signal and aborts the previous in-flight
// request of that kind; `accept(kind, reply, ticket)` is true only for the newest seq that is also higher than the last
// applied. A dropped reply is logged at debug level and never shown (AC-2); a cancelled request is `isSuperseded` and
// shows no error (AC-3). `pending(kind)` is true from `next` until the newest request settled (AC-4).
import { reactive } from 'vue'

export const KINDS = Object.freeze(['outcome', 'leg-edit', 'execute'])

/** True for the rejection of a request this helper aborted (axios ERR_CANCELED / CanceledError, or api.js's marker). */
export function isSuperseded(error) {
  return Boolean(error && (error.superseded === true || error.code === 'ERR_CANCELED' || error.__CANCEL__ === true || error.name === 'CanceledError'))
}

export function createNewestWins() {
  const state = Object.fromEntries(KINDS.map((k) => [k, { sent: 0, applied: 0, controller: null }]))
  const pendingByKind = reactive(Object.fromEntries(KINDS.map((k) => [k, false])))
  const slot = (kind) => {
    if (!state[kind]) throw new Error(`unknown request kind: ${kind}`)
    return state[kind]
  }
  const abortInFlight = (s) => {
    s.controller?.abort()
    s.controller = null
  }
  return {
    pending: pendingByKind,
    /** A new request of this kind: aborts the previous one still in flight. */
    next(kind) {
      const s = slot(kind)
      abortInFlight(s)
      s.controller = new AbortController()
      s.sent += 1
      pendingByKind[kind] = true
      return { kind, seq: s.sent, signal: s.controller.signal }
    },
    /** Invalidates the request in flight (its reply is dropped, it is aborted) without sending a new one. */
    cancel(kind) {
      const s = slot(kind)
      abortInFlight(s)
      s.sent += 1
      pendingByKind[kind] = false
    },
    /** True only when this reply answers the newest request of its kind and is newer than the last one applied. A reply with
     *  no seq of its own takes the seq of the request it answered, so it can never land over a newer one. */
    accept(kind, reply, ticket) {
      const s = slot(kind)
      const seq = Number.isInteger(reply?.seq) ? reply.seq : ticket?.seq
      if (seq === s.sent && seq > s.applied) {
        s.applied = seq
        return true
      }
      console.debug(`stale ${kind} reply dropped: seq ${seq}, newest sent ${s.sent}, last applied ${s.applied}`) // AC-2
      return false
    },
    /** `accept` for a caller that has nothing else to wait for: false = an older reply (drop it silently); throws when the NEWEST
     *  request got a reply that does not answer it (a wrong echoed seq), so the page shows its error and never waits forever. */
    claim(kind, reply, ticket) {
      if (this.accept(kind, reply, ticket)) return true
      if (ticket?.seq === slot(kind).sent) throw new Error('the reply does not answer the newest request')
      return false
    },
    /** The ticket's request is over (answered, failed or cancelled): the kind stops being pending when it was the newest. */
    settle(kind, ticket) {
      if (ticket?.seq === slot(kind).sent) pendingByKind[kind] = false
    },
    /** True when this ticket is still the newest request of its kind. */
    isNewest(kind, ticket) {
      return ticket?.seq === slot(kind).sent
    },
  }
}
