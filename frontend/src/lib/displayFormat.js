// Display formats for the Strategy Builder screen (W-072; ADR-086). Display only: the API keeps sending ids and ISO
// times. No money value is read, parsed or formatted here (ADR-008); a strike is a contract label, handled as text.

export const CONTRACT_UNAVAILABLE = 'Contract details not available'
export const TIME_UNAVAILABLE = 'Time not available'

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const MONTH_BY_TEXT = Object.fromEntries(MONTHS.map((m, i) => [String(i + 1).padStart(2, '0'), m])) // '01' -> 'Jan'

/** '2026-10-19' -> '19 Oct', or null when it is not a calendar date string. */
export function expiryText(expiry) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(expiry ?? ''))
  if (!m) return null
  const month = MONTH_BY_TEXT[m[2]]
  const day = m[3].replace(/^0/, '')
  return month && /^([1-9]|[12]\d|3[01])$/.test(day) ? `${day} ${month}` : null
}

/** '23200.00' -> '23200'; a strike with a real fraction keeps it, minus trailing zeros ('23212.50' -> '23212.5'). Text only,
 *  no number is computed. Null when the text is not a plain decimal. */
function strikeText(strike) {
  const m = /^(\d+)(?:\.(\d*))?$/.exec(String(strike ?? '').trim())
  if (!m) return null
  const fraction = (m[2] ?? '').replace(/0+$/, '')
  return fraction ? `${m[1]}.${fraction}` : m[1]
}

/** The one home of the strike-label rule (#582 item 8; Sensibull screen 032 prints integers): '22150.00' -> '22150',
 *  '22150.50' -> '22150.5'. Empty, null or non-numeric text comes back unchanged. */
export function strikeLabel(text) {
  return strikeText(text) ?? text
}

/** REQ-135 AC-2: an expiry with the days left the SERVER counted (IST): '27 Oct (6 days)', 'Today (0 days)'. The browser
 *  counts nothing: a missing or non-integer day count shows the date alone, '9 Nov' (never a guessed number, and never
 *  the raw '2026-11-09', REQ-148 AC-2); text that is not a date comes back as it was sent. */
export function expiryWithDays(expiry, days) {
  const day = expiryText(expiry)
  if (!day) return expiry ?? ''
  if (!Number.isInteger(days) || days < 0) return day
  return days === 0 ? 'Today (0 days)' : `${day} (${days} days)`
}

/** The server's `expiry_days` list ([{expiry, days}], 1:1 with the expiries) as an object by expiry; unreadable -> {}. */
export function daysByExpiry(list) {
  return Object.fromEntries((Array.isArray(list) ? list : []).filter((x) => typeof x?.expiry === 'string').map((x) => [x.expiry, x.days]))
}

const commaless = (t) => String(t ?? '').replace(/,/g, '').trim()

/** D-B29 / D-B30 / D-B39 (REQ-146 AC-5, REQ-151, ADR-204): the instrument as Sensibull prints it, "1 x 3 Nov 22600 CE".
 *  `lots` is the server's own whole-lot count for the leg (the reply's `lots`; the browser divides nothing, ADR-008), or
 *  null when the reply did not give one for this row: then the quantity form "100 units 3 Nov 22600 CE" is printed
 *  (never a fraction of a lot, never a guessed count). A FUT leg has no strike or CE/PE: "1 x 3 Nov FUT"; an option
 *  leg without a strike prints "-" there. A date that is not a date stays as sent. `parts` are the table's display texts
 *  (quantity, expiry, strike, instrument). */
export function instrumentText(parts, lots) {
  const qty = commaless(parts?.quantity)
  const head = Number.isInteger(lots) && lots > 0 ? `${lots} x` : /^\d+$/.test(qty) ? `${qty} units` : ''
  const type = parts?.instrument ?? ''
  const strike = type === 'FUT' ? '' : (strikeLabel(commaless(parts?.strike)) || '-')
  const day = expiryText(parts?.expiry) ?? parts?.expiry ?? ''
  return [head, day, strike, type].filter(Boolean).join(' ')
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

// date, time, optional fraction of any length, then Z or +hh:mm (#244: one pattern, no Date.parse on the input text)
const ISO_INSTANT = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:Z|([+-])(\d{2}):(\d{2}))$/

/** The instant of a strict ISO string in milliseconds, or null: an impossible calendar date (2026-02-30), time or offset
 *  is refused, never rolled over to the next month. */
function isoMillis(text) {
  const m = ISO_INSTANT.exec(text.trim())
  if (!m) return null
  const [y, mo, d, h, mi, s] = m.slice(1, 7).map((x) => +x)
  const day = new Date(Date.UTC(y, mo - 1, d, h, mi, s))
  if (day.getUTCFullYear() !== y || day.getUTCMonth() !== mo - 1 || day.getUTCDate() !== d) return null
  if (h > 23 || mi > 59 || s > 59) return null
  let offset = 0
  if (m[7]) {
    if (+m[8] > 23 || +m[9] > 59) return null
    offset = (m[7] === '-' ? -1 : 1) * (+m[8] * 60 + +m[9]) * 60000
  }
  return day.getTime() - offset
}

/** An ISO instant (with an offset or Z) as '15 Oct 2026, 11:59:59 IST', always in India time. Unparseable, impossible, or
 *  without an offset (its zone would be a guess), -> TIME_UNAVAILABLE, never the raw string. */
export function istTime(iso) {
  const ms = typeof iso === 'string' ? isoMillis(iso) : null
  if (ms === null) return TIME_UNAVAILABLE
  const p = Object.fromEntries(IST.formatToParts(new Date(ms)).map((x) => [x.type, x.value]))
  return `${p.day} ${MONTHS[new Date(ms + 19800000).getUTCMonth()]} ${p.year}, ${p.hour}:${p.minute}:${p.second} IST`
}

/** An ISO instant (with an offset or Z) as 'HH:MM:SS' in India time, or null when it cannot be read (never the raw string,
 *  never the browser clock). The time part of istTime. */
export function istClock(iso) {
  const t = istTime(iso)
  return t === TIME_UNAVAILABLE ? null : t.slice(-12, -4)
}

/** ADR-197: the caption word of an entry captured from the last close ("Close, 27 Oct 2026, 15:30:00 IST"). */
export const CLOSE_CAPTION_PREFIX = 'Close, '

/** Review 3 (REQ-077 AC-1): a captured price's caption. "captured 10:35:12" when the capture is on today's India date,
 *  else "captured 21 Oct 2026, 10:35:12 IST"; null when the time is missing or unreadable. `now` is only the clock used to
 *  name today (an ISO instant; the browser clock when omitted): no number is computed from it. */
export function capturedCaption(iso, now = new Date().toISOString(), closeAt = null) {
  // ADR-197: an entry captured outside market hours is the close, labelled with the quote's own last-price time
  // (`close_at`, sent by the server), never the capture clock time
  if (closeAt != null) {
    const c = istTime(closeAt)
    if (c !== TIME_UNAVAILABLE) return `${CLOSE_CAPTION_PREFIX}${c}`
  }
  const t = istTime(iso)
  if (t === TIME_UNAVAILABLE) return null
  const today = istTime(now)
  const day = (x) => x.slice(0, x.indexOf(','))
  return day(t) === day(today) ? `captured ${t.slice(-12, -4)}` : `captured ${t}`
}

/** Max profit / max loss line of an outcome summary: the server string untouched, "Unlimited" when its flag is set, "-" when
 *  absent. `side` is "profit" or "loss". One home for the Builder page and the Live Strategies card. */
export function maxLine(summary, side) {
  if (!summary) return '-'
  if (summary[`max_${side}_unlimited`]) return 'Unlimited'
  // REQ-148 AC-4/AC-6 (G-065, ADR-143): the engine gave no single maximum (legs on more than one expiry); the reason is
  // the summary's own sentence under the figure. Never '-', '0' or a number the browser made up.
  return summary[`max_${side}`] ?? MAX_NOT_AVAILABLE
}

export const MAX_NOT_AVAILABLE = 'Not available'

/** REQ-081 AC-1 (screens 012, 107): Indian-style thousands separators on the server's money TEXT: '68007.07' ->
 *  '68,007.07', '-17436.25' -> '-17,436.25', 'Rs 1234567.5' -> 'Rs 12,34,567.5'. Display only: the digits are regrouped as
 *  text, never read as numbers (ADR-008); text with no 4-or-more-digit whole part comes back as it was. */
export function groupMoney(text) {
  if (typeof text !== 'string') return text
  return text.replace(/(?<![\d.,])(\d{4,})(?![\d,])/g, (whole) => {
    const rest = whole.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ',')
    return `${rest},${whole.slice(-3)}`
  })
}
