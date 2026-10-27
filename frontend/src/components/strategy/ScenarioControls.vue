<!-- W-090 (REQ-034 AC-4, AC-6): the At Expiry / Estimated Now switch and the range pick (the step is the Admin setting) for the scenario
     columns. It only sends the pick (an event); every level and number comes back from the outcome API. The estimate
     label is the server's own text (scenario.label), shown whenever the Estimated Now column is on. -->
<script setup>
import { computed, ref, watch } from 'vue'
import { VIEWS, isPoints, rangeIsComplete } from '@/lib/scenarioChoice'
import FigureHint from '@/components/common/FigureHint.vue'
import Tooltip from '@/components/common/Tooltip.vue'

const props = defineProps({
  choice: { type: Object, required: true },
  scenarioLabel: { type: String, default: '' },
  // W-193 (I-9): the reply's data label (for example "estimated from spot"), the tooltip beside the Estimated Now switch
  // until the chart legend (PR-2c) draws the estimate; the server's text as sent.
  estimateNote: { type: String, default: '' },
})
const emit = defineEmits(['update:choice'])

const start = ref(props.choice.rangeStart)
const end = ref(props.choice.rangeEnd)
watch(() => [props.choice.rangeStart, props.choice.rangeEnd], ([s, e]) => {
  start.value = s
  end.value = e
})

const rangeText = computed(() => ({ rangeStart: start.value, rangeEnd: end.value }))
const rangeError = computed(() => {
  if (!isPoints(start.value) || !isPoints(end.value)) return 'Enter whole index points, for example 22800.'
  if (!rangeIsComplete(rangeText.value)) return 'Enter both the first and the last level, or leave both empty.'
  return ''
})

const set = (patch) => emit('update:choice', { ...props.choice, ...patch })
const applyRange = () => {
  if (!rangeError.value) set({ rangeStart: String(start.value).trim(), rangeEnd: String(end.value).trim() })
}
const resetRange = () => {
  start.value = ''
  end.value = ''
  set({ rangeStart: '', rangeEnd: '' })
}
</script>

<template>
  <!-- W-194: restyled for the chart card header (tokens only; Sensibull S-012 puts the expiry/now switch and range above
       the graph). Same controls, same test ids. -->
  <div class="text-sm" data-testid="scenario-controls">
    <div class="flex flex-wrap items-center gap-3">
      <div class="inline-flex items-center gap-1 rounded-md border border-line p-0.5" role="group" aria-label="Scenario column">
        <button
          v-for="v in VIEWS"
          :key="v.key"
          type="button"
          :data-testid="`view-${v.key}`"
          :aria-pressed="choice.view === v.key"
          :class="['rounded px-3 py-1 font-medium', choice.view === v.key ? 'bg-accent text-surface' : 'text-ink-muted hover:text-ink']"
          @click="set({ view: v.key })"
        >
          {{ v.label }}
        </button>
        <span v-if="estimateNote" data-testid="estimate-note"><Tooltip :text="estimateNote" label="About the price data of the estimate" /></span>
      </div>
      <label class="flex items-center gap-1.5 text-ink-muted">From
        <input v-model="start" data-testid="range-start" inputmode="numeric" aria-label="First level" class="w-20 rounded-md border border-line px-2 py-1 text-ink" />
      </label>
      <label class="flex items-center gap-1.5 text-ink-muted">To
        <input v-model="end" data-testid="range-end" inputmode="numeric" aria-label="Last level" class="w-20 rounded-md border border-line px-2 py-1 text-ink" />
      </label>
      <button type="button" data-testid="range-apply" class="rounded-md border border-line px-3 py-1 font-medium text-ink disabled:opacity-50" :disabled="!!rangeError" @click="applyRange">Apply range</button>
      <button type="button" data-testid="range-reset" class="rounded-md px-2 py-1 font-medium text-accent hover:text-accent-hover" @click="resetRange">Default range</button>
    </div>
    <p v-if="rangeError" class="mt-1 text-ink-muted" data-testid="range-hint">{{ rangeError }}</p>
    <div v-if="choice.view === 'estimated_now' && scenarioLabel" class="mt-2 flex items-center">
      <p class="text-ink-muted" data-testid="scenario-label">{{ scenarioLabel }}</p>
      <FigureHint id="estimated_now" />
    </div>
  </div>
</template>
