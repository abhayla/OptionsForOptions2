// GC-TP step 6b (REQ-084 AC-1, AC-2; ADR-208): the what-if Target block's request side. The browser sends only
// `target_level` (whole index points, as typed or as the slider's value) and `target_at` (an ISO time with +05:30); every
// figure it shows comes from the reply's `target` block (see TargetBlock.vue). Nothing here touches money (ADR-008): the
// date slider's stops are clock times (a position on a slider), and the level slider takes its limits and step from the reply.
export const TARGET_DEBOUNCE_MS = 250 // REQ-084: a drag sends one request, 250 ms after the last move
const MIN = 60000
const IST_OFFSET = 330 * MIN // India time is a fixed UTC+05:30
const DAY = 24 * 60 * MIN
const OPEN = 9 * 60 + 15 // the last day's 15-minute steps run from the 09:15 open
const CLOSE = 15 * 60 + 30 // to the 15:30 close
const STEP_MIN = 15
const pad = (n) => String(n).padStart(2, '0')

/** An instant (ms) as 'YYYY-MM-DDTHH:MM:SS+05:30'. */
function istIso(ms) {
  const d = new Date(ms + IST_OFFSET)
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}T${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}+05:30`
}

/** The earliest expiry (a 'YYYY-MM-DD' text) among the reply's legs, or null. */
export function firstExpiry(legs) {
  const dates = (legs ?? []).map((l) => l?.expiry).filter((e) => typeof e === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(e))
  return dates.length ? dates.reduce((a, b) => (b < a ? b : a)) : null
}

/** The date slider's stops from now (the reply's valuation time, stop 0 = no target date) to the first expiry's 15:30 IST:
 *  daily at the valuation's time of day before the expiry day, then 15-minute steps on the expiry day. Each stop is the ISO
 *  text sent as `target_at`; the server clamps anything outside (target.clamp). [] when the reply gives no usable time. */
export function dateStops(valuation, expiry) {
  const start = Date.parse(valuation)
  const day = typeof expiry === 'string' ? Date.parse(`${expiry}T00:00:00+05:30`) : NaN
  if (!Number.isFinite(start) || !Number.isFinite(day)) return []
  const stops = [valuation]
  const startMinute = Math.floor((start + IST_OFFSET) % DAY / MIN) // minute of the IST day
  const startDay = Math.floor((start + IST_OFFSET) / DAY) * DAY - IST_OFFSET // that day's 00:00 IST
  for (let d = startDay + DAY; d < day; d += DAY) stops.push(istIso(d + startMinute * MIN))
  for (let m = OPEN; m <= CLOSE; m += STEP_MIN) {
    const ms = day + m * MIN
    if (ms > start) stops.push(istIso(ms))
  }
  return stops
}

/** The request fields for a pick { active, level, dateIndex }: only what the user moved. A started target with neither
 *  moved asks for the target at now (the reply then carries the limits). Nothing started: no target field at all. */
export function targetFields(pick, stops) {
  if (!pick?.active) return {}
  const out = {}
  if (pick.level) out.target_level = String(pick.level)
  if (pick.dateIndex > 0 && stops[pick.dateIndex]) out.target_at = stops[pick.dateIndex]
  if (!out.target_level && !out.target_at && stops[0]) out.target_at = stops[0]
  return out
}

/** True for a whole number of index points (the only form the route accepts). */
export const isWholePoints = (text) => /^[1-9]\d{0,6}$/.test(String(text).trim())

/** A debounced caller: runs `fn` once, `ms` after the last call. */
export function debounced(fn, ms = TARGET_DEBOUNCE_MS) {
  let timer = null
  const call = (...args) => {
    clearTimeout(timer)
    timer = setTimeout(() => { timer = null; fn(...args) }, ms)
  }
  call.cancel = () => { clearTimeout(timer); timer = null }
  return call
}
