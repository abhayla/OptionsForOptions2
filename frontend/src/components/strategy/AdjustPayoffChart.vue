<!-- Adjust compare chart (GC-ADJ1 step 3; REQ-156 AC-5; ADR-008): the Before as a dashed line and each approach as its own line,
     with a legend chip per line that hides or shows it. Every level and P&L is the reply's text; chart.js receives the texts
     and coerces them for drawing only (no number is computed here). New small component: PayoffChart.vue is fixed to the
     two at-expiry / estimated curves of one reply, so it cannot hold one line per approach. -->
<template>
  <figure class="min-w-0" data-testid="adjust-chart">
    <div class="mb-1 flex flex-wrap items-center gap-2 text-xs" data-testid="adjust-legend">
      <button
        v-for="l in lines" :key="l.id" type="button" class="inline-flex items-center gap-1 rounded border border-line px-2 py-0.5"
        :class="hidden.includes(l.id) ? 'text-ink-muted line-through' : 'text-ink'" :aria-pressed="hidden.includes(l.id) ? 'false' : 'true'"
        :data-testid="`adjust-legend-${l.id}`" @click="emit('toggle', l.id)"
      >
        <span class="inline-block h-0.5 w-4" :style="{ background: l.colour, borderTop: l.dashed ? `2px dashed ${l.colour}` : 'none', height: l.dashed ? '0' : '2px' }"></span>{{ l.name }}
      </button>
    </div>
    <div class="relative h-72 w-full" data-testid="adjust-plot"><canvas ref="canvas" role="img" :aria-label="`Payoff at expiry, whole trade: ${shown.length} lines`"></canvas></div>
  </figure>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import Chart from 'chart.js/auto'

const props = defineProps({
  lines: { type: Array, default: () => [] }, // [{ id, name, colour, dashed, points: [[level, pnl], ...] }] as the reply sent them
  hidden: { type: Array, default: () => [] }, // ids the user hid
})
const emit = defineEmits(['toggle'])
const canvas = ref(null)
let chart = null
const shown = computed(() => props.lines.filter((l) => !props.hidden.includes(l.id)))

function draw() {
  chart?.destroy()
  chart = null
  if (!canvas.value) return
  chart = new Chart(canvas.value, {
    type: 'line',
    data: {
      datasets: shown.value.map((l) => ({
        label: l.name, id: l.id, borderColor: l.colour, backgroundColor: l.colour, borderWidth: 2, borderDash: l.dashed ? [6, 4] : [], pointRadius: 0,
        data: l.points.map(([x, y]) => ({ x, y })), // texts as sent; chart.js coerces them to pixels
      })),
    },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false, parsing: true,
      plugins: { legend: { display: false } },
      scales: { x: { type: 'linear', ticks: { maxTicksLimit: 8, font: { size: 10 } } }, y: { title: { display: true, text: 'Profit / loss', font: { size: 11 } }, ticks: { font: { size: 10 } } } },
    },
  })
}
onMounted(draw)
watch(() => [props.lines, props.hidden], draw, { deep: true })
onBeforeUnmount(() => chart?.destroy())
</script>
