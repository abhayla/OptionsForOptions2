// B4 / F1 (Phase 2 of the modular plan, 25 Nov 2026): the ONE price-freshness rule of the paper screens and its wording.
// Spec basis: REQ-109 AC-5 (a paper figure is paused, with the time of the last price, when prices are not live or the
// last read failed; no exit is offered from old prices), D-05 (Positions blocks Exit on a failed read), D-39.
// The server answers "may this act now?" (`ofo_app/may_act.py`); a screen asks THIS: what state are the prices it shows in?
// States: live | stale (the server says paused) | missing (not connected) | closed (the server's after-close sentence)
// | read_failed (the last read failed while a list or book is on screen: the old figures stay, marked old).
// Wording here is the wording each screen already showed; no sentence is new.
import { computed, toValue } from 'vue'
import { isoMillis, istClock, istTime } from '@/lib/displayFormat'

export const PAUSED_TEXT = 'Paper P&L paused - prices not live'
export const NOT_CONNECTED_TEXT = 'Paper P&L paused - live prices are not connected'
export const NOT_LIVE_EXIT = 'Prices are not live; try again when they update' // REQ-109 AC-5
export const CHANGED_ELSEWHERE_EXIT = 'This trade changed elsewhere. Reload to see the current legs.' // ADR-328 (4), verbatim

/** REQ-109 AC-5's paused text, with the time of the last price; null time reads as not available. */
export const pausedText = (asOf) => `${PAUSED_TEXT}, as of ${istTime(asOf)}`

/** ADR-330 (28), REQ-109 AC-1: the line the Add to Paper confirm list carries while the prices are not live (owner's sentence;
 *  the time is HH:MM India time of the OLDEST capture among the listed legs, so no leg reads fresher than it is). With no
 *  readable capture time the clause "as of ..." is left out, never invented. */
export const notLiveEntryLine = (asOf) => {
  const at = asOf ? istClock(asOf)?.slice(0, 5) : null
  return `Prices are not live; the entry is the last captured price${at ? `, as of ${at}` : ''}.`
}
/** The oldest readable `captured_at` of `legs` (an ISO text), or null. */
export function oldestCapture(legs) {
  let best = null
  let bestMs = Infinity
  for (const l of legs ?? []) {
    const ms = typeof l?.captured_at === 'string' ? isoMillis(l.captured_at) : null
    if (ms !== null && ms < bestMs) { best = l.captured_at; bestMs = ms }
  }
  return best
}

/** The ONE paused decision of every paper P&L screen (REQ-109 AC-5): a refresh failed or did not read while a list is held. */
export const listIsStale = (failed, list) => !!failed && !!list

/** A book the server marks as not priced: paused (prices not live) or not connected. */
export const bookNotLive = (book) => book?.state === 'PAUSED' || book?.state === 'NOT_CONNECTED'

/**
 * The state of the prices a screen shows. `readFailed`: the last read failed; `held`: the list or book on screen (null:
 * nothing); `serverState`: the book's own state (LIVE, PAUSED, NOT_CONNECTED, EXITED; anything else or absent reads as
 * missing, never live); `closedText`: the server's after-close sentence when it sent one.
 */
export function priceState({ readFailed = false, held = null, serverState = undefined, closedText = null } = {}) {
  if (listIsStale(readFailed, held)) return 'read_failed'
  if (serverState === 'LIVE' || serverState === 'EXITED') return 'live'
  if (serverState === 'PAUSED') return closedText ? 'closed' : 'stale'
  return 'missing'
}

/** The composable: each input is a value, a ref or a getter. `readOk` is the Positions rule (D-05): false while the last read failed with a list on screen. */
export function usePriceFreshness({ readFailed, held, serverState, closedText }) {
  const state = computed(() => priceState({
    readFailed: toValue(readFailed), held: toValue(held), serverState: toValue(serverState), closedText: toValue(closedText),
  }))
  const readFailedNow = computed(() => state.value === 'read_failed')
  const readOk = computed(() => !readFailedNow.value)
  return {
    state,
    live: computed(() => state.value === 'live'),
    readFailed: readFailedNow,
    readOk,
    exitReason: computed(() => (readOk.value ? null : NOT_LIVE_EXIT)),
  }
}
