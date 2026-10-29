// GC-TP step 4b (REQ-109 AC-2, AC-4; ADR-008; Sensibull Positions 050-053, Draft Portfolios 090-092): the one reading of
// GET /paper/strategies (step 4a) for the Paper tab. Fail closed: a strategy whose state, money texts or positions do not
// read is {readable:false}, shown with UNREADABLE_TEXT and no figure, never dropped. Every rupee is the server's text, only
// re-grouped: no sum, no product, no difference is formed here. The only arithmetic is on units (an integer count) when an
// exit order is built, and its price is the reply's own ltp string.
import { plainName } from '@/lib/saveDraft'
import { UNREADABLE_TEXT, EXITED_TEXT } from '@/lib/tracking'

const STATES = new Set(['LIVE', 'PAUSED', 'NOT_CONNECTED', 'EXITED'])
export const PAPER_NO_FIGURE = '—'
export const PAPER_PAUSED = 'Paper P&L paused - prices not live'
export const PAPER_NOT_CONNECTED = 'Paper P&L paused - live prices are not connected'
export const SHOW_CLOSED_LABEL = 'Show closed positions'
export const ALL_CLOSED_TEXT = 'No open paper positions. Turn on Show closed positions to see the exited ones.'

const text = (v) => (typeof v === 'string' && v.trim() !== '' ? v.trim() : null)
const isCount = (v) => Number.isInteger(v) && v >= 0

function readPosition(p) {
  if (!p || !Number.isInteger(p.contract_id) || !Number.isInteger(p.net_quantity) || typeof p.contract_text !== 'string') return null
  const open = p.net_quantity !== 0
  return {
    key: String(p.contract_id),
    contractId: p.contract_id,
    name: p.contract_text,
    side: p.net_quantity > 0 ? 'B' : p.net_quantity < 0 ? 'S' : null,
    open,
    units: p.net_quantity,
    qtyText: String(p.net_quantity),
    averageText: text(p.average_text),
    ltpText: p.price_state === 'live' ? text(p.ltp_text) : null,
    exitPrice: p.price_state === 'live' ? text(p.ltp) : null, // the reply's own string, sent back as the exit price
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
    positions,
  }
}

function readTotals(t) {
  if (!t || typeof t !== 'object') return null
  return {
    total: text(t.total_text), booked: text(t.booked_text), unbooked: text(t.unbooked_text), decay: text(t.decay_text),
    totalReason: text(t.totals_reason), decayReason: text(t.decay_reason),
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

/** The exit orders (REQ-109 AC-4) for the ticked open contracts: the opposite side, all units, at the reply's ltp. */
export function exitOrdersFor(positions) {
  const rows = positions.filter((p) => p.open && p.exitPrice !== null)
  if (rows.length !== positions.length) return null
  return rows.map((p) => ({ contract_id: p.contractId, side: p.units > 0 ? 'SELL' : 'BUY', quantity: p.units < 0 ? -p.units : p.units, price: p.exitPrice, kind: 'exit' }))
}
