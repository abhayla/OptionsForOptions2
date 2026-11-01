// REQ-167 AC-5 / AC-7: the one place the browser reads app-wide limits and waits from (GET /api/settings). Nothing is
// typed here and nothing falls back to a number: until the read answers, `integer` is null and the screen shows its normal
// loading state; a failed read leaves it null (fail closed) and the next call tries again.
import { ref } from 'vue'
import { defineStore } from 'pinia'
import api from '@/services/api'
import { settingsMap, strictInt } from '@/lib/settingsValues'

export const SETTINGS_PATH = '/settings' // relative to the api base (/api)

export const useSettingsValues = defineStore('settingsValues', () => {
  const values = ref(null) // { key: decimal string } once read
  let inflight = null

  /** Read the settings once (shared by every caller); resolves when the answer is in or the read failed. */
  function load() {
    if (values.value !== null) return Promise.resolve()
    inflight ??= api.get(SETTINGS_PATH).then(({ data }) => { values.value = settingsMap(data) })
      .catch(() => { values.value = null })
      .finally(() => { inflight = null })
    return inflight
  }

  /** The whole-number value of `key`, or null while not loaded / not a whole number. */
  const integer = (key) => (values.value === null ? null : strictInt(values.value[key]))

  /** Seconds of `key` as milliseconds for a timer, or null. */
  const millis = (key) => {
    const s = integer(key)
    return s === null ? null : s * 1000
  }

  /** Read (once), then the wait of `key` in milliseconds, or null when it could not be read. Used at the moment a timer
   *  starts, so a screen that never starts one makes no settings read. */
  async function waitMs(key) {
    await load()
    return millis(key)
  }

  return { values, load, integer, millis, waitMs }
})
