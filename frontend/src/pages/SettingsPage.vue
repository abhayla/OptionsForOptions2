<!-- App settings (GC-SET step 2; REQ-167 AC-2, AC-3, AC-5): every app-wide number a calculation uses, by group, with the
     value in force, its default, when it took effect and who set it, and the history. The admin changes a value from a
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
const STATE_WORD = { in_force: 'In force', scheduled: 'Scheduled', earlier: 'Earlier' }

const data = ref(null)
const state = ref('loading') // loading | ready | unavailable
const error = ref(null)
const forms = reactive({}) // key -> { value, effective_from, note, busy, reason, open }
const charges = reactive({ open: false, busy: false, reason: '', source_url: '', read_on: '', note: '', ...Object.fromEntries(CHARGE_FIELDS.map(([k]) => [k, ''])) })

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

// the time the admin typed (a local date-time) as an instant with its zone; blank = now (the server's clock)
function instant(local) {
  return local ? new Date(local).toISOString() : undefined
}

async function save(key) {
  const f = formFor(key)
  f.busy = true
  f.reason = ''
  try {
    const body = { value: f.value, note: f.note }
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
      stay in the history.
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
                <td data-testid="setting-value">{{ s.value }}</td>
                <td>{{ s.unit }}</td>
                <td data-testid="setting-default">{{ s.default }}</td>
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
                    <label>New value ({{ s.unit }}, from {{ s.min }} to {{ s.max }})
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
              <tr v-if="s.history.length" :data-testid="`history-${s.key}`">
                <td colspan="8" class="pb-2">
                  <details>
                    <summary>History ({{ s.history.length }})</summary>
                    <ul>
                      <li v-for="(h, i) in s.history" :key="i" data-testid="history-row">
                        {{ h.value }} - {{ STATE_WORD[h.state] }} from {{ when(h.effective_from) }}, set by {{ h.set_by }}
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
