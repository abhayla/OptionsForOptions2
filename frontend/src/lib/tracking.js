// W-122 (REQ-109 AC-1, AC-2, AC-5; REQ-045 AC-1; REQ-046 AC-1; ADR-166): the paper-tracking panel's words and the one
// reading of the tracking answer. The browser computes no money: every figure is the server's Decimal string, only
// re-grouped for display. An answer this module cannot read shows no figure (fail closed).
import { groupedIndian, instrumentText, istClock, istTime, strikeLabel } from '@/lib/displayFormat'

/** GC-UI b2 D-B48 (REQ-109 AC-1, REQ-152): one leg's paper P&L as the server wrote it (`pnl_text`, signed, to the paisa),
 *  "booked" added for a leg the server marks booked (paper-exited); no text -> "—", never a browser figure (ADR-008). */
export const LEG_PNL_MISSING = '—'
const legPnlText = (leg) => {
  const text = typeof leg?.pnl_text === 'string' ? leg.pnl_text.trim() : ''
  // ADR-311: an open leg with no live price says so in the server's words ("no price"), never 0 and never a blank
  if (!text) return (typeof leg?.no_price_text === 'string' && leg.no_price_text.trim()) || LEG_PNL_MISSING
  return leg.pnl_kind === 'booked' ? `${text} booked` : text
}
import { plainName } from '@/lib/saveDraft'
import { NOT_CONNECTED_TEXT, bookNotLive, pausedText } from '@/lib/priceState'

/** GC-TP step 2 (ADR-207 (1)): the builder's action replaces "Start tracking". REQ-109 AC-1's footer, said plainly. */
export const ADD_TO_PAPER_LABEL = 'Add to Paper'
export const PAPER_NOT_REAL_TEXT = 'This is not a real trade. Paper orders use no real money.'
export const PAPER_EXIT_CHECKING_TEXT = 'Checking whether this exit leaves a sold option without protection...'
export const PAPER_EXIT_UNCHECKED_TEXT = 'The app could not check whether this exit leaves a sold option without protection. You can still confirm.'
export const PAPER_PRICE_REASON = 'Enter a price in steps of 0.05'
export const PAPER_PRICE_ZERO_REASON = 'A price of 0 cannot be used. Enter 0.05 or more' // pending owner read (D-58): a zero is not a step problem
export const PAPER_LOTS_REASON = 'Enter whole lots, 1 or more'
export const PAPER_ADDED_TEXT = 'Added to Paper'
// a typed price: digits with at most two decimals whose last decimal is 0 or 5 (a multiple of 0.05), and not zero. Judged on
// the text alone, no number is formed (ADR-008).
const PRICE_TEXT = /^\d{1,7}(?:\.\d[05]?)?$/
const ZERO_TEXT = /^0+(?:\.0+)?$/
export function paperPriceOk(text) {
  const typed = String(text ?? '').trim()
  return PRICE_TEXT.test(typed) && !ZERO_TEXT.test(typed)
}
/** The reason a typed price is refused, or '' when it is fine: zero has its own words (D-58), any other bad text the steps reason. */
export function paperPriceReason(text) {
  if (paperPriceOk(text)) return ''
  return ZERO_TEXT.test(String(text ?? '').trim()) ? PAPER_PRICE_ZERO_REASON : PAPER_PRICE_REASON
}
export const paperLotsOk = (text) => /^[1-9]\d{0,5}$/.test(String(text ?? '').trim())

// fix/paper-dialog-safe (ADR-017: no automatic retry; submitted is not executed): what a paper-order dialog does with each
// answer to its ONE POST. Before this, every failure read as "not placed" and Confirm came back, so a POST the server had
// stored (201) but whose answer or follow-up read was lost could be sent a second time (live 2026-11-06, strategy 86).
export const PAPER_PLACED_NOT_REFRESHED_TEXT = 'Placed on paper. Loading the position again.' // pending owner read (15 Nov 2026), issue 18: no "reload" dead end
export const PAPER_UNKNOWN_TEXT = 'We could not confirm the order. Check Orderbook before trying again.'
export const PAPER_OPEN_ORDERBOOK_LABEL = 'Open Orderbook'
/** An exit's price is read by the server when the order is placed (live in market hours, the last close after hours). */
export const PAPER_EXIT_PRICED_BY_SERVER_TEXT = 'the server sets the exit price when you confirm'
export const PAPER_PLANNED_PRICE_NOTE = 'planned price, no live quote'
/** How long Confirm stays locked after an answer of unknown outcome (the user checks the Orderbook first). */
export const PAPER_UNKNOWN_HOLD_MS = 5000
/** The dialog states after Confirm: '' (ready), 'refused', 'unknown', 'placed'. */
export const PAPER_STATE = Object.freeze({ READY: '', REFUSED: 'refused', UNKNOWN: 'unknown', PLACED: 'placed' })
/** Classify a FAILED paper-order POST (the mapped client error). 'superseded' = the page cancelled it itself (silent);
 *  'refused' = the server answered 4xx, so it stored nothing (one transaction or none); 'unknown' = no answer (timeout,
 *  dropped connection) or a 5xx (a gateway timeout can follow a commit): the order may be stored, so it is never re-offered
 *  as if it were not. */
export function paperPostOutcome(e) {
  if (e?.superseded) return 'superseded'
  const status = Number.isInteger(e?.status) ? e.status : null
  if (status !== null && status >= 400 && status < 500) return PAPER_STATE.REFUSED
  return PAPER_STATE.UNKNOWN
}
/** An entry (`open`) row's starting price: the live price the page holds for the leg (the LTP the table shows), else the
 *  planned entry with a note saying so. The planned-entry field itself is never changed. */
export function entryPriceFor(leg, livePriceById = {}) {
  const live = livePriceById?.[leg?.instrument_id]
  const planned = typeof leg?.planned_entry === 'string' ? leg.planned_entry : ''
  // GC-ICLIVE-B D-15 (c): a live price that is not the plan's says so ("plan 36.45"): no re-quote is hidden
  if (typeof live === 'string' && live.trim() !== '') return { price: live.trim(), price_note: planned && planned !== live.trim() ? `plan ${planned}` : '' }
  return { price: planned, price_note: planned ? PAPER_PLANNED_PRICE_NOTE : '' }
}

/** POST the confirmed orders in ONE request (the server stores them in one transaction or none). Throws the client error. */
export async function addToPaper(client, strategyId, orders, suggestionIds = [], basketLegs = null, held = null, approachId = null) {
  // REQ-163 AC-1: the acted-on records this basket answers (Compare -> Open in builder); omitted when none
  const body = suggestionIds.length ? { orders, suggestion_ids: suggestionIds } : { orders }
  if (suggestionIds.length && basketLegs) body.basket_legs = basketLegs // REQ-112: the prepared basket's size
  if (approachId) body.approach_id = approachId // D-25 (ADR-326 (1)): a Take profit basket (A-24 / A-25), checked by the server
  if (held) body.held = held // GC-TRACK1 k10: only on the first basket, only when the user ticked "Held at my broker"
  const { data } = await client.post(`/paper/strategies/${strategyId}/orders`, body)
  return data
}
// GC-TRACK1 k10 (ADR-292 (1), (3), (4)): the texts of a condor typed in as held at the user's broker.
export const HELD_LABEL = 'Held at my broker'
export const HELD_NOTE = 'Changes you make at your broker are not seen by the app. Record them here.'
const SHORT_IST = /^(\d{1,2} [A-Za-z]{3}) \d{4}, (\d{2}:\d{2}):\d{2} IST$/
const shortIst = (iso) => { const m = SHORT_IST.exec(istTime(iso)); return m ? `${m[1]} ${m[2]}` : null }
/** The reply's `held` as the lines to show, or null (plain paper strategy, a missing key, a non-object or an unreadable
 *  entry_at show nothing held, never a guess). rules_start_at null/unreadable -> no "Rules start" line. */
export function heldView(held) {
  if (!held || typeof held !== 'object' || Array.isArray(held)) return null
  const entry = shortIst(held.entry_at)
  if (entry === null) return null
  const rules = shortIst(held.rules_start_at)
  return { label: HELD_LABEL, entry: `Entry ${entry}`, rules: rules === null ? null : `Rules start from ${rules}`, broker: typeof held.broker === 'string' && held.broker !== '' ? held.broker : null }
}
/** The POST's held block from the form: entry time typed as 'YYYY-MM-DDTHH:mm' (India time), broker optional. */
export function heldBlock(entryAt, broker) {
  const b = (broker ?? '').trim()
  return { entry_at: `${entryAt}:00+05:30`, broker: b === '' ? null : b }
}
/** GC-BP F-1: a tracked strategy's paper P&L is re-read this often while it is on screen (the strike picker's rate). */
export const TRACKING_REFRESH_MS = 5000
/** REQ-045 AC-1: the label of every platform detection. */
export const PLATFORM_DETECTION_LABEL = 'Adjustment opportunity detected'
/** REQ-109 AC-2: every paper figure says it is not real. */
export const PAPER_PNL_PREFIX = 'Paper P&L (not real): '
export const UNREADABLE_TEXT = 'Paper P&L is not available right now.'
export const CONDITION_TEXT = Object.freeze({
  near_short_strike: 'Index is near a short strike',
  near_breakeven: 'Index is near a breakeven',
})

export { NOT_CONNECTED_TEXT, pausedText } // the one wording lives in lib/priceState.js (REQ-109 AC-5)

const MONEY = /^(-?)(\d+)\.(\d{2})$/

/** A 2-decimal money string as "+1,240.50" / "-390.00" (zero reads "+0.00"); null for anything else. */
export function signedRupees(text) {
  const m = typeof text === 'string' ? MONEY.exec(text) : null
  if (!m) return null
  const [, minus, whole, paise] = m
  const zero = /^0+$/.test(whole) && paise === '00'
  return `${minus && !zero ? '-' : '+'}${groupedIndian(String(BigInt(whole)))}.${paise}`
}

/** Exited is the server's own marker (exited_at, or a booked P&L), never the presence of a price text. */
const isExited = (leg) => (leg?.exited_at !== null && leg?.exited_at !== undefined) || leg?.pnl_kind === 'booked'
/** A money figure as the server wrote it (REQ-152 AC-4); no text -> null (shown as a dash). Nothing is formed here. */
const serverText = (v) => (typeof v === 'string' && v.trim() !== '' ? v.trim() : null)

export const AFTER_CHARGES = '(after charges)'
export const BEFORE_CHARGES = '(before charges)'
/** GC-ICFIX u123 (ADR-263, ADR-008): which total a screen shows. `src` is a reply object, `before` its before-charges text,
 *  `pausedText` the screen's own paused sentence (REQ-109 AC-5). kind 'after': the server's total_after_text, only when it
 *  sent no reason with it. 'paused': prices not live, no number. Else 'before': the before text with the server's reason
 *  sentence; an older server (no after fields) lands here too, so a before figure is never shown under an "after" label. */
export const BREAKDOWN_LABELS = Object.freeze({ before: 'Before charges', paid: 'Charges paid', close: 'Estimated charges to close', after: 'After charges' })
/** GC-ICFIX u127 (ADR-263, ADR-008, REQ-109 AC-10): what one tap on the figure opens. Every text is a server field as sent; a row
 *  whose text the reply lacks is left out (never formatted here); `parts` says which charge rows apply to this figure (Booked
 *  -> paid, Unbooked -> close, Profit / Loss left -> none). Null = nothing to open (paused, or an older reply with no new field). */
function breakdownOf(src, before, after, why, parts) {
  const row = (id, text) => (text === null ? [] : [{ id, label: BREAKDOWN_LABELS[id], text }])
  if (after !== null) {
    const paid = parts.includes('paid') ? row('paid', serverText(src?.charges_paid_text ?? src?.charges_paid)) : []
    const close = parts.includes('close') ? row('close', serverText(src?.charges_to_close_text)) : []
    return { rows: [...row('before', before), ...paid, ...close, ...row('after', after)], reason: null }
  }
  return why !== null && before !== null ? { rows: row('before', before), reason: why } : null
}
export function afterFigure(src, before, pausedText = null, afterKey = 'total_after_text', parts = ['paid', 'close']) {
  // ADR-311: Booked after has its OWN reason (the charges paid are unknown); every other figure follows the book's reason
  const own = afterKey === 'booked_after_text' && src !== null && typeof src === 'object' && 'booked_after_reason' in src // the totals row has none: unchanged
  const ownReason = own ? (src.booked_after_reason ?? null) : null
  // a Booked figure the server gave stands even while the total is paused; otherwise its own reason, else the book's
  const reason = ownReason ?? (own && serverText(src[afterKey]) !== null ? null : (src?.after_charges_reason ?? null))
  const raw = ownReason !== null ? src.booked_after_reason_text : src?.after_charges_reason_text // a sentence, or {what_happened} on the replies that word it as an explanation
  const why = serverText(raw && typeof raw === 'object' ? raw.what_happened : raw)
  if (reason === 'prices_not_live') return { kind: 'paused', text: null, label: '', reason: pausedText ?? why, breakdown: null }
  const after = serverText(src?.[afterKey]) // u124: the same rule for booked_after_text / profit_left_after_text / ...
  if (after !== null && reason === null) return { kind: 'after', text: after, label: AFTER_CHARGES, reason: null, breakdown: breakdownOf(src, before, after, null, parts) }
  return { kind: 'before', text: before, label: before === null ? '' : BEFORE_CHARGES, reason: why ?? (before === null ? pausedText : null), breakdown: breakdownOf(src, before, null, why, parts) }
}

/** GC-ICFIX round 2 (F4, ADR-008, ADR-306): the ONE total of a practice trade, from the page's one read of /paper/strategies/{id}.
 *  The paper panel, the tracking box and the P&L table TOTAL row all show this: the reply's total_after_text (or the labelled
 *  before text with the server's reason; no number when prices are not live) and the same line under it: "As of HH:MM:SS IST"
 *  from the reply's answered_at, or the paused sentence when the last read failed / the prices are not live (REQ-109 AC-5). */
export const CONTRACTS_CHANGED_TEXT = 'The open contracts changed, so the screen could not refresh them: reload to see them.'
export function sharedTotal(book, failed = false) {
  if (!book || typeof book !== 'object') return null
  const notLive = bookNotLive(book)
  const shown = afterFigure(book, serverText(book.total_text), pausedText(book.as_of ?? null))
  const at = istClock(book.answered_at ?? null)
  const closedLine = serverText(book.after_close_text) // D-64: after the close the server's sentence says why, in place of "prices not live"
  const line = failed ? pausedText(book.answered_at ?? null) : closedLine !== null && notLive ? closedLine : notLive ? pausedText(book.as_of ?? null) : at === null ? null : `As of ${at} IST`
  // ADR-311: the legs that pause the total, named by the server (null when none); a paused total is never a number
  return { kind: shown.kind, text: shown.text, label: shown.label, reason: shown.reason, breakdown: shown.breakdown, line, unpriced: closedLine !== null ? null : serverText(book.unpriced_text) }
}

const STATES = new Set(['LIVE', 'PAUSED', 'NOT_CONNECTED', 'EXITED'])
const CONDITIONS = new Set(Object.keys(CONDITION_TEXT))

const INVALID = Object.freeze({ kind: 'invalid', text: UNREADABLE_TEXT, figure: null, legs: [], detections: [] })

const lotsOf = (replyLegs, leg) => (Array.isArray(replyLegs)
  ? replyLegs.find((r) => r?.instrument_id === leg.instrument_id && String(r.quantity) === String(leg.quantity))?.lots ?? null
  : null)

/** REQ-046 AC-5: the data state of the figures behind a detection, from the server's price_health (live / stale / missing).
 *  An answer that is itself PAUSED / NOT_CONNECTED reads paused; a state not named here is said as not known. */
const DATA_STATE_TEXT = Object.freeze({ live: 'Data: live', stale: 'Data: stale', missing: 'Data: paused' })
export function dataStateText(health, answerState) {
  if (answerState === 'PAUSED' || answerState === 'NOT_CONNECTED') return 'Data: paused'
  return DATA_STATE_TEXT[health] ?? 'Data: not known'
}

/** The one reading of GET/POST /strategies/{id}/tracking. kind: live | paused | not_connected | exited | invalid.
 *  booked / unbooked are the server's signed texts (null when absent). */
export function readTracking(body, replyLegs = null) {
  if (!body || typeof body !== 'object' || !STATES.has(body.state) || !Array.isArray(body.legs)) return INVALID
  const legs = body.legs.map((leg) => ({
    key: leg.instrument_id,
    contractId: leg.contract_id, // D-41: the book's key of this leg (key is the feed identity "NSE_FO:..."); absent in an older reply
    action: leg.action,
    instrument: leg.instrument,
    strike: leg.strike,
    // GC-UI D-B39 / D-B49: "<lots> x <D Mon> <strike> <type>"; the lots are the builder reply's own whole-lot count for the
    // same instrument and quantity text, else the quantity form (no division here, ADR-008)
    text: instrumentText({ quantity: String(leg.quantity ?? ''), expiry: leg.expiry, strike: leg.strike ?? '', instrument: leg.instrument }, lotsOf(replyLegs, leg)),
    entry: leg.entry_price_display ?? null, // GC-UI D-PX: the server's two-decimal text, printed as sent
    current: leg.price_state === 'live' ? (leg.current_price_display ?? null) : null,
    quoteAt: leg.price_state === 'live' && typeof leg.price_at === 'string' ? leg.price_at : null, // D-18: when THIS leg's price was quoted (the server's price_at)
    exited: isExited(leg),
    exitPrice: leg.exit_price_display ?? null, // REQ-109 AC-4: the server's text of the exit price; null = a dash
    pnl: legPnlText(leg),
  }))
  // an answer carrying a detection this screen cannot name is unreadable as a whole: never silently dropped
  if (!Array.isArray(body.detections)) return INVALID
  if (!body.detections.every((d) => d && d.kind === 'platform_detection' && CONDITIONS.has(d.condition))) return INVALID
  const detections = body.detections
    .map((d) => {
      const distance = `${d.distance_points} points (${d.distance_percent}%)`
      const condition = CONDITION_TEXT[d.condition]
      return {
        key: `${d.condition}-${d.level}`,
        label: PLATFORM_DETECTION_LABEL,
        condition,
        level: d.level,
        index: d.index_level,
        distance,
        threshold: `${d.threshold_percent}%`,
        at: istTime(d.at),
        // GC-UI D-B50 (ADR-202 (1), ADR-204): one visible line, the rest of REQ-046 AC-1's Layer 1 behind the "?"
        // REQ-151 AC-2: the strike the server sent ("22400.00") trims only its trailing zeros -> "22400"
        line: `${PLATFORM_DETECTION_LABEL}: ${condition}: ${strikeLabel(d.level)}, ${distance} away`,
        details: [`Index: ${d.index_level}`, `Distance: ${distance}`, `Threshold: ${d.threshold_percent}%`,
          dataStateText(d.price_health, body.state), `As of ${istTime(d.at)}`],
      }
    })
  if (body.state === 'NOT_CONNECTED') return { kind: 'not_connected', text: NOT_CONNECTED_TEXT, figure: null, legs, detections }
  if (body.state === 'PAUSED') return { kind: 'paused', text: serverText(body.after_close_text) ?? pausedText(body.as_of), figure: null, legs, detections, unpriced: serverText(body.after_close_text) !== null ? null : serverText(body.unpriced_text) }
  // live #603 item 1 (REQ-152 AC-4, ADR-008): the total, booked and unbooked are the server's signed texts as sent (one
  // minus character with the leg figures); a live / exited answer without the total's text is unreadable
  const signed = serverText(body.paper_pnl_text)
  if (signed === null) return INVALID
  const booked = serverText(body.booked_text)
  const unbooked = serverText(body.unbooked_text)
  // GC-ICFIX u123 (ADR-263): the headline is the after-charges figure, labelled; no after figure -> the before figure, labelled
  const shown = afterFigure(body, signed)
  if (shown.kind === 'paused') return { kind: 'paused', text: serverText(body.after_close_text) ?? pausedText(body.as_of), figure: null, legs, detections, unpriced: serverText(body.after_close_text) !== null ? null : serverText(body.unpriced_text) }
  const text = `${PAPER_PNL_PREFIX}${shown.text} ${shown.label}`
  const base = { figure: shown.text, afterReason: shown.reason, breakdown: shown.breakdown, booked, unbooked, legs, detections }
  if (body.state === 'EXITED') return { kind: 'exited', text: `${text} - exited`, ...base }
  return { kind: 'live', text, ...base }
}

export const EXITED_TEXT = 'Exited'
const money = (v) => v === null || v === undefined || signedRupees(v) !== null

/** GC-BP step 6: one item of GET /tracking for the Paper list. Fail closed: an item whose state, money strings or legs do
 *  not read is {readable:false} (shown with UNREADABLE_TEXT and no figure), never dropped. Money is the server's string
 *  only re-grouped; nothing is summed here (ADR-008). Total / unbooked may be null only when prices are not live. */
export function readTrackingItem(item, index = 0) {
  const bad = (id) => ({ readable: false, id: id ?? `unreadable-${index}`, text: UNREADABLE_TEXT })
  if (!item || typeof item !== 'object') return bad(null)
  const id = Number.isInteger(item.strategy_id) ? item.strategy_id : null
  if (id === null || !STATES.has(item.state) || !Array.isArray(item.legs)) return bad(id)
  if (!money(item.total) || !money(item.booked) || !money(item.unbooked) || signedRupees(item.booked) === null) return bad(id)
  if ((item.state === 'LIVE' || item.state === 'EXITED') && signedRupees(item.total) === null) return bad(id)
  if (item.state === 'LIVE' && signedRupees(item.unbooked) === null) return bad(id)
  const legs = []
  for (const l of item.legs) {
    if (!l || !Number.isInteger(l.leg_index) || typeof l.action !== 'string' || typeof l.instrument !== 'string') return bad(id)
    const exited = isExited(l)
    legs.push({
      key: `${l.leg_index}`,
      index: l.leg_index,
      contractId: /^\d+$/.test(String(l.instrument_id ?? '')) ? String(l.instrument_id) : null, // GC-TP 7b: the stop's contract id, a digit string sent as is (no number is formed)
      action: l.action === 'BUY' ? 'Buy' : l.action === 'SELL' ? 'Sell' : l.action,
      instrument: l.instrument,
      strike: l.strike,
      expiry: l.expiry,
      quantity: l.quantity,
      entry: l.entry_price_display ?? null,
      current: l.price_state === 'live' ? (l.current_price_display ?? null) : null,
      exited,
      exitPrice: exited ? (l.exit_price_display ?? null) : null, // null = the server sent no text: shown as a dash
    })
  }
  let stateText = ''
  if (item.state === 'PAUSED') stateText = pausedText(item.as_of)
  else if (item.state === 'NOT_CONNECTED') stateText = NOT_CONNECTED_TEXT
  else if (item.state === 'EXITED') stateText = EXITED_TEXT
  return {
    readable: true,
    id,
    name: plainName(item.name),
    underlying: item.underlying,
    state: item.state,
    stateText,
    total: serverText(item.total_text),
    booked: serverText(item.booked_text),
    unbooked: serverText(item.unbooked_text),
    legs,
  }
}
