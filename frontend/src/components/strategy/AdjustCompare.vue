<!-- Strategy Builder adjust mode (GC-ADJ1 step 3; REQ-156 AC-1..AC-5, REQ-157 AC-1..AC-5; ADR-214 (2a)(2b), ADR-003, ADR-008).
     Reads POST /api/strategies/{id}/adjustment-approaches ONCE and draws the reply: the whole-trade payoff chart (Before dashed,
     one line per approach, legend chips hide / show), the filter panel (choices and ranges built from the reply's approaches),
     the criteria table (leader cells, "Leads on N of M"), refused approaches with their reason, and the approach to prepare.
     No figure is computed here. The app picks no overall approach for you. -->
<template>
  <section class="mt-3 flex min-w-0 flex-col gap-4" data-testid="adjust-compare" :data-state="state">
    <h2 class="text-lg font-semibold" data-testid="adjust-title">Compare possible approaches{{ name ? `: ${name}` : '' }}</h2>
    <p class="text-sm text-ink-muted" data-testid="adjust-intro">{{ INTRO }}</p>
    <ErrorMessage v-if="state === 'error'" :parts="errorParts" compact prefix="adjust-error" data-testid="adjust-error" />
    <p v-else-if="state === 'loading'" class="text-sm text-ink-muted" data-testid="adjust-loading">Loading the approaches.</p>

    <template v-else-if="reply">
      <div v-if="picked.length" class="flex flex-wrap items-center gap-2 text-sm" data-testid="adjust-scope">
        <label class="flex items-center gap-2">Approaches in the compare
          <select v-model="scope" class="h-9 rounded border border-line px-2" data-testid="adjust-scope-select">
            <option value="all">All {{ allCount }} that apply</option>
            <option value="picked">Only the ones picked in the drawer</option>
          </select>
        </label>
      </div>
      <div v-if="why" class="rounded-lg border border-line bg-surface p-3" data-testid="adjust-why">
        <h3 class="text-sm font-semibold">Why detected · current state</h3>
        <p v-for="l in why.lines" :key="l" class="mt-1 text-sm" data-testid="adjust-why-line">{{ l }}</p>
        <dl class="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-sm min-[700px]:grid-cols-4">
          <template v-for="r in why.rows" :key="r.id"><dt class="text-ink-muted">{{ r.label }}</dt><dd class="tabular-nums" :data-testid="`adjust-why-${r.id}`">{{ r.value }}</dd></template>
        </dl>
      </div>
      <div class="grid min-w-0 grid-cols-1 gap-4 min-[1100px]:grid-cols-2">
        <div class="min-w-0 rounded-lg border border-line bg-surface p-3" data-testid="adjust-chart-card">
          <h3 class="mb-1 text-sm font-semibold">Payoff at expiry, whole trade</h3>
          <AdjustPayoffChart :lines="chartLines" :hidden="hiddenLines" @toggle="toggleLine" />
          <p class="mt-1 text-xs text-ink-muted" data-testid="adjust-chart-note">Dashed grey = no change. Tap a name to hide or show its line.</p>
          <p class="mt-1 text-xs text-ink-muted" data-testid="adjust-spot">{{ spotLine }}</p>
        </div>

        <div class="flex min-w-0 flex-col gap-4">
          <div class="rounded-lg border border-line bg-surface p-3" data-testid="adjust-filters">
            <div class="flex flex-wrap items-center justify-between gap-2">
              <h3 class="text-sm font-semibold">Filter approaches</h3>
              <span class="text-sm" data-testid="adjust-showing">{{ showingText(kept.length, total) }}</span>
              <button type="button" class="rounded border border-line px-2 py-0.5 text-xs" data-testid="adjust-clear" @click="clearFilters">Clear filters</button>
            </div>
            <p class="mt-1 text-xs text-ink-muted" data-testid="adjust-filter-note">{{ FILTER_NOTE }}</p>
            <fieldset v-if="facets.kinds.length" class="mt-2" data-testid="adjust-kinds">
              <legend class="text-xs font-semibold">Kind of action</legend>
              <button
                v-for="k in facets.kinds" :key="k.id" type="button" class="mr-1 mt-1 rounded border px-2 py-0.5 text-xs" :class="filters.kinds.includes(k.id) ? 'border-accent bg-accent-soft' : 'border-line'"
                :aria-pressed="filters.kinds.includes(k.id) ? 'true' : 'false'" :data-testid="`adjust-kind-${k.id}`" @click="flip('kinds', k.id)"
              >{{ KIND_TITLES[k.id] ?? k.id }} ({{ k.count }})</button>
            </fieldset>
            <fieldset v-if="facets.sides.length" class="mt-2" data-testid="adjust-sides">
              <legend class="text-xs font-semibold">Side it touches</legend>
              <button
                v-for="k in facets.sides" :key="k.id" type="button" class="mr-1 mt-1 rounded border px-2 py-0.5 text-xs" :class="filters.sides.includes(k.id) ? 'border-accent bg-accent-soft' : 'border-line'"
                :aria-pressed="filters.sides.includes(k.id) ? 'true' : 'false'" :data-testid="`adjust-side-${k.id}`" @click="flip('sides', k.id)"
              >{{ SIDE_TITLES[k.id] ?? k.id }} ({{ k.count }})</button>
            </fieldset>
            <fieldset v-if="facets.risk.length" class="mt-2" data-testid="adjust-risk">
              <legend class="text-xs font-semibold">Risk after</legend>
              <button
                v-for="k in facets.risk" :key="k.id" type="button" class="mr-1 mt-1 rounded border px-2 py-0.5 text-xs" :class="filters.risk.includes(k.id) ? 'border-accent bg-accent-soft' : 'border-line'"
                :aria-pressed="filters.risk.includes(k.id) ? 'true' : 'false'" :data-testid="`adjust-risk-${k.id}`" @click="flip('risk', k.id)"
              >{{ k.label }} ({{ k.count }})</button>
            </fieldset>
            <div v-for="r in RANGES.filter((x) => facets.ranges[x.id])" :key="r.id" class="mt-2" :data-testid="`adjust-range-${r.id}`">
              <label class="flex flex-wrap items-center gap-2 text-xs">
                <span class="font-semibold">{{ r.label }}</span>
                <span class="text-ink-muted" :data-testid="`adjust-range-${r.id}-min`">{{ facets.ranges[r.id].min }}</span>
                <input
                  type="range" step="any" class="min-w-0 flex-1" :min="facets.ranges[r.id].min" :max="facets.ranges[r.id].max"
                  :value="filters.limits[r.id] ?? (r.at === 'most' ? facets.ranges[r.id].max : facets.ranges[r.id].min)" :data-testid="`adjust-range-${r.id}-input`"
                  @input="setLimit(r, $event.target.value)"
                />
                <span class="text-ink-muted" :data-testid="`adjust-range-${r.id}-max`">{{ facets.ranges[r.id].max }}</span>
              </label>
            </div>
          </div>
        </div>
      </div>

      <div class="min-w-0 overflow-x-auto rounded-lg border border-line bg-surface" data-testid="adjust-table-scroll">
        <table class="w-full border-collapse text-sm" data-testid="adjust-table">
          <thead>
            <tr>
              <th scope="col" class="p-2 text-left text-xs">Criterion</th>
              <th v-for="x in kept" :key="x.a.id" scope="col" class="min-w-[140px] p-2 text-left" :data-testid="`adjust-col-${x.a.id}`">
                <div class="font-semibold">{{ x.a.name ?? x.a.id }}</div>
                <div v-if="x.unavailable.length" class="text-xs font-normal text-ink-muted" :data-testid="`adjust-unavailable-${x.a.id}`">{{ UNAVAILABLE_FOR_FILTER }}</div>
              </th>
            </tr>
          </thead>
          <tbody>
            <template v-for="g in groups" :key="g.id">
              <tr class="bg-surface-muted"><th :colspan="kept.length + 1" scope="colgroup" class="p-2 text-left text-xs font-semibold" :data-testid="`adjust-group-${g.id}`">{{ GROUP_TITLES[g.id] ?? g.id }}</th></tr>
              <tr v-for="c in g.rows" :key="c.id" :data-testid="`adjust-row-${c.id}`">
                <th scope="row" class="p-2 text-left font-normal">
                  <div>{{ c.label }}</div>
                  <div v-if="c.hint" class="text-xs text-ink-muted">{{ c.hint }}</div>
                </th>
                <td v-for="x in kept" :key="x.a.id" class="p-2 align-top" :class="isLeader(c, x.a.id) ? 'bg-profit-soft' : ''" :data-leader="isLeader(c, x.a.id) ? 'true' : 'false'" :data-testid="`adjust-cell-${c.id}-${x.a.id}`">
                  <template v-if="cellOf(c, x.a.id)?.text != null && cellOf(c, x.a.id)?.unavailable_reason == null">
                    <div>{{ cellOf(c, x.a.id).text }}</div>
                    <div v-if="isLeader(c, x.a.id)" class="text-xs text-ink-muted" data-testid="adjust-leader-label">{{ c.leader_label }}</div>
                  </template>
                  <template v-else>
                    <div>{{ UNAVAILABLE_VALUE }}</div>
                    <div v-if="cellOf(c, x.a.id)?.unavailable_reason" class="text-xs text-ink-muted" data-testid="adjust-cell-reason">{{ cellOf(c, x.a.id).unavailable_reason }}</div>
                  </template>
                </td>
              </tr>
            </template>
            <tr class="bg-surface-muted"><th :colspan="kept.length + 1" scope="colgroup" class="p-2 text-left text-xs font-semibold" data-testid="adjust-group-summary">Summary</th></tr>
            <tr data-testid="adjust-row-leads">
              <th scope="row" class="p-2 text-left font-normal"><div>Leads on</div><div class="text-xs text-ink-muted">count of the lines above</div></th>
              <td v-for="x in kept" :key="x.a.id" class="p-2" :data-testid="`adjust-leads-${x.a.id}`">{{ leadsText(x.a.id) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="refused.length" class="rounded-lg border border-line bg-surface p-3" data-testid="adjust-refused">
        <h3 class="text-sm font-semibold">Not offered for this strategy now</h3>
        <ul class="mt-1 text-sm">
          <li v-for="a in refused" :key="a.id" :data-testid="`adjust-refused-${a.id}`"><span class="font-semibold">{{ a.name ?? a.id }}</span>: {{ refusalText(a) }}<span v-if="a.refusal?.next_action" class="text-ink-muted"> {{ a.refusal.next_action }}</span></li>
        </ul>
      </div>

      <div class="flex flex-wrap items-center gap-2 rounded-lg border border-line bg-surface p-3" data-testid="adjust-prepare">
        <label class="flex items-center gap-2 text-sm">Approach to prepare
          <select v-model="pick" class="h-9 rounded border border-line px-2" :disabled="!pickable.length" data-testid="adjust-pick">
            <option v-for="x in pickable" :key="x.a.id" :value="x.a.id">{{ x.a.name ?? x.a.id }}</option>
          </select>
        </label>
        <button type="button" class="h-9 rounded-lg bg-accent px-3 font-medium text-white disabled:opacity-50" :disabled="!pick" data-testid="adjust-open" @click="openInBuilder">Open in builder and prepare basket</button>
        <span v-if="!pickable.length" class="text-sm text-ink-muted" data-testid="adjust-pick-empty">{{ NONE_TO_PREPARE }}</span>
        <ErrorMessage v-if="prepareError" :parts="prepareError" compact prefix="adjust-prepare-error" data-testid="adjust-prepare-error" />
      </div>
    </template>
  </section>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import api, { NEUTRAL_PARTS } from '@/services/api'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import AdjustPayoffChart from '@/components/strategy/AdjustPayoffChart.vue'
import { istTime } from '@/lib/displayFormat'
import { plainName } from '@/lib/saveDraft'
import { readTracking } from '@/lib/tracking'
import { stateRows } from '@/lib/adjustDrawer'
import {
  EMPTY_FILTERS, GROUP_TITLES, KIND_TITLES, NO_CHANGE_ID, RANGES, SIDE_TITLES, UNAVAILABLE_FOR_FILTER, UNAVAILABLE_VALUE,
  applyFilters, buildFacets, cmpDecimal, isNoChange, legsFromApproach, refusalText, refusedApproaches, showingText, tableApproaches,
} from '@/lib/adjustCompare'

const props = defineProps({
  strategyId: { type: [String, Number], required: true },
  client: { type: Object, default: () => api }, // the api module; a test passes a stand-in
  picked: { type: Array, default: () => [] }, // the approach ids ticked in the drawer (`pick` in the address); none = all
})
const emit = defineEmits(['prepare']) // { legs, underlying }: the chosen approach's legs as builder legs (no order is placed)

const INTRO = 'Each approach is shown as the whole trade, including P&L already booked. The green cells mark which approach leads on each line. The app picks no overall approach for you; you decide.'
const FILTER_NOTE = 'The choices and ranges come from this strategy\'s approaches right now, so they change as the market moves. "No change" stays in the table as the baseline.'
const NONE_TO_PREPARE = 'No approach is left to prepare: the filters keep only "No change". Clear the filters to choose one.'
const PALETTE = ['#2563eb', '#16a34a', '#d97706', '#9333ea', '#0891b2', '#db2777', '#65a30d', '#ea580c']

const state = ref('loading') // loading | ready | error
const reply = ref(null)
const name = ref(null)
const underlying = ref(null)
const errorParts = ref(NEUTRAL_PARTS)
const prepareError = ref(null)
const filters = ref(EMPTY_FILTERS())
const hiddenLines = ref([])
const pick = ref('')
const scope = ref(props.picked.length ? 'picked' : 'all') // 'all' | 'picked'
const why = ref(null) // the drawer's layers 1-2 again: { lines, rows } from a tracking read, null when it cannot be read

async function load() {
  state.value = 'loading'
  try {
    const res = await props.client.post(`/strategies/${props.strategyId}/adjustment-approaches`, {})
    reply.value = res.data
    state.value = 'ready'
  } catch (e) {
    errorParts.value = e?.parts ?? NEUTRAL_PARTS
    state.value = 'error'
    return
  }
  try { // layers 1-2 again (display only); a strategy that is not tracked simply shows no card
    const body = (await props.client.get(`/strategies/${props.strategyId}/tracking`)).data
    const t = readTracking(body)
    why.value = { lines: t.detections.map((d) => d.line), rows: stateRows(body) }
  } catch { why.value = null }
  try { // the name and underlying are a convenience: the compare works without them
    const s = (await props.client.get(`/strategies/${props.strategyId}`)).data
    name.value = plainName(s?.name)
    underlying.value = s?.definition?.underlying ?? null
  } catch { /* the heading then names no strategy */ }
}
onMounted(load)

// Which approaches the compare covers: all that apply, or only the ones picked in the drawer (No change is always in).
// A picked approach the server refused stays listed with its reason; a refused one nobody picked is not mentioned.
const view = computed(() => {
  const r = reply.value
  if (!r || scope.value !== 'picked' || !props.picked.length) return r
  return { ...r, approaches: (r.approaches ?? []).filter((a) => isNoChange(a) || props.picked.includes(a.id)) }
})
const facets = computed(() => (view.value ? buildFacets(view.value) : { kinds: [], sides: [], risk: [], ranges: {} }))
// REQ-157 AC-2: when the approaches are recomputed, a choice or limit that is no longer offered is dropped.
watch(facets, (f) => {
  const keep = (sel, list) => sel.filter((s) => list.some((x) => x.id === s))
  const cur = filters.value
  const limits = Object.fromEntries(Object.entries(cur.limits).filter(([k, v]) => f.ranges[k] && cmpDecimal(v, f.ranges[k].min) >= 0 && cmpDecimal(v, f.ranges[k].max) <= 0))
  filters.value = { kinds: keep(cur.kinds, f.kinds), sides: keep(cur.sides, f.sides), risk: keep(cur.risk, f.risk), limits }
})

const all = computed(() => (view.value ? tableApproaches(view.value) : []))
const kept = computed(() => (view.value ? applyFilters(view.value, filters.value) : []))
const allCount = computed(() => (reply.value ? tableApproaches(reply.value).length : 0))
const total = computed(() => all.value.length)
const refused = computed(() => (view.value ? refusedApproaches(view.value) : []))
const pickable = computed(() => kept.value.filter((x) => !isNoChange(x.a)))
watch(pickable, (list) => { if (!list.some((x) => x.a.id === pick.value)) pick.value = list[0]?.a.id ?? '' }, { immediate: true })

const chartLines = computed(() => {
  const curves = reply.value?.curves ?? {}
  const out = []
  if (curves.before) out.push({ id: 'before', name: 'Before', colour: '#6b7280', dashed: true, points: curves.before })
  kept.value.forEach((x, i) => {
    if (curves[x.a.id]) out.push({ id: x.a.id, name: x.a.name ?? x.a.id, colour: PALETTE[i % PALETTE.length], dashed: false, points: curves[x.a.id] })
  })
  return out
})
const toggleLine = (id) => { hiddenLines.value = hiddenLines.value.includes(id) ? hiddenLines.value.filter((x) => x !== id) : [...hiddenLines.value, id] }

const groups = computed(() => {
  const order = []
  for (const c of reply.value?.criteria ?? []) {
    let g = order.find((x) => x.id === c.group)
    if (!g) order.push((g = { id: c.group, rows: [] }))
    g.rows.push(c)
  }
  return order
})
const cellOf = (c, id) => c.values?.[id]
const isLeader = (c, id) => (c.leaders ?? []).includes(id) && cellOf(c, id)?.unavailable_reason == null && cellOf(c, id)?.text != null
const leadsText = (id) => { const l = reply.value?.leads?.[id]; return l ? `${l.n} of ${l.m}` : UNAVAILABLE_VALUE }

const spotLine = computed(() => {
  const s = reply.value?.spot
  if (!s || s.value == null) return `Spot not available${s?.text ? `: ${s.text}` : ''}`
  const src = s.source_text ?? s.source ?? ''
  const at = s.at ? istTime(s.at) : ''
  return ['Spot ' + s.value, src, at].filter(Boolean).join(' · ')
})

function flip(group, id) {
  const cur = filters.value[group]
  filters.value = { ...filters.value, [group]: cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id] }
}
function setLimit(r, v) {
  const span = facets.value.ranges[r.id]
  const end = r.at === 'most' ? span.max : span.min
  const limits = { ...filters.value.limits }
  if (cmpDecimal(v, end) === 0) delete limits[r.id]
  else limits[r.id] = v
  filters.value = { ...filters.value, limits }
}
const clearFilters = () => { filters.value = EMPTY_FILTERS() }

async function openInBuilder() {
  prepareError.value = null
  const a = all.value.find((x) => x.id === pick.value && x.id !== NO_CHANGE_ID)
  if (!a || !underlying.value) { prepareError.value = NEUTRAL_PARTS; return }
  try {
    const expiries = [...new Set((a.after_legs ?? []).map((l) => l.expiry))]
    const contracts = []
    for (const e of expiries) contracts.push(...(await props.client.get(`/catalogue/${underlying.value}/contracts?expiry=${e}`)).data.contracts)
    const legs = legsFromApproach(underlying.value, a, contracts, reply.value.spot?.at ?? null)
    if (!legs) { prepareError.value = NEUTRAL_PARTS; return }
    emit('prepare', { legs, underlying: underlying.value })
  } catch (e) {
    prepareError.value = e?.parts ?? NEUTRAL_PARTS
  }
}
</script>
