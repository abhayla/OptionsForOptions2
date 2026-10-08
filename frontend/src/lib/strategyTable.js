// Column rules for the single strategy table (W-064; REQ-035 AC-2, AC-3, AC-5, AC-7; ADR-008).
// The API sends the columns in their locked order with a `visible` flag per UX level; this file only FILTERS that list
// (never reorders). It reads no money value and does no arithmetic.

/** How many left-hand columns stay in view while the table scrolls sideways (REQ-035 AC-3): leg, action, instrument. */
export const STICKY_COUNT = 3

/** The columns to draw, in the order the API gave them (REQ-035 AC-2: never reordered). Bid and Ask are NOT table
 *  columns: the API sends them only in `advanced_details` (see advancedDetails below). */
export function columnsToRender(columns) {
  return columns.filter((c) => c.visible)
}

/** REQ-035 AC-5: the Advanced Details rows, or null. Shown only at the Advanced level AND only when the response
 *  carries the block (the API omits it at Guided and Standard). Values are the API's strings, never computed. */
export function advancedDetails(response, uxLevel) {
  if (uxLevel !== 'advanced') return null
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
