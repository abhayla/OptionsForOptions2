// B4 / F1 (Phase 2 of the modular plan, 25 Nov 2026): the ONE price-freshness rule of the paper screens and its wording.
// Spec basis: REQ-109 AC-5 (a paper figure is paused, with the time of the last price, when prices are not live or the
// last read failed; no exit is offered from old prices), D-05 (Positions blocks Exit on a failed read), D-39.
// The server answers "may this act now?" (`ofo_app/may_act.py`); a screen asks THIS: what state are the prices it shows in?
// States: live | stale (the server says paused) | missing (not connected) | closed (the server's after-close sentence)
// | read_failed (the last read failed while a list or book is on screen: the old figures stay, marked old).
// Wording here is the wording each screen already showed; no sentence is new.
import { computed, toValue } from 'vue'
import { TIME_UNAVAILABLE, isoMillis, istClock, istStamp, istTime } from '@/lib/displayFormat'
import { marketClosedText } from '@/lib/sharedStateText'

export const PAUSED_TEXT = 'Paper P&L paused - prices not live'
export const NOT_CONNECTED_TEXT = 'Paper P&L paused - live prices are not connected'
export const NOT_LIVE_EXIT = 'Prices are not live; try again when they update' // REQ-109 AC-5
export const CHANGED_ELSEWHERE_EXIT = 'This trade changed elsewhere. Reload to see the current legs.' // ADR-328 (4), verbatim

/** The ONE as-of clause: ", as of <time>" when the time reads, else '' (the sentence states its reason without a time;
 *  "Time not available" is never printed inside a sentence). */
export const asOfClause = (asOf) => {
  const t = typeof asOf === 'string' ? istTime(asOf) : TIME_UNAVAILABLE
  return t === TIME_UNAVAILABLE ? '' : `, as of ${t}`
}
/** REQ-109 AC-5's paused text, with the time of the last price when it is known. */
export const pausedText = (asOf) => `${PAUSED_TEXT}${asOfClause(asOf)}`

/** ADR-330 (56): the ONE not-live notice of a screen, "Prices are not live. Figures are as of <HH:MM:SS> IST." The time is the last
 *  captured price's; with none readable the clause is left out, never a load time or a made-up one. */
export const notLiveNotice = (asOf) => {
  const clock = typeof asOf === 'string' ? istClock(asOf) : null
  return clock ? `Prices are not live. Figures are as of ${clock} IST.` : 'Prices are not live.'
}

/** ADR-330 (56): the ONE class every list of strategies puts on a tile whose figures are last-known (greyed; style.css). */
export const PRICE_GREYED_CLASS = `price-greyed`
/**
 * ADR-330 (56): the ONE "how many strategies are affected?" rule of every list. `isAffected(row)`: this row's contract has no price /
 * its book is paused. scope: none (nothing to say) | one (no page notice; only that tile carries the line) | many (the page notice,
 * tiles greyed with no sentence of their own). `idOf` names a row for `tileNotLive`.
 */
export function priceScope(rows, isAffected, idOf = (r) => r.id) {
  const ids = new Set((Array.isArray(rows) ? rows : []).filter((r) => isAffected(r)).map(idOf))
  const count = ids.size
  return { count, scope: count === 0 ? 'none' : count === 1 ? 'one' : 'many', ids }
}
/** What one tile shows under a scope: greyed when it is affected, the sentence only when it is the one affected tile. */
export const tileNotLive = (scope, id) => {
  const affected = !!scope?.ids?.has(id)
  return { greyed: affected, line: affected && scope.scope === 'one' }
}

// A reply is complete unless the page is still loading it or the read failed: a reply held then is partial (it may be the previous legs').
const PARTIAL_STATES = ['loading', 'error']
/**
 * ONE price state of a page (A4/A5/B1, 27 Nov 2026): {kind: live | last_close | stale | unavailable, at, text}.
 * `reply`: the builder's outcome reply (market_closed, last_price_at, closed_prices_text); `answer`: the index answer the page holds;
 * `pageState`: the page's own state word; `reconnecting`: the feed is down in hours. Either the reply or the index answer saying the
 * market is closed makes it last_close (pre-open is the calendar's closed). The time comes only from a COMPLETE reply
 * (a partial one, held while loading, may carry a leg first priced after the close); with no reply at all it is the index answer's.
 */
export function priceNow({ reply = null, answer = null, pageState = 'loading', reconnecting = false } = {}) {
  const complete = !!reply && !PARTIAL_STATES.includes(pageState)
  const closed = reply?.market_closed === true || answer?.market_closed === true
  if (closed) {
    const raw = complete ? (reply.market_closed === true ? reply.last_price_at : answer?.last_price_at) : (reply ? null : answer?.last_price_at)
    const at = typeof raw === 'string' && istTime(raw) !== TIME_UNAVAILABLE ? raw : null
    const server = complete && reply.market_closed === true && typeof reply.closed_prices_text === 'string' ? reply.closed_prices_text : null
    return { kind: 'last_close', at, text: server ?? marketClosedText(at ? istTime(at) : null) }
  }
  if (pageState === 'computed' && !reconnecting) return { kind: 'live', at: complete ? reply.last_price_at ?? null : null, text: '' }
  if (complete && (pageState === 'stale' || reconnecting || pageState === 'computed')) {
    const at = typeof reply.last_price_at === 'string' && istTime(reply.last_price_at) !== TIME_UNAVAILABLE ? reply.last_price_at : null
    return { kind: 'stale', at, text: pausedText(at) }
  }
  return { kind: 'unavailable', at: null, text: PAUSED_TEXT }
}

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
export function usePriceFreshness({ readFailed, held, serverState, closedText, reply, answer, pageState, reconnecting } = {}) {
  const now = computed(() => priceNow({ reply: toValue(reply) ?? null, answer: toValue(answer) ?? null, pageState: toValue(pageState) ?? 'loading', reconnecting: !!toValue(reconnecting) }))
  const state = computed(() => (pageState !== undefined
    ? (now.value.kind === 'live' ? 'live' : now.value.kind === 'last_close' ? 'closed' : now.value.kind === 'stale' ? 'stale' : 'missing')
    : priceState({
    readFailed: toValue(readFailed), held: toValue(held), serverState: toValue(serverState), closedText: toValue(closedText),
  })))
  const readFailedNow = computed(() => state.value === 'read_failed')
  const readOk = computed(() => !readFailedNow.value)
  return {
    state,
    now,
    live: computed(() => state.value === 'live'),
    readFailed: readFailedNow,
    readOk,
    exitReason: computed(() => (readOk.value ? null : NOT_LIVE_EXIT)),
  }
}

/** Lane FA r2 (I-17; ADR-330 (60), REQ-109 AC-5): the ONE as-of formatter of an Exit dialog. `rows`: the dialog's orders
 *  ({kind, price, price_at}); only exit rows count. {state, text}: one plain line, the first of these that holds:
 *  no_price (an exit row has no price) | no_time (a price with no quote time) | unreadable (a quote time that does not parse) |
 *  not_live (`notLive`: "Prices are not live. Last price as of ...") | fresh (under a minute) | stale (minutes, hours, days).
 *  The age is told for the OLDEST quote; a quote dated after `nowMs` is never "ago". No exit row: {state:'', text:''}.
 *  Wording is new, pending owner read. Times only; no money here (ADR-008). */
export function priceAgeLine(rows, { nowMs = Date.now(), notLive = false } = {}) {
  const exits = (Array.isArray(rows) ? rows : []).filter((r) => r?.kind === 'exit')
  if (!exits.length) return { state: '', text: '' }
  const noPrice = exits.filter((r) => !String(r.price ?? '').trim()).length
  if (noPrice) return { state: 'no_price', text: `No price for ${noPrice} of ${exits.length} legs; the server prices the exit when you confirm.` }
  const times = exits.map((r) => r.price_at)
  if (times.some((t) => t === null || t === undefined || t === '')) return { state: 'no_time', text: 'The time of the price is not available.' }
  const ms = times.map((t) => (typeof t === 'string' ? isoMillis(t) : null))
  if (ms.some((m) => m === null)) return { state: 'unreadable', text: 'The time of the price could not be read.' }
  let at = 0 // index of the oldest quote
  for (let i = 1; i < ms.length; i += 1) if (ms[i] < ms[at]) at = i
  const oldest = times[at]
  const stamp = istStamp(oldest, new Date(nowMs).toISOString())
  const whole = (n) => n - (n % 1) // whole units of TIME (never money, ADR-008); no Math/Number: the screen guards ban those
  const secs = whole((nowMs - ms[at]) / 1000)
  const unit = (n, w) => `${n} ${w}${n === 1 ? '' : 's'} ago`
  const ago = secs < 0 ? '' : secs < 60 ? unit(secs, 'second') : secs < 3600 ? unit(whole(secs / 60), 'minute') : secs < 86400 ? unit(whole(secs / 3600), 'hour') : unit(whole(secs / 86400), 'day')
  const asOf = `${stamp}${ago ? `, ${ago}` : ''}`
  if (notLive) return { state: 'not_live', text: `Prices are not live. Last price as of ${asOf}.` }
  return { state: secs < 60 ? 'fresh' : 'stale', text: `Price as of ${asOf}.` }
}
