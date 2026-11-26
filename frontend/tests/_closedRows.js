// D-10: the recorded replies in tests/fixtures predate the `closed` rows; a server now sends one per closed lifecycle. This adds
// them from the recorded flat contracts (side and prices are test inputs here; the booked text is the recorded one).
export const closedFrom = (positions) => positions.filter((p) => p.net_quantity === 0).map((p) => ({
  contract_id: p.contract_id, contract_text: p.contract_text, side: 'SELL', quantity: p.lot_size ?? 65, lots: 1, lot_size: p.lot_size ?? 65,
  average_entry_text: '100.00', average_exit_text: '90.00', booked_text: p.booked_text, opened_at: `2026-10-28T05:03:0${p.contract_id % 10}Z`,
}))
export const withClosed = (book) => ({ ...book, closed: closedFrom(book.positions) })
