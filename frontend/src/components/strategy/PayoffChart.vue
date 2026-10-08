<!-- The payoff line drawn from the API's payoff points (W-064; REQ-034 AC-8: the same engine call as the table).
     New file (the legacy PayoffChart computes P&L in the browser, so it is not copied; ADR-008). Only the line's
     position is derived (src/lib/chartGeometry.js); every label is the API's own string. -->
<script setup>
import { computed } from 'vue'
import { plotPoints, plotAxes } from '@/lib/chartGeometry'

const props = defineProps({
  points: { type: Array, required: true },
  currentLevel: { type: String, default: null },
})
const W = 640
const H = 220
const PAD = 24
const plotted = computed(() => plotPoints(props.points, W, H, PAD))
const axes = computed(() => plotAxes(props.points, props.currentLevel, W, H, PAD))
const line = computed(() => plotted.value.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' '))
const first = computed(() => props.points[0])
const last = computed(() => props.points[props.points.length - 1])
</script>

<template>
  <figure class="rounded border border-line bg-surface p-3" data-testid="payoff-chart">
    <svg :viewBox="`0 0 ${W} ${H}`" role="img" aria-label="Profit and loss at expiry across index levels" class="w-full">
      <line :x1="PAD" :x2="W - PAD" :y1="axes.zeroY" :y2="axes.zeroY" stroke="#9aa3ad" stroke-dasharray="4 3" />
      <line v-if="axes.currentX !== null" :x1="axes.currentX" :x2="axes.currentX" :y1="PAD" :y2="H - PAD" stroke="#2f5bff" stroke-dasharray="2 3" data-testid="payoff-current" />
      <polyline :points="line" fill="none" stroke="#1b1f24" stroke-width="2" data-testid="payoff-line" />
    </svg>
    <figcaption class="mt-1 flex justify-between text-xs text-ink-muted">
      <span data-testid="payoff-first">{{ first?.level }}</span>
      <span>Index level at expiry; the dashed line is zero profit and loss</span>
      <span data-testid="payoff-last">{{ last?.level }}</span>
    </figcaption>
  </figure>
</template>
