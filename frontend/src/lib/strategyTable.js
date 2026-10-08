// Column rules for the single strategy table (W-064; REQ-035 AC-2, AC-3, AC-5, AC-7; ADR-008).
// The API sends the columns in their locked order with a `visible` flag per UX level; this file only FILTERS that list
// (never reorders) and drops Bid/Ask unless the UX level is Advanced. It reads no money value and does no arithmetic.

/** Column ids that belong to Advanced Details only (REQ-035 AC-5). */
export const ADVANCED_ONLY = Object.freeze(['bid', 'ask'])

/** How many left-hand columns stay in view while the table scrolls sideways (REQ-035 AC-3): leg, action, instrument. */
export const STICKY_COUNT = 3

/** The columns to draw, in the order the API gave them. */
export function columnsToRender(columns, uxLevel) {
  return columns.filter((c) => c.visible && (uxLevel === 'advanced' || !ADVANCED_ONLY.includes(c.id)))
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
