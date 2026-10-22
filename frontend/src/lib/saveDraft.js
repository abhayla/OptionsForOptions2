// Save Draft / reopen helpers (W-071; REQ-038 AC-5, ADR-057, ADR-068 item 1, ADR-075, ADR-008). Pure functions.
// Adapted from the legacy strategy save/load calls only (legacy-reuse row 146): no client P&L, no price fallback.
// Strings stay strings: a planned entry and a capture time are sent and shown exactly as the API gave them.

/** The Save Draft body. Per leg exactly: contract_id, action, quantity (units = lots x lot size, a count, not money) and,
 *  when the leg has one, planned_entry + captured_at together. Never a live price, never an instrument id. */
export function buildSaveBody(legs, rulesRef) {
  const body = {
    underlying: legs[0].underlying,
    legs: legs.map((l) => {
      const out = { contract_id: l.contract_id, action: l.action, quantity: l.lots * l.lot_size }
      if (l.planned_entry != null && l.captured_at != null) {
        out.planned_entry = l.planned_entry
        out.captured_at = l.captured_at
      }
      return out
    }),
  }
  if (rulesRef) body.rules_ref = rulesRef
  return body
}

/** True when a draft can be saved: it has legs and every leg names its catalogue contract and a lot size. */
export function canSaveLegs(legs) {
  return legs.length > 0 && legs.every((l) => Number.isInteger(l.contract_id) && Number.isInteger(l.lot_size) && l.lot_size > 0)
}

/** The distinct expiries of a saved definition (one catalogue call each rebuilds its legs). */
export function expiriesOf(definition) {
  return [...new Set(definition.legs.map((l) => l.expiry))]
}

/** Rebuild the screen's legs from a saved definition (LegOut) and the catalogue contracts of its expiries.
 *  Planned entry and capture time come from the saved leg exactly; a pre-ADR-075 leg has neither and stays without
 *  (needsReprice) - nothing is captured here. Returns null when a leg's contract is not in the catalogue answer or does
 *  not divide into whole lots (fail closed: the caller shows the catalogue error and keeps what is on screen). */
export function legsFromSaved(definition, contracts) {
  const byId = new Map(contracts.map((c) => [c.contract_id, c]))
  const out = []
  for (const [i, l] of definition.legs.entries()) {
    const c = byId.get(l.contract_id)
    if (!c || c.exchange_segment !== l.exchange_segment || c.exchange_token !== l.exchange_token) return null
    if (!Number.isInteger(l.quantity) || l.quantity % c.lot_size !== 0) return null
    out.push({
      id: `saved-${i}`,
      underlying: definition.underlying,
      instrument_id: `${l.exchange_segment}:${l.exchange_token}`,
      contract_id: l.contract_id,
      symbol: c.symbol,
      expiry: c.expiry,
      instrument_type: c.instrument_type,
      strike: c.strike,
      lot_size: c.lot_size,
      action: l.action,
      lots: l.quantity / c.lot_size,
      planned_entry: l.planned_entry ?? null,
      captured_at: l.captured_at ?? null,
      source: null,
      reason_code: l.planned_entry == null ? 'needs_reprice' : null,
    })
  }
  return out
}

/** Load saved strategy `id` (GET /strategies/{id}) and rebuild its legs from the catalogue contracts of its expiries.
 *  `client` is the api module. Throws on a request failure (its mapped error) or when the legs will not rebuild. */
export async function fetchSavedLegs(client, id) {
  return (await fetchSavedDraft(client, id)).legs
}

/** W-122: the saved legs AND the revision they were loaded at (the revision a later action, e.g. Start tracking, is
 *  based on: the page's own loaded revision, never a freshly fetched one). */
export async function fetchSavedDraft(client, id) {
  const body = (await client.get(`/strategies/${id}`)).data
  const def = body.definition
  const contracts = []
  for (const expiry of expiriesOf(def)) {
    contracts.push(...(await client.get(`/catalogue/${def.underlying}/contracts?expiry=${expiry}`)).data.contracts)
  }
  const legs = legsFromSaved(def, contracts)
  if (!legs) throw new Error('unreadable draft') // fail closed: the caller keeps what is on screen
  return { legs, revision: Number.isInteger(body.revision) ? body.revision : null }
}
