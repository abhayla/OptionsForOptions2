<!-- Greeks panel (W-127; REQ-084 AC-8, AC-9; shown at the Advanced level only). Follows Sensibull screens 212-217 (Greeks tab,
     "Multiply by Lot Size": delta 0.52 -> 34): per-leg rows and a Total, with a per unit / per position switch. Both
     scalings come from the server (the engine multiplies by quantity and lot size); the switch only chooses which set to
     show, and the rupee examples are the server's sentences (AC-9: the browser does not multiply Greeks into rupees). -->
<template>
  <section class="rounded border border-line bg-surface p-3" data-testid="greeks-panel">
    <div class="flex items-center justify-between">
      <h3 class="text-sm font-medium">Greeks at your target</h3>
      <div role="group" aria-label="Greeks scale" class="text-xs">
        <button type="button" data-testid="greeks-per-unit" :aria-pressed="!perPosition" class="px-2 underline" @click="perPosition = false">Per unit</button>
        <button type="button" data-testid="greeks-per-position" :aria-pressed="perPosition" class="px-2 underline" @click="perPosition = true">Per position</button>
      </div>
    </div>

    <p v-if="reason" class="mt-1 text-xs" data-testid="greeks-reason">{{ reason }}</p>
    <template v-else-if="greeks">
      <table class="mt-2 w-full text-sm" data-testid="greeks-table">
        <thead>
          <tr class="text-left text-xs text-ink-muted"><th>Leg</th><th>Delta</th><th>Gamma</th><th>Theta</th><th>Vega</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in greeks.rows" :key="row.instrument_id" data-testid="greeks-row">
            <td>{{ nameOf(row.instrument_id) }}</td>
            <td v-for="g in GREEKS" :key="g">{{ (perPosition ? row.per_position : row.per_unit)[g] }}</td>
          </tr>
          <tr class="font-medium" data-testid="greeks-total">
            <td>Total</td>
            <td v-for="g in GREEKS" :key="g">{{ (totalShown)[g] }}</td>
          </tr>
        </tbody>
      </table>
      <p v-if="!perPosition && !greeks.total_per_unit" class="text-xs text-ink-muted" data-testid="greeks-no-unit-total">
        The legs have different lot sizes, so there is no per unit total.
      </p>
      <ul class="mt-2 text-xs" data-testid="greeks-examples">
        <li v-for="e in greeks.examples" :key="e.greek">{{ e.sentence }}</li>
      </ul>
    </template>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  greeks: { type: Object, default: null }, // whatif.greeks as sent
  reason: { type: String, default: null }, // whatif.greeks_reason
  nameOf: { type: Function, default: (id) => id },
})
const GREEKS = ['delta', 'gamma', 'theta', 'vega']
const perPosition = ref(true)
// per unit total is absent when lot sizes differ; the position total is then shown in its own column set only
const totalShown = computed(() => (perPosition.value ? props.greeks.total_per_position : props.greeks.total_per_unit ?? {}))
</script>
