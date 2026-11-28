// GC-TP step 4b (REQ-109 AC-2, AC-4; ADR-008; Sensibull Positions 050-053, Draft Portfolios 090-092): the one reading of
// GET /paper/strategies (step 4a) for the Paper tab. Fail closed: a strategy whose state, money texts or positions do not
// read is {readable:false}, shown with UNREADABLE_TEXT and no figure, never dropped. Every rupee is the server's text, only
// re-grouped: no sum, no product, no difference is formed here. The only arithmetic is on units (an integer count) when an
// exit order is built, and its price is the reply's own ltp string.
import { plainName } from '@/lib/saveDraft'
import { contractName, CONTRACT_UNAVAILABLE } from '@/lib/displayFormat'
import { UNREADABLE_TEXT, EXITED_TEXT, afterFigure } from '@/lib/tracking'
import { istTime, noteShownDate } from '@/lib/displayFormat'
import { LAST_CLOSE_LABEL } from '@/lib/paperDrafts'
import { PAUSED_TEXT as PAPER_PAUSED, NOT_CONNECTED_TEXT as PAPER_NOT_CONNECTED, listIsStale } from '@/lib/priceState'

const WORDS = ['Draft', 'Running', 'Completed']
const STATES = new Set(['LIVE', 'PAUSED', 'NOT_CONNECTED', 'EXITED'])
export const PAPER_NO_FIGURE = '—'
export { PAPER_PAUSED, PAPER_NOT_CONNECTED, listIsStale } // the one rule and wording live in lib/priceState.js
export const NOT_WHOLE_LOTS_TEXT = 'Not a whole number of lots'
export const SHOW_CLOSED_LABEL = 'Show closed positions'
export const ALL_CLOSED_TEXT = 'No open paper positions. Turn on Show closed positions to see the exited ones.'

// R-20 (ADR-210) and GC-TP fix1 (ADR-211 (5)): a reason code is never shown and no reason sentence is written here; the reply's
// own `*_reason_text` (a pinned server template, one per code) is shown beside the dash as sent. No text: UNREADABLE_TEXT.
export const DECAY_LEFT_TODAY_HEADING = 'Decay left today'
export const GREEK_COLUMNS = [
  { key: 'delta', label: 'Delta' }, { key: 'gamma', label: 'Gamma' }, { key: 'theta', label: 'Theta' }, { key: 'vega', label: 'Vega' },
]
const text = (v) => (typeof v === 'string' && v.trim() !== '' ? v.trim() : null)
// REQ-109 AC-5: "<sentence>, as of <time>" when the server sent the time (as_of / totals_as_of); no time (null, not a
// string the clock can read): the sentence as sent, never a made-up time. Only a PAUSED book carries one.
export const withAsOf = (sentence, asOf) => (sentence !== null && typeof asOf === 'string' && istTime(asOf).endsWith('IST') ? `${sentence}, as of ${istTime(asOf)}` : sentence)
const isCount = (v) => Number.isInteger(v) && v >= 0

// U16 (REQ-151): the same 'NIFTY 3 Nov 22950 CE' text every other screen shows; the server's contract_text (ISO date) is the fallback.
function shownName(p, underlying) {
  const name = contractName({ underlying, expiry: p.expiry, strike: p.strike, instrument: p.instrument })
  return name === CONTRACT_UNAVAILABLE ? p.contract_text : name
}

function readPosition(p, underlying) {
  if (!p || !Number.isInteger(p.contract_id) || !Number.isInteger(p.net_quantity) || typeof p.contract_text !== 'string') return null
  if (!Number.isInteger(p.lot_size) || p.lot_size <= 0) return null // no lot size, no lots: the group does not read
  const open = p.net_quantity !== 0
  const held = p.net_quantity < 0 ? -p.net_quantity : p.net_quantity // a count of units, not money
  const whole = held % p.lot_size === 0
  return {
    key: String(p.contract_id),
    contractId: p.contract_id,
    expiry: typeof p.expiry === 'string' ? p.expiry : null, // ADR-330 (19): the group label's expiry
    name: shownName(p, underlying),
    side: p.net_quantity > 0 ? 'B' : p.net_quantity < 0 ? 'S' : null,
    open,
    units: p.net_quantity,
    lotSize: p.lot_size,
    lots: whole ? held / p.lot_size : null,
    // Lots = |net quantity| / lot size; a quantity that is not whole lots is shown as units, with the reason
    qtyText: whole ? `${held / p.lot_size} ${held === p.lot_size ? 'lot' : 'lots'}` : `${held} units`,
    qtyNote: whole ? '' : NOT_WHOLE_LOTS_TEXT,
    averageText: text(p.average_text),
    live: p.price_state === 'live', // Lane U hotfix 27 Nov: the leg's live flag, exactly as the server sent it (usePaperExit.exitLegsNotLive; missing reads as not live)
    ltpText: p.price_state === 'live' ? text(p.ltp_text) : null,
    priceAt: p.price_state === 'live' && typeof p.price_at === 'string' ? p.price_at : null, // D-09: when that quote was made
    ltpReason: p.price_state === 'live' ? null : text(p.price_state_text), // ADR-210: the server's sentence for a retired / delisted contract
    booked: text(p.booked_text),
    unbooked: text(p.unbooked_text),
    noPrice: open && text(p.unbooked_text) === null ? text(p.no_price_text) : null, // ADR-311: "no price", never 0 or blank
    total: text(p.total_text),
  }
}

// D-10 (ADR-207 (2)): one CLOSED lifecycle of a contract as the server sent it: entry and exit average, its own booked. Texts as sent.
function readClosed(c, underlying) {
  if (!c || !Number.isInteger(c.contract_id) || typeof c.contract_text !== 'string' || !Number.isInteger(c.quantity)) return null
  return {
    key: `${c.contract_id}:${c.opened_at}`,
    contractId: c.contract_id,
    name: shownName(c, underlying),
    side: c.side === 'BUY' ? 'B' : 'S', // the side that opened it
    qtyText: Number.isInteger(c.lots) ? `${c.lots} ${c.lots === 1 ? 'lot' : 'lots'}` : `${c.quantity} units`,
    entryText: text(c.average_entry_text),
    exitText: text(c.average_exit_text),
    reasonText: text(c.reason_text), // N-47: the server's settlement / stop sentence, as the builder's closed rows print it
    booked: text(c.booked_text),
  }
}

// GC-TP R-19b: Breakeven / Max Profit / Max Loss and the net Greeks are the server's texts, only re-grouped (ADR-008). A reply
// that lacks a field (an older server) or sends it as not-a-list/not-an-object reads as absent with UNREADABLE_TEXT: a dash, never 0.
function readSummary(s) {
  const absent = (reasonText) => text(reasonText) ?? UNREADABLE_TEXT
  const hasBe = Array.isArray(s.breakevens_display) && s.breakevens_display.every((t) => text(t) !== null) && s.breakevens_display.length > 0
  const shownText = (t, code) => ({ text: text(t), reason: text(t) === null ? absent(code) : null })
  const profit = shownText(s.max_profit_text, s.extremes_reason_text)
  const loss = shownText(s.max_loss_text, s.extremes_reason_text)
  const g = s.greeks
  // D-12 (ADR-320 (1)): on expiry day the server's "Decay left today: Rs X" stands in the theta place; nothing computed here
  const greekRow = (r) => (r && typeof r === 'object' ? Object.fromEntries(GREEK_COLUMNS.map((c) => [c.key, text(c.key === 'theta' && text(r.decay_left_today_text) !== null ? r.decay_left_today_text : r[`${c.key}_text`])])) : null)
  const legs = g && Array.isArray(g.legs) ? g.legs.map((l) => (l && Number.isInteger(l.contract_id) ? { contractId: l.contract_id, ...greekRow(l) } : null)) : null
  const net = g ? greekRow(g.net) : null
  const greeksOk = !!net && !!legs && !legs.includes(null) && GREEK_COLUMNS.every((c) => net[c.key] !== null && legs.every((l) => l[c.key] !== null))
  return {
    decayLeftToday: !!g && text(g.net?.decay_left_today_text) !== null,
    breakevens: hasBe ? s.breakevens_display.map((t) => t.trim()) : null,
    breakevensReason: hasBe ? null : (Array.isArray(s.breakevens) && s.breakevens.length === 0 ? null : absent(s.breakevens_reason_text)),
    maxProfit: profit.text, maxProfitReason: profit.reason,
    // D-14 round 2: the server's sentence on whether charges are inside Max Profit / Max Loss (before charges when they could not be priced)
    extremesBasis: text(s.extremes_charges_text),
    // D-14 (ADR-320 (2)): on the trade's expiry day only, the server's "If held to expiry" Max profit; null other days
    maxProfitHold: text(s.max_profit_hold_text),
    maxLoss: loss.text, maxLossReason: loss.reason,
    greeks: greeksOk ? { legs, net, basis: text(g.basis_text) } : null, // D-63: "summed across 2 expiries" as sent
    greeksReason: greeksOk ? null : (s.state === 'PAUSED' && s.greeks_reason === 'prices_not_live' ? withAsOf(absent(s.greeks_reason_text), s.as_of) : absent(s.greeks_reason_text)),
  }
}

/** One strategy of the reply. */
export function readPaperStrategy(s, index = 0) {
  const bad = (id) => ({ readable: false, id: id ?? `unreadable-${index}`, text: UNREADABLE_TEXT, state: null })
  if (!s || typeof s !== 'object') return bad(null)
  const id = Number.isInteger(s.strategy_id) ? s.strategy_id : null
  if (id === null || !STATES.has(s.state) || !Array.isArray(s.positions) || !isCount(s.open_count) || !isCount(s.position_count)) return bad(id)
  const positions = s.positions.map((p) => readPosition(p, s.underlying))
  if (positions.some((p) => p === null)) return bad(id)
  const closed = (Array.isArray(s.closed) ? s.closed : []).map((c) => readClosed(c, s.underlying))
  if (closed.some((c) => c === null)) return bad(id)
  let stateText = ''
  if (s.state === 'PAUSED') stateText = withAsOf(PAPER_PAUSED, s.as_of)
  else if (s.state === 'NOT_CONNECTED') stateText = PAPER_NOT_CONNECTED
  else if (s.state === 'EXITED') stateText = EXITED_TEXT
  const pauseReason = s.state === 'PAUSED' || s.state === 'NOT_CONNECTED' ? withAsOf(text(s.pause_reason_text), s.as_of) : text(s.pause_reason_text)
  return {
    readable: true,
    id,
    name: plainName(s.name),
    expiries: positions.map((p) => p.expiry).filter((e) => e !== null), // ADR-330 (19): the dates the group label may show
    underlying: s.underlying,
    state: s.state,
    // owner 28 Nov: the tag is the server's; only exactly 'real' or 'unknown' differs from paper (a missing tag on this list reads paper: it is the paper list)
    positionKind: s.position_kind === 'real' ? 'real' : s.position_kind === 'unknown' ? 'unknown' : 'paper',
    positionKindText: text(s.position_kind_text),
    storedNotSent: s.stored_not_sent === true,
    record: s.record && typeof s.record === 'object' ? s.record : null,
    statusWord: WORDS.includes(s.status_word) ? s.status_word : null, // ADR-299 (4): the server's word, never derived here
    stateText,
    openCount: s.open_count,
    positionCount: s.position_count,
    total: text(s.total_text),
    booked: text(s.booked_text),
    unbooked: text(s.unbooked_text),
    charges: text(s.charges_text), // GC-TP step 8b: beside the P&L, never subtracted from it (REQ-109 AC-10)
    chargesReason: text(s.charges_reason_text),
    pauseReason,
    afterCloseText: text(s.after_close_text), // D-64: after the close the server's line replaces the unpriced naming
    unpricedText: text(s.after_close_text) !== null ? null : text(s.unpriced_text), // ADR-311: the open legs with no price, named by the server
    totalAfter: afterFigure(s, text(s.total_text), pauseReason), // GC-ICFIX u123: the headline total, labelled
    bookedAfter: afterFigure(s, text(s.booked_text), pauseReason, 'booked_after_text', ['paid']), // u124 (ADR-303): the same rule per figure; u127: Booked carries the charges paid
    unbookedAfter: afterFigure(s, text(s.unbooked_text), pauseReason, 'unbooked_after_text', ['close']), // ... Unbooked the estimate to close
    held: s.held ?? null, // GC-TRACK1 k10: shown by HeldNote, which reads nothing it cannot parse
    ...readSummary(s),
    positions,
    closed,
    closedText: text(s.closed_text), // D-10 (ADR-306 (5)): a fully closed book says so, with its result
  }
}

function readTotals(t) {
  if (!t || typeof t !== 'object') return null
  // REQ-109 AC-5: a paused total always says so, with the time of the last price: ONE sentence for Positions and Home (pnlFigure reads it)
  const totalReason = withAsOf(text(t.totals_reason_text) ?? (t.after_charges_reason === 'prices_not_live' ? PAPER_PAUSED : null), t.totals_as_of)
  return {
    totalAfter: afterFigure(t, text(t.total_text), totalReason), // GC-ICFIX u123: one total from the engine's sum, never a partial one
    bookedAfter: afterFigure(t, text(t.booked_text), totalReason, 'booked_after_text', ['paid']),
    unbookedAfter: afterFigure(t, text(t.unbooked_text), totalReason, 'unbooked_after_text', ['close']),
    total: text(t.total_text), booked: text(t.booked_text), unbooked: text(t.unbooked_text), decay: text(t.decay_text),
    charges: text(t.charges_text), chargesReason: text(t.charges_reason_text),
    closedNote: text(t.closed_text), // ADR-330 (15): the server's "Includes N closed strategies" line, never built here
    leftOut: text(t.left_out_text), // D-40 (ADR-324): the server's line saying how many expired strategies the figures leave out
    totalReason, decayReason: t.decay_reason === 'prices_not_live' ? withAsOf(text(t.decay_reason_text), t.totals_as_of) : text(t.decay_reason_text),
  }
}

/** D-68 (ADR-320 point 6): the header's "Today" block as the server sent it; null when the reply has none (older server). The
 *  figure follows the totals' paused rule (afterFigure); `count` 0 shows the server's sentence and no figure. Nothing is summed here. */
function readToday(t) {
  if (!t || typeof t !== 'object' || !Number.isInteger(t.count) || t.count < 0) return null
  const reason = withAsOf(text(t.totals_reason_text), t.totals_as_of)
  return { count: t.count, emptyText: t.count === 0 ? text(t.empty_text) : null, total: text(t.total_text), totalReason: reason,
    totalAfter: afterFigure(t, text(t.total_text), reason) }
}

/** The whole reply: {groups, totals, today}, or null when it does not read (the caller shows the neutral error, no figure). */
export function readPaperList(data) {
  if (!data || !Array.isArray(data.strategies)) return null
  noteShownDate(data) // ADR-330 (19): before any group label is written
  const groups = data.strategies.map(readPaperStrategy)
  return { groups, totals: tieClosedLine(readTotals(data.totals), data.totals, groups), today: readToday(data.today) }
}

/** Lane L item 2 (ADR-330 (15)): "Includes N closed strategies" must be the count of the closed rows of the SAME reply. The server
 *  sends `closed_count` beside its sentence; when it differs from the closed rows this reply lists (an integer count, no money), the
 *  sentence is not shown (fail closed) and the difference is named in `closedMismatch` for the page. A reply with an unreadable
 *  row, or without a count, cannot be tied: the server's sentence stands as sent. */
function tieClosedLine(totals, raw, groups) {
  if (!totals || !isCount(raw?.closed_count) || !groups.every((g) => g.readable)) return totals
  const rows = groups.filter((g) => !isOpenGroup(g)).length
  return rows === raw.closed_count ? totals : { ...totals, closedNote: null, closedMismatch: { server: raw.closed_count, rows } }
}

/** A group is open when the server counts an open position in it (never a fully exited one). */
export const isOpenGroup = (g) => g.readable && g.state !== 'EXITED' && g.openCount > 0

/** What the Paper tab lists: everything with Show closed positions on; else only open strategies and their open contracts. */
export function visibleGroups(groups, showClosed) {
  if (showClosed) return groups
  return groups.filter((g) => !g.readable || isOpenGroup(g)).map((g) => (g.readable ? { ...g, positions: g.positions.filter((p) => p.open), closed: [] } : g))
}

/** The confirm list's rows (PaperConfirmDialog orders) for the ticked open contracts: the opposite side, all open lots, price
 *  = the reply's ltp text. After hours (no live ltp) the price is empty and marked "last close" (REQ-109 AC-4). Null when a
 *  contract is not open or not in whole lots: no exit is offered for it. Quantities only: no price is formed here (ADR-008). */
export function exitRowsFor(positions) {
  if (positions.some((p) => !p.open || p.lots === null)) return null
  const rows = positions.map((p, i) => ({
    key: `exit-${p.contractId}-${i}`, contract_id: p.contractId, side: p.units > 0 ? 'SELL' : 'BUY', text: p.name,
    lots: p.lots, lot_size: p.lotSize, price: p.ltpText ?? '', price_at: p.ltpText ? p.priceAt ?? null : null, kind: 'exit', price_note: p.ltpText ? '' : LAST_CLOSE_LABEL,
  }))
  // D-02 (REQ-159 AC-6): buy-backs of shorts before sales of longs, the order the server records; stable (ES2019)
  return rows.sort((a, b) => (a.side === 'BUY' ? 0 : 1) - (b.side === 'BUY' ? 0 : 1))
}
