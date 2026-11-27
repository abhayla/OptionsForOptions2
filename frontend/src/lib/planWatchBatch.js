// Lane H (27 Nov 2026, REQ-049 AC-4): the ONE reader of GET /api/plan-watch?strategy_ids=1,2,3, the Plan watch of a whole
// Positions list in ONE request (the page asked once per row; 20 rows made 20 requests that the server ran one after another).
// Per row the server answers either the single route's reply ("ok": parsed by the same parsePlanWatch) or that route's
// refusal ("refused": its status and its message), so one bad row never hides the others. This module adds, compares and rounds
// nothing. It never throws; a failed whole request gives EVERY asked id a failed view (no old figure is kept).
// Result: a Map id -> view, the same view shape readPlanWatch gives for that id (state ok | not_found | failed | unavailable).
import api, { NEUTRAL_PARTS } from '@/services/api'
import { PLAN_WATCH_NOT_FOUND, PLAN_WATCH_UNAVAILABLE, parsePlanWatch } from './planWatch'

/** The server answers at most this many rows in one request (routes/plan_watch_batch.py MAX_ROWS). */
export const PLAN_WATCH_BATCH_MAX_ROWS = 20
/** The one request's own timeout: the rows run one after another on the server, so it is the single read's 20 s. */
export const PLAN_WATCH_BATCH_TIMEOUT_MS = 20000

const isText = (v) => typeof v === 'string' && v.trim() !== ''
const failedView = (state, text) => ({
  state, text, planState: null, noPlanText: null, armedHeading: null, pausedText: null, asOfText: null,
  planLines: [], armedLines: [], empty: false,
})

function viewOfItem(item, id) {
  if (item.state === 'ok') return parsePlanWatch(item.watch, id) ?? failedView('unavailable', PLAN_WATCH_UNAVAILABLE)
  if (item.status === 404) return failedView('not_found', PLAN_WATCH_NOT_FOUND)
  const said = item.refusal && isText(item.refusal.what_happened) ? item.refusal.what_happened : PLAN_WATCH_UNAVAILABLE
  return failedView('failed', said)
}

/** Read the Plan watch of `ids` (at most PLAN_WATCH_BATCH_MAX_ROWS) in one request. Resolves to Map id -> view; never throws. */
export async function readPlanWatchBatch(ids) {
  const asked = [...new Set(ids.map(String))]
  const views = new Map()
  let data
  try {
    data = (await api.get(`/plan-watch?strategy_ids=${asked.join(',')}`, { timeout: PLAN_WATCH_BATCH_TIMEOUT_MS })).data
  } catch (e) {
    if (e?.superseded) { for (const id of asked) views.set(id, failedView('superseded', '')); return views }
    const said = e?.parts && e.parts !== NEUTRAL_PARTS && isText(e.parts.what_happened) ? e.parts.what_happened : PLAN_WATCH_UNAVAILABLE
    for (const id of asked) views.set(id, failedView('failed', said))
    return views
  }
  const items = data && Array.isArray(data.items) ? data.items : []
  for (const id of asked) {
    const item = items.find((x) => x && String(x.strategy_id) === id)
    views.set(id, item ? viewOfItem(item, id) : failedView('unavailable', PLAN_WATCH_UNAVAILABLE))
  }
  return views
}
