<!-- W-090 (REQ-034 AC-4, AC-6): the At Expiry / Estimated Now switch and the range pick (the step is the Admin setting) for the scenario
     columns. It only sends the pick (an event); every level and number comes back from the outcome API. The estimate
     label is the server's own text (scenario.label), shown whenever the Estimated Now column is on. -->
<script setup>
import { computed, ref, watch } from 'vue'
import { VIEWS, isPoints, rangeIsComplete } from '@/lib/scenarioChoice'
import FigureHint from '@/components/common/FigureHint.vue'

const props = defineProps({
  choice: { type: Object, required: true },
  scenarioLabel: { type: String, default: '' },
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
  <div class="mt-3 rounded border border-line bg-surface p-3 text-sm" data-testid="scenario-controls">
    <div class="flex flex-wrap items-center gap-4">
      <div class="flex items-center gap-2" role="group" aria-label="Scenario column">
        <button
          v-for="v in VIEWS"
          :key="v.key"
          type="button"
          :data-testid="`view-${v.key}`"
          :aria-pressed="choice.view === v.key"
          :class="['px-3 py-1.5 font-medium rounded-lg', choice.view === v.key ? 'bg-[#387ed1] text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200']"
          @click="set({ view: v.key })"
        >
          {{ v.label }}
        </button>
      </div>
      <label class="flex items-center gap-2">First level
        <input v-model="start" data-testid="range-start" inputmode="numeric" class="w-24 rounded border border-line px-2 py-1" />
      </label>
      <label class="flex items-center gap-2">Last level
        <input v-model="end" data-testid="range-end" inputmode="numeric" class="w-24 rounded border border-line px-2 py-1" />
      </label>
      <button type="button" data-testid="range-apply" class="rounded-lg bg-gray-100 px-3 py-1.5 font-medium disabled:opacity-50" :disabled="!!rangeError" @click="applyRange">Apply range</button>
      <button type="button" data-testid="range-reset" class="rounded-lg bg-gray-100 px-3 py-1.5 font-medium" @click="resetRange">Default range</button>
    </div>
    <p v-if="rangeError" class="mt-1 text-ink-muted" data-testid="range-hint">{{ rangeError }}</p>
    <div v-if="choice.view === 'estimated_now' && scenarioLabel" class="mt-2 flex items-center">
      <p class="text-ink-muted" data-testid="scenario-label">{{ scenarioLabel }}</p>
      <FigureHint id="estimated_now" />
    </div>
  </div>
</template>
