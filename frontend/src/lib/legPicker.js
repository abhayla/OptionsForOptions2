// Leg picker helpers (W-068; REQ-035 AC-8, ADR-068, ADR-008). Pure functions; no price or P&L is ever computed here.
// Strings only: a strike and a planned entry stay exactly the strings the API sent.

export { UNDERLYINGS } from '@/lib/underlyings'

/** The one wording for a draft that has no live data (the backend constant NOT_CONNECTED_LABEL, ADR-020 Q185). */
export const NOT_CONNECTED_LABEL = 'Draft — Live data not connected'

/** Catalogue template `draft_leg_needs_reprice` (owner-approved 2026-10-15). A reopened leg saved without a planned entry (pre-ADR-075 draft): nothing is captured until the user reprices it. */
export const REPRICE_PROMPT = 'This leg was saved without a planned entry. Reprice it to see its numbers.'

/** Issue #500: a reopened leg whose stored contract is no longer live (the server's contract_state: contract_retired,
 *  contract_delisted, token_reassigned, contract_missing). It carries no instrument id, so it is never priced; the words
 *  follow the catalogue template `tracking_contract_not_live`. */
export const LEG_NOT_LIVE_LABEL =
  'This leg is no longer a live contract (expired, delisted, or its exchange token now belongs to another contract). It is not priced.'

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
  // Issue #500 (fail closed): a strategy with a leg that is no longer live sends no outcome request at all; pricing the
  // other legs alone would show a P&L that is not the strategy's.
  if (legs.some((l) => l.not_live)) return null
  // W-148 (REQ-076 AC-6): an unticked leg is left out of every number, so it is never sent to the outcome.
  const included = legs.filter((l) => l.included !== false)
  // REQ-077 AC-9 (fail closed): a strategy is priced only when EVERY included leg has its entry and capture time; one
  // unpriced leg next to a priced one would otherwise be priced as if it did not exist. The server's own rule (a leg
  // without an entry -> not connected / reprice) then never has to run because that leg is never sent.
  if (included.some((l) => l.planned_entry == null || l.captured_at == null)) return null
  const priced = included
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

// ---- REQ-080 (W-147): the Strikes and Futures tabs, multi-select and the depth popup. Display only: every price, IV,
// delta, forward and depth level is the string the server sent; a null shows '-' with the server's reason. ----

/** REQ-080 AC-1: strikes each side of ATM the user can choose (the backend's WIDTHS); 10 is the default. */
export const STRIKE_WIDTHS = Object.freeze([10, 20, 30, 40])
export const DEFAULT_STRIKE_WIDTH = 10
/** How many lots (or lot-size multiples) a cell's selector lists. */
export const LOT_CHOICES = 10
/** The picker refreshes the open list this often (the server reads the feed at most once a second, ADR-012). */
export const PICKER_REFRESH_MS = 5000
/** The depth popup refreshes this often while open: at most once a second (REQ-080 AC-7). */
export const DEPTH_REFRESH_MS = 1000

export const PRICE_MISSING = '-'
export const DEPTH_NOT_AVAILABLE = 'Depth not available'
export const FORWARD_LABEL = 'Forward used for pricing'

const LIST_REASON_TEXT = Object.freeze({
  CATALOGUE_UNREADABLE: 'The list of contracts could not be read right now.',
  CATALOGUE_EMPTY: 'No contracts are listed for this underlying yet.',
  EXPIRY_UNKNOWN: 'This expiry is not in the list of contracts.',
  NOT_CONNECTED: 'Live data is not connected, so no prices are shown.',
  SPOT_MISSING: 'The index price is not available, so no ATM is marked.',
  FEED_STALE: 'The live feed is not fresh, so no prices are shown as current.',
  WAITING_FOR_PRICES: 'Waiting for the first prices from the live feed.',
  SOME_PRICES_MISSING: 'Some strikes have no live price right now; they show a dash.',
})
const FUTURE_REASON_TEXT = Object.freeze({
  NOT_OFFERED: 'Futures prices are not offered by the data provider.',
  NOT_STREAMABLE: 'This future cannot be streamed right now.',
  NO_QUOTE: 'No price has been received for this future yet.',
  FEED_STALE: 'The live feed is not fresh, so no price is shown as current.',
  NOT_LIVE: 'This future has no live price.',
})
const FUTURES_LIST_REASON_TEXT = Object.freeze({
  CATALOGUE_UNREADABLE: LIST_REASON_TEXT.CATALOGUE_UNREADABLE,
  CATALOGUE_EMPTY: 'No futures are listed for this underlying yet.',
  NOT_CONNECTED: LIST_REASON_TEXT.NOT_CONNECTED,
  SPOT_MISSING: 'The index price is not available, so no forward can be shown.',
})
const FORWARD_REASON_TEXT = Object.freeze({
  SPOT_MISSING: 'The index price is not available.',
  NOT_PRICEABLE: 'The engine cannot price this expiry right now.',
})
const DEPTH_REASON_TEXT = Object.freeze({
  NO_SESSION: 'The broker account is not connected.',
  FEED_STALE: 'The live feed is not fresh.',
  NOT_STREAMING: 'This contract is not streaming.',
  NO_DEPTH_RECEIVED: 'No depth has been received for this contract yet.',
  DEPTH_EMPTY: 'The depth the feed sent is empty.',
})
const DAY_STATS_REASON_TEXT = Object.freeze({
  NOT_OFFERED: 'The data provider does not send day figures.',
  NOT_HELD: 'The day figures are not held right now.',
  FEED_NOT_HEALTHY: 'The live feed is not healthy, so day figures are not shown.',
  PACKET_WITHOUT_DAY_FIELDS: 'The last update carried no day figures.',
})
const UNKNOWN_REASON = 'The reason was not given.'

const wording = (map, code) => (typeof code === 'string' && Object.hasOwn(map, code) ? map[code] : UNKNOWN_REASON)
/** Closed maps: an unrecognised code reads as "not given", never a guess. */
export const listReasonText = (code) => (code == null ? null : wording(LIST_REASON_TEXT, code))
export const futureReasonText = (code) => (code == null ? null : wording(FUTURE_REASON_TEXT, code))
export const futuresListReasonText = (code) => (code == null ? null : wording(FUTURES_LIST_REASON_TEXT, code))
export const forwardReasonText = (code) => (code == null ? null : wording(FORWARD_REASON_TEXT, code))
export const depthReasonText = (code) => wording(DEPTH_REASON_TEXT, code)
export const dayStatsReasonText = (code) => wording(DAY_STATS_REASON_TEXT, code)

/** How the strikes list is centred when there is no live spot (REQ-080 AC-5): the dated last known spot, or the middle strike. */
export function centreText(strikes, timeText) {
  if (!strikes || strikes.centre === 'LIVE_SPOT') return null
  if (strikes.centre === 'LAST_KNOWN_SPOT') {
    const at = strikes.spot_at ? timeText(strikes.spot_at) : ''
    return `Centred on the last known index price ${strikes.spot ?? ''}${at ? `, as of ${at}` : ''}.`
  }
  if (strikes.centre === 'MIDDLE_STRIKE') return 'ATM unknown - no live price. The list is centred on the middle listed strike.'
  return UNKNOWN_REASON
}

/** A price-like cell value as shown: the server's string, or '-' when it sent none. */
export const shown = (value) => (value == null || value === '' ? PRICE_MISSING : String(value))

/** The lots selector's choices. Lots mode lists 1, 2, 3 ...; quantity mode lists multiples of the lot size the server
 *  sent for that contract (REQ-080 AC-4), none when it sent no usable lot size. `value` is always a whole number of lots. */
export function lotChoices(mode, lotSize) {
  const size = Number.isInteger(lotSize) && lotSize > 0 ? lotSize : null
  if (mode === 'quantity' && size === null) return []
  return Array.from({ length: LOT_CHOICES }, (_, i) => ({
    value: i + 1,
    label: mode === 'quantity' ? String((i + 1) * size) : String(i + 1),
  }))
}

/** The offered contract with this instrument id (segment:token), or null: a strike row maps to its catalogue contract. */
export function contractByInstrumentId(contracts, id) {
  return contracts.find((c) => instrumentId(c.exchange_segment, c.exchange_token) === id) ?? null
}

/** W-195 (UI-202): the OI bar's display scale - each cell's OI as a percent of the largest OI in the rows on screen,
 *  keyed by instrument id. A drawing width only, never shown as a figure and never a money number (ADR-008); the OI
 *  itself is shown as the server sent it. A missing or non-integer OI draws no bar. */
export function oiBarPercents(rows) {
  const cells = (rows ?? []).flatMap((r) => [r?.ce, r?.pe]).filter((c) => c && Number.isInteger(c.oi))
  const largest = cells.reduce((m, c) => (c.oi > m ? c.oi : m), 0)
  const out = {}
  if (largest > 0) for (const c of cells) out[c.instrument_id] = (c.oi * 100) / largest
  return out
}

/** W-195 (UI-202): which half of each row is in the money, read from the server's ATM flag and the ascending row order
 *  only (calls below the ATM row, puts above it). No ATM row (no live spot) shades nothing: never guessed. */
export function itmSides(rows) {
  const atm = (rows ?? []).findIndex((r) => r.is_atm)
  return (rows ?? []).map((_, i) => ({ ce: atm >= 0 && i < atm, pe: atm >= 0 && i > atm }))
}
