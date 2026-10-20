// The Orders screen's wording (GC-6 ORDERS-SCREEN; ADR-135, ADR-138 (1)). Exactly four state words; the server decides the
// state (routes/orders.py) and the browser only spells it. The count is the API's own two integers, never computed here.

/** The three fixed words, keyed by the API's `state`. `executed` is spelled by `stateText` (it carries the counts). */
export const STATE_WORDS = Object.freeze({
  not_sent: 'Not sent to Zerodha',
  placed: 'Order placed',
  not_executed: 'Not executed - see Kite',
})

/** The line's state word, or null when the API gave no state (could-not-confirm and reconciliation lines). */
export function stateText(line) {
  if (line.state === 'executed') return `Executed ${line.filled_quantity} of ${line.ordered_quantity}`
  return STATE_WORDS[line.state] ?? null
}

export const EMPTY_MESSAGE = 'No orders yet.'
export const CREATE_STRATEGY_LABEL = 'Create Strategy'
export const KITE_LINK_LABEL = 'Open Kite order book'
export const NEEDS_CHECK_TEXT = 'Zerodha has to be checked before this order can be shown.'
