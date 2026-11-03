<!-- GC-IC1 steps 4b (REQ-155): the Compare page's three controls. No figure is computed here (ADR-008, ADR-012).
     (1) A-38 pause: GET/PUT/DELETE /api/strategies/{id}/monitoring-pause. The server reads the end as "HH:MM" (what a time
         input gives) and answers `until` as HHMM (1030); both texts (label, state_text, a refusal's reason) are the server's.
     (2) A-37 watch a level: GET /level-watch, PUT/DELETE /level-watch/{above|below}; the level goes as typed, the server
         answers the level as a plain number and refuses a non-number with its own reason.
     (3) A-23: the `delta_neutral` block of the approaches reply, shown as given (figures, or "not known" + its reason;
         absent on an older server = nothing drawn). -->
<template>
  <section class="flex min-w-0 flex-col gap-3" data-testid="adjust-controls">
    <div class="rounded-lg border border-line bg-surface p-3" data-testid="pause-card">
      <h3 class="text-sm font-semibold" data-testid="pause-label">{{ pause.data?.label ?? 'Pause' }}</h3>
      <p v-if="pause.data?.state_text" class="mt-1 text-sm" :data-paused="pause.data.paused ? 'true' : 'false'" data-testid="pause-state">{{ pause.data.state_text }}</p>
      <div class="mt-2 flex flex-wrap items-center gap-2">
        <input v-model="pauseTime" type="time" class="h-9 rounded border border-line px-2 text-sm" aria-label="Pause until" data-testid="pause-time" />
        <button type="button" class="h-9 rounded border border-line px-3 text-sm disabled:opacity-50" :disabled="!pauseTime || pause.busy" data-testid="pause-set" @click="setPause">Pause</button>
        <button type="button" class="h-9 rounded border border-line px-3 text-sm disabled:opacity-50" :disabled="pause.busy" data-testid="pause-clear" @click="clearPause">Clear</button>
      </div>
      <p v-if="pause.reason" class="mt-1 text-sm text-error" role="alert" data-testid="pause-refusal">{{ pause.reason }}</p>
      <ErrorMessage v-if="pause.failed" :parts="pause.failed" compact prefix="pause-failed" data-testid="pause-failed" />
    </div>

    <div class="rounded-lg border border-line bg-surface p-3" data-testid="watch-card">
      <h3 class="text-sm font-semibold">Watch an index level</h3>
      <div v-for="d in DIRECTIONS" :key="d" class="mt-2 flex flex-wrap items-center gap-2 text-sm" :data-testid="`watch-${d}`">
        <span class="w-14 capitalize">{{ d }}</span>
        <span class="min-w-16 tabular-nums" :data-testid="`watch-${d}-now`">{{ watch.data?.[d] ?? 'None' }}</span>
        <input v-model="levels[d]" inputmode="decimal" class="h-9 w-28 rounded border border-line px-2" :aria-label="`Level ${d}`" :data-testid="`watch-${d}-input`" />
        <button type="button" class="h-9 rounded border border-line px-3 disabled:opacity-50" :disabled="!levels[d] || watch.busy" :data-testid="`watch-${d}-set`" @click="setWatch(d)">Watch</button>
        <button type="button" class="h-9 rounded border border-line px-3 disabled:opacity-50" :disabled="watch.busy" :data-testid="`watch-${d}-clear`" @click="clearWatch(d)">Clear</button>
      </div>
      <p v-if="watch.reason" class="mt-1 text-sm text-error" role="alert" data-testid="watch-refusal">{{ watch.reason }}</p>
      <ErrorMessage v-if="watch.failed" :parts="watch.failed" compact prefix="watch-failed" data-testid="watch-failed" />
    </div>

    <div v-if="delta" class="rounded-lg border border-line bg-surface p-3" data-testid="delta-card" :data-known="delta.known ? 'true' : 'false'">
      <h3 class="text-sm font-semibold" data-testid="delta-label">{{ delta.label }}</h3>
      <p v-if="!delta.known" class="mt-1 text-sm" data-testid="delta-reason">{{ delta.reason }}<span v-if="delta.missing_leg" class="text-ink-muted"> ({{ delta.missing_leg }})</span></p>
      <dl v-else class="mt-2 grid grid-cols-[1fr_auto] gap-x-3 gap-y-1 text-sm">
        <template v-for="r in deltaRows" :key="r.id"><dt class="text-ink-muted">{{ r.label }}</dt><dd class="tabular-nums" :data-testid="`delta-${r.id}`">{{ r.value }}</dd></template>
      </dl>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import api, { NEUTRAL_PARTS } from '@/services/api'
import ErrorMessage from '@/components/common/ErrorMessage.vue'

const props = defineProps({
  strategyId: { type: [String, Number], required: true },
  client: { type: Object, default: () => api },
  deltaNeutral: { type: Object, default: null }, // the approaches reply's `delta_neutral` block; null = absent
})
const DIRECTIONS = ['above', 'below']
const base = computed(() => `/strategies/${props.strategyId}`)

// One state shape per control: data (the server's last answer), busy, reason (a 422/409 refusal text), failed (error parts).
const pause = reactive({ data: null, busy: false, reason: null, failed: null })
const watch = reactive({ data: null, busy: false, reason: null, failed: null })
const pauseTime = ref('')
const levels = reactive({ above: '', below: '' })

async function run(state, call) {
  state.busy = true
  state.reason = null
  state.failed = null
  try {
    state.data = (await call()).data
  } catch (e) {
    if (typeof e?.reason === 'string' && e.reason) state.reason = e.reason // the server's refusal, verbatim
    else state.failed = e?.parts ?? NEUTRAL_PARTS // a dropped connection etc.: named, the control stays usable
  } finally { state.busy = false }
}

onMounted(() => {
  run(pause, () => props.client.get(`${base.value}/monitoring-pause`))
  run(watch, () => props.client.get(`${base.value}/level-watch`))
})

const setPause = () => run(pause, () => props.client.put(`${base.value}/monitoring-pause`, { until: pauseTime.value })) // "10:30" as the server reads it
const clearPause = () => run(pause, () => props.client.delete(`${base.value}/monitoring-pause`))
const setWatch = (d) => run(watch, () => props.client.put(`${base.value}/level-watch/${d}`, { level: levels[d].trim() }))
const clearWatch = (d) => run(watch, () => props.client.delete(`${base.value}/level-watch/${d}`))

const delta = computed(() => props.deltaNeutral)
const deltaRows = computed(() => {
  const d = props.deltaNeutral
  if (!d?.known) return []
  const rows = [{ id: 'net_delta', label: 'Net delta', value: d.net_delta }]
  if (d.option_type) {
    rows.push({ id: 'option', label: `${d.option_type} ${d.option_strike ?? ''} lots`.replace('  ', ' '), value: d.option_lots })
    rows.push({ id: 'option_remaining', label: 'Delta left with the option', value: d.option_remaining })
  }
  rows.push({ id: 'future_lots', label: 'Future lots', value: d.future_lots })
  rows.push({ id: 'future_remaining', label: 'Delta left with the future', value: d.future_remaining })
  return rows
})
</script>
