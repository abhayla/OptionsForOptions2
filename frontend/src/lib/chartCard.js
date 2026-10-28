// W-194 (ADR-193, ADR-194; REQ-035 AC-1, AC-7 as amended): the views of the builder's chart card, read from the
// outcome reply's one strategy table. Text only: every value is a cell's own `display` string, picked by column id;
// nothing is summed, scaled, interpolated or derived here (ADR-008). A view whose columns the reply does not carry
// returns null, and the screen shows an empty state instead of a placeholder number.
import { isCurrentColumn } from '@/lib/strategyTable'
import { expiryText, strikeLabel } from '@/lib/displayFormat'

export const TOTAL_ROW_ID = 'TOTAL'

/** The compact P&L view's value columns (ADR-194 (1)), in its order: Planned entry, LTP, P&L, P&L %. */
export const COMPACT_COLUMNS = [
  { id: 'entry_price', label: 'Planned entry' },
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

const commaless = (t) => String(t ?? '').replace(/,/g, '').trim()

/** D-B29 / D-B30 / D-B39 (REQ-146 AC-5, REQ-151, ADR-204): the instrument as Sensibull prints it, "1 x 3 Nov 22600 CE".
 *  `lots` is the server's own whole-lot count for the leg (the reply's `lots`; the browser divides nothing, ADR-008), or
 *  null when the reply did not give one for this row: then the quantity form "100 units 3 Nov 22600 CE" is printed
 *  (never a fraction of a lot, never a guessed count). A FUT leg has no strike or CE/PE: "1 x 3 Nov FUT"; an option
 *  leg without a strike prints "-" there. A date that is not a date stays as sent. `parts` are the table's display texts
 *  (quantity, expiry, strike, instrument). */
export function instrumentText(parts, lots) {
  const qty = commaless(parts?.quantity)
  const head = Number.isInteger(lots) && lots > 0 ? `${lots} x` : /^\d+$/.test(qty) ? `${qty} units` : ''
  const type = parts?.instrument ?? ''
  const strike = type === 'FUT' ? '' : (strikeLabel(commaless(parts?.strike)) || '-')
  const day = expiryText(parts?.expiry) ?? parts?.expiry ?? ''
  return [head, day, strike, type].filter(Boolean).join(' ')
}

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
  if (!table || !hasColumns(table, [...INSTRUMENT_PARTS, ...ids])) return null
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

/** The sign of a reply value string, read from its text: 'loss', 'profit' or '' (zero, empty or not a number). */
export function signOf(value) {
  const s = String(value ?? '').trim()
  if (s.startsWith('-')) return /[1-9]/.test(s) ? 'loss' : ''
  return /^\+?(?=.*[1-9])\d+(\.\d*)?$/.test(s) ? 'profit' : ''
}
