<!-- Copied/adapted from abhayla/algochanakya@bf9faf7:frontend/src/components/strategy/PayoffChart.vue (ADR-047).
     Changed: props are the outcome API's payoff points (level and pnl strings, as given) instead of number arrays;
     the tooltip and the end labels show the API's own strings; the numbers handed to chart.js are for drawing only.
     This file is on the no-client-maths scan's allowlist by name for that reason (tests/strategy-table.test.js). -->
<template>
  <figure class="bg-white rounded-xl border border-gray-200 p-4 shadow-sm h-full" data-testid="payoff-chart">
    <div class="flex items-center justify-between mb-3">
      <h3 class="text-sm font-semibold text-gray-700">Payoff Diagram</h3>
      <div class="flex gap-3 text-xs">
        <span class="flex items-center text-green-600">
          <span class="w-3 h-0.5 bg-green-500 mr-1"></span> Profit
        </span>
        <span class="flex items-center text-red-600">
          <span class="w-3 h-0.5 bg-red-500 mr-1"></span> Loss
        </span>
      </div>
    </div>
    <div class="h-48">
      <canvas ref="chartCanvas" role="img" aria-label="Profit and loss at expiry across index levels"></canvas>
    </div>
    <figcaption class="mt-1 flex justify-between text-xs text-ink-muted">
      <span data-testid="payoff-first">{{ points[0]?.level }}</span>
      <span>Index level at expiry</span>
      <span data-testid="payoff-last">{{ points[points.length - 1]?.level }}</span>
    </figcaption>
  </figure>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue'
import Chart from 'chart.js/auto'

const props = defineProps({
  points: { type: Array, default: () => [] }, // [{ level: '22500', pnl: '1234.50' }] as the API sent them
})

const chartCanvas = ref(null)
let chartInstance = null

// Drawing only: chart.js needs numbers to place a point. Nothing here is displayed.
const splitPnlData = (points) => {
  const pnl = points.map((p) => Number(p.pnl))
  return { profitData: pnl.map((v) => (v >= 0 ? v : 0)), lossData: pnl.map((v) => (v <= 0 ? v : 0)) }
}

const createChart = () => {
  if (!chartCanvas.value || !props.points.length) return
  if (chartInstance) chartInstance.destroy()

  const ctx = chartCanvas.value.getContext('2d')
  const { profitData, lossData } = splitPnlData(props.points)

  chartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels: props.points.map((p) => p.level),
      datasets: [
        { label: 'Profit', data: profitData, borderColor: '#22c55e', backgroundColor: 'rgba(34,197,94,0.1)', borderWidth: 2, pointRadius: 0, tension: 0.1, fill: true },
        { label: 'Loss', data: lossData, borderColor: '#ef4444', backgroundColor: 'rgba(239,68,68,0.1)', borderWidth: 2, pointRadius: 0, tension: 0.1, fill: true },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title: (items) => 'Index level: ' + items[0].label,
            // the API's own string, never the drawn number
            label: (item) => 'P/L: ₹' + props.points[item.dataIndex].pnl,
          },
        },
      },
      scales: {
        x: { display: true, grid: { display: false }, ticks: { maxTicksLimit: 8, font: { size: 10 } } },
        y: { display: true, grid: { color: '#f1f5f9' }, ticks: { font: { size: 10 } } },
      },
    },
  })
}

watch(() => props.points, createChart, { deep: true })
onMounted(createChart)
onUnmounted(() => {
  if (chartInstance) chartInstance.destroy()
})
</script>
