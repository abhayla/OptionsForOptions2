// Save Draft / reopen helpers (W-071; REQ-038 AC-5, ADR-057, ADR-068 item 1, ADR-075, ADR-008). Pure functions.
// Adapted from the legacy strategy save/load calls only (legacy-reuse row 146): no client P&L, no price fallback.
import { CONTRACT_UNAVAILABLE, contractName, expiryText } from '@/lib/displayFormat'
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
  if (typeof name === 'string') body.name = name // REQ-134 AC-1: sent as typed; the server trims, checks 1 to 20 and refuses
  return body
}

/** REQ-134 AC-2: the update body (PUT /strategies/{id}): the same legs and the revision the page loaded. It carries no name:
 *  a Save on a saved strategy never asks for or changes one (a rename is its own route). */
export function buildUpdateBody(legs, rulesRef, revision) {
  return { ...buildSaveBody(legs, rulesRef), expected_revision: revision } // no name argument: the body has no name key
}

// REQ-134 (AC-1, AC-2): the name's default, cap and Save As suffix. The server owns the rule (ofo.strategy.definition
// STRATEGY_NAME_TYPED_MAX (ADR-183), explanations DEFAULT_STRATEGY_NAME); these are the field's prefill and its length hint only.
export const STRATEGY_NAME_DEFAULT = 'New Strategy'
export const STRATEGY_NAME_MAX = 20
export const SAVE_AS_SUFFIX = ' copy'

// pending owner read (25 Nov 2026), D-53: the name box stops at the limit, so the limit is said beside it in three states:
// room left, exactly at the limit (typing stops), over it (a name stored before ADR-183 keeps its length but cannot be saved as is)
export function nameLimitText(length) {
  if (length > STRATEGY_NAME_MAX) return `This name is longer than ${STRATEGY_NAME_MAX} characters: shorten it to save.`
  if (length === STRATEGY_NAME_MAX) return `That is the ${STRATEGY_NAME_MAX}-character limit: nothing more can be typed.`
  return `A name can be up to ${STRATEGY_NAME_MAX} characters.`
}

/** ADR-192 (REQ-134 AC-2): the Save As pre-fill. The original name (the API's quotes stripped; the default when there is none)
 *  is cut from its end, and trailing spaces dropped, so that the original part plus " copy" is 20 characters or fewer. */
export function saveAsName(shown) {
  const original = Array.from(plainName(shown) ?? STRATEGY_NAME_DEFAULT) // characters (code points), as the server counts
  const room = STRATEGY_NAME_MAX - SAVE_AS_SUFFIX.length
  return `${(original.length > room ? original.slice(0, room).join('').trimEnd() : original.join(''))}${SAVE_AS_SUFFIX}`
}

/** The API sends a name as the user's quoted words (ADR-003, template strategy_name_shown): "NIFTY Oct condor" arrives
 *  wrapped in one pair of double quotes. Strips exactly one outer pair for display and for prefilling a name field; inner
 *  quote marks stay ('"say "hi""' -> 'say "hi"'). A value not wrapped in a pair, or empty inside it, is returned as
 *  received (fail closed, never guessed); a non-text value gives null. */
export function plainName(shown) {
  if (typeof shown !== 'string' || !shown) return null
  if (shown.length >= 3 && shown.startsWith('"') && shown.endsWith('"')) return shown.slice(1, -1)
  // ADR-330 (19)(b): an alert's title label is the quoted name plus the server's '(#172, 1 Dec)' / '(#172)': only the name's quotes go
  const label = /^"(.+)"( \(#\d+(?:, \d{1,2} [A-Z][a-z]{2})?\))$/s.exec(shown)
  if (label) return `${label[1]}${label[2]}`
  return shown
}

/** REQ-134 AC-3: rename a saved strategy (PATCH /strategies/{id}/name) with the revision the caller holds. The one rename call for
 *  the list and the builder. Returns the reply (id, quoted name, revision unchanged); throws the mapped error on a refusal and
 *  an Error when the reply carries no name (fail closed: nothing is shown as renamed). `name` is sent as typed; the server owns the rule. */
export async function renameStrategy(client, id, revision, name) {
  // D-65: a paper trade opened in Drafts Mode holds no revision (the paper book has none): read the saved copy's revision first,
  // never send null (the server refuses it as "missing or not in the expected form"); an unreadable answer sends nothing
  let held = revision
  if (!Number.isInteger(held)) {
    held = (await client.get(`/strategies/${id}`)).data?.revision
    if (!Number.isInteger(held)) throw new Error('unreadable answer')
  }
  const done = (await client.patch(`/strategies/${id}/name`, { name, expected_revision: held })).data
  if (typeof done?.name !== 'string') throw new Error('unreadable answer')
  return done
}

/** The label of a saved strategy row: its name, or `fallback` when the server (an older one) sent none. */
export function strategyLabel(row, fallback) {
  return plainName(row?.name) ?? fallback
}

/** ADR-330 (19): the label every strategy LIST shows (My Strategies, Live Strategies, Positions > Paper, Home): the name with the
 *  trade's number and expiry beside it, 'Short Iron Condor (#172, 1 Dec)', so four strategies of one name can be told apart.
 *  `expiries` = the expiry dates (ISO text) the reply carries for that strategy; exactly ONE distinct readable date prints it
 *  (written by the one expiry formatter); none or several print only the number, '(#172)'. A strategy with no name shows the
 *  caller's `fallback` as is (it already carries the number). Text only, no date arithmetic. */
export function strategyListLabel({ name, id, expiries = [], fallback }) {
  const base = plainName(name)
  if (base === null) return fallback
  const days = [...new Set((Array.isArray(expiries) ? expiries : [expiries]).map((e) => expiryText(e)).filter((t) => t !== null))]
  return `${base} (#${id}${days.length === 1 ? `, ${days[0]}` : ''})`
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
  return draftFromReply(client, (await client.get(`/strategies/${id}`)).data)
}

/** The saved legs, id, revision and name of one StrategyOut reply (a read, or a restore's answer: one leg builder for both). */
export async function draftFromReply(client, body) {
  const def = body.definition
  const contracts = []
  for (const expiry of expiriesOf(def)) {
    contracts.push(...(await client.get(`/catalogue/${def.underlying}/contracts?expiry=${expiry}`)).data.contracts)
  }
  const legs = legsFromSaved(def, contracts)
  if (!legs) throw new Error('unreadable draft') // fail closed: the caller keeps what is on screen
  return { legs, id: Number.isInteger(body.id) ? body.id : null, revision: Number.isInteger(body.revision) ? body.revision : null, name: typeof body.name === 'string' ? body.name : null }
}
