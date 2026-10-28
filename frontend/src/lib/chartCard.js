// W-194 (ADR-193, ADR-194; REQ-035 AC-1, AC-7 as amended): the views of the builder's chart card, read from the
// outcome reply's one strategy table. Text only: every value is a cell's own `display` string, picked by column id;
// nothing is summed, scaled, interpolated or derived here (ADR-008). A view whose columns the reply does not carry
// returns null, and the screen shows an empty state instead of a placeholder number.
import { isCurrentColumn } from '@/lib/strategyTable'
import { instrumentText, strikeLabel } from '@/lib/displayFormat'

export { instrumentText }

export const TOTAL_ROW_ID = 'TOTAL'

/** The compact P&L view's value columns (ADR-194 (1)), in its order: Planned entry, LTP, P&L, P&L %. */
export const COMPACT_COLUMNS = [
  { id: 'entry_price', label: 'Planned entry' },
  { id: 'ltp', label: 'LTP' },
  { id: 'unrealized_pnl', label: 'P&L' },
  { id: 'pnl_percent', label: 'P&L %' },
]

/** The Greeks tab's per-leg columns (ADR-194 (2)) in REQ-145 AC-2's order (D-B34, Sensibull 015 / sb-05): Delta, Theta,
 *  Decay, Gamma, Vega, IV - whatever order the reply's own columns come in. */
export const GREEK_COLUMNS = [
  { id: 'delta', label: 'Delta' },
  { id: 'theta', label: 'Theta' },
  { id: 'decay', label: 'Decay' },
  { id: 'gamma', label: 'Gamma' },
  { id: 'vega', label: 'Vega' },
  { id: 'iv', label: 'IV' },
]
// a reply made before the Decay column (REQ-145) still fills the Greeks tab; its Decay cells print the em dash
const OPTIONAL_GREEK_IDS = new Set(['decay'])

// The instrument parts of a leg (the B/S chip, quantity, expiry, strike, type), all as the table sent them.
const INSTRUMENT_PARTS = ['action', 'quantity', 'expiry', 'strike', 'instrument']

const display = (row, id) => row.cells?.[id]?.display ?? ''
const hasColumns = (table, ids) => {
  const have = new Set((table?.columns ?? []).map((c) => c.id))
  return ids.every((id) => have.has(id))
}

const commaless = (t) => String(t ?? '').replace(/,/g, '').trim()

/** The whole-lot count the reply sent for a table row: the row's `leg` number is the 1-based place in the reply's legs.
 *  Trusted only when side, type, expiry, strike and quantity text all agree with the row; otherwise null. */
function lotsOfRow(row, legs) {
  if (!Array.isArray(legs)) return null
  const c = row.cells ?? {}
  const l = legs.find((_, i) => String(i + 1) === String(c.leg?.value))
  if (!l || l.action !== c.action?.value || l.instrument !== c.instrument?.value || l.expiry !== c.expiry?.value) return null
  if (strikeLabel(commaless(l.strike)) !== strikeLabel(commaless(c.strike?.value))) return null
  return String(l.quantity) === commaless(c.quantity?.value) && Number.isInteger(l.lots) ? l.lots : null
}

function viewRows(table, valueIds, legs) {
  return (table.rows ?? []).map((row) => {
    const isTotal = row.row_id === TOTAL_ROW_ID
    const parts = Object.fromEntries(INSTRUMENT_PARTS.map((id) => [id, display(row, id)]))
    return {
      rowId: row.row_id,
      isTotal,
      side: isTotal ? null : (row.cells?.action?.value ?? null),
      parts,
      text: isTotal ? '' : instrumentText(parts, lotsOfRow(row, legs)),
      values: Object.fromEntries(valueIds.map((id) => [id, {
        display: display(row, id),
        value: row.cells?.[id]?.value ?? null,
        perUnitDisplay: row.cells?.[id]?.per_unit_display ?? null,
      }])),
    }
  })
}

// REQ-084 AC-8 / sb-05, REQ-145 AC-3: the Greeks tab prints only server-made text; the browser formats no number.
const DASH = '—'

/** One Greeks cell as printed. mode 'unit' prints the server's `per_unit_display`, 'position' the cell's `display`
 *  (IV's `display` in both modes). Null, missing or empty text gives "—". */
export function greekText(cell, id, mode) {
  const s = String((mode === 'unit' && id !== 'iv' ? cell?.perUnitDisplay : cell?.display) ?? '').trim()
  return s || DASH
}

/** The Greeks column-heading note: "Per unit", or "Per position, N units" when every leg row carries the same quantity. */
export function greekModeHeading(rows, mode) {
  if (mode === 'unit') return 'Per unit'
  const qty = new Set((rows ?? []).filter((r) => !r.isTotal).map((r) => r.parts.quantity))
  const only = qty.size === 1 ? [...qty][0] : ''
  return only && only !== DASH ? `Per position, ${only} units` : 'Per position'
}

/** ADR-194 (1): one row per leg plus the reply's own TOTAL row when it sent one (never a browser sum). Null when the
 *  reply's table lacks a compact column. */
export function compactRows(table, legs = null) {
  const ids = COMPACT_COLUMNS.map((c) => c.id)
  if (!table || !hasColumns(table, [...INSTRUMENT_PARTS, ...ids])) return null
  return viewRows(table, ids, legs)
}

/** ADR-194 (2): the per-leg Greeks and IV the reply carries, with its TOTAL row only if sent. Null when the reply
 *  carries no Greek columns (the Greeks tab then shows its empty state). */
export function greekRows(table, legs = null) {
  const ids = GREEK_COLUMNS.map((c) => c.id)
  const needed = ids.filter((id) => !OPTIONAL_GREEK_IDS.has(id))
  if (!table || !hasColumns(table, [...INSTRUMENT_PARTS, ...needed])) return null
  return viewRows(table, ids, legs)
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

/** REQ-137 AC-1 (D-B24): the payoff table's intervals the server accepts, in index points. */
export const PAYOFF_STEPS = ['10', '25', '50', '100']

/** D-B24 / D-B25 / D-B26 (REQ-137 AC-1): the reply's own `payoff_table`, as printed. Columns in the server's order with
 *  its labels; one row per server row with each column's `display` ("—" when the cell is null); the row the server marks
 *  `nearest_spot` flagged. No percent: the reply carries none, so Show % is not built (ADR-008). Null when the reply has
 *  no `payoff_table` block (an older reply: the page falls back to the scenario-level rows). */
export function payoffStepTable(pt) {
  if (!pt || typeof pt !== 'object') return null
  if (pt.available === false || !Array.isArray(pt.rows) || !Array.isArray(pt.columns)) {
    return { available: false, reason: pt.unavailable_reason ?? null, step: pt.step ?? null, columns: [], rows: [], notes: [] }
  }
  const columns = pt.columns.map((c) => ({ view: c.view, label: c.label ?? c.view, available: c.available !== false, reason: c.unavailable_reason ?? null }))
  const rows = pt.rows.map((r) => ({
    level: r.level,
    levelText: r.level_display ?? r.level,
    current: r.nearest_spot === true,
    cells: Object.fromEntries(columns.map((c) => {
      const cell = r[c.view]
      return [c.view, { text: String(cell?.display ?? '').trim() || DASH, value: cell?.pnl ?? null }]
    })),
  }))
  const notes = columns.filter((c) => !c.available).map((c) => `${c.label}: ${c.reason ?? 'not available'}`)
  return { available: true, reason: null, step: pt.step == null ? null : String(pt.step), columns, rows, notes }
}

/** The sign of a reply value string, read from its text: 'loss', 'profit' or '' (zero, empty or not a number). */
export function signOf(value) {
  const s = String(value ?? '').trim()
  if (s.startsWith('-')) return /[1-9]/.test(s) ? 'loss' : ''
  return /^\+?(?=.*[1-9])\d+(\.\d*)?$/.test(s) ? 'profit' : ''
}
