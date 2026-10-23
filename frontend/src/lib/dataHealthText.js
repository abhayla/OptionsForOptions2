// REQ-049 AC-4 (RD-045, RD-048): a data-health state is explained in one sentence with its reason, and a missing value
// carries a short reason in place. Closed maps: an unknown code or state gets the generic sentence, never nothing.
// Health states are the REQ-049 AC-2 list (`available` needs no sentence).
export const HEALTH_SENTENCES = {
  stale: 'Stale: the latest price for this contract is older than expected, so the figure may be out of date.',
  delayed: 'Delayed: prices for this contract are arriving later than they should, so the figure may be behind the market.',
  unhealthy: 'Unhealthy: the data for this contract looks wrong or incomplete, so do not rely on the figure.',
  unavailable: 'Unavailable: no price has been received for this contract, so no figure is shown.',
}
export const HEALTH_UNKNOWN_SENTENCE = 'The health of the data for this contract is not known, so the figure may not be current.'

/** One sentence for a health word other than `available`; null for `available`. Anything else is the generic sentence. */
export function healthSentence(health) {
  if (health === 'available') return null
  return Object.hasOwn(HEALTH_SENTENCES, health) ? HEALTH_SENTENCES[health] : HEALTH_UNKNOWN_SENTENCE
}

export const MISSING_REASONS = {
  no_contract: 'There is no contract at this strike for this expiry.',
  no_quote: 'No price has been received for this contract yet.',
  not_sent: 'Zerodha did not send this figure for this contract.',
}

/** The reason code for a missing chain value: no cell -> no_contract; a cell whose price is not available -> no_quote;
 *  otherwise the figure itself was not sent. Null when the value is present. */
export function missingCode(cell, key) {
  if (!cell) return 'no_contract'
  const v = cell[key]
  if (typeof v === 'string' || typeof v === 'number') return null
  return cell.health && cell.health !== 'available' ? 'no_quote' : 'not_sent'
}

export const missingReason = (cell, key) => {
  const code = missingCode(cell, key)
  return code === null ? undefined : MISSING_REASONS[code]
}
