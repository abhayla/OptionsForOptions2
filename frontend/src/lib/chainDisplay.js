// Row 33 (REQ-029 AC-2/AC-3/AC-9; ADR-056, ADR-168): which chain columns are shown and which rows pass the filters.
// One set for every user: there is no Guided/Standard/Advanced level (ADR-168 (4)); the Details toggle is the only
// switch. Column key/label pairs taken from PR #509's frontend/src/lib/chainDisplay.js, without its level switch.
// Display only: every value is the server's string (IV and Greeks come from the engine, ADR-008); the filters compare
// those strings as numbers to HIDE rows, never change a number, never touch the selection.

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

/** The line under the table naming what the engine's IV and Greeks rest on, or why there are none (ADR-061). */
export const GREEKS_BASIS_LINES = {
  SPOT_FALLBACK: 'IV and Greeks: estimated from spot (the forward could not be derived from the chain).',
}
export const GREEKS_MISSING_LINES = {
  SPOT_REFUSED: 'IV and Greeks are not shown: the underlying price is not usable right now.',
  FORWARD_UNAVAILABLE: 'IV and Greeks are not shown: the expiry forward could not be derived.',
}

/** ITM/ATM/OTM is read from the calls' side against the server's ATM strike: calls below ATM are ITM (their puts OTM). */
export const MONEYNESS = [['ALL', 'All strikes'], ['ITM', 'ITM calls / OTM puts'], ['ATM', 'ATM'], ['OTM', 'OTM calls / ITM puts']]

export const NO_FILTERS = Object.freeze({ moneyness: 'ALL', minOi: '', minVolume: '', minLtp: '', bidAndAsk: false })

const num = (v) => (v === null || v === undefined || v === '' ? null : Number(v))
const atLeast = (value, min) => num(min) === null || (num(value) !== null && num(value) >= num(min))
const sides = (row) => [row.ce, row.pe].filter(Boolean)

function moneynessOf(row, atm) {
  if (atm === null || atm === undefined) return null
  const d = Number(row.strike) - Number(atm)
  return d === 0 ? 'ATM' : d < 0 ? 'ITM' : 'OTM'
}

/** True when the row passes every filter. A numeric filter passes when EITHER side of the row meets it (a row is one
 *  strike: hiding it for one side's thin market would hide the other side too). With no ATM (no live spot) the
 *  moneyness filter cannot be read, so it hides nothing. */
export function rowPasses(row, filters, atm) {
  const f = { ...NO_FILTERS, ...filters }
  if (f.moneyness !== 'ALL') {
    const m = moneynessOf(row, atm)
    if (m !== null && m !== f.moneyness) return false
  }
  const cells = sides(row)
  const any = (test) => cells.some(test)
  if (!any((c) => atLeast(c.oi, f.minOi))) return false
  if (!any((c) => atLeast(c.volume, f.minVolume))) return false
  if (!any((c) => atLeast(c.ltp, f.minLtp))) return false
  if (f.bidAndAsk && !any((c) => num(c.bid) !== null && num(c.ask) !== null)) return false
  return true
}

/** The rows to show: the server's rows, in order, filtered. Never a new row, never a changed value. */
export function filterRows(rows, filters, atm) {
  return (rows ?? []).filter((r) => rowPasses(r, filters, atm))
}
