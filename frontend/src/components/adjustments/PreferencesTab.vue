<!-- Contract "Your adjustment settings" step 4 (ADR-245, ADR-247; was GC-SET REQ-168 AC-2 + GC-ALERT1 item 6): the
     Adjustments screen's "Adjustment settings" tab, built from the owner-approved mockup. Every setting is grouped by the
     trader's question (lib/settingsGroups.js), and every value names its source (ADR-245): "Default", "Yours" or "This
     strategy"; a value whose source the server did not send says "source unavailable", never a guessed tag.
     Reads: GET /api/adjustments/preferences (each preference: value, source, admin default, range, earlier values),
     GET /api/strategies (the "Show for" picker), GET /api/strategies/{id}/adjustment-plan (the picked strategy's plan:
     target, stop, most adjustments, time exit). Writes: POST /api/adjustments/preferences/{key} and .../{key}/reset, and
     PUT /api/strategies/{id}/adjustment-plan for a plan value; the server answers and the shown list is always re-read.
     Every number is shown exactly as the server sent it (a decimal string, never parsed to a float here); a "time"
     preference travels as the whole number HHMM and is shown and typed as HH:MM. No browser clock is sent.
     Answer states per read: present (shown), absent (a field missing: "value unavailable" / "source unavailable"),
     failed (a sentence, no value, Try again), empty (the list is empty: said in words), unreadable (no list in the
     answer: treated as failed, no value shown). Decision support only (ADR-003): nothing here places an order. -->
<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import api from '@/services/api'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import { ALERT_KEY, CHIPS, GROUPS, OPEN_BY_DEFAULT, groupOf, isYours, matches, sourceWord } from '@/lib/settingsGroups'
import { fetchPlan, saveBody, sendPlan } from '@/lib/adjustPlan'

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
  if (v === null || v === undefined || v === '') return 'value unavailable'
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
const hasValue = (p) => p.value !== null && p.value !== undefined && p.value !== ''

async function load() {
  state.value = 'loading'
  try {
    const list = (await api.get('/adjustments/preferences')).data?.preferences
    if (!Array.isArray(list)) throw new Error('unreadable answer') // fail closed: no list, no value shown
    prefs.value = list.filter((p) => p && typeof p.key === 'string').map(withEarlier)
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
    f.open = false
    await load()
  } catch (e) {
    f.reason = e.reason || 'The reset was not saved. Try again.'
  } finally {
    f.busy = false
  }
}

// ---- "Show for": all my strategies, or one strategy (its plan values carry "This strategy") ----
const strategies = ref([])
const scope = ref('all')
async function loadStrategies() {
  try {
    const list = (await api.get('/strategies')).data?.strategies
    strategies.value = Array.isArray(list) ? list.filter((s) => Number.isInteger(s?.id)) : []
  } catch {
    strategies.value = [] // failed: the picker keeps "All my strategies" only
  }
}
// strategy id from the picker value (a string); null when not a positive integer
// looked up in the loaded list (ids are integers there), so no number parsing is needed
const strategyIdOf = (v) => strategies.value.find((s) => String(s.id) === String(v))?.id ?? null
const scopeName = computed(() => strategies.value.find((s) => String(s.id) === scope.value))
const stratLabel = (s) => (s.name ? `${s.id} · ${s.name}` : String(s.id))

const plan = reactive({ state: 'idle', sheet: null, error: null, form: null, busy: false, reason: '' })
async function loadPlan() {
  if (scope.value === 'all') {
    plan.state = 'idle'
    plan.sheet = null
    return
  }
  plan.state = 'loading'
  plan.form = null
  try {
    const sheet = await fetchPlan(api, strategyIdOf(scope.value))
    plan.sheet = sheet
    plan.state = sheet.kind === 'invalid' ? 'unavailable' : sheet.kind === 'generic' ? 'generic' : sheet.plan ? 'plan' : 'none'
  } catch (e) {
    plan.error = e
    plan.sheet = null
    plan.state = 'unavailable'
  }
}
watch(scope, loadPlan)

const PLAN_FIELDS = [
  { id: 'target', group: 'g-exit', label: 'Profit target', unit: '%' },
  { id: 'stop', group: 'g-exit', label: 'Plan stop', unit: '%' },
  { id: 'max_adjustments', group: 'g-plan', label: 'Most adjustments' },
  { id: 'time_exit', group: 'g-plan', label: 'Time exit' },
]
const FORM_KEY = { target: 'target', stop: 'stop', max_adjustments: 'maxAdjustments', time_exit: 'timeExit' }
const WORDS_KEY = { target: 'targetWords', stop: 'stopWords' }
// The plan's own values when one is accepted ("This strategy"), else the playbook's starting values ("Default").
const planSrc = computed(() => (plan.state === 'plan' ? plan.sheet.plan : plan.state === 'none' ? plan.sheet.prefill : null))
function planLabel(f) {
  return plan.sheet?.labels?.[f.id] || f.label
}
function planValue(f) {
  const src = planSrc.value
  const v = src?.[FORM_KEY[f.id]]
  if (!v) return 'not set'
  const words = src[WORDS_KEY[f.id]]
  return [f.unit ? `${v} ${f.unit}` : v, words].filter(Boolean).join(' ')
}
const planTag = computed(() => (plan.state === 'plan' ? 'This strategy' : 'Default'))
function editPlan() {
  const p = plan.sheet.plan
  plan.form = { playbookId: p.playbookId, target: p.target, stop: p.stop, maxAdjustments: p.maxAdjustments, timeExit: p.timeExit }
  plan.reason = ''
}
async function savePlan() {
  plan.busy = true
  plan.reason = ''
  try {
    const sheet = await sendPlan(api, strategyIdOf(scope.value), saveBody(plan.form), true)
    plan.form = null
    if (sheet.kind === 'invalid') await loadPlan()
    else {
      plan.sheet = sheet
      plan.state = sheet.plan ? 'plan' : 'none'
    }
  } catch (e) {
    plan.reason = e.reason || e.parts?.what_happened || 'The plan change was not saved. Try again.'
  } finally {
    plan.busy = false
  }
}

// ---- search, chips, accordions ----
const search = ref('')
const pressed = reactive(Object.fromEntries(CHIPS.map((c) => [c.id, false])))
const filtering = computed(() => search.value.trim() !== '' || CHIPS.some((c) => pressed[c.id]))
function clearFilters() {
  search.value = ''
  for (const c of CHIPS) pressed[c.id] = false
}
const openSet = reactive(Object.fromEntries(GROUPS.map((g) => [g.id, OPEN_BY_DEFAULT.includes(g.id)])))
const allOpen = computed(() => GROUPS.every((g) => openSet[g.id]))
function toggleAll() {
  const to = !allOpen.value
  for (const g of GROUPS) openSet[g.id] = to
}
function jump(id) {
  openSet[id] = true
  document.getElementById(id)?.scrollIntoView?.({ block: 'start' })
}

const visible = computed(() => prefs.value.filter((p) => matches(p, search.value, pressed)))
const inGroup = (id) => visible.value.filter((p) => groupOf(p.key) === id)
const general = (id) => inGroup(id).filter((p) => !ALERT_KEY.test(p.key))
const changedIn = (id) => prefs.value.filter((p) => groupOf(p.key) === id && isYours(p.source))
// Groups with no server preference of their own (the exits table, plan values, playbook, orders, the admin list) show
// while no filter is on; with a filter, only the groups holding a matching preference show.
const STATIC = ['g-exit', 'g-plan', 'g-pb', 'g-order', 'g-admin']
const shownGroups = computed(() => GROUPS.filter((g) => {
  if (filtering.value || g.id === 'g-other') return inGroup(g.id).length > 0
  return true // no filter: every question's group shows, an empty one says "No setting here."
}))
const isOpen = (id) => filtering.value || openSet[id]

const groupReset = reactive({ busy: '', reason: '' })
async function resetGroup(id) {
  groupReset.busy = id
  groupReset.reason = ''
  try {
    for (const p of changedIn(id)) await api.post(`/adjustments/preferences/${p.key}/reset`, { note: '' })
  } catch (e) {
    groupReset.reason = e.reason || 'Not every value was reset. The list below is what the server holds now.'
  }
  await load()
  groupReset.busy = ''
}

// GC-ALERT1 item 6 (REQ-170 Q-AD-1, AC-6): the alert values a user may change come as one small table per trading style.
// A key alerts.<style>.<field> belongs to that style's table; the table title and row names are the server's label split
// at its first ': ' ("Weekly expiry: cool-down, same rule"), the words themselves untouched.
const head = (label) => String(label).split(': ')[0]
const rowLabel = (p) => {
  const name = String(p.label).split(': ').slice(1).join(': ') || String(p.label)
  return name.charAt(0).toUpperCase() + name.slice(1)
}
// The one place a registry `unit` becomes the short word shown after a style-table value; a time carries none (HH:MM).
const UNIT_WORD = { minutes: 'min', percent: '%' }
const withUnit = (p, v) => {
  const val = shown(p, v)
  if (val === 'value unavailable') return val
  if (p.key.endsWith('.daily_cap')) return `${val} a day`
  const word = UNIT_WORD[p.unit]
  if (!word) return val
  return word === '%' ? `${val}%` : `${val} ${word}`
}
// The styles are whatever the server sent (alerts.<style>.<field>), in the order it sent them; no style word is written here.
const styleTables = computed(() => {
  const rows = inGroup('g-loud')
  const order = []
  for (const p of rows) {
    const style = ALERT_KEY.exec(p.key)?.[1]
    if (style && !order.includes(style)) order.push(style)
  }
  return order.map((style) => ({ style, rows: rows.filter((p) => ALERT_KEY.exec(p.key)?.[1] === style) }))
    .map((t) => ({ ...t, title: head(t.rows[0].label) }))
})

onMounted(() => {
  load()
  loadStrategies()
})
</script>

<template>
  <section data-testid="prefs-tab" class="min-w-0">
    <h2 class="text-lg font-semibold" data-testid="settings-title">Adjustment settings</h2>
    <div class="mt-2 rounded-lg border border-line bg-surface p-3">
      <div class="flex flex-wrap items-end gap-3">
        <label class="flex min-w-0 flex-col text-sm text-ink-muted">Show for
          <select v-model="scope" class="mt-1 max-w-full rounded border border-line bg-surface px-2 py-1 text-ink" data-testid="settings-scope">
            <option value="all">All my strategies (your values)</option>
            <option v-for="s in strategies" :key="s.id" :value="String(s.id)">{{ stratLabel(s) }}</option>
          </select>
        </label>
        <input
v-model="search" type="search" class="min-w-0 flex-1 rounded border border-line px-2 py-1" placeholder="Search settings"
               aria-label="Search settings" data-testid="settings-search" />
      </div>
      <div class="mt-2 flex flex-wrap gap-2" role="group" aria-label="Filter settings">
        <button
v-for="c in CHIPS" :key="c.id" type="button" class="chip" :class="pressed[c.id] ? 'border-accent bg-accent-soft' : 'border-line'"
                :aria-pressed="pressed[c.id]" :data-testid="`settings-chip-${c.id}`" @click="pressed[c.id] = !pressed[c.id]">{{ c.label }}</button>
      </div>
      <p class="mt-2 text-sm text-ink-muted" data-testid="settings-intro">
        Three layers: the default, your value for all strategies, and a value for one strategy. A default shows with a small
        "Default" tag; tap a value to change it. A change applies at the next check; a saved plan is not changed.
        <template v-if="scope !== 'all'">
          Shown for {{ scopeName ? stratLabel(scopeName) : scope }}: its plan values carry "This strategy". Its own values for the other
          settings are not sent by the server yet, so each shows your value or the default.
        </template>
      </p>
    </div>

    <p v-if="state === 'loading'" class="mt-3" data-testid="prefs-loading">Loading settings…</p>
    <div v-else-if="state === 'unavailable'" class="mt-3" data-testid="prefs-unavailable">
      <ErrorMessage v-if="error?.parts" :parts="error.parts" />
      <p v-else>The settings could not be read, so no value is shown.</p>
      <button type="button" class="mt-2 underline" data-testid="prefs-retry" @click="load">Try again</button>
    </div>
    <div v-else class="mt-3 md:grid md:grid-cols-[12rem_minmax(0,1fr)] md:gap-4">
      <nav class="mb-3 md:sticky md:top-2 md:mb-0 md:self-start" aria-label="Setting groups" data-testid="settings-rail">
        <ul class="flex flex-wrap gap-2 md:flex-col md:gap-1">
          <li v-for="g in shownGroups" :key="g.id" class="min-w-0">
            <a :href="`#${g.id}`" class="flex items-start gap-1 rounded px-1 text-sm underline md:no-underline" @click.prevent="jump(g.id)">
              <span class="min-w-0">{{ g.title }}</span>
              <span v-if="changedIn(g.id).length" class="chip border-accent bg-accent-soft text-xs" :title="`${changedIn(g.id).length} changed`">{{ changedIn(g.id).length }}</span>
            </a>
          </li>
        </ul>
      </nav>

      <div class="min-w-0">
        <p v-if="!prefs.length" class="mb-2 text-sm text-ink-muted" data-testid="prefs-empty">
          No setting came back from the server for you, so no value is shown here.
        </p>
        <div v-if="!shownGroups.length" class="rounded-lg border border-line p-3 text-sm" data-testid="settings-no-match">
          No setting matches these filters.
          <button type="button" class="underline" data-testid="settings-clear" @click="clearFilters">Clear filters</button>
        </div>
        <div v-else class="mb-2 flex flex-wrap items-center gap-2">
          <button type="button" class="btn btn-sm" data-testid="settings-expand-all" :aria-pressed="allOpen" @click="toggleAll">{{ allOpen ? 'Collapse all' : 'Expand all' }}</button>
          <span class="text-sm text-ink-muted">{{ filtering ? 'Showing the groups with a matching setting.' : allOpen ? 'All groups open.' : '' }}</span>
          <button v-if="filtering" type="button" class="text-sm underline" data-testid="settings-clear" @click="clearFilters">Clear filters</button>
        </div>

        <section v-for="g in shownGroups" :id="g.id" :key="g.id" class="mb-3 rounded-lg border border-line bg-surface" data-testid="set-group">
          <button
type="button" class="flex min-h-11 w-full items-center justify-between px-3 py-2 text-left font-semibold"
                  :aria-expanded="isOpen(g.id)" :aria-controls="`body-${g.id}`" data-testid="set-group-toggle"
                  @click="openSet[g.id] = !openSet[g.id]">
            <span><span data-testid="set-group-title">{{ g.title }}</span>
              <span v-if="changedIn(g.id).length" class="chip ml-1 border-accent bg-accent-soft text-xs font-normal">{{ changedIn(g.id).length }} changed</span></span>
            <span aria-hidden="true">{{ isOpen(g.id) ? '▴' : '▾' }}</span>
          </button>
          <div v-show="isOpen(g.id)" :id="`body-${g.id}`" class="min-w-0 px-3 pb-3">
            <!-- Exits and targets: every threshold in one table (ADR-247 default stop) -->
            <template v-if="g.id === 'g-exit' && !filtering">
              <div class="overflow-x-auto" data-h-scroll><table class="w-full table-fixed text-sm" data-testid="exit-table">
                <thead>
                  <tr class="text-left text-xs text-ink-muted">
                    <th class="w-1/3 py-1 pr-2 font-semibold">Threshold</th>
                    <th class="py-1 pr-2 font-semibold">Value</th>
                    <th class="py-1 font-semibold">What it does</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="f in PLAN_FIELDS.filter((x) => x.group === 'g-exit')" v-show="planSrc" :key="f.id" class="border-t border-line align-top" :data-testid="planSrc ? `plan-${f.id}` : null">
                    <th scope="row" class="break-words py-1 pr-2 text-left font-normal">{{ planLabel(f) }}</th>
                    <td class="break-words py-1 pr-2"><span data-testid="plan-value">{{ planValue(f) }}</span> <span class="chip border-line bg-surface-muted text-xs text-ink-muted" data-testid="pref-source">{{ planTag }}</span></td>
                    <td class="break-words py-1 text-ink-muted">an alert when it is reached; nothing is placed</td>
                  </tr>
                  <tr class="border-t border-line align-top" data-testid="exit-stop_loss">
                    <th scope="row" class="break-words py-1 pr-2 text-left font-normal">Stop at % of max loss</th>
                    <td class="break-words py-1 pr-2">50 % of max loss <span class="chip border-line bg-surface-muted text-xs text-ink-muted">source unavailable</span></td>
                    <td class="break-words py-1 text-ink-muted">always active; one stop alert, at whichever active stop comes first</td>
                  </tr>
                  <tr class="border-t border-line align-top" data-testid="exit-credit2">
                    <th scope="row" class="break-words py-1 pr-2 text-left font-normal">Stop at 2× credit</th>
                    <td class="break-words py-1 pr-2">2× the credit received <span class="chip border-line bg-surface-muted text-xs text-ink-muted">source unavailable</span></td>
                    <td class="break-words py-1 text-ink-muted">Stop at 2x the credit received: for plans accepted from 5 Nov 2026; older plans keep their own stops. Whichever stop comes first raises the one alert</td>
                  </tr>
                  <tr class="border-t border-line align-top text-ink-muted" data-testid="exit-stop_margin">
                    <th scope="row" class="break-words py-1 pr-2 text-left font-normal">Stop at % of margin</th>
                    <td class="break-words py-1 pr-2">
                      <label class="inline-flex items-center gap-1">
                        <input type="checkbox" role="switch" disabled :checked="false" aria-label="Stop at % of margin: off" data-testid="margin-stop-switch" />
                        <span>Off</span>
                      </label>
                    </td>
                    <td class="break-words py-1">off by default; checked only while the app is open, not in the background yet</td>
                  </tr>
                </tbody>
              </table></div>
              <p v-if="scope === 'all'" class="mt-2 text-sm text-ink-muted" data-testid="plan-per-strategy">
                &#128274; The profit target and the plan stop are set per strategy: pick one strategy in "Show for" to see and change them.
              </p>
            </template>

            <!-- Plan limits / Playbook triggers: the picked strategy's plan -->
            <template v-if="(g.id === 'g-plan' || g.id === 'g-pb') && !filtering">
              <p v-if="scope === 'all'" class="text-sm text-ink-muted">&#128274; Set per strategy: pick one strategy in "Show for" to see and change them.</p>
              <p v-else-if="plan.state === 'loading'" class="text-sm">Loading the plan…</p>
              <div v-else-if="plan.state === 'unavailable'" class="text-sm" :data-testid="g.id === 'g-plan' ? 'plan-unavailable' : null">
                The plan could not be read, so no plan value is shown.
                <button type="button" class="underline" @click="loadPlan">Try again</button>
              </div>
              <p v-else-if="plan.state === 'generic'" class="text-sm">{{ plan.sheet.text }}</p>
              <template v-else-if="g.id === 'g-plan'">
                <div v-for="f in PLAN_FIELDS.filter((x) => x.group === 'g-plan')" :key="f.id" class="grid grid-cols-1 gap-x-4 gap-y-1 border-t border-line py-2 first:border-t-0 sm:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]" :data-testid="`plan-${f.id}`">
                  <b class="min-w-0">{{ planLabel(f) }}</b>
                  <span class="min-w-0"><span data-testid="plan-value">{{ planValue(f) }}</span> <span class="chip border-line bg-surface-muted text-xs text-ink-muted" data-testid="pref-source">{{ planTag }}</span></span>
                </div>
                <p v-if="plan.state === 'none'" class="text-sm text-ink-muted">No plan is accepted for this strategy yet: these are the playbook's starting values. Accept a plan on the strategy page.</p>
                <button v-if="plan.state === 'plan' && !plan.form" type="button" class="btn btn-sm mt-2" data-testid="plan-edit" @click="editPlan">Change plan values</button>
                <form v-if="plan.form" class="mt-2 flex flex-wrap items-end gap-2" data-testid="plan-form" @submit.prevent="savePlan">
                  <label>Profit target (%)<input v-model="plan.form.target" class="block w-24 border px-1" inputmode="decimal" /></label>
                  <label>Plan stop (%)<input v-model="plan.form.stop" class="block w-24 border px-1" inputmode="decimal" /></label>
                  <label>Most adjustments<input v-model="plan.form.maxAdjustments" class="block w-24 border px-1" inputmode="numeric" /></label>
                  <label>Time exit (IST)<input v-model="plan.form.timeExit" class="block border px-1" type="time" /></label>
                  <button type="submit" class="btn btn-sm" :disabled="plan.busy">Save</button>
                  <button type="button" class="btn btn-sm" :disabled="plan.busy" @click="plan.form = null">Cancel</button>
                </form>
                <p v-if="plan.reason" role="alert" class="mt-1 text-error" data-testid="plan-refusal">{{ plan.reason }}</p>
              </template>
              <template v-else>
                <p class="text-sm" data-testid="plan-playbook">Playbook: <b>{{ plan.sheet?.plan?.playbookName || 'none accepted yet' }}</b></p>
                <p class="text-sm text-ink-muted">The trigger values (Trigger 1 to 3) are not sent by the server yet; change them in the playbook on the Playbooks tab.</p>
              </template>
            </template>

            <p v-if="g.id === 'g-order'" class="text-sm text-ink-muted">No order default is sent by the server yet.</p>

            <template v-if="g.id === 'g-admin'">
              <p class="text-sm text-ink-muted">&#128274; Shown for reference; only the admin changes these.</p>
              <ul class="ml-4 list-disc text-sm">
                <li><b>Check and push speeds</b>: server load for every user.</li>
                <li><b>Feed health</b>: how stale a price may be.</li>
                <li><b>Market facts</b>: lot sizes, strike steps, expiry days.</li>
                <li><b>Limits</b> such as the daily alert ceiling; <b>billing</b> and <b>pricing</b>.</li>
              </ul>
            </template>

            <!-- the server's preferences in this group, one row each -->
            <ul v-if="general(g.id).length" class="divide-y divide-line">
              <li v-for="p in general(g.id)" :key="p.key" class="grid grid-cols-1 gap-x-4 gap-y-1 py-2 sm:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]" :data-testid="`pref-${p.key}`">
                <div class="min-w-0">
                  <h3 class="font-semibold">{{ p.label }}</h3>
                  <p class="text-sm text-ink-muted">{{ p.what_it_changes }}</p>
                </div>
                <div class="min-w-0">
                  <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <button
v-if="hasValue(p)" type="button" class="underline" data-testid="pref-edit" :aria-label="`Change ${p.label}, now ${shown(p, p.value)}`"
                            @click="formFor(p.key).open = !formFor(p.key).open"><span data-testid="pref-value">{{ shown(p, p.value) }}</span></button>
                    <span v-else data-testid="pref-value">value unavailable</span>
                    <span class="chip border-line bg-surface-muted text-xs text-ink-muted" data-testid="pref-source">{{ sourceWord(p.source) }}</span>
                  </div>
                  <p class="text-xs text-ink-muted">
                    <span data-testid="pref-admin-default">Admin default: {{ shown(p, p.admin_default) }}</span> ·
                    <span data-testid="pref-range">Allowed: {{ shown(p, p.min) }} to {{ shown(p, p.max) }}</span>
                    <template v-if="!isTime(p) && p.unit"> · Unit: {{ p.unit }}</template><template v-if="isTime(p)"> · time (IST)</template>
                  </p>
                </div>
                <div v-if="formFor(p.key).open" :data-testid="`pref-form-${p.key}`" class="min-w-0 sm:col-span-2">
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
                    <button type="submit" class="btn btn-sm" :disabled="formFor(p.key).busy" data-testid="pref-save">Save</button>
                    <button type="button" class="btn btn-sm" :disabled="formFor(p.key).busy" data-testid="pref-reset" @click="reset(p)">Reset to default</button>
                  </form>
                </div>
                <p v-if="formFor(p.key).reason" role="alert" class="text-error sm:col-span-2" data-testid="pref-refusal">{{ formFor(p.key).reason }}</p>
                <details v-if="p.earlier.length" :data-testid="`pref-earlier-${p.key}`" class="text-sm sm:col-span-2">
                  <summary>Earlier values ({{ p.earlier.length }})</summary>
                  <ul>
                    <li v-for="(h, i) in p.earlier" :key="i" data-testid="pref-earlier-row">
                      {{ h.value === null ? 'Reset to the admin default' : shown(p, h.value) }} from {{ when(h.effective_from) }}
                    </li>
                  </ul>
                </details>
              </li>
            </ul>

            <!-- Alert pace and sound: one table per trading style -->
            <template v-if="g.id === 'g-loud'">
              <p class="text-sm text-ink-muted">One table per alert style. The daily limit cannot go above the admin limit.</p>
              <section v-for="t in styleTables" :key="t.style" class="mt-3" :data-testid="`prefs-alerts-${t.style}`">
                <h3 class="font-semibold" data-testid="prefs-alerts-title">{{ t.title }}</h3>
                <div class="overflow-x-auto" data-h-scroll><table class="w-full table-auto text-sm">
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
                          <span class="chip ml-1 border-line bg-surface-muted text-xs text-ink-muted" data-testid="pref-source">{{ sourceWord(p.source) }}</span>
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
                            <button type="submit" class="btn btn-sm" :disabled="formFor(p.key).busy" data-testid="pref-save">Save</button>
                            <button type="button" class="btn btn-sm" :disabled="formFor(p.key).busy" data-testid="pref-reset" @click="reset(p)">Reset to default</button>
                          </form>
                          <p v-if="formFor(p.key).reason" role="alert" class="mt-1 text-error" data-testid="pref-refusal">{{ formFor(p.key).reason }}</p>
                        </td>
                      </tr>
                    </template>
                  </tbody>
                </table></div>
              </section>
              <p v-if="!styleTables.length" class="text-sm text-ink-muted">No alert value came back from the server.</p>
            </template>

            <p v-if="['g-land', 'g-size', 'g-tell', 'g-disp'].includes(g.id) && !general(g.id).length" class="text-sm text-ink-muted">No setting here.</p>

            <div v-if="!STATIC.includes(g.id)" class="mt-2 flex flex-wrap items-center gap-2">
              <button type="button" class="btn btn-sm" :disabled="!changedIn(g.id).length || groupReset.busy === g.id" :data-testid="`group-reset-${g.id}`" @click="resetGroup(g.id)">Reset this group to the defaults</button>
              <span v-if="!changedIn(g.id).length" class="text-xs text-ink-muted">nothing changed here</span>
              <p v-if="groupReset.reason && groupReset.busy === ''" role="alert" class="text-error">{{ groupReset.reason }}</p>
            </div>
          </div>
        </section>
      </div>
    </div>
  </section>
</template>
