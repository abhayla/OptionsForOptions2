<!-- Strategy controls (W-126; REQ-076 AC-4, REQ-077 AC-5, REQ-078 AC-2/AC-3/AC-6): Multiplier, Shift / Width / Hedge steppers
     and Reset Prices. Follows the Sensibull study: screens 108-110 (Shift shows the cumulative move, Width and Hedge steppers
     disabled when the shape does not allow them), bundle-findings 7.2 (group "Strike Controls"). A click emits only the
     control and its direction; the server does the work. No strike or price is computed here (ADR-008). -->
<template>
  <div class="mt-3 flex flex-wrap items-end gap-4 text-sm" data-testid="strategy-controls">
    <label class="flex flex-col">
      <span class="text-ink-muted">Multiplier</span>
      <input v-model.number="multiplier" class="w-16 rounded border border-line px-1" inputmode="numeric" data-testid="multiplier" @change="setMultiplier" />
    </label>
    <p v-if="multiplierBad" class="text-ink-muted" data-testid="multiplier-reason">Use a whole number from 1 to 50.</p>

    <div v-for="c in STEPPERS" :key="c.id" class="flex flex-col" :data-testid="`control-${c.id}`">
      <span class="text-ink-muted">{{ c.label }}<span v-if="c.id === 'shift' && controls.shift" data-testid="shift-total"> {{ shiftText(controls.shiftTotal) }}</span></span>
      <span class="flex gap-1">
        <button type="button" class="rounded border border-line px-2" :disabled="!controls[c.id]" :title="controls[c.id] ? '' : REASONS[c.id]" :data-testid="`${c.id}-minus`" @click="emit('edit', { control: c.id, direction: -1 })">-</button>
        <button type="button" class="rounded border border-line px-2" :disabled="!controls[c.id]" :title="controls[c.id] ? '' : REASONS[c.id]" :data-testid="`${c.id}-plus`" @click="emit('edit', { control: c.id, direction: 1 })">+</button>
      </span>
      <span v-if="!controls[c.id]" class="text-ink-muted" :data-testid="`${c.id}-reason`">{{ REASONS[c.id] }}</span>
    </div>

    <button type="button" class="rounded border border-line px-2 py-1" data-testid="reset-prices" @click="emit('edit', { control: 'reset_prices' })">Reset Prices</button>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { REASONS, multiplierValid, shiftText } from '@/lib/legEdit'

defineProps({
  controls: { type: Object, required: true },
})
const emit = defineEmits(['edit'])

const STEPPERS = [
  { id: 'shift', label: 'Shift' },
  { id: 'width', label: 'Width' },
  { id: 'hedge', label: 'Hedge' },
]
const multiplier = ref(1)
const multiplierBad = ref(false)

function setMultiplier() {
  multiplierBad.value = !multiplierValid(multiplier.value)
  if (!multiplierBad.value) emit('edit', { control: 'multiplier', multiplier: multiplier.value })
}
</script>
