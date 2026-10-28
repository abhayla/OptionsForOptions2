// W-122 (REQ-109 AC-1, AC-2, AC-5; REQ-045 AC-1; REQ-046 AC-1; ADR-166): the paper-tracking panel's words and the one
// reading of the tracking answer. The browser computes no money: every figure is the server's Decimal string, only
// re-grouped for display. An answer this module cannot read shows no figure (fail closed).
import { istTime } from '@/lib/displayFormat'
import { plainName } from '@/lib/saveDraft'

/** ADR-166: the action's label on every screen (owner decision; change it here only). */
export const START_TRACKING_LABEL = 'Start tracking'
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

const STATES = new Set(['LIVE', 'PAUSED', 'NOT_CONNECTED', 'EXITED'])
const CONDITIONS = new Set(Object.keys(CONDITION_TEXT))

const INVALID = Object.freeze({ kind: 'invalid', text: UNREADABLE_TEXT, figure: null, legs: [], detections: [] })

/** The one reading of GET/POST /strategies/{id}/tracking. kind: live | paused | not_connected | exited | invalid.
 *  booked / unbooked are the server's strings, signed for display (null when absent or unreadable). */
export function readTracking(body) {
  if (!body || typeof body !== 'object' || !STATES.has(body.state) || !Array.isArray(body.legs)) return INVALID
  const legs = body.legs.map((leg) => ({
    key: leg.instrument_id,
    action: leg.action,
    instrument: leg.instrument,
    strike: leg.strike,
    entry: leg.entry_price,
    current: leg.price_state === 'live' ? leg.current_price : null,
  }))
  // an answer carrying a detection this screen cannot name is unreadable as a whole: never silently dropped
  if (!Array.isArray(body.detections)) return INVALID
  if (!body.detections.every((d) => d && d.kind === 'platform_detection' && CONDITIONS.has(d.condition))) return INVALID
  const detections = body.detections
    .map((d) => ({
      key: `${d.condition}-${d.level}`,
      label: PLATFORM_DETECTION_LABEL,
      condition: CONDITION_TEXT[d.condition],
      level: d.level,
      index: d.index_level,
      distance: `${d.distance_points} points (${d.distance_percent}%)`,
      threshold: `${d.threshold_percent}%`,
      at: istTime(d.at),
    }))
  if (body.state === 'NOT_CONNECTED') return { kind: 'not_connected', text: NOT_CONNECTED_TEXT, figure: null, legs, detections }
  if (body.state === 'PAUSED') return { kind: 'paused', text: pausedText(body.as_of), figure: null, legs, detections }
  const signed = signedRupees(body.paper_pnl)
  if (signed === null) return INVALID
  const booked = signedRupees(body.booked)
  const unbooked = signedRupees(body.unbooked)
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
    const exited = l.exit_price !== null && l.exit_price !== undefined
    legs.push({
      key: `${l.leg_index}`,
      index: l.leg_index,
      action: l.action === 'BUY' ? 'Buy' : l.action === 'SELL' ? 'Sell' : l.action,
      instrument: l.instrument,
      strike: l.strike,
      expiry: l.expiry,
      quantity: l.quantity,
      entry: l.entry_price,
      current: l.price_state === 'live' ? l.current_price : null,
      exited,
      exitPrice: exited ? l.exit_price : null,
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
    pauseReason: item.state === 'PAUSED' ? item.pause_reason ?? null : null,
    total: signedRupees(item.total),
    booked: signedRupees(item.booked),
    unbooked: signedRupees(item.unbooked),
    legs,
  }
}
