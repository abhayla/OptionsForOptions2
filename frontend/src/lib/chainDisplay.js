// Row 33 (REQ-029 AC-2/AC-3/AC-9; ADR-056, ADR-168): which chain columns are shown and which rows pass the filters.
// One set for every user: there is no Guided/Standard/Advanced level (ADR-168 (4)); the Details toggle is the only
// switch. Column key/label pairs taken from PR #509's frontend/src/lib/chainDisplay.js, without its level switch.
// No price, strike, OI or volume maths here (ADR-008): the server marks each row's moneyness and applies the numeric
// filters (they travel as request fields); the browser only matches a word and passes the user's typed text on.

/** REQ-029 AC-2: the default columns per side, IV included for every user. */
export const DEFAULT_FIELDS = [['ltp', 'LTP'], ['change', 'Change'], ['oi', 'OI'], ['volume', 'Volume'], ['iv', 'IV']]
/** REQ-029 AC-3: what the Details view adds, the same for every user. */
export const DETAIL_FIELDS = [
  ['bid', 'Bid'], ['ask', 'Ask'], ['oi_change', 'OI Change'],
  ['delta', 'Delta'], ['gamma', 'Gamma'], ['theta', 'Theta'], ['vega', 'Vega'],
]

/** The columns per side: AC-2's defaults, plus AC-3's fields when Details is on. Takes no user level. */
export function fieldsFor(details) {
  return details ? [...DEFAULT_FIELDS, ...DETAIL_FIELDS] : [...DEFAULT_FIELDS]
}

/** REQ-029 AC-9 strike range: strikes either side of ATM the server is asked for (chain_push.MAX_STRIKES_EACH_SIDE). */
export const STRIKE_RANGES = [5, 10, 15]

/** The line naming what the engine's IV and Greeks rest on, or why there are none (ADR-061: never silent). */
export const GREEKS_BASIS_LINES = {
  SPOT_FALLBACK: 'IV and Greeks: estimated from spot (the forward could not be derived from the chain).',
}
export const GREEKS_MISSING_LINES = {
  SPOT_REFUSED: 'IV and Greeks are not shown: the underlying price is not usable right now.',
  FORWARD_UNAVAILABLE: 'IV and Greeks are not shown: the expiry forward could not be derived.',
}

/** The columns the engine computes from the spot (IV and the four Greeks): the ones that carry the stale label. */
export const GREEK_KEYS = ['iv', 'delta', 'gamma', 'theta', 'vega']

/** REQ-072 AC-2: the label of one column, taken as the server sent it ("stale since 09:20 IST", "delayed, as of 09:20
 *  IST"). Only the IV and Greek columns carry it, and only when the server sent one (a live spot sends none). Never
 *  built or timed here (ADR-008). */
export function greeksStaleLabel(view, key) {
  if (view?.market_closed === true) return '' // ADR-177: the one market-closed banner carries it
  const label = view?.greeks_label
  return GREEK_KEYS.includes(key) && typeof label === 'string' ? label : ''
}

/** The server's row.moneyness is read on the calls' side: ITM calls are OTM puts. */
export const MONEYNESS = [['ALL', 'All strikes'], ['ITM', 'ITM calls / OTM puts'], ['ATM', 'ATM'], ['OTM', 'OTM calls / ITM puts']]

export const NO_FILTERS = Object.freeze({ moneyness: 'ALL', minOi: '', minVolume: '', minLtp: '', bidAndAsk: false })

/** The rows to show: the server's rows, in order, matched on the server's moneyness word. Never a changed value. */
export function filterRows(rows, moneyness) {
  return moneyness === 'ALL' ? [...(rows ?? [])] : (rows ?? []).filter((r) => r.moneyness === moneyness)
}

/** The request fields for the server-side filters: only the ones set, the user's text passed on as typed. */
export function filterParams(filters) {
  const f = { ...NO_FILTERS, ...filters }
  const out = {}
  const text = (v) => (v === null || v === undefined ? '' : String(v).trim())
  if (text(f.minOi)) out.min_oi = text(f.minOi)
  if (text(f.minVolume)) out.min_volume = text(f.minVolume)
  if (text(f.minLtp)) out.min_ltp = text(f.minLtp)
  if (f.bidAndAsk) out.bid_and_ask = true
  return out
}

/** True when any server-side filter is on (an empty answer then means "nothing matches", not "no data"). */
export const anyServerFilter = (filters) => Object.keys(filterParams(filters)).length > 0
