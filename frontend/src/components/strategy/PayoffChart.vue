<!-- Copied/adapted from abhayla/algochanakya@bf9faf7:frontend/src/components/strategy/PayoffChart.vue (ADR-047).
     Changed: props are the outcome API's payoff points (level and pnl strings, as given) instead of number arrays;
     the tooltip and the end labels show the API's own strings; the numbers handed to chart.js are for drawing only.
     W-127 (REQ-083): also draws the Estimated curve (blue), the expected-move lines, the current-price line and the OI
     bars from the API's own arrays. Follows Sensibull screens 012-021 (green/red expiry line + blue target-date curve,
     call OI red / put OI green on the same x axis, -2SD -1SD 1SD 2SD marked, "Current price" marker) and 122-123 (hover
     shows both values at one level). The hover shows the SERVER's strings at the nearest computed level; nothing is
     interpolated, and a curve is never drawn beyond the points it was sent (REQ-083 AC-2, AC-7).
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
        <span v-if="estimated.length" class="flex items-center text-blue-600" data-testid="legend-estimated">
          <span class="w-3 h-0.5 bg-blue-500 mr-1"></span> Estimated
        </span>
      </div>
    </div>
    <p v-if="!estimated.length && estimatedReason" class="mb-1 text-xs text-ink-muted" data-testid="estimate-reason">{{ estimatedReason }}</p>
    <div class="h-48">
      <canvas ref="chartCanvas" role="img" aria-label="Profit and loss at expiry and at the target date across index levels"></canvas>
    </div>
    <figcaption class="mt-1 flex justify-between text-xs text-ink-muted">
      <span data-testid="payoff-first">{{ points[0]?.level }}</span>
      <span>Index level</span>
      <span data-testid="payoff-last">{{ points[points.length - 1]?.level }}</span>
    </figcaption>
    <p v-if="estimated.length && estimateLabel" class="mt-1 text-xs text-ink-muted" data-testid="estimate-label">{{ estimateLabel }}</p>
    <p v-if="!bands.length && bandsReason" class="mt-1 text-xs text-ink-muted" data-testid="bands-reason">{{ bandsReason }}</p>
    <div v-if="oiShown" class="mt-1 flex items-center gap-3 text-xs" data-testid="oi-controls">
      <label><input v-model="oiMode" type="radio" value="oi" data-testid="oi-mode-oi" /> OI</label>
      <label><input v-model="oiMode" type="radio" value="change" data-testid="oi-mode-change" /> Change in OI</label>
      <span v-if="oi && oi.stale" data-testid="oi-stale">OI is older than its refresh interval (read {{ oi.read_at }}).</span>
    </div>
    <p v-else-if="showOi && oiReason" class="mt-1 text-xs text-ink-muted" data-testid="oi-reason">{{ oiReason }}</p>
  </figure>
</template>

<script>
// Pure drawing helpers (named exports so a test can call them). They turn the API's arrays into chart.js datasets or
// marker positions; the strings shown to the user are always the API's own.
const same = (a, b) => Number(a) === Number(b)

/** Index of the label nearest to `level` (ties go to the lower index): a marker position, never a displayed value. */
export function nearestIndex(labels, level) {
  let best = -1
  let gap = Infinity
  labels.forEach((l, i) => {
    const d = Math.abs(Number(l) - Number(level))
    if (d < gap) {
      gap = d
      best = i
    }
  })
  return best
}

/** Vertical markers: the SD bands and the current price, each at the nearest computed level. */
export function markers(labels, bands, current) {
  const out = bands.map((b) => ({ text: b.label, level: b.level, index: nearestIndex(labels, b.level), kind: 'sd' }))
  if (current != null && labels.length) out.push({ text: 'Current price', level: current, index: nearestIndex(labels, current), kind: 'spot' })
  return out
}

/** OI bar values aligned to the labels. A label with no strike, or a strike with no figure, is null: never a zero bar. */
export function oiSeries(labels, oi, mode) {
  const call = labels.map(() => null)
  const put = labels.map(() => null)
  if (!oi) return { call, put }
  const [cKey, pKey] = mode === 'change' ? ['call_oi_change', 'put_oi_change'] : ['call_oi', 'put_oi']
  for (const s of oi.strikes) {
    const i = labels.findIndex((l) => same(l, s.strike))
    if (i < 0) continue
    call[i] = s[cKey] ?? null
    put[i] = s[pKey] ?? null
  }
  return { call, put }
}

/** What the hover shows at one computed level: the server's strings for both curves (no interpolation). */
export function hoverRows(points, estimated, index) {
  return { level: points[index]?.level, expiry: points[index]?.pnl, estimated: estimated[index]?.pnl ?? null }
}
</script>

<script setup>
import { computed, ref, watch, onMounted, onUnmounted } from 'vue'
import Chart from 'chart.js/auto'
import { payoffRegions } from '@/lib/payoffRegions'

const props = defineProps({
  points: { type: Array, default: () => [] }, // [{ level: '22500', pnl: '1234.50' }] as the API sent them
  estimated: { type: Array, default: () => [] }, // whatif.estimated_points, same levels as `points`
  estimateLabel: { type: String, default: '' },
  estimatedReason: { type: String, default: '' },
  bands: { type: Array, default: () => [] }, // whatif.bands: [{ label: '1SD', level: '23400' }]
  bandsReason: { type: String, default: '' },
  currentLevel: { type: String, default: null },
  oi: { type: Object, default: null }, // whatif.oi
  oiReason: { type: String, default: '' },
  showOi: { type: Boolean, default: true }, // on by default at Standard and Advanced, off at Guided (REQ-083 AC-5)
})

const chartCanvas = ref(null)
const oiMode = ref('oi')
const oiShown = computed(() => props.showOi && props.oi && props.oi.strikes.length > 0)
let chartInstance = null

// Drawing only: chart.js needs numbers to place a point. Nothing here is displayed.
// A line has a value only over its own region (issue 297 item 4); elsewhere null, so no segment is drawn at 0.
const splitPnlData = (points) => {
  const pnl = points.map((p) => Number(p.pnl))
  const { loss, profit } = payoffRegions(points)
  return { profitData: pnl.map((v, i) => (profit[i] ? v : null)), lossData: pnl.map((v, i) => (loss[i] ? v : null)) }
}

// Vertical lines drawn over the plot at the computed marker levels (drawing only).
const markerPlugin = {
  id: 'markers',
  afterDatasetsDraw(chart, _args, opts) {
    const x = chart.scales?.x
    if (!x || !opts?.items) return
    const { ctx, chartArea } = chart
    ctx.save()
    ctx.font = '10px sans-serif'
    for (const m of opts.items) {
      if (m.index < 0) continue
      const px = x.getPixelForValue(m.index)
      ctx.strokeStyle = m.kind === 'spot' ? '#111827' : '#94a3b8'
      ctx.setLineDash(m.kind === 'spot' ? [] : [4, 3])
      ctx.beginPath()
      ctx.moveTo(px, chartArea.top)
      ctx.lineTo(px, chartArea.bottom)
      ctx.stroke()
      ctx.fillStyle = '#475569'
      ctx.fillText(m.text, px + 2, chartArea.top + 10)
    }
    ctx.restore()
  },
}

const createChart = () => {
  if (!chartCanvas.value || !props.points.length) return
  if (chartInstance) chartInstance.destroy()

  const ctx = chartCanvas.value.getContext('2d')
  const { profitData, lossData } = splitPnlData(props.points)
  const labels = props.points.map((p) => p.level)
  const datasets = [
    { label: 'Profit', data: profitData, borderColor: '#22c55e', backgroundColor: 'rgba(34,197,94,0.1)', borderWidth: 2, pointRadius: 0, tension: 0.1, fill: true },
    { label: 'Loss', data: lossData, borderColor: '#ef4444', backgroundColor: 'rgba(239,68,68,0.1)', borderWidth: 2, pointRadius: 0, tension: 0.1, fill: true },
  ]
  if (props.estimated.length) {
    datasets.push({ label: 'Estimated', data: props.estimated.map((p) => Number(p.pnl)), borderColor: '#3b82f6', borderWidth: 2, pointRadius: 0, tension: 0.1, fill: false })
  }
  if (oiShown.value) {
    const { call, put } = oiSeries(labels, props.oi, oiMode.value)
    datasets.push({ type: 'bar', label: 'Call OI', data: call, backgroundColor: 'rgba(239,68,68,0.35)', yAxisID: 'yOi', order: 5 })
    datasets.push({ type: 'bar', label: 'Put OI', data: put, backgroundColor: 'rgba(34,197,94,0.35)', yAxisID: 'yOi', order: 5 })
  }

  chartInstance = new Chart(ctx, {
    type: 'line',
    data: { labels, datasets },
    plugins: [markerPlugin],
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: 'index', intersect: false }, // the nearest COMPUTED level; no value between two points
      plugins: {
        legend: { display: false },
        markers: { items: markers(labels, props.bands, props.currentLevel) },
        tooltip: {
          callbacks: {
            title: (items) => 'Index level: ' + items[0].label,
            // the API's own strings, never the drawn numbers
            label: (item) => {
              const row = hoverRows(props.points, props.estimated, item.dataIndex)
              if (item.dataset.label === 'Estimated') return 'Estimated P/L: ₹' + row.estimated
              if (item.dataset.label === 'Call OI' || item.dataset.label === 'Put OI') {
                const s = props.oi.strikes.find((k) => same(k.strike, item.label))
                const key = (item.dataset.label === 'Call OI' ? 'call_' : 'put_') + (oiMode.value === 'change' ? 'oi_change' : 'oi')
                return item.dataset.label + ': ' + s?.[key]
              }
              return 'At expiry P/L: ₹' + row.expiry
            },
          },
        },
      },
      scales: {
        x: { display: true, grid: { display: false }, ticks: { maxTicksLimit: 8, font: { size: 10 } } },
        y: { display: true, grid: { color: '#f1f5f9' }, ticks: { font: { size: 10 } } },
        yOi: { display: false, position: 'right', beginAtZero: true, grid: { display: false } },
      },
    },
  })
}

watch(() => [props.points, props.estimated, props.bands, props.oi, props.showOi, props.currentLevel, oiMode.value], createChart, { deep: true })
onMounted(createChart)
onUnmounted(() => {
  if (chartInstance) chartInstance.destroy()
})
</script>
