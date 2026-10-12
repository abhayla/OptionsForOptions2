// Leg picker helpers (W-068; REQ-035 AC-8, ADR-068, ADR-008). Pure functions; no price or P&L is ever computed here.
// Strings only: a strike and a planned entry stay exactly the strings the API sent.

export const UNDERLYINGS = ['NIFTY', 'SENSEX']

/** The one wording for a draft that has no live data (the backend constant NOT_CONNECTED_LABEL, ADR-020 Q185). */
export const NOT_CONNECTED_LABEL = 'Draft - Live data not connected'

/** The outcome API's instrument id. The catalogue API sends segment and token apart (its Identifier type forbids ':'),
 *  so the browser joins the two strings. This is identifier assembly, not a calculation. */
export function instrumentId(exchangeSegment, exchangeToken) {
  return `${exchangeSegment}:${exchangeToken}`
}

/** A whole number of lots from 1 to 10000, typed as digits (no sign, no decimal point, no leading zero). */
export function lotsValid(text) {
  return /^([1-9]\d{0,3}|10000)$/.test(String(text ?? ''))
}

/** The contract types the API offered for the chosen expiry, in the fixed display order. */
export function offeredTypes(contracts) {
  const present = new Set(contracts.map((c) => c.instrument_type))
  return ['CE', 'PE', 'FUT'].filter((t) => present.has(t))
}

/** Strike strings offered for one option type, in the API's order (it sorts them; the browser does not). */
export function offeredStrikes(contracts, type) {
  if (type !== 'CE' && type !== 'PE') return []
  return contracts.filter((c) => c.instrument_type === type && c.strike != null).map((c) => c.strike)
}

/** The offered contract the form currently names, or null. A FUT has no strike. */
export function selectedContract(contracts, type, strike) {
  if (type === 'FUT') return contracts.find((c) => c.instrument_type === 'FUT') ?? null
  if (type !== 'CE' && type !== 'PE') return null
  return contracts.find((c) => c.instrument_type === type && c.strike === strike) ?? null
}

/** The body the outcome API takes. Only legs that carry a planned entry and its capture time can be sent (its leg model
 *  requires both); a leg without them stays in the picker's list and is shown as not connected. null when none can be sent. */
export function buildDraft(legs) {
  const priced = legs.filter((l) => l.planned_entry != null && l.captured_at != null)
  if (!priced.length) return null
  return {
    underlying: priced[0].underlying,
    legs: priced.map((l) => ({
      instrument_id: l.instrument_id,
      action: l.action,
      lots: l.lots,
      planned_entry: l.planned_entry,
      captured_at: l.captured_at,
    })),
  }
}
