// W-122 (REQ-109 AC-1, AC-2, AC-5; REQ-045 AC-1; REQ-046 AC-1; ADR-166): the paper-tracking panel's words and the one
// reading of the tracking answer. The browser computes no money: every figure is the server's Decimal string, only
// re-grouped for display. An answer this module cannot read shows no figure (fail closed).
import { istTime } from '@/lib/displayFormat'

/** ADR-166: the action's label on every screen (owner decision; change it here only). */
export const START_TRACKING_LABEL = 'Start tracking'
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

const STATES = new Set(['LIVE', 'PAUSED', 'NOT_CONNECTED'])
const CONDITIONS = new Set(Object.keys(CONDITION_TEXT))

/** The one reading of GET/POST /strategies/{id}/tracking. kind: live | paused | not_connected | invalid. */
export function readTracking(body) {
  if (!body || typeof body !== 'object' || !STATES.has(body.state) || !Array.isArray(body.legs)) {
    return { kind: 'invalid', text: UNREADABLE_TEXT, figure: null, legs: [], detections: [] }
  }
  const legs = body.legs.map((leg) => ({
    key: leg.instrument_id,
    action: leg.action,
    instrument: leg.instrument,
    strike: leg.strike,
    entry: leg.entry_price,
    current: leg.price_state === 'live' ? leg.current_price : null,
  }))
  const detections = (Array.isArray(body.detections) ? body.detections : [])
    .filter((d) => d && d.kind === 'platform_detection' && CONDITIONS.has(d.condition))
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
  if (signed === null) return { kind: 'invalid', text: UNREADABLE_TEXT, figure: null, legs: [], detections: [] }
  return { kind: 'live', text: `${PAPER_PNL_PREFIX}${signed}`, figure: signed, legs, detections }
}
