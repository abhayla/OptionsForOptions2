// W-194 (ADR-193, ADR-194; REQ-035 AC-1, AC-7 as amended): the views of the builder's chart card, read from the
// outcome reply's one strategy table. Text only: every value is a cell's own `display` string, picked by column id;
// nothing is summed, scaled, interpolated or derived here (ADR-008). A view whose columns the reply does not carry
// returns null, and the screen shows an empty state instead of a placeholder number.
import { isCurrentColumn } from '@/lib/strategyTable'

export const TOTAL_ROW_ID = 'TOTAL'

/** The compact P&L view's value columns (ADR-194 (1)), in its order: Entry, LTP, P&L, P&L %. */
export const COMPACT_COLUMNS = [
  { id: 'entry_price', label: 'Entry' },
  { id: 'ltp', label: 'LTP' },
  { id: 'unrealized_pnl', label: 'P&L' },
  { id: 'pnl_percent', label: 'P&L %' },
]

/** The Greeks tab's per-leg columns (ADR-194 (2)), in its order. */
export const GREEK_COLUMNS = [
  { id: 'delta', label: 'Delta' },
  { id: 'gamma', label: 'Gamma' },
  { id: 'theta', label: 'Theta' },
  { id: 'vega', label: 'Vega' },
  { id: 'iv', label: 'IV' },
]

// The instrument parts of a leg (the B/S chip, quantity, expiry, strike, type), all as the table sent them.
const INSTRUMENT_PARTS = ['action', 'quantity', 'expiry', 'strike', 'instrument']

const display = (row, id) => row.cells?.[id]?.display ?? ''
const hasColumns = (table, ids) => {
  const have = new Set((table?.columns ?? []).map((c) => c.id))
  return ids.every((id) => have.has(id))
}

function viewRows(table, valueIds) {
  return (table.rows ?? []).map((row) => {
    const isTotal = row.row_id === TOTAL_ROW_ID
    return {
      rowId: row.row_id,
      isTotal,
      side: isTotal ? null : (row.cells?.action?.value ?? null),
      parts: Object.fromEntries(INSTRUMENT_PARTS.map((id) => [id, display(row, id)])),
      values: Object.fromEntries(valueIds.map((id) => [id, { display: display(row, id), value: row.cells?.[id]?.value ?? null }])),
    }
  })
}

/** ADR-194 (1): one row per leg plus the reply's own TOTAL row when it sent one (never a browser sum). Null when the
 *  reply's table lacks a compact column. */
export function compactRows(table) {
  const ids = COMPACT_COLUMNS.map((c) => c.id)
  if (!table || !hasColumns(table, [...INSTRUMENT_PARTS, ...ids])) return null
  return viewRows(table, ids)
}

/** ADR-194 (2): the per-leg Greeks and IV the reply carries, with its TOTAL row only if sent. Null when the reply
 *  carries no Greek columns (the Greeks tab then shows its empty state). */
export function greekRows(table) {
  const ids = GREEK_COLUMNS.map((c) => c.id)
  if (!table || !hasColumns(table, [...INSTRUMENT_PARTS, ...ids])) return null
  return viewRows(table, ids)
}

/** The Payoff tab's Table view (REQ-137 kept separate; no interval chooser yet): one row per scenario level the reply
 *  sent, in its order, with the TOTAL row's cell for that level. The row the reply marks CURRENT is flagged. Null when
 *  the reply has no TOTAL row or no scenario columns (nothing is computed to stand in). */
export function payoffLevelRows(table) {
  const total = (table?.rows ?? []).find((r) => r.row_id === TOTAL_ROW_ID)
  const levels = (table?.columns ?? []).filter((c) => c.is_scenario_level)
  if (!total || !levels.length) return null
  return levels.map((c) => ({
    id: c.id,
    level: c.label,
    pnl: display(total, c.id),
    value: total.cells?.[c.id]?.value ?? null,
    current: isCurrentColumn(c),
  }))
}

/** The sign of a reply value string, read from its text: 'loss', 'profit' or '' (zero, empty or not a number). */
export function signOf(value) {
  const s = String(value ?? '').trim()
  if (s.startsWith('-')) return /[1-9]/.test(s) ? 'loss' : ''
  return /^\+?(?=.*[1-9])\d+(\.\d*)?$/.test(s) ? 'profit' : ''
}
