// P10 Wave 2 (ADR-330 (11), (13); ADR-008; ADR-003): the ONE reader of GET /api/strategies/{id}/plan-watch, the live "Plan watch".
// The server composes every line (fires at / now / distance in rupees and percent / state) from the one engine; this module only
// checks the shape and renames fields. It adds, compares and rounds nothing. A figure the server sent as absent stays null (never 0).
// Answer states of readPlanWatch (it never throws, and a failed read carries NO lines, so an old figure is never kept):
//   ok (planState planned | no_plan | paused; lines may be empty) | not_found (404) | failed (request failed) |
//   unavailable (the reply does not parse) | superseded (a newer request of the same kind replaced this one).
import api, { NEUTRAL_PARTS } from '@/services/api'
import { serverNextAction, serverSentence } from '@/lib/serverText'

/** Least gap between two reads of one Plan watch box. The host ticks every TRACKING_REFRESH_MS (5 s, lib/tracking.js); each read
 *  makes the server run the whole rule check and read prices, and 5 s reads piled up behind a slow price read (27 Nov 2026: 20 s
 *  answers). Trigger distances change slowly; 15 s keeps them fresh enough at a third of the load. The first read (mount, a new
 *  strategy) is immediate. */
export const PLAN_WATCH_MIN_READ_GAP_MS = 15000
/** A compact box on Positions: at most one read a minute, counted from its last answer (Lane R, 27 Nov 2026; see lib/planWatchQueue). */
export const PLAN_WATCH_COMPACT_READ_GAP_MS = 60000

/** The plan-watch request's OWN timeout (Lane R, 27 Nov 2026): the route answered 200 in 6-11 s and the shared client's 10 s gave up on
 *  it. The route's bounds are a 4 s price budget plus an 8 s margin (about 12 s); 20 s covers that. Set per request, never on the client. */
export const PLAN_WATCH_REQUEST_TIMEOUT_MS = 20000

export const PLAN_WATCH_UNAVAILABLE = 'The plan watch is not available right now.'
export const PLAN_WATCH_NOT_FOUND = 'This strategy was not found, so there is nothing to watch.'

const PLAN_STATES = ['planned', 'no_plan', 'paused']
const SECTIONS = ['plan', 'armed']
const LINE_STATES = ['watching', 'fired', 'not_applicable', 'not_computable', 'paused']
const KINDS = ['target', 'stop', 'credit_stop', 'rule', 'index_exit', 'leg_stop']
const UNITS = ['pnl_rupees', 'index_points', 'option_price', 'percent', 'rule_unit']

const isText = (v) => typeof v === 'string' && v.trim() !== ''
// A CatalogueText is a sentence, null or an error object (lib/serverText): the not-checked rules carry their reason as the object
// (Lane R, 27 Nov 2026, AX-14, proven by the PC's raw body: every #209 reason was an object, and the old reader rejected the whole reply).
const sentence = (v) => serverSentence(v) ?? null
// An optional text that is null, absent, empty or blank is NONE; a value that is neither a sentence nor null is present-but-wrong (false).
const textOrNull = (v) => { const t = serverSentence(v); return t === undefined ? false : t }
// The server writes a figure as plain decimal text (Money: format(v, "f")). A leading "+" is read as no sign; anything else is wrong (false).
const figure = (v) => (v === null || v === undefined ? null : typeof v === 'string' && /^[+-]?\d+(\.\d+)?$/.test(v.trim()) ? v.trim().replace(/^\+/, '') : false)

const empty = (state, text = '') => ({
  state, text, planState: null, noPlanText: null, armedHeading: null, pausedText: null, asOfText: null,
  planLines: [], armedLines: [], empty: false,
})

const pick = (list, v, fallback) => (list.includes(v) ? v : fallback)

/** One line of the server's reply. Never null: a field it cannot read degrades THIS line to "not checked" (state not_computable, no
 *  figures, no reason) and its field names go to ONE console.warn (names only, never a value). `i` is the line's place in the reply. */
function readLine(x, i) {
  const bad = []
  const o = x && typeof x === 'object' && !Array.isArray(x) ? x : {}
  if (o !== x) bad.push('line')
  const f = { firesAt: figure(o.fires_at), now: figure(o.now), distanceRs: figure(o.distance_rs), distancePct: figure(o.distance_pct), reason: textOrNull(o.reason ?? null) }
  const names = { firesAt: 'fires_at', now: 'now', distanceRs: 'distance_rs', distancePct: 'distance_pct', reason: 'reason' }
  for (const k of Object.keys(f)) if (f[k] === false) { bad.push(names[k]); f[k] = null }
  const key = isText(o.key) ? o.key : null
  if (key === null) bad.push('key')
  const label = sentence(o.label)
  if (label === null) bad.push('label')
  if (!KINDS.includes(o.kind)) bad.push('kind')
  if (!SECTIONS.includes(o.section)) bad.push('section')
  if (!UNITS.includes(o.unit)) bad.push('unit')
  if (!LINE_STATES.includes(o.state)) bad.push('state')
  const line = {
    key: key ?? `line-${i}`, kind: pick(KINDS, o.kind, 'rule'), section: pick(SECTIONS, o.section, 'plan'), label: label ?? key ?? 'Trigger',
    unit: pick(UNITS, o.unit, 'rule_unit'), state: pick(LINE_STATES, o.state, 'not_computable'), ...f, reasonNext: serverNextAction(o.reason),
  }
  if (bad.length === 0) return line
  console.warn(`plan watch: line ${i} degraded to not checked; unreadable field(s): ${[...new Set(bad)].join(', ')}`)
  return { ...line, state: 'not_computable', firesAt: null, now: null, distanceRs: null, distancePct: null, reason: null, reasonNext: null }
}

/** The view of a reply in the server's shape, or null when its top level is unusable (not an object, no `lines` array) or it answers
 *  another strategy. `id` is the strategy asked for. One bad line never rejects the reply (see readLine). */
export function parsePlanWatch(data, id) {
  if (!data || typeof data !== 'object' || Array.isArray(data) || !Array.isArray(data.lines)) return null
  if (String(data.strategy_id) !== String(id)) return null
  const lines = data.lines.map(readLine)
  const text = (name) => { const v = textOrNull(data[name] ?? null); if (v === false) { console.warn(`plan watch: ${name} unreadable`); return null } return v }
  const noPlanText = text('no_plan_text')
  const armedHeading = text('armed_heading')
  const asOfText = text('as_of_text')
  const planState = pick(PLAN_STATES, data.plan_state, 'planned')
  if (planState !== data.plan_state) console.warn('plan watch: plan_state unreadable')
  if (planState === 'no_plan' && noPlanText === null) return null // ADR-330 (13): the no-plan sentence is the server's; without it the answer is refused (fail closed), not shown empty
  const pausedText = planState === 'paused' ? sentence(data.paused?.text) : null
  const planLines = lines.filter((l) => l.section === 'plan')
  const armedLines = lines.filter((l) => l.section === 'armed')
  return {
    state: 'ok', text: '', planState, noPlanText, armedHeading, pausedText, asOfText,
    planLines, armedLines, empty: lines.length === 0,
  }
}

/** The ONE read. Resolves to a view object (see the header); never throws. */
export async function readPlanWatch(id) {
  let data
  try {
    data = (await api.get(`/strategies/${id}/plan-watch`, { timeout: PLAN_WATCH_REQUEST_TIMEOUT_MS })).data
  } catch (e) {
    if (e?.superseded) return empty('superseded')
    if (e?.status === 404) return empty('not_found', PLAN_WATCH_NOT_FOUND)
    const said = e?.parts && e.parts !== NEUTRAL_PARTS && isText(e.parts.what_happened) ? e.parts.what_happened : PLAN_WATCH_UNAVAILABLE
    return empty('failed', said)
  }
  return parsePlanWatch(data, id) ?? empty('unavailable', PLAN_WATCH_UNAVAILABLE)
}
