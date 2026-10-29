// GC-TP step 4b (REQ-109 AC-2, AC-4; ADR-008; Sensibull Positions 050-053, Draft Portfolios 090-092): the one reading of
// GET /paper/strategies (step 4a) for the Paper tab. Fail closed: a strategy whose state, money texts or positions do not
// read is {readable:false}, shown with UNREADABLE_TEXT and no figure, never dropped. Every rupee is the server's text, only
// re-grouped: no sum, no product, no difference is formed here. The only arithmetic is on units (an integer count) when an
// exit order is built, and its price is the reply's own ltp string.
import { plainName } from '@/lib/saveDraft'
import { UNREADABLE_TEXT, EXITED_TEXT } from '@/lib/tracking'
import { LAST_CLOSE_LABEL } from '@/lib/paperDrafts'

const STATES = new Set(['LIVE', 'PAUSED', 'NOT_CONNECTED', 'EXITED'])
export const PAPER_NO_FIGURE = '—'
export const PAPER_PAUSED = 'Paper P&L paused - prices not live'
export const PAPER_NOT_CONNECTED = 'Paper P&L paused - live prices are not connected'
export const NOT_WHOLE_LOTS_TEXT = 'Not a whole number of lots'
export const SHOW_CLOSED_LABEL = 'Show closed positions'
export const ALL_CLOSED_TEXT = 'No open paper positions. Turn on Show closed positions to see the exited ones.'

// R-20 (ADR-210): a reason code is never shown and no reason sentence is written here; the reply's own `*_reason_text` (a pinned
// server template, one per code) is shown beside the dash as sent.
const text = (v) => (typeof v === 'string' && v.trim() !== '' ? v.trim() : null)
const isCount = (v) => Number.isInteger(v) && v >= 0

function readPosition(p) {
  if (!p || !Number.isInteger(p.contract_id) || !Number.isInteger(p.net_quantity) || typeof p.contract_text !== 'string') return null
  if (!Number.isInteger(p.lot_size) || p.lot_size <= 0) return null // no lot size, no lots: the group does not read
  const open = p.net_quantity !== 0
  const held = p.net_quantity < 0 ? -p.net_quantity : p.net_quantity // a count of units, not money
  const whole = held % p.lot_size === 0
  return {
    key: String(p.contract_id),
    contractId: p.contract_id,
    name: p.contract_text,
    side: p.net_quantity > 0 ? 'B' : p.net_quantity < 0 ? 'S' : null,
    open,
    units: p.net_quantity,
    lotSize: p.lot_size,
    lots: whole ? held / p.lot_size : null,
    // Lots = |net quantity| / lot size; a quantity that is not whole lots is shown as units, with the reason
    qtyText: whole ? `${held / p.lot_size} ${held === p.lot_size ? 'lot' : 'lots'}` : `${held} units`,
    qtyNote: whole ? '' : NOT_WHOLE_LOTS_TEXT,
    averageText: text(p.average_text),
    ltpText: p.price_state === 'live' ? text(p.ltp_text) : null,
    ltpReason: p.price_state === 'live' ? null : text(p.price_state_text), // ADR-210: the server's sentence for a retired / delisted contract
    booked: text(p.booked_text),
    unbooked: text(p.unbooked_text),
    total: text(p.total_text),
  }
}

/** One strategy of the reply. */
export function readPaperStrategy(s, index = 0) {
  const bad = (id) => ({ readable: false, id: id ?? `unreadable-${index}`, text: UNREADABLE_TEXT, state: null })
  if (!s || typeof s !== 'object') return bad(null)
  const id = Number.isInteger(s.strategy_id) ? s.strategy_id : null
  if (id === null || !STATES.has(s.state) || !Array.isArray(s.positions) || !isCount(s.open_count) || !isCount(s.position_count)) return bad(id)
  const positions = s.positions.map(readPosition)
  if (positions.some((p) => p === null)) return bad(id)
  let stateText = ''
  if (s.state === 'PAUSED') stateText = PAPER_PAUSED
  else if (s.state === 'NOT_CONNECTED') stateText = PAPER_NOT_CONNECTED
  else if (s.state === 'EXITED') stateText = EXITED_TEXT
  return {
    readable: true,
    id,
    name: plainName(s.name),
    underlying: s.underlying,
    state: s.state,
    stateText,
    openCount: s.open_count,
    positionCount: s.position_count,
    total: text(s.total_text),
    booked: text(s.booked_text),
    unbooked: text(s.unbooked_text),
    charges: text(s.charges_text), // GC-TP step 8b: beside the P&L, never subtracted from it (REQ-109 AC-10)
    chargesReason: text(s.charges_reason_text),
    pauseReason: text(s.pause_reason_text),
    positions,
  }
}

function readTotals(t) {
  if (!t || typeof t !== 'object') return null
  return {
    total: text(t.total_text), booked: text(t.booked_text), unbooked: text(t.unbooked_text), decay: text(t.decay_text),
    charges: text(t.charges_text), chargesReason: text(t.charges_reason_text),
    totalReason: text(t.totals_reason_text), decayReason: text(t.decay_reason_text),
  }
}

/** The whole reply: {groups, totals}, or null when it does not read (the caller shows the neutral error, no figure). */
export function readPaperList(data) {
  if (!data || !Array.isArray(data.strategies)) return null
  return { groups: data.strategies.map(readPaperStrategy), totals: readTotals(data.totals) }
}

/** A group is open when the server counts an open position in it (never a fully exited one). */
export const isOpenGroup = (g) => g.readable && g.state !== 'EXITED' && g.openCount > 0

/** What the Paper tab lists: everything with Show closed positions on; else only open strategies and their open contracts. */
export function visibleGroups(groups, showClosed) {
  if (showClosed) return groups
  return groups.filter((g) => !g.readable || isOpenGroup(g)).map((g) => (g.readable ? { ...g, positions: g.positions.filter((p) => p.open) } : g))
}

/** The confirm list's rows (PaperConfirmDialog orders) for the ticked open contracts: the opposite side, all open lots, price
 *  = the reply's ltp text. After hours (no live ltp) the price is empty and marked "last close" (REQ-109 AC-4). Null when a
 *  contract is not open or not in whole lots: no exit is offered for it. Quantities only: no price is formed here (ADR-008). */
export function exitRowsFor(positions) {
  if (positions.some((p) => !p.open || p.lots === null)) return null
  return positions.map((p, i) => ({
    key: `exit-${p.contractId}-${i}`, contract_id: p.contractId, side: p.units > 0 ? 'SELL' : 'BUY', text: p.name,
    lots: p.lots, lot_size: p.lotSize, price: p.ltpText ?? '', kind: 'exit', price_note: p.ltpText ? '' : LAST_CLOSE_LABEL,
  }))
}
