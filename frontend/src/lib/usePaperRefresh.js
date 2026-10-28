// GC-BP F-1, one home: the re-read loop of every paper-tracking view (TrackingPanel and the Paper strategies list).
// One read at a time (a tick while a read is in flight does nothing); an answer for a key no longer shown is dropped; a
// failed read goes to onError, whose caller shows NO figure (an old figure is never left on screen as if current); the
// timer is cleared on unmount. refreshNow() is the explicit re-read after an action: it queues one more read if one is in
// flight, so the answer shown is never older than the action.
import { onBeforeUnmount } from 'vue'
import { TRACKING_REFRESH_MS } from '@/lib/tracking'

export function usePaperRefresh({ key, enabled = () => true, read, onData, onError }) {
  let reading = false
  let again = false
  async function refresh() {
    const k = key()
    if (!enabled() || reading || !k) return
    reading = true
    try {
      const data = await read(k)
      if (k !== key()) return
      onData(data)
    } catch (e) {
      if (k === key()) onError(e)
    } finally {
      reading = false
      if (again) {
        again = false
        refresh()
      }
    }
  }
  function refreshNow() {
    if (reading) again = true
    else refresh()
  }
  const timer = setInterval(refresh, TRACKING_REFRESH_MS)
  onBeforeUnmount(() => {
    clearInterval(timer)
    again = false
  })
  return { refresh, refreshNow }
}
