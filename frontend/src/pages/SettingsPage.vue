<!-- App settings (GC-SET step 2; REQ-167 AC-2, AC-3, AC-5): every app-wide number a calculation uses, by group, with the
     value in force, its default, when it took effect and who set it, and the earlier values. The admin changes a value from a
     stated time (now by default), resets it to the default (a new row, never a delete), and adds a charge rate set with
     its source address. Every number is shown exactly as the server sent it (a decimal string: never parsed to a float
     here). A refused change shows the server's reason inline. States of the page: loading, ready, unavailable. -->
<script setup>
import PageHeader from '@/components/common/PageHeader.vue'
import { onMounted, reactive, ref } from 'vue'
import api from '@/services/api'
import ErrorMessage from '@/components/common/ErrorMessage.vue'

const CHARGE_FIELDS = [
  ['brokerage_per_order', 'Brokerage per order (rupees)'],
  ['stt_sell_rate', 'STT on sell premium (fraction)'],
  ['stt_exercise_rate', 'STT on exercise (fraction)'],
  ['transaction_rate_nse_fo', 'NSE transaction charge (fraction)'],
  ['transaction_rate_bse_fo', 'BSE transaction charge (fraction)'],
  ['sebi_rate', 'SEBI charge (fraction)'],
  ['stamp_buy_rate', 'Stamp duty on buy premium (fraction)'],
  ['gst_rate', 'GST (fraction)'],
]
const RATE_HINT = 'Rates are fractions: enter 0.001 for 0.1%. Brokerage is in rupees (for example 20).'
const STATE_WORD = { in_force: 'In force', scheduled: 'Scheduled', earlier: 'Earlier' }

const data = ref(null)
const state = ref('loading') // loading | ready | unavailable
const error = ref(null)
const forms = reactive({}) // key -> { value, effective_from, note, busy, reason, open }
const charges = reactive({ open: false, busy: false, reason: '', source_url: '', read_on: '', note: '', ...Object.fromEntries(CHARGE_FIELDS.map(([k]) => [k, ''])) })

// A "time" setting travels as the whole number HHMM (1545 = 15:45, 830 = 08:30); the admin sees and types HH:MM. The API
// keeps HHMM (one exact number in the store and the history); this page converts at the edges only.
const isTime = (s) => s.unit === 'time'
function clock(hhmm) {
  const n = String(hhmm).padStart(4, '0')
  return `${n.slice(0, 2)}:${n.slice(2)}`
}
function shown(s, v) {
  return isTime(s) && /^\d{1,4}$/.test(String(v)) ? clock(v) : v
}
const TIME_HINT = 'Enter a time as HH:MM, for example 09:30.'
function toHhmm(typed) {
  const m = /^(\d{1,2}):(\d{2})$/.exec(String(typed).trim())
  if (!m || Number(m[1]) > 23 || Number(m[2]) > 59) return null
  return String(Number(m[1]) * 100 + Number(m[2]))
}

function formFor(key) {
  if (!forms[key]) forms[key] = { value: '', effective_from: '', note: '', busy: false, reason: '', open: false }
  return forms[key]
}

function when(iso) {
  return iso ? new Date(iso).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', dateStyle: 'medium', timeStyle: 'short' }) + ' IST' : ''
}

async function load() {
  state.value = 'loading'
  try {
    data.value = (await api.get('/settings')).data
    state.value = 'ready'
  } catch (e) {
    error.value = e
    state.value = 'unavailable'
  }
}

function replace(updated) {
  for (const g of data.value.groups) {
    const at = g.settings.findIndex((s) => s.key === updated.key)
    if (at >= 0) g.settings[at] = updated
  }
}

// Only a time the admin chose in the FUTURE is sent (as an instant with its zone). Blank, or a time not after the browser's
// clock, sends nothing: "now" is the server's clock, so a skewed or truncated browser time can never be refused as back-dated.
function instant(local) {
  if (!local) return undefined
  const at = new Date(local)
  return at.getTime() > Date.now() ? at.toISOString() : undefined
}

async function save(key) {
  const f = formFor(key)
  f.busy = true
  f.reason = ''
  try {
    const setting = data.value.groups.flatMap((g) => g.settings).find((x) => x.key === key)
    let value = f.value
    if (setting && isTime(setting)) {
      value = toHhmm(f.value)
      if (value === null) {
        f.reason = TIME_HINT
        return
      }
    }
    const body = { value, note: f.note }
    const at = instant(f.effective_from)
    if (at) body.effective_from = at
    replace((await api.post(`/settings/${key}`, body)).data)
    f.value = ''
    f.note = ''
    f.effective_from = ''
    f.open = false
  } catch (e) {
    f.reason = e.reason || 'The change was not saved. Try again.'
  } finally {
    f.busy = false
  }
}

async function reset(key) {
  const f = formFor(key)
  f.busy = true
  f.reason = ''
  try {
    replace((await api.post(`/settings/${key}/reset`, { note: f.note })).data)
    f.note = ''
  } catch (e) {
    f.reason = e.reason || 'The reset was not saved. Try again.'
  } finally {
    f.busy = false
  }
}

async function addRateSet() {
  charges.busy = true
  charges.reason = ''
  try {
    const body = { source_url: charges.source_url, note: charges.note }
    for (const [k] of CHARGE_FIELDS) body[k] = charges[k]
    if (charges.read_on) body.read_on = charges.read_on
    await api.post('/settings/charges', body)
    charges.open = false
    await load()
  } catch (e) {
    charges.reason = e.reason || 'The rate set was not saved. Try again.'
  } finally {
    charges.busy = false
  }
}

onMounted(load)
</script>

<template>
  <section data-testid="settings-page">
    <PageHeader title="Settings" />
    <p class="mb-4 text-sm text-ink-muted">
      App-wide numbers that every screen uses. A change takes effect from the time you choose (now by default) and the earlier values
      stay in the earlier values.
    </p>
    <p v-if="state === 'loading'" data-testid="settings-loading">Loading settings…</p>
    <div v-else-if="state === 'unavailable'" data-testid="settings-unavailable">
      <ErrorMessage v-if="error?.parts" :parts="error.parts" />
      <p v-else>The settings could not be read, so no value is shown.</p>
      <button type="button" class="mt-2 underline" data-testid="settings-retry" @click="load">Try again</button>
    </div>
    <div v-else>
      <section v-for="g in data.groups" :key="g.name" class="mb-8" :data-testid="`settings-group-${g.name}`">
        <h2 class="mb-2 text-lg font-semibold">{{ g.name }}</h2>
        <table class="w-full text-left text-sm">
          <thead>
            <tr class="text-ink-muted">
              <th>Setting</th><th>Value in force</th><th>Unit</th><th>Default</th><th>Since</th><th>Set by</th><th>What it changes</th><th></th>
            </tr>
          </thead>
          <tbody>
            <template v-for="s in g.settings" :key="s.key">
              <tr :data-testid="`setting-${s.key}`" class="border-t align-top">
                <td>{{ s.label }}</td>
                <td data-testid="setting-value">{{ shown(s, s.value) }}</td>
                <td>{{ isTime(s) ? 'time (IST)' : s.unit }}</td>
                <td data-testid="setting-default">{{ shown(s, s.default) }}</td>
                <td>{{ s.is_default ? 'Default' : when(s.effective_from) }}</td>
                <td>{{ s.set_by || '' }}</td>
                <td>{{ s.what_it_changes }}</td>
                <td>
                  <button type="button" class="underline" :data-testid="`edit-${s.key}`" @click="formFor(s.key).open = !formFor(s.key).open">Change</button>
                </td>
              </tr>
              <tr v-if="formFor(s.key).open" :data-testid="`form-${s.key}`">
                <td colspan="8" class="pb-3">
                  <form class="flex flex-wrap items-end gap-2" @submit.prevent="save(s.key)">
                    <label v-if="isTime(s)">New time (IST, HH:MM, from {{ shown(s, s.min) }} to {{ shown(s, s.max) }})
                      <input v-model="formFor(s.key).value" data-testid="input-value" class="block border px-1" type="time" required />
                    </label>
                    <label v-else>New value ({{ s.unit }}, from {{ s.min }} to {{ s.max }})
                      <input v-model="formFor(s.key).value" data-testid="input-value" class="block border px-1" inputmode="decimal" required />
                    </label>
                    <label>Takes effect (blank = now)
                      <input v-model="formFor(s.key).effective_from" data-testid="input-time" type="datetime-local" class="block border px-1" />
                    </label>
                    <label>Note (why)
                      <input v-model="formFor(s.key).note" data-testid="input-note" class="block border px-1" required maxlength="500" />
                    </label>
                    <button type="submit" :disabled="formFor(s.key).busy" data-testid="save">Save</button>
                    <button type="button" :disabled="formFor(s.key).busy" data-testid="reset" @click="reset(s.key)">Reset to default</button>
                  </form>
                  <p v-if="formFor(s.key).reason" role="alert" class="mt-1 text-error" data-testid="refusal">{{ formFor(s.key).reason }}</p>
                </td>
              </tr>
              <tr v-if="s.earlier_values.length" :data-testid="`earlier-values-${s.key}`">
                <td colspan="8" class="pb-2">
                  <details>
                    <summary>Earlier values ({{ s.earlier_values.length }})</summary>
                    <ul>
                      <li v-for="(h, i) in s.earlier_values" :key="i" data-testid="earlier-value-row">
                        {{ shown(s, h.value) }} - {{ STATE_WORD[h.state] }} from {{ when(h.effective_from) }}, set by {{ h.set_by }}
                      </li>
                    </ul>
                  </details>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </section>

      <section class="mb-8" data-testid="settings-group-Charges">
        <h2 class="mb-2 text-lg font-semibold">Charges</h2>
        <div v-if="data.charges" data-testid="charges-in-force">
          <p class="text-sm">Rate set read on {{ data.charges.read_on }}, source {{ data.charges.source_url }}</p>
          <ul class="text-sm">
            <li v-for="[k, label] in CHARGE_FIELDS" :key="k" :data-testid="`charge-${k}`">{{ label }}: {{ data.charges.rates[k] }}</li>
          </ul>
        </div>
        <p v-else data-testid="charges-none">No charge rate set is stored yet.</p>
        <button type="button" class="mt-2 underline" data-testid="add-rate-set" @click="charges.open = !charges.open">Add rate set</button>
        <form v-if="charges.open" class="mt-2 flex flex-wrap items-end gap-2" data-testid="rate-set-form" @submit.prevent="addRateSet">
          <p class="w-full text-sm text-ink-muted" data-testid="rate-hint">{{ RATE_HINT }}</p>
          <label v-for="[k, label] in CHARGE_FIELDS" :key="k">{{ label }}
            <input v-model="charges[k]" :data-testid="`rate-${k}`" class="block border px-1" inputmode="decimal" required />
          </label>
          <label>Source web address
            <input v-model="charges.source_url" data-testid="rate-source" class="block border px-1" required />
          </label>
          <label>Rates read on (blank = today)
            <input v-model="charges.read_on" data-testid="rate-read-on" type="date" class="block border px-1" />
          </label>
          <label>Note
            <input v-model="charges.note" data-testid="rate-note" class="block border px-1" maxlength="500" />
          </label>
          <button type="submit" :disabled="charges.busy" data-testid="rate-save">Save rate set</button>
        </form>
        <p v-if="charges.reason" role="alert" class="mt-1 text-error" data-testid="rate-refusal">{{ charges.reason }}</p>
      </section>
    </div>
  </section>
</template>
