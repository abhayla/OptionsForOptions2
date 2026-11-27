// Lane Y item 1 (REQ-115 AC-4/AC-6, REQ-049 line 38, REQ-165, domain-model line 71; ADR-330 (58)): whether the worker is watching a
// running trade. ONE read of GET /monitoring-state; every sentence comes from the server. Nothing is decided here except
// fail closed: a read that failed, an id the answer does not name, or a status other than "active" is NOT healthy.
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import api from '@/services/api'

export const MONITORING_REFRESH_MS = 30000
export const MONITORING_MAX_AGE_MS = 90000 // an answer older than three refresh cycles is not used
// pending owner read: the words used only when the server could not answer at all
export const MONITORING_UNREAD_BADGE = 'Monitoring paused'
export const MONITORING_UNREAD_HEALTH = 'Health unknown'
export const MONITORING_UNREAD_REASON = 'Could not read whether this trade is being watched.'

/** The reply as a Map id -> entry, or null when it is not our shape (never a guessed "fine"). */
export function readMonitoring(data) {
  const rows = data?.strategies
  if (!Array.isArray(rows)) return null
  const out = new Map()
  for (const r of rows) if (r && Number.isInteger(r.strategy_id)) out.set(r.strategy_id, r)
  return out
}

/** The entry one badge prints: the server's, or the fail-closed one (read failed / id not named / status not "active"). */
export function entryFor(map, id, failed = false) {
  const e = failed ? undefined : map?.get(id) // a failed or old read overrides every cached entry (never a stale "active")
  if (e && e.watch_state === 'active') return e
  if (e) return { ...e, watch_state: 'paused', badge_text: e.badge_text || MONITORING_UNREAD_BADGE, health_text: e.health_text || MONITORING_UNREAD_HEALTH, reason_text: e.reason_text || MONITORING_UNREAD_REASON }
  return { watch_state: 'paused', strategy_id: id, reason: failed ? 'unreadable' : 'not_listed', badge_text: MONITORING_UNREAD_BADGE, health_text: MONITORING_UNREAD_HEALTH, reason_text: MONITORING_UNREAD_REASON, since_text: null }
}

/** The page's one read, repeated on a timer; `loaded` is false until the first answer (nothing is shown before it). */
export function useMonitoringState() {
  const map = ref(null)
  const failed = ref(false)
  const loaded = ref(false)
  const okAt = ref(0)
  let timer = null
  let gone = false
  const refresh = async () => {
    try {
      const m = readMonitoring((await api.get('/monitoring-state')).data)
      if (gone) return
      if (m === null) failed.value = true
      else { map.value = m; failed.value = false; okAt.value = Date.now() }
    } catch {
      if (!gone) failed.value = true
    }
    loaded.value = true
  }
  onMounted(() => { refresh(); timer = setInterval(refresh, MONITORING_REFRESH_MS) })
  onBeforeUnmount(() => { gone = true; clearInterval(timer) })
  const entryOf = (id) => (loaded.value ? entryFor(map.value, id, failed.value || map.value === null || Date.now() - okAt.value > MONITORING_MAX_AGE_MS) : null)
  return { loaded, failed, entryOf, refresh, entries: computed(() => map.value) }
}
