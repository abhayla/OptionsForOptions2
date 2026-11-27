// ADR-330 (3), (4): the one reading of the server's unanswered actionable alerts, shared by the header bell and Alerts > Active.
import { reactive } from 'vue'
import api, { NEUTRAL_PARTS } from '@/services/api'

export const PAPER_ALERTS_EMPTY = 'No alerts yet. Alerts start when strategy monitoring rules are added.'

// ADR-330 (3), (4): ONE server read, GET /alerts/active, feeds the header bell AND the Alerts > Active list, so the two cannot
// differ. The browser counts nothing: the number and every text are the server's, printed as sent. A read that fails or does not
// parse leaves NO count and NO rows (an old figure is never kept as if current).
export const activeAlerts = reactive({ count: 0, alerts: [], parts: null, loaded: false })

// ADR-330 (3), REQ-170 AC-3: an alert is announced once per (id, escalated_at): a new id or a later escalation re-announces, nothing else.
const announcedActive = new Set()
const announceKey = (a) => `${a.id}|${a.escalated_at ?? ''}`
let activeSeen = false

// ADR-330 (3)(b): a fired Stops-panel exit is an informational History row (kind stop_fired), popped once as a short
// message. ONE reader: GET /alerts/answered?after=<last id seen>. Rows present at the page's first good read never pop
// (no flood of old messages); a failed or unreadable read pops nothing and changes nothing (bell included: these rows
// are never in activeAlerts).
let stopSeen = null
const stopRowOk = (r) => r && Number.isInteger(r.id) && typeof r.kind === 'string' && typeof r.text === 'string'

/** The stop_fired rows of one answer of GET /alerts/answered that are new since the last good read (never on the first). */
export function takeStopFired(data) {
  if (!data || !Array.isArray(data.items) || !data.items.every(stopRowOk)) return []
  const rows = data.items.filter((r) => r.kind === 'stop_fired')
  let top = stopSeen ?? 0 // the highest row id seen (an id, not an amount: ADR-008 is about money)
  for (const r of rows) if (r.id > top) top = r.id
  const first = stopSeen === null
  const fresh = first ? [] : rows.filter((r) => r.id > stopSeen)
  stopSeen = top
  return fresh
}

export const readStopFired = async () =>
  (await api.get('/alerts/answered', { params: stopSeen === null ? {} : { after: stopSeen } })).data

export function resetActiveAlerts() {
  stopSeen = null
  Object.assign(activeAlerts, { count: 0, alerts: [], parts: null, loaded: false })
  announcedActive.clear()
  activeSeen = false
}

const answerOk = (x) => x && typeof x.code === 'string' && typeof x.label === 'string'
const rowOk = (a) =>
  a && Number.isInteger(a.id) && Number.isInteger(a.strategy_id) && typeof a.text === 'string' && typeof a.kind === 'string' &&
  typeof a.fired_line === 'string' && Array.isArray(a.answers) && a.answers.every(answerOk)

/**
 * Take one answer of GET /alerts/active. Returns the alerts NEW or newly escalated since the last good read (never on the first
 * good read). isDue(alert) is the D-67 quiet rule (ADR-326 (5)): a not-due alert is counted but neither announced nor marked, so it
 * is announced on the poll that finds it due; the default is due (fail open toward telling the trader).
 */
export function takeActive(data, isDue = () => true) {
  if (!data || !Number.isInteger(data.count) || data.count < 0 || !Array.isArray(data.alerts) || !data.alerts.every(rowOk)) {
    dropActive(null)
    return []
  }
  Object.assign(activeAlerts, { count: data.count, alerts: data.alerts, parts: null, loaded: true })
  const due = data.alerts.filter(isDue)
  const fresh = due.filter((a) => !announcedActive.has(announceKey(a)))
  due.forEach((a) => announcedActive.add(announceKey(a)))
  const first = !activeSeen
  activeSeen = true
  return first ? [] : fresh
}

/** A failed read: no count, no rows, the server's reason (or the neutral one). */
export function dropActive(e) {
  Object.assign(activeAlerts, { count: 0, alerts: [], parts: e ? (e.parts ?? NEUTRAL_PARTS) : NEUTRAL_PARTS, loaded: true })
}

export const readActive = async () => (await api.get('/alerts/active')).data

/** Post the user's answer; throws the api error (with its parts) on 404 / 409 / 422 / network. Re-reads Active on success. */
export async function answerAlert(id, code) {
  await api.post(`/alerts/${id}/answer`, { answer: code })
  try {
    takeActive(await readActive())
  } catch (e) {
    dropActive(e)
  }
}

// ADR-330 (3): the History tab = the answered actionable alerts (GET /alerts/answered); a failed read shows no rows and its reason.
export const alertHistory = reactive({ items: [], parts: null, loaded: false })
const historyOk = (h) => h && Number.isInteger(h.id) && typeof h.text === 'string'
export async function loadAlertHistory() {
  try {
    const data = (await api.get('/alerts/answered')).data
    if (!data || !Array.isArray(data.items) || !data.items.every(historyOk)) throw new Error('unreadable')
    Object.assign(alertHistory, { items: data.items, parts: null, loaded: true })
  } catch (e) {
    Object.assign(alertHistory, { items: [], parts: e?.parts ?? NEUTRAL_PARTS, loaded: true })
  }
}

// D-22 / D-71: the Alerts page's third tab = the server's records of every fired stop and every expiry settlement, newest first, text as sent.
export const RECORDS_EMPTY = 'No stops or expiry settlements yet.'
export const paperRecords = reactive({ records: [], parts: null, loaded: false })
const recordOk = (r) => r && typeof r.at === 'string' && typeof r.title === 'string' && typeof r.body === 'string' && Number.isInteger(r.strategy_id)
export async function loadPaperRecords() {
  try {
    const data = (await api.get('/paper/alerts/records')).data
    if (!data || !Array.isArray(data.records) || !data.records.every(recordOk)) throw new Error('unreadable')
    Object.assign(paperRecords, { records: data.records, parts: null, loaded: true })
  } catch (e) {
    Object.assign(paperRecords, { records: [], parts: e?.parts ?? NEUTRAL_PARTS, loaded: true })
  }
}

// IC e2e stage B4 (design decision 10): the OPEN adjustment records of GET /adjustment-opportunities (no longer counted by the bell,
// ADR-330 (4)), read on the SAME tick as the active alerts (no timer, no seen-state store beyond the ids already announced this page load).
// The browser counts nothing but list lengths of the server's own rows; a failed read leaves NO open records (paper count only).
// Issue 8 (ADR-260): each open record also carries the trade's name and the rule's words (the server's own text, printed as sent)
// so the pop-up names the same record.
export const openRecords = reactive({ list: [] }) // [{ id, strategy_id, strategy_name, text }] in the server's order
// Issue 12 (u241): the SAME read's settled records (not open), per strategy, for the trade page's rules line: a rule that fired and cleared.
export const settledRecords = reactive({ byStrategy: {}, state: 'loading' }) // state: 'loading' (not read yet) | 'ok' | 'failed' // { [strategy_id]: [{ id, text, outcome_text, shown_at }] }
const announced = new Set()
let opportunitiesLoaded = false

export function resetOpenRecords() {
  openRecords.list = []
  settledRecords.byStrategy = {}
  settledRecords.state = 'loading'
  announced.clear()
  opportunitiesLoaded = false
}

// ADR-330 (4): the bell = the server's count of unanswered actionable alerts = the Active rows; nothing is added to it.
// ADR-242 (3): a watched level's record (rule id watch.level.above / .below, the server's ofo.adjustment.level_watch.RULE_PREFIX);
// it is not an actionable alert (never in /alerts/active, never on the bell), so the header announces it from the open records
export const LEVEL_WATCH_PREFIX = 'watch.level.'
export const isLevelWatch = (r) => typeof r?.rule_id === 'string' && r.rule_id.startsWith(LEVEL_WATCH_PREFIX)
export const bellCount = () => activeAlerts.count

/** Take one answer of GET /adjustment-opportunities. Returns the NEW open records (never on the first good read). */
export function takeOpportunities(data) {
  const groups = data && Array.isArray(data.groups) ? data.groups : null
  if (!groups) {
    openRecords.list = []
    settledRecords.byStrategy = {}
    settledRecords.state = 'failed'
    return []
  }
  const open = []
  const settled = {}
  for (const g of groups) {
    for (const r of Array.isArray(g?.records) ? g.records : []) {
      if (r && r.outcome === 'open' && Number.isInteger(r.id)) {
        // D-67 (ADR-326 (5)): popup_due is the SERVER's answer (ofo.adjustment.popup_quiet); absent = due (fail open)
        open.push({ id: r.id, rule_id: r.rule_id ?? null, strategy_id: g.strategy_id, strategy_name: g.strategy_name ?? null, text: r.condition || g.label || '', shown_at: r.shown_at ?? g.shown_at ?? null, popup_due: r.popup_due !== false })
      } else if (r && Number.isInteger(r.id) && r.outcome !== 'open') {
        (settled[g.strategy_id] ??= []).push({ id: r.id, text: r.condition || g.label || '', outcome_text: r.outcome_text ?? '', shown_at: r.shown_at ?? g.shown_at ?? null, closed_at: r.closed_at ?? null })
      }
    }
  }
  openRecords.list = open
  settledRecords.byStrategy = settled
  settledRecords.state = 'ok'
  // D-67: a quiet record is counted (openRecords) but not announced yet; it is announced on the poll that finds it due
  const due = open.filter((r) => r.popup_due)
  const fresh = due.filter((r) => !announced.has(r.id))
  due.forEach((r) => announced.add(r.id))
  const first = !opportunitiesLoaded
  opportunitiesLoaded = true
  return first ? [] : fresh
}

export const readOpportunities = async () => (await api.get('/adjustment-opportunities')).data
