// W-122 (REQ-109 AC-1, AC-2, AC-5; REQ-045 AC-1; REQ-046 AC-1; ADR-166): the paper-tracking panel's words and the one
// reading of the tracking answer. The browser computes no money: every figure is the server's Decimal string, only
// re-grouped for display. An answer this module cannot read shows no figure (fail closed).
import { instrumentText, istTime, strikeLabel } from '@/lib/displayFormat'

/** GC-UI b2 D-B48 (REQ-109 AC-1, REQ-152): one leg's paper P&L as the server wrote it (`pnl_text`, signed, to the paisa),
 *  "booked" added for a leg the server marks booked (paper-exited); no text -> "—", never a browser figure (ADR-008). */
export const LEG_PNL_MISSING = '—'
const legPnlText = (leg) => {
  const text = typeof leg?.pnl_text === 'string' ? leg.pnl_text.trim() : ''
  if (!text) return LEG_PNL_MISSING
  return leg.pnl_kind === 'booked' ? `${text} booked` : text
}
import { plainName } from '@/lib/saveDraft'

/** GC-TP step 2 (ADR-207 (1)): the builder's action replaces "Start tracking". REQ-109 AC-1's footer, said plainly. */
export const ADD_TO_PAPER_LABEL = 'Add to Paper'
export const PAPER_NOT_REAL_TEXT = 'This is not a real trade. Paper orders use no real money.'
export const PAPER_PRICE_REASON = 'Enter a price in steps of 0.05'
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
export const paperLotsOk = (text) => /^[1-9]\d{0,5}$/.test(String(text ?? '').trim())

/** POST the confirmed orders in ONE request (the server stores them in one transaction or none). Throws the client error. */
export async function addToPaper(client, strategyId, orders) {
  const { data } = await client.post(`/paper/strategies/${strategyId}/orders`, { orders })
  return data
}
/** GC-BP F-1: a tracked strategy's paper P&L is re-read this often while it is on screen (the strike picker's rate). */
export const TRACKING_REFRESH_MS = 5000
/** REQ-045 AC-1: the label of every platform detection. */
export const PLATFORM_DETECTION_LABEL = 'Adjustment opportunity detected'
/** REQ-109 AC-2: every paper figure says it is not real. */
export const PAPER_PNL_PREFIX = 'Paper P&L (not real): '
export const NOT_CONNECTED_TEXT = 'Paper P&L paused - live prices are not connected'
export const UNREADABLE_TEXT = 'Paper P&L is not available right now.'
export const CONDITION_TEXT = Object.freeze({
  near_short_strike: 'Index is near a short strike',
  near_breakeven: 'Index is near a breakeven',
})

/** REQ-109 AC-5's paused text, with the time of the last price; null time reads as not available. */
export function pausedText(asOf) {
  return `Paper P&L paused - prices not live, as of ${istTime(asOf)}`
}

const MONEY = /^(-?)(\d+)\.(\d{2})$/

function groupIndian(digits) {
  if (digits.length <= 3) return digits
  const head = digits.slice(0, -3)
  return `${head.replace(/\B(?=(\d{2})+(?!\d))/g, ',')},${digits.slice(-3)}`
}

/** A 2-decimal money string as "+1,240.50" / "-390.00" (zero reads "+0.00"); null for anything else. */
export function signedRupees(text) {
  const m = typeof text === 'string' ? MONEY.exec(text) : null
  if (!m) return null
  const [, minus, whole, paise] = m
  const zero = /^0+$/.test(whole) && paise === '00'
  return `${minus && !zero ? '-' : '+'}${groupIndian(String(BigInt(whole)))}.${paise}`
}

/** Exited is the server's own marker (exited_at, or a booked P&L), never the presence of a price text. */
const isExited = (leg) => (leg?.exited_at !== null && leg?.exited_at !== undefined) || leg?.pnl_kind === 'booked'
/** A money figure as the server wrote it (REQ-152 AC-4); no text -> null (shown as a dash). Nothing is formed here. */
const serverText = (v) => (typeof v === 'string' && v.trim() !== '' ? v.trim() : null)

const STATES = new Set(['LIVE', 'PAUSED', 'NOT_CONNECTED', 'EXITED'])
const CONDITIONS = new Set(Object.keys(CONDITION_TEXT))

const INVALID = Object.freeze({ kind: 'invalid', text: UNREADABLE_TEXT, figure: null, legs: [], detections: [] })

const lotsOf = (replyLegs, leg) => (Array.isArray(replyLegs)
  ? replyLegs.find((r) => r?.instrument_id === leg.instrument_id && String(r.quantity) === String(leg.quantity))?.lots ?? null
  : null)

/** The one reading of GET/POST /strategies/{id}/tracking. kind: live | paused | not_connected | exited | invalid.
 *  booked / unbooked are the server's signed texts (null when absent). */
export function readTracking(body, replyLegs = null) {
  if (!body || typeof body !== 'object' || !STATES.has(body.state) || !Array.isArray(body.legs)) return INVALID
  const legs = body.legs.map((leg) => ({
    key: leg.instrument_id,
    action: leg.action,
    instrument: leg.instrument,
    strike: leg.strike,
    // GC-UI D-B39 / D-B49: "<lots> x <D Mon> <strike> <type>"; the lots are the builder reply's own whole-lot count for the
    // same instrument and quantity text, else the quantity form (no division here, ADR-008)
    text: instrumentText({ quantity: String(leg.quantity ?? ''), expiry: leg.expiry, strike: leg.strike ?? '', instrument: leg.instrument }, lotsOf(replyLegs, leg)),
    entry: leg.entry_price_display ?? null, // GC-UI D-PX: the server's two-decimal text, printed as sent
    current: leg.price_state === 'live' ? (leg.current_price_display ?? null) : null,
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
        details: [`Index: ${d.index_level}`, `Distance: ${distance}`, `Threshold: ${d.threshold_percent}%`, `As of ${istTime(d.at)}`],
      }
    })
  if (body.state === 'NOT_CONNECTED') return { kind: 'not_connected', text: NOT_CONNECTED_TEXT, figure: null, legs, detections }
  if (body.state === 'PAUSED') return { kind: 'paused', text: pausedText(body.as_of), figure: null, legs, detections }
  // live #603 item 1 (REQ-152 AC-4, ADR-008): the total, booked and unbooked are the server's signed texts as sent (one
  // minus character with the leg figures); a live / exited answer without the total's text is unreadable
  const signed = serverText(body.paper_pnl_text)
  if (signed === null) return INVALID
  const booked = serverText(body.booked_text)
  const unbooked = serverText(body.unbooked_text)
  if (body.state === 'EXITED') return { kind: 'exited', text: `${PAPER_PNL_PREFIX}${signed} - exited`, figure: signed, booked, unbooked, legs, detections }
  return { kind: 'live', text: `${PAPER_PNL_PREFIX}${signed}`, figure: signed, booked, unbooked, legs, detections }
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
      contractId: /^\d+$/.test(String(l.instrument_id ?? '')) ? Number(l.instrument_id) : null, // GC-TP 7b: the stop's contract id
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
