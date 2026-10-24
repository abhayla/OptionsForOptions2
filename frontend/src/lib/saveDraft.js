// Save Draft / reopen helpers (W-071; REQ-038 AC-5, ADR-057, ADR-068 item 1, ADR-075, ADR-008). Pure functions.
// Adapted from the legacy strategy save/load calls only (legacy-reuse row 146): no client P&L, no price fallback.
import { CONTRACT_UNAVAILABLE, contractName } from '@/lib/displayFormat'
// Strings stay strings: a planned entry and a capture time are sent and shown exactly as the API gave them.

/** The Save Draft body. Per leg exactly: contract_id, action, quantity (units = lots x lot size, a count, not money) and,
 *  when the leg has one, planned_entry + captured_at together (+ entry_source 'typed' for a typed price). Never a live price, never an instrument id. */
export function buildSaveBody(legs, rulesRef, name) {
  const body = {
    underlying: legs[0].underlying,
    legs: legs.map((l) => {
      const out = { contract_id: l.contract_id, action: l.action, quantity: l.lots * l.lot_size }
      if (l.planned_entry != null && l.captured_at != null) {
        out.planned_entry = l.planned_entry
        out.captured_at = l.captured_at
        if (l.typed === true) out.entry_source = 'typed' // REQ-077 AC-4: the mark goes with the pair; a captured leg sends none
      }
      return out
    }),
  }
  if (rulesRef) body.rules_ref = rulesRef
  if (typeof name === 'string') body.name = name // REQ-134 AC-1: sent as typed; the server trims, checks 1 to 40 and refuses
  return body
}

/** REQ-134 AC-2: the update body (PUT /strategies/{id}): the same legs and the revision the page loaded. It carries no name:
 *  a Save on a saved strategy never asks for or changes one (a rename is its own route). */
export function buildUpdateBody(legs, rulesRef, revision) {
  return { ...buildSaveBody(legs, rulesRef), expected_revision: revision } // no name argument: the body has no name key
}

// REQ-134 (AC-1, AC-2): the name's default, cap and Save As suffix. The server owns the rule (ofo.strategy.definition
// STRATEGY_NAME_MAX, explanations DEFAULT_STRATEGY_NAME); these are the field's prefill and its length hint only.
export const STRATEGY_NAME_DEFAULT = 'New Strategy'
export const STRATEGY_NAME_MAX = 40
export const SAVE_AS_SUFFIX = ' copy'

/** The API sends a name as the user's quoted words (ADR-003, template strategy_name_shown): "NIFTY Oct condor" arrives
 *  wrapped in one pair of double quotes. Strips exactly one outer pair for display and for prefilling a name field; inner
 *  quote marks stay ('"say "hi""' -> 'say "hi"'). A value not wrapped in a pair, or empty inside it, is returned as
 *  received (fail closed, never guessed); a non-text value gives null. */
export function plainName(shown) {
  if (typeof shown !== 'string' || !shown) return null
  if (shown.length >= 3 && shown.startsWith('"') && shown.endsWith('"')) return shown.slice(1, -1)
  return shown
}

/** The label of a saved strategy row: its name, or `fallback` when the server (an older one) sent none. */
export function strategyLabel(row, fallback) {
  return plainName(row?.name) ?? fallback
}

/** REQ-134 AC-4: 'NIFTY 27 Oct 22500 PE and 3 more' from the list row's first_leg and leg_count (Sensibull screen 117).
 *  null when the row carries neither (an older server); the contract-unavailable text when the first leg is unreadable. */
export function legsLine(row) {
  const first = row?.first_leg
  if (!first || !Number.isInteger(row.leg_count) || row.leg_count < 1) return null
  const name = contractName({ underlying: row.underlying, expiry: first.expiry, strike: first.strike, instrument: first.instrument })
  if (name === CONTRACT_UNAVAILABLE) return name
  return row.leg_count > 1 ? `${name} and ${row.leg_count - 1} more` : name
}

/** REQ-134 AC-4: the tracked state as the server sent it: true, false, null (could not be read: never 'Not tracked'),
 *  or absent (an older server: nothing shown). */
export function trackedText(tracked) {
  if (tracked === true) return 'Tracked'
  if (tracked === false) return 'Not tracked'
  return tracked === null ? 'Tracking not known' : null
}

/** REQ-134 AC-4: the rows whose name contains `text`, case-insensitive, as typed (a row with no name never matches a typed
 *  text; an empty text keeps every row). */
export function searchStrategies(rows, text) {
  const wanted = String(text ?? '').trim().toLowerCase()
  if (!wanted) return rows
  return rows.filter((r) => (plainName(r?.name) ?? '').toLowerCase().includes(wanted))
}

export const noMatchText = (text) => `No saved strategy matches ${String(text).trim()}`

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
    if (l.contract_state !== 'live') {
      // Issue #500: the server gives a leg that is no longer live no segment and token, only its state. It is shown with
      // that reason, from the saved leg's own terms, and never priced (no instrument id; buildDraft sends nothing).
      if (!l.contract_state || l.exchange_segment != null || l.exchange_token != null) return null // unknown shape
      out.push({
        id: `saved-${i}`,
        underlying: definition.underlying,
        instrument_id: null,
        contract_id: l.contract_id,
        symbol: null,
        expiry: l.expiry,
        instrument_type: l.instrument,
        strike: l.strike,
        lot_size: null,
        action: l.action,
        lots: null,
        planned_entry: null,
        captured_at: null,
        source: null,
        reason_code: l.contract_state,
        not_live: true,
      })
      continue
    }
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
      typed: l.entry_source === 'typed', // REQ-077 AC-4/AC-7: the saved mark is shown and re-sent as it was
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
  return { legs, revision: Number.isInteger(body.revision) ? body.revision : null, name: typeof body.name === 'string' ? body.name : null }
}
