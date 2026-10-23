// Column rules for the single strategy table (W-064; REQ-035 AC-2, AC-3, AC-5, AC-7; ADR-008).
// The API sends the one column set in its locked order; the screen draws it as given (never reorders, never filters
// by a level: ADR-168). It reads no money value and does no arithmetic.

/** How many left-hand columns stay in view while the table scrolls sideways (REQ-035 AC-3): leg, action, instrument. */
export const STICKY_COUNT = 3

/** REQ-035 AC-5: the Details rows (Bid and Ask per leg), or null when the response carries no block. Bid and Ask
 *  are NOT table columns. Values are the API's strings, never computed. */
export function advancedDetails(response) {
  return Array.isArray(response?.advanced_details) ? response.advanced_details : null
}

/** True for the column the API marks as the current market level (the highlight, REQ-035 AC-3). */
export function isCurrentColumn(column) {
  return Array.isArray(column.markers) && column.markers.includes('CURRENT')
}

/** The text of a cell exactly as the API sent it ('' when the row has no such cell). */
export function cellText(row, column) {
  const cell = row.cells[column.id]
  return cell ? cell.display : ''
}
