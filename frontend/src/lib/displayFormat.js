// Display formats for the Strategy Builder screen (W-072; ADR-086). Display only: the API keeps sending ids and ISO
// times. No money value is read, parsed or formatted here (ADR-008); a strike is a contract label, handled as text.

export const CONTRACT_UNAVAILABLE = 'Contract details not available'
export const TIME_UNAVAILABLE = 'Time not available'

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const MONTH_BY_TEXT = Object.fromEntries(MONTHS.map((m, i) => [String(i + 1).padStart(2, '0'), m])) // '01' -> 'Jan'

/** '2026-10-19' -> '19 Oct', or null when it is not a calendar date string. */
function expiryText(expiry) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(expiry ?? ''))
  if (!m) return null
  const month = MONTH_BY_TEXT[m[2]]
  const day = m[3].replace(/^0/, '')
  return month && /^([1-9]|[12]\d|3[01])$/.test(day) ? `${day} ${month}` : null
}

/** '23200.00' -> '23200'; a strike with a real fraction keeps it ('23212.50'). Text only, no number is computed. */
function strikeText(strike) {
  const m = /^(\d+)(?:\.(\d*))?$/.exec(String(strike ?? '').trim())
  if (!m) return null
  return /^0*$/.test(m[2] ?? '') ? m[1] : `${m[1]}.${m[2]}`
}

/** The leg's contract name: '<UNDERLYING> <D Mon> <strike> <CE|PE>', or '<UNDERLYING> <D Mon> FUT'. Built from underlying,
 *  expiry, strike and type only; never from an instrument id or a broker trading symbol. A leg missing any of them shows
 *  CONTRACT_UNAVAILABLE. The type is `instrument_type` (picker legs) or `instrument` (outcome answer legs). */
export function contractName(leg) {
  const type = leg?.instrument_type ?? leg?.instrument
  const day = expiryText(leg?.expiry)
  const underlying = typeof leg?.underlying === 'string' && leg.underlying ? leg.underlying : null
  if (!underlying || !day) return CONTRACT_UNAVAILABLE
  if (type === 'FUT') return `${underlying} ${day} FUT`
  const strike = strikeText(leg?.strike)
  if ((type !== 'CE' && type !== 'PE') || !strike) return CONTRACT_UNAVAILABLE
  return `${underlying} ${day} ${strike} ${type}`
}

/** Name a leg that may lack contract fields (an outcome answer leg): fill the gaps from `pool` (the page's draft legs) by
 *  instrument_id, and from `underlying`. Still incomplete -> CONTRACT_UNAVAILABLE. */
export function nameFromPool(leg, pool, underlying) {
  const known = (pool ?? []).find((p) => p.instrument_id === leg?.instrument_id) ?? {}
  return contractName({
    underlying: leg?.underlying ?? known.underlying ?? underlying,
    expiry: leg?.expiry ?? known.expiry,
    instrument_type: leg?.instrument_type ?? leg?.instrument ?? known.instrument_type,
    strike: leg?.strike ?? known.strike,
  })
}

const IST = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Asia/Kolkata', day: 'numeric', month: 'short', year: 'numeric',
  hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
})

/** An ISO instant (with an offset or Z) as '15 Oct 2026, 11:59:59 IST', always in India time. Unparseable, or without an
 *  offset (its zone would be a guess), -> TIME_UNAVAILABLE, never the raw string. */
export function istTime(iso) {
  if (typeof iso !== 'string' || !/(Z|[+-]\d{2}:?\d{2})$/i.test(iso.trim())) return TIME_UNAVAILABLE
  const ms = Date.parse(iso)
  if (Number.isNaN(ms)) return TIME_UNAVAILABLE
  const p = Object.fromEntries(IST.formatToParts(new Date(ms)).map((x) => [x.type, x.value]))
  return `${p.day} ${MONTHS[new Date(ms + 19800000).getUTCMonth()]} ${p.year}, ${p.hour}:${p.minute}:${p.second} IST`
}
