<!-- GC-TP step 7b (REQ-109 AC-8; ADR-207 (5); RD-121; Sensibull Conditional Exits, catalogue 221-224): arm a Conditional exit
     (the index crosses above / below a level: exit all legs) or a per-leg Stop on one paper strategy, list its triggers
     and cancel the armed ones. Paper only: the exits are recorded in the app and nothing is sent to Zerodha. A level is
     judged on its text (a multiple of 0.05, not zero) and sent as typed; every level and contract shown is the server's text
     (ADR-008). A refusal shows the server's words, never swallowed. -->
<script setup>
import { computed, onMounted, ref } from 'vue'
import api, { NEUTRAL_ERROR } from '@/services/api'
import { PAPER_PRICE_REASON, paperPriceOk } from '@/lib/tracking'

const props = defineProps({
  strategyId: { type: Number, required: true },
  underlying: { type: String, default: '' },
  // the strategy's open legs: { index, label, contractId }
  legs: { type: Array, default: () => [] },
})

const LABEL = 'Paper - exits are recorded in the app, not sent to Zerodha'
const AT_LEAST_ONE = 'Enter at least one level'
const path = `/paper/strategies/${props.strategyId}/triggers`

const triggers = ref(null) // null = not read (or unreadable)
const error = ref('')
const busy = ref(false)
const above = ref('')
const below = ref('')
const stop = ref({}) // leg index -> { level, direction }

const typed = (v) => String(v ?? '').trim()
const stopOf = (i) => stop.value[i] ?? { level: '', direction: 'above' }
const setStop = (i, patch) => { stop.value = { ...stop.value, [i]: { ...stopOf(i), ...patch } } }

const ceReason = computed(() => {
  const set = [above.value, below.value].map(typed).filter(Boolean)
  if (!set.length) return AT_LEAST_ONE
  return set.every(paperPriceOk) ? '' : PAPER_PRICE_REASON
})
const stopReason = (i) => (paperPriceOk(stopOf(i).level) ? '' : PAPER_PRICE_REASON)

function take(data) {
  if (data && Array.isArray(data.triggers)) {
    triggers.value = data.triggers
    return true
  }
  triggers.value = null
  error.value = NEUTRAL_ERROR
  return false
}
const refusal = (e) => e?.parts?.what_happened || NEUTRAL_ERROR

async function run(call) {
  if (busy.value) return false
  busy.value = true
  error.value = ''
  try {
    return take((await call()).data)
  } catch (e) {
    error.value = refusal(e)
    return false
  } finally {
    busy.value = false
  }
}

onMounted(() => run(() => api.get(path)))

async function saveExit() {
  if (ceReason.value) return
  const body = { kind: 'conditional_exit' }
  if (typed(above.value)) body.above = typed(above.value)
  if (typed(below.value)) body.below = typed(below.value)
  if (await run(() => api.post(path, body))) {
    above.value = ''
    below.value = ''
  }
}
async function saveStop(leg) {
  if (stopReason(leg.index)) return
  const s = stopOf(leg.index)
  if (await run(() => api.post(path, { kind: 'leg_stop', contract_id: leg.contractId, direction: s.direction, level: typed(s.level) }))) {
    setStop(leg.index, { level: '' })
  }
}
const cancel = (t) => run(() => api.delete(`${path}/${t.id}`))
</script>

<template>
  <div class="mt-2 rounded border border-line p-2" data-testid="paper-stops">
    <p class="text-xs font-semibold" data-testid="stops-label">{{ LABEL }}</p>

    <div class="mt-2" data-testid="conditional-exit">
      <p class="font-medium">Conditional exit{{ underlying ? ` - ${underlying}` : '' }}</p>
      <p class="text-xs text-ink-muted">Exit all legs when the index crosses a level. Fill one or both.</p>
      <div class="mt-1 flex flex-wrap items-end gap-3">
        <label class="text-xs">Above<input v-model="above" type="text" inputmode="decimal" class="ml-1 w-28 rounded border border-line px-1 py-0.5 text-sm" data-testid="ce-above" /></label>
        <label class="text-xs">Below<input v-model="below" type="text" inputmode="decimal" class="ml-1 w-28 rounded border border-line px-1 py-0.5 text-sm" data-testid="ce-below" /></label>
        <button type="button" class="rounded border border-line px-3 py-1" :disabled="busy || !!ceReason" data-testid="ce-save" @click="saveExit">Save</button>
      </div>
      <p v-if="ceReason" class="text-xs text-ink-muted" data-testid="ce-reason">{{ ceReason }}</p>
    </div>

    <div v-if="legs.length" class="mt-2" data-testid="leg-stops">
      <p class="font-medium">Stop on a leg</p>
      <div v-for="l in legs" :key="l.index" class="mt-1 flex flex-wrap items-center gap-2" :data-testid="`stop-row-${l.index}`">
        <span class="min-w-40">{{ l.label }}</span>
        <select :value="stopOf(l.index).direction" class="rounded border border-line px-1 py-0.5" :data-testid="`stop-direction-${l.index}`" :aria-label="`Stop direction for ${l.label}`" @change="setStop(l.index, { direction: $event.target.value })">
          <option value="above">Above</option>
          <option value="below">Below</option>
        </select>
        <input :value="stopOf(l.index).level" type="text" inputmode="decimal" placeholder="Stop price" class="w-24 rounded border border-line px-1 py-0.5" :data-testid="`stop-level-${l.index}`" :aria-label="`Stop price for ${l.label}`" @input="setStop(l.index, { level: $event.target.value })" />
        <button type="button" class="rounded border border-line px-3 py-1" :disabled="busy || !!stopReason(l.index)" :data-testid="`stop-save-${l.index}`" @click="saveStop(l)">Save</button>
        <span v-if="stopReason(l.index) && typed(stopOf(l.index).level)" class="text-xs text-ink-muted" :data-testid="`stop-reason-${l.index}`">{{ stopReason(l.index) }}</span>
      </div>
    </div>

    <p v-if="error" class="mt-2 text-red-700" role="alert" data-testid="stops-error">{{ error }}</p>

    <div class="mt-2" data-testid="triggers">
      <p class="font-medium">Stops on this strategy</p>
      <p v-if="triggers && !triggers.length" class="text-xs text-ink-muted" data-testid="stops-empty">No stops set.</p>
      <ul v-else-if="triggers">
        <li v-for="t in triggers" :key="t.id" class="flex flex-wrap items-center gap-2 border-b border-line py-1" data-testid="trigger-row">
          <span>{{ t.kind === 'leg_stop' ? (t.contract_text ?? 'Leg stop') : 'Conditional exit' }}</span>
          <span data-testid="trigger-level">{{ t.level_text }}</span>
          <span class="rounded bg-surface-muted px-1" data-testid="trigger-state">{{ t.state }}</span>
          <button v-if="t.state === 'armed'" type="button" class="rounded border border-line px-2 py-0.5" :disabled="busy" :data-testid="`trigger-cancel-${t.id}`" @click="cancel(t)">Cancel</button>
        </li>
      </ul>
    </div>
  </div>
</template>
