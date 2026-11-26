// D-48 (REQ-078 AC-11): the underlying's listed expiries for the "Change expiry" controls, read from the one catalogue reader
// (GET /api/catalogue/{underlying}/expiries, the leg picker's own). Texts and dates only: the browser never builds an expiry
// (ADR-008) and sends back exactly the date text the server listed.
import { ref, watch } from 'vue'
import api from '@/services/api'
import { daysByExpiry } from '@/lib/displayFormat'

export const EXPIRY_LIST_UNREADABLE = 'The expiry list could not be read. Try again in a moment.'
export const NO_OTHER_EXPIRY = 'No other expiry is listed.'

/** `underlying` is a getter. Answer states: loading (`state` 'loading'), read (`list` of { expiry, days }), unreadable
 *  ('failed', never a guessed list), nothing listed (`list` empty). */
export function useExpiryChoices(underlying) {
  const list = ref([])
  const state = ref('loading')
  let seq = 0
  async function load(name) {
    const mine = ++seq
    list.value = []
    if (!name) { state.value = 'loading'; return }
    state.value = 'loading'
    try {
      const res = await api.get(`/catalogue/${name}/expiries`)
      if (mine !== seq) return
      const days = daysByExpiry(res.data?.expiry_days)
      list.value = (Array.isArray(res.data?.expiries) ? res.data.expiries : []).map((expiry) => ({ expiry, days: days[expiry] }))
      state.value = 'read'
    } catch {
      if (mine !== seq) return
      state.value = 'failed'
    }
  }
  watch(underlying, load, { immediate: true })
  return { list, state }
}
