// Column rules for the single strategy table (W-064; REQ-035 AC-2, AC-3, AC-5, AC-7; ADR-008).
// The API sends the one column set in its locked order; the screen draws it as given (never reorders, never filters
// by a level: ADR-168). It reads no money value and does no arithmetic.

/** How many left-hand columns stay in view while the table scrolls sideways (REQ-035 AC-3): leg, action, instrument. */
export const STICKY_COUNT = 3

/** REQ-035 AC-5: the Details rows (Bid and Ask per leg), or null when the response carries no block. Bid and Ask
 *  are NOT table columns. Values are the API's strings, never computed. */
export function legQuotes(response) {
  return Array.isArray(response?.leg_quotes) ? response.leg_quotes : null
}

/** True for the column the API marks as the current market level (the highlight, REQ-035 AC-3). */
export function isCurrentColumn(column) {
  return Array.isArray(column.markers) && column.markers.includes('CURRENT')
}

import { expiryText, strikeLabel } from '@/lib/displayFormat'

/** The text of a cell as the API sent it ('' when the row has no such cell). Two text-only re-spellings, no number read
 *  (GC-UI b2 carry-over): the contract date as day and month ("2026-10-13" -> "13 Oct", REQ-146 AC-5) and the strike
 *  without its grouping comma or trailing zeros ("22,600" -> "22600", REQ-151 AC-1, AC-2); text that is not a date or a
 *  plain decimal (the TOTAL row's dash) stays as sent. */
export function cellText(row, column) {
  const cell = row.cells[column.id]
  if (!cell) return ''
  if (column.id === 'expiry') return expiryText(cell.display) ?? cell.display
  if (column.id === 'strike') return strikeLabel(String(cell.display ?? '').replace(/,/g, ''))
  return cell.display
}
