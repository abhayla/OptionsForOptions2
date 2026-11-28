// Lane FJ r3 (coordinator rule): a read that has not answered after STILL_LOADING_AFTER_MS keeps its loading state and adds ONE plain line; the failure
// sentence comes only from a real failure or the read's limit (services/api.js SLOW_READ_BUDGETS_MS). Nothing is cancelled here.
import { onBeforeUnmount, ref, watch } from 'vue'

export const STILL_LOADING_AFTER_MS = 4000
export const STILL_LOADING_TEXT = 'Still loading. The server is taking longer than usual to answer.' // new wording, pending owner read (28 Nov 2026)

/** `loading` is a getter. Returns a ref that turns true when the read has been waiting for `afterMs`, and false again when it ends. */
export function useStillLoading(loading, afterMs = STILL_LOADING_AFTER_MS) {
  const still = ref(false)
  let timer = null
  const stop = () => { if (timer !== null) { clearTimeout(timer); timer = null } }
  watch(loading, (on) => {
    stop()
    still.value = false
    if (on) timer = setTimeout(() => { still.value = true; timer = null }, afterMs)
  }, { immediate: true })
  onBeforeUnmount(stop)
  return still
}
