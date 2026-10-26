<!-- Copied/adapted from abhayla/algochanakya@bf9faf7:frontend/src/components/strategy/PayoffChart.vue (ADR-047).
     Changed: props are the outcome API's payoff points (level and pnl strings, as given) instead of number arrays;
     the tooltip and the end labels show the API's own strings; the numbers handed to chart.js are for drawing only.
     This file is on the no-client-maths scan's allowlist by name for that reason (tests/strategy-table.test.js).
     W-194 (ADR-193 UI-121, UI study Region F, Revision 1; Sensibull S-012, S-015): restyled for the chart card. The
     expiry line is coloured by sign with a soft fill (token colours), a dashed vertical line marks the reply's spot with
     a label box holding the reply's own spot text, and a legend sits top right. Hover snaps to the nearest level the
     server SENT (chart.js 'nearest' on x over the sent points only) and shows that point's own strings: never an
     interpolated level, never a derived percent (the reply carries none). -->
<template>
  <figure class="h-full" data-testid="payoff-chart">
    <div class="mb-2 flex items-center justify-end gap-4 text-xs text-ink-muted" data-testid="payoff-legend">
      <span class="flex items-center gap-1"><span class="inline-block h-0.5 w-3 bg-profit"></span> Profit</span>
      <span class="flex items-center gap-1"><span class="inline-block h-0.5 w-3 bg-loss"></span> Loss</span>
      <span v-if="spot" class="flex items-center gap-1" data-testid="payoff-legend-spot"><span class="inline-block w-3 border-t border-dashed border-ink-muted"></span> Spot {{ spot }}</span>
    </div>
    <div class="h-64">
      <canvas ref="chartCanvas" role="img" :aria-label="ariaLabel"></canvas>
    </div>
    <figcaption class="mt-1 flex justify-between text-xs text-ink-muted">
      <span data-testid="payoff-first">{{ points[0]?.level }}</span>
      <span>Index level at expiry</span>
      <span data-testid="payoff-last">{{ points[points.length - 1]?.level }}</span>
    </figcaption>
  </figure>
</template>

<script setup>
import { computed, ref, watch, onMounted, onUnmounted } from 'vue'
import Chart from 'chart.js/auto'
import { payoffRegions } from '@/lib/payoffRegions'

const props = defineProps({
  points: { type: Array, default: () => [] }, // [{ level: '22500', pnl: '1234.50' }] as the API sent them
  spot: { type: String, default: '' }, // the reply's spot_level text, as sent ('' = no spot line)
})

const chartCanvas = ref(null)
let chartInstance = null

const ariaLabel = computed(() => 'Profit and loss at expiry across index levels' + (props.spot ? `; spot ${props.spot}` : ''))

// Colours come from the design tokens (style.css), read at draw time; '' falls back to chart.js defaults (jsdom).
const token = (name) => (typeof window !== 'undefined' && window.getComputedStyle ? window.getComputedStyle(document.documentElement).getPropertyValue(name).trim() : '')

// Drawing only: chart.js needs numbers to place a point. Nothing here is displayed.
// A line has a value only over its own region (issue 297 item 4); elsewhere null, so no segment is drawn at 0.
const splitPnlData = (points) => {
  const { loss, profit } = payoffRegions(points)
  const at = (p, on) => ({ x: Number(p.level), y: on ? Number(p.pnl) : null })
  return { profitData: points.map((p, i) => at(p, profit[i])), lossData: points.map((p, i) => at(p, loss[i])) }
}

// The spot marker: a dashed vertical line at the reply's spot and a small box with the reply's own spot text.
const spotLine = {
  id: 'spotLine',
  afterDatasetsDraw(chart) {
    if (!props.spot) return
    const x = chart.scales.x.getPixelForValue(Number(props.spot))
    const { top, bottom, left, right } = chart.chartArea
    if (!(x >= left && x <= right)) return
    const ctx = chart.ctx
    const ink = token('--color-ink-muted') || '#5b6470'
    ctx.save()
    ctx.setLineDash([4, 4])
    ctx.strokeStyle = ink
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(x, top)
    ctx.lineTo(x, bottom)
    ctx.stroke()
    ctx.setLineDash([])
    const text = props.spot
    ctx.font = '11px sans-serif'
    const w = ctx.measureText(text).width + 8
    ctx.fillStyle = token('--color-surface') || '#ffffff'
    ctx.strokeStyle = ink
    ctx.fillRect(x - w / 2, top, w, 16)
    ctx.strokeRect(x - w / 2, top, w, 16)
    ctx.fillStyle = token('--color-ink') || '#1b1f24'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(text, x, top + 8)
    ctx.restore()
  },
}

const createChart = () => {
  if (!chartCanvas.value || !props.points.length) return
  if (chartInstance) chartInstance.destroy()

  const ctx = chartCanvas.value.getContext ? chartCanvas.value.getContext('2d') : null
  const { profitData, lossData } = splitPnlData(props.points)
  const grid = token('--color-line')

  chartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels: props.points.map((p) => p.level),
      datasets: [
        { label: 'Profit', data: profitData, borderColor: token('--color-profit'), backgroundColor: token('--color-profit-soft'), borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, tension: 0, fill: 'origin' },
        { label: 'Loss', data: lossData, borderColor: token('--color-loss'), backgroundColor: token('--color-loss-soft'), borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, tension: 0, fill: 'origin' },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      parsing: true,
      // Hover snaps to the nearest SENT level on x: only the API's points exist in the data, so no level in between.
      interaction: { mode: 'nearest', axis: 'x', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          filter: (item) => item.raw && item.raw.y !== null,
          callbacks: {
            title: (items) => 'Index level: ' + props.points[items[0].dataIndex].level,
            // the API's own string, never the drawn number
            label: (item) => 'P/L: ₹' + props.points[item.dataIndex].pnl,
          },
        },
      },
      scales: {
        x: { type: 'linear', display: true, grid: { display: false }, ticks: { maxTicksLimit: 8, font: { size: 10 } } },
        y: { display: true, grid: grid ? { color: grid } : {}, ticks: { font: { size: 10 } } },
      },
    },
    plugins: [spotLine],
  })
}

watch(() => [props.points, props.spot], createChart, { deep: true })
onMounted(createChart)
onUnmounted(() => {
  if (chartInstance) chartInstance.destroy()
})
</script>
