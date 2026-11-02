<!-- GC-SET (REQ-168 AC-2, ADR-222 (6)): the Preferences tab of the Adjustments screen. Each of the user's adjustment
     preferences from GET /api/adjustments/preferences: its value, "Your value" or "Default", the admin default and the
     allowed range. The user changes one (POST .../{key}) or resets it to follow the default (POST .../{key}/reset); the
     server answers with the whole list, which replaces the shown one. A refused value shows the server's reason from the
     422 body, verbatim. Every number is shown exactly as the server sent it (a decimal string, never parsed to a float
     here); a "time" preference travels as the whole number HHMM and is shown and typed as HH:MM. No browser clock is sent.
     A change applies at the next check; a saved plan is not changed. Decision support only. States: loading, ready,
     unavailable. -->
<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import api from '@/services/api'
import ErrorMessage from '@/components/common/ErrorMessage.vue'

const prefs = ref([])
const state = ref('loading') // loading | ready | unavailable
const error = ref(null)
const forms = reactive({}) // key -> { value, note, busy, reason, open }

// The answer's one list per preference (the user's own earlier rows) is the only array in it; read it as `earlier`.
const withEarlier = (p) => ({ ...p, earlier: Object.values(p).find(Array.isArray) ?? [] })
const isTime = (p) => p.unit === 'time'
function clock(hhmm) {
  const n = String(hhmm).padStart(4, '0')
  return `${n.slice(0, 2)}:${n.slice(2)}`
}
function shown(p, v) {
  return isTime(p) && /^\d{1,4}$/.test(String(v)) ? clock(v) : v
}
const TIME_HINT = 'Enter a time as HH:MM, for example 09:30.'
function toHhmm(typed) {
  const m = /^([01]?\d|2[0-3]):([0-5]\d)$/.exec(String(typed).trim())
  if (!m) return null
  return (m[1] + m[2]).replace(/^0+(?=\d)/, '') // "09:30" -> "930": text only, no arithmetic
}
function formFor(key) {
  if (!forms[key]) forms[key] = { value: '', note: '', busy: false, reason: '', open: false }
  return forms[key]
}
function when(iso) {
  return iso ? new Date(iso).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', dateStyle: 'medium', timeStyle: 'short' }) + ' IST' : ''
}

async function load() {
  state.value = 'loading'
  try {
    prefs.value = (await api.get('/adjustments/preferences')).data.preferences.map(withEarlier)
    state.value = 'ready'
  } catch (e) {
    error.value = e
    state.value = 'unavailable'
  }
}

async function save(p) {
  const f = formFor(p.key)
  f.busy = true
  f.reason = ''
  try {
    let value = f.value
    if (isTime(p)) {
      value = toHhmm(f.value)
      if (value === null) {
        f.reason = TIME_HINT
        return
      }
    }
    await api.post(`/adjustments/preferences/${p.key}`, { value, note: f.note })
    f.value = ''
    f.note = ''
    f.open = false
    await load() // read again: the shown list is always the server's
  } catch (e) {
    f.reason = e.reason || 'The change was not saved. Try again.'
  } finally {
    f.busy = false
  }
}

async function reset(p) {
  const f = formFor(p.key)
  f.busy = true
  f.reason = ''
  try {
    await api.post(`/adjustments/preferences/${p.key}/reset`, { note: f.note })
    f.note = ''
    await load()
  } catch (e) {
    f.reason = e.reason || 'The reset was not saved. Try again.'
  } finally {
    f.busy = false
  }
}

// GC-ALERT1 item 6 (REQ-170 Q-AD-1, AC-6): the alert values a user may change come as one small table per trading style.
// A key alerts.<style>.<field> belongs to that style's table; the table title and row names are the server's label split
// at its first ': ' ("Weekly expiry: cool-down, same rule"), the words themselves untouched.
const ALERT_KEY = /^alerts\.([a-z_]+)\./
const general = computed(() => prefs.value.filter((p) => !ALERT_KEY.test(p.key)))
const head = (label) => String(label).split(': ')[0]
const rowLabel = (p) => {
  const name = String(p.label).split(': ').slice(1).join(': ') || String(p.label)
  return name.charAt(0).toUpperCase() + name.slice(1)
}
// The one place a registry `unit` becomes the short word shown after a style-table value; a time carries none (HH:MM).
const UNIT_WORD = { minutes: 'min', percent: '%' }
const withUnit = (p, v) => {
  const val = shown(p, v)
  if (p.key.endsWith('.daily_cap')) return `${val} a day`
  const word = UNIT_WORD[p.unit]
  if (!word) return val
  return word === '%' ? `${val}%` : `${val} ${word}`
}
// The styles are whatever the server sent (alerts.<style>.<field>), in the order it sent them; no style word is written here.
const styleTables = computed(() => {
  const order = []
  for (const p of prefs.value) {
    const style = ALERT_KEY.exec(p.key)?.[1]
    if (style && !order.includes(style)) order.push(style)
  }
  return order.map((style) => ({ style, rows: prefs.value.filter((p) => ALERT_KEY.exec(p.key)?.[1] === style) }))
    .map((t) => ({ ...t, title: head(t.rows[0].label) }))
})

onMounted(load)
</script>

<template>
  <section data-testid="prefs-tab">
    <p class="mb-3 text-sm text-ink-muted">
      Your own starting values for the adjustment checks. A change applies at the next check; a saved plan is not changed.
      Reset makes a preference follow the admin default again.
    </p>
    <p v-if="state === 'loading'" data-testid="prefs-loading">Loading preferences…</p>
    <div v-else-if="state === 'unavailable'" data-testid="prefs-unavailable">
      <ErrorMessage v-if="error?.parts" :parts="error.parts" />
      <p v-else>The preferences could not be read, so no value is shown.</p>
      <button type="button" class="mt-2 underline" data-testid="prefs-retry" @click="load">Try again</button>
    </div>
    <ul v-else class="divide-y divide-line">
      <li v-for="p in general" :key="p.key" class="py-3" :data-testid="`pref-${p.key}`">
        <div class="flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <h3 class="font-semibold">{{ p.label }}</h3>
          <span data-testid="pref-value">{{ shown(p, p.value) }}</span>
          <span class="chip border-line bg-surface-muted text-xs text-ink-muted" data-testid="pref-source">{{ p.source === 'yours' ? 'Your value' : 'Default' }}</span>
          <span class="text-sm text-ink-muted">Unit: {{ isTime(p) ? 'time (IST)' : p.unit }}</span>
          <span class="text-sm text-ink-muted" data-testid="pref-admin-default">Admin default: {{ shown(p, p.admin_default) }}</span>
          <span class="text-sm text-ink-muted" data-testid="pref-range">Allowed: {{ shown(p, p.min) }} to {{ shown(p, p.max) }}</span>
          <button type="button" class="underline" data-testid="pref-edit" @click="formFor(p.key).open = !formFor(p.key).open">Change</button>
        </div>
        <p class="text-sm text-ink-muted">{{ p.what_it_changes }}</p>
        <div v-if="formFor(p.key).open" :data-testid="`pref-form-${p.key}`" class="mt-2">
          <form class="flex flex-wrap items-end gap-2" @submit.prevent="save(p)">
            <label v-if="isTime(p)">New time (IST, HH:MM, from {{ shown(p, p.min) }} to {{ shown(p, p.max) }})
              <input v-model="formFor(p.key).value" data-testid="pref-input" class="block border px-1" type="time" required />
            </label>
            <label v-else>New value (from {{ p.min }} to {{ p.max }})
              <input v-model="formFor(p.key).value" data-testid="pref-input" class="block border px-1" inputmode="decimal" required />
            </label>
            <label>Note (optional)
              <input v-model="formFor(p.key).note" data-testid="pref-note" class="block border px-1" maxlength="500" />
            </label>
            <button type="submit" :disabled="formFor(p.key).busy" data-testid="pref-save">Save</button>
            <button type="button" :disabled="formFor(p.key).busy" data-testid="pref-reset" @click="reset(p)">Reset to default</button>
          </form>
        </div>
        <p v-if="formFor(p.key).reason" role="alert" class="mt-1 text-error" data-testid="pref-refusal">{{ formFor(p.key).reason }}</p>
        <details v-if="p.earlier.length" :data-testid="`pref-earlier-${p.key}`" class="mt-1 text-sm">
          <summary>Earlier values ({{ p.earlier.length }})</summary>
          <ul>
            <li v-for="(h, i) in p.earlier" :key="i" data-testid="pref-earlier-row">
              {{ h.value === null ? 'Reset to the admin default' : shown(p, h.value) }} from {{ when(h.effective_from) }}
            </li>
          </ul>
        </details>
      </li>
    </ul>
    <section v-for="t in styleTables" :key="t.style" class="mt-4" :data-testid="`prefs-alerts-${t.style}`">
      <h3 class="font-semibold" data-testid="prefs-alerts-title">{{ t.title }}</h3>
      <table class="w-full table-auto text-sm">
        <thead>
          <tr class="text-left text-ink-muted">
            <th class="py-1 pr-2 font-normal">Setting</th>
            <th class="py-1 pr-2 font-normal">Value</th>
            <th class="py-1 pr-2 font-normal">Admin</th>
            <th class="py-1 font-normal"><span class="sr-only">Change</span></th>
          </tr>
        </thead>
        <tbody>
          <template v-for="p in t.rows" :key="p.key">
            <tr class="border-t border-line align-top" :data-testid="`pref-${p.key}`">
              <td class="break-words py-1 pr-2" data-testid="pref-name">{{ rowLabel(p) }}</td>
              <td class="py-1 pr-2">
                <span data-testid="pref-value">{{ withUnit(p, p.value) }}</span>
                <span class="chip ml-1 border-line bg-surface-muted text-xs text-ink-muted" data-testid="pref-source">{{ p.source === 'yours' ? 'Your value' : 'Default' }}</span>
              </td>
              <td class="py-1 pr-2" data-testid="pref-admin-default">{{ withUnit(p, p.admin_default) }}</td>
              <td class="py-1"><button type="button" class="underline" data-testid="pref-edit" @click="formFor(p.key).open = !formFor(p.key).open">Change</button></td>
            </tr>
            <tr v-if="formFor(p.key).open || formFor(p.key).reason">
              <td colspan="4" class="pb-2">
                <form v-if="formFor(p.key).open" class="flex flex-wrap items-end gap-2" :data-testid="`pref-form-${p.key}`" @submit.prevent="save(p)">
                  <label>New value (from {{ shown(p, p.min) }} to {{ shown(p, p.max) }})
                    <input v-if="isTime(p)" v-model="formFor(p.key).value" data-testid="pref-input" class="block border px-1" type="time" required />
                    <input v-else v-model="formFor(p.key).value" data-testid="pref-input" class="block border px-1" inputmode="decimal" required />
                  </label>
                  <button type="submit" :disabled="formFor(p.key).busy" data-testid="pref-save">Save</button>
                  <button type="button" :disabled="formFor(p.key).busy" data-testid="pref-reset" @click="reset(p)">Reset to default</button>
                </form>
                <p v-if="formFor(p.key).reason" role="alert" class="mt-1 text-error" data-testid="pref-refusal">{{ formFor(p.key).reason }}</p>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </section>
  </section>
</template>
