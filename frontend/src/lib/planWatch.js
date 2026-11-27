// P10 Wave 2 (ADR-330 (11), (13); ADR-008; ADR-003): the ONE reader of GET /api/strategies/{id}/plan-watch, the live "Plan watch".
// The server composes every line (fires at / now / distance in rupees and percent / state) from the one engine; this module only
// checks the shape and renames fields. It adds, compares and rounds nothing. A figure the server sent as absent stays null (never 0).
// Answer states of readPlanWatch (it never throws, and a failed read carries NO lines, so an old figure is never kept):
//   ok (planState planned | no_plan | paused; lines may be empty) | not_found (404) | failed (request failed) |
//   unavailable (the reply does not parse) | superseded (a newer request of the same kind replaced this one).
import api, { NEUTRAL_PARTS } from '@/services/api'

/** Least gap between two reads of one Plan watch box. The host ticks every TRACKING_REFRESH_MS (5 s, lib/tracking.js); each read
 *  makes the server run the whole rule check and read prices, and 5 s reads piled up behind a slow price read (27 Nov 2026: 20 s
 *  answers). Trigger distances change slowly; 15 s keeps them fresh enough at a third of the load. The first read (mount, a new
 *  strategy) is immediate. */
export const PLAN_WATCH_MIN_READ_GAP_MS = 15000
/** A compact box on Positions: at most one read a minute, counted from its last answer (Lane R, 27 Nov 2026; see lib/planWatchQueue). */
export const PLAN_WATCH_COMPACT_READ_GAP_MS = 60000

export const PLAN_WATCH_UNAVAILABLE = 'The plan watch is not available right now.'
export const PLAN_WATCH_NOT_FOUND = 'This strategy was not found, so there is nothing to watch.'

const PLAN_STATES = ['planned', 'no_plan', 'paused']
const SECTIONS = ['plan', 'armed']
const LINE_STATES = ['watching', 'fired', 'not_applicable', 'not_computable', 'paused']
const KINDS = ['target', 'stop', 'credit_stop', 'rule', 'index_exit', 'leg_stop']
const UNITS = ['pnl_rupees', 'index_points', 'option_price', 'percent', 'rule_unit']

const isText = (v) => typeof v === 'string' && v.trim() !== ''
const textOrNull = (v) => (v === null || v === undefined ? null : isText(v) ? v : false) // false = present but wrong
const figure = (v) => (v === null ? null : typeof v === 'string' && /^-?\d+(\.\d+)?$/.test(v.trim()) ? v.trim() : false)

const empty = (state, text = '') => ({
  state, text, planState: null, noPlanText: null, armedHeading: null, pausedText: null, asOfText: null,
  planLines: [], armedLines: [], empty: false,
})

function readLine(x) {
  if (!x || typeof x !== 'object') return null
  const f = { firesAt: figure(x.fires_at), now: figure(x.now), distanceRs: figure(x.distance_rs), distancePct: figure(x.distance_pct), reason: textOrNull(x.reason ?? null) }
  if (!isText(x.key) || !isText(x.label) || !KINDS.includes(x.kind) || !SECTIONS.includes(x.section) || !UNITS.includes(x.unit) || !LINE_STATES.includes(x.state)) return null
  if (Object.values(f).includes(false)) return null
  return { key: x.key, kind: x.kind, section: x.section, label: x.label, unit: x.unit, state: x.state, ...f }
}

/** The view of a reply in the server's shape, or null when it does not parse. `id` is the strategy asked for. */
export function parsePlanWatch(data, id) {
  if (!data || typeof data !== 'object' || !PLAN_STATES.includes(data.plan_state) || !Array.isArray(data.lines)) return null
  if (String(data.strategy_id) !== String(id)) return null
  const lines = data.lines.map(readLine)
  if (lines.includes(null)) return null
  const noPlanText = textOrNull(data.no_plan_text ?? null)
  const armedHeading = textOrNull(data.armed_heading ?? null)
  const asOfText = textOrNull(data.as_of_text ?? null)
  if (noPlanText === false || armedHeading === false || asOfText === false) return null
  if (data.plan_state === 'no_plan' && noPlanText === null) return null // ADR-330 (11): the no-plan sentence is the server's
  let pausedText = null
  if (data.plan_state === 'paused') {
    pausedText = data.paused && isText(data.paused.text) ? data.paused.text : null
    if (pausedText === null) return null
  }
  const planLines = lines.filter((l) => l.section === 'plan')
  const armedLines = lines.filter((l) => l.section === 'armed')
  return {
    state: 'ok', text: '', planState: data.plan_state, noPlanText, armedHeading, pausedText, asOfText,
    planLines, armedLines, empty: lines.length === 0,
  }
}

/** The ONE read. Resolves to a view object (see the header); never throws. */
export async function readPlanWatch(id) {
  let data
  try {
    data = (await api.get(`/strategies/${id}/plan-watch`)).data
  } catch (e) {
    if (e?.superseded) return empty('superseded')
    if (e?.status === 404) return empty('not_found', PLAN_WATCH_NOT_FOUND)
    const said = e?.parts && e.parts !== NEUTRAL_PARTS && isText(e.parts.what_happened) ? e.parts.what_happened : PLAN_WATCH_UNAVAILABLE
    return empty('failed', said)
  }
  return parsePlanWatch(data, id) ?? empty('unavailable', PLAN_WATCH_UNAVAILABLE)
}
