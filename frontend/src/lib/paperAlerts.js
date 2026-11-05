// GC-TP step 7b (REQ-109 AC-8; ADR-207 (5)): the one reading of the server's paper alerts, shared by the header bell and the
// Alerts page. The browser counts nothing: the unread number and every text are the server's, printed as sent. An answer
// that does not read, or a failed read, leaves NO count and NO rows (an old figure is never kept as if current).
import { reactive } from 'vue'
import api, { NEUTRAL_PARTS } from '@/services/api'

export const PAPER_ALERTS_EMPTY = 'No alerts yet. Alerts start when strategy monitoring rules are added.'

export const paperAlerts = reactive({ unread: 0, alerts: [], parts: null, loaded: false })

export function resetPaperAlerts() {
  Object.assign(paperAlerts, { unread: 0, alerts: [], parts: null, loaded: false })
}

const rowOk = (a) => a && Number.isInteger(a.id) && typeof a.created_at === 'string' && typeof a.title === 'string' && typeof a.body === 'string'

/** Take one answer of GET /paper/alerts or POST /paper/alerts/read. Returns true when it read. */
export function takeAlerts(data) {
  if (!data || !Number.isInteger(data.unread) || data.unread < 0 || !Array.isArray(data.alerts) || !data.alerts.every(rowOk)) {
    dropAlerts(null)
    return false
  }
  Object.assign(paperAlerts, { unread: data.unread, alerts: data.alerts, parts: null, loaded: true })
  return true
}

/** A failed read: no count, no rows, the server's reason (or the neutral one). */
export function dropAlerts(e) {
  Object.assign(paperAlerts, { unread: 0, alerts: [], parts: e ? (e.parts ?? NEUTRAL_PARTS) : NEUTRAL_PARTS, loaded: true })
}

export const readPaperAlerts = async () => (await api.get('/paper/alerts')).data

/** Mark every alert read (one POST). A failure keeps what is shown; the next read brings the server's count back. */
export async function markPaperAlertsRead() {
  try {
    takeAlertsKeepRows((await api.post('/paper/alerts/read')).data)
  } catch {
    /* rows stay; the bell count comes from the next read */
  }
}
// after marking read the rows on screen stay (the user is looking at them); only the unread number follows the server
function takeAlertsKeepRows(data) {
  if (data && Number.isInteger(data.unread) && data.unread >= 0) paperAlerts.unread = data.unread
}

// IC e2e stage B4 (design decision 10): the bell also counts the OPEN adjustment records of GET /adjustment-opportunities,
// read on the SAME tick as the paper alerts (no timer, no seen-state store beyond the ids already announced this page load).
// The browser counts nothing but list lengths of the server's own rows; a failed read leaves NO open records (paper count only).
export const openRecords = reactive({ list: [] }) // [{ id, strategy_id }] in the server's order
const announced = new Set()
let opportunitiesLoaded = false

export function resetOpenRecords() {
  openRecords.list = []
  announced.clear()
  opportunitiesLoaded = false
}

export const bellCount = () => paperAlerts.unread + openRecords.list.length

/** Take one answer of GET /adjustment-opportunities. Returns the NEW open records (never on the first good read). */
export function takeOpportunities(data) {
  const groups = data && Array.isArray(data.groups) ? data.groups : null
  if (!groups) {
    openRecords.list = []
    return []
  }
  const open = []
  for (const g of groups) {
    for (const r of Array.isArray(g?.records) ? g.records : []) {
      if (r && r.outcome === 'open' && Number.isInteger(r.id)) open.push({ id: r.id, strategy_id: g.strategy_id })
    }
  }
  openRecords.list = open
  const fresh = open.filter((r) => !announced.has(r.id))
  open.forEach((r) => announced.add(r.id))
  const first = !opportunitiesLoaded
  opportunitiesLoaded = true
  return first ? [] : fresh
}

export const readOpportunities = async () => (await api.get('/adjustment-opportunities')).data
