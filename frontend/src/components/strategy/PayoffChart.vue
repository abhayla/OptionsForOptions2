<!-- Copied/adapted from abhayla/algochanakya@bf9faf7:frontend/src/components/strategy/PayoffChart.vue (ADR-047).
     Changed: props are the outcome API's payoff points (level and pnl strings, as given) instead of number arrays;
     the tooltip and the end labels show the API's own strings; the numbers handed to chart.js are for drawing only.
     This file is on the no-client-maths scan's allowlist by name for that reason (tests/strategy-table.test.js).
     W-194 (ADR-193 UI-121, UI study Region F, Revision 1; Sensibull S-012, S-015): restyled for the chart card. The
     expiry line is coloured by sign with a soft fill (token colours), a dashed vertical line marks the reply's spot with
     a label box holding the reply's own spot text, and a legend sits top right. Hover snaps to the nearest level the
     server SENT (chart.js 'nearest' on x over the sent points only) and shows that point's own strings: never an
     interpolated level, never a derived percent (the reply carries none).
     G-051 (REQ-083 AC-2; Sensibull S-122): the hover is now this component's own DOM tooltip (chart.js's canvas one is
     off), so mouse AND keyboard reach it and a test can read it. It snaps to the nearest level the server SENT (a tie
     takes the lower level) and shows "At <level> (<+/-x.x%>)" and one line per curve the reply carries, labelled by
     the reply's view, with the money text the table shows for that level (prop pnlText, the reply's own display
     strings) or, without it, the point's own pnl string regrouped by groupMoney. No money value is parsed for display
     or computed between points (ADR-008). The % from spot is the one browser-computed figure: a ratio of two index
     levels the reply sent (the reply carries no per-point percent), never money. A vertical guide line marks the
     hovered level; the tooltip is clamped inside the chart area. -->
<template>
  <figure class="h-full" data-testid="payoff-chart">
    <div class="mb-2 flex items-center justify-end gap-4 text-xs text-ink-muted" data-testid="payoff-legend">
      <span class="flex items-center gap-1"><span class="inline-block h-0.5 w-3 bg-profit"></span> Profit</span>
      <span class="flex items-center gap-1"><span class="inline-block h-0.5 w-3 bg-loss"></span> Loss</span>
      <span v-if="spot" class="flex items-center gap-1" data-testid="payoff-legend-spot"><span class="inline-block w-3 border-t border-dashed border-ink-muted"></span> Spot {{ spot }}</span>
    </div>
    <p v-if="!points.length && unavailableReason" class="mb-2 text-sm text-ink-muted" data-testid="payoff-unavailable">{{ unavailableReason }}</p>
    <div
      ref="plot"
      class="relative h-64 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      tabindex="0"
      :aria-label="points.length ? 'Payoff chart: use the left and right arrow keys to read each index level' : undefined"
      data-testid="payoff-plot"
      @mousemove="onMove"
      @mouseleave="hide"
      @focus="onFocus"
      @blur="hide"
      @keydown="onKey"
    >
      <canvas ref="chartCanvas" role="img" :aria-label="ariaLabel"></canvas>
      <div
        v-if="hovered"
        class="pointer-events-none absolute w-px border-l border-dashed border-ink"
        :style="{ left: `${hovered.x}px`, top: `${hovered.area.top}px`, height: `${hovered.area.bottom - hovered.area.top}px` }"
        data-testid="payoff-guide"
      ></div>
      <div
        v-if="hovered"
        ref="tipEl"
        role="status"
        class="pointer-events-none absolute z-10 whitespace-nowrap rounded border border-line bg-surface px-2 py-1 text-xs shadow"
        :style="{ left: `${tipLeft}px`, top: `${hovered.area.top}px` }"
        data-testid="payoff-tooltip"
      >
        <div class="font-semibold" data-testid="payoff-tooltip-title">{{ hovered.title }}</div>
        <div v-for="l in hovered.lines" :key="l.view" :data-view="l.view" data-testid="payoff-tooltip-line">
          <span class="text-ink-muted">{{ l.label }}</span> <span class="tabular-nums" data-testid="payoff-tooltip-pnl">{{ l.pnl }}</span>
        </div>
      </div>
    </div>
    <figcaption class="mt-1 flex justify-between text-xs text-ink-muted">
      <span data-testid="payoff-first">{{ points[0]?.level }}</span>
      <span>Index level at expiry</span>
      <span data-testid="payoff-last">{{ points[points.length - 1]?.level }}</span>
    </figcaption>
  </figure>
</template>

<script setup>
import { computed, nextTick, ref, watch, onMounted, onUnmounted } from 'vue'
import Chart from 'chart.js/auto'
import { pointSigns, segmentColour } from '@/lib/payoffRegions'
import { groupMoney } from '@/lib/displayFormat'

// GC-BM F-11: the pixel half of the zero-crossing colour (ADR-008 drawing exception): red below the pixel row of 0,
// green above it, one gradient across the segment that changes sign. Null when the chart has no drawable area.
function crossingGradient(chart, colours) {
  const area = chart?.chartArea
  const y0 = chart?.scales?.y?.getPixelForValue?.(0)
  if (!chart?.ctx?.createLinearGradient || !area || !(area.bottom > area.top) || !Number.isFinite(y0)) return null
  const at = Math.max(0, Math.min(1, (y0 - area.top) / (area.bottom - area.top)))
  const g = chart.ctx.createLinearGradient(0, area.top, 0, area.bottom)
  g.addColorStop(0, colours.profit)
  g.addColorStop(at, colours.profit)
  g.addColorStop(at, colours.loss)
  g.addColorStop(1, colours.loss)
  return g
}

const props = defineProps({
  points: { type: Array, default: () => [] }, // [{ level: '22500', pnl: '1234.50' }] as the API sent them
  spot: { type: String, default: '' }, // the reply's spot_level text, as sent ('' = no spot line)
  view: { type: String, default: '' }, // the reply's payoff.view: which curve the points are ('' = unknown: no P&L line)
  pnlText: { type: Object, default: null }, // { [level]: the reply's display string for that level } (the table's)
  unavailableReason: { type: String, default: null }, // the reply's scenario.unavailable_reason when it has no curve
})

// The reply's view decides the line's label; a view with no label here shows no line rather than a guessed one.
const VIEW_LABELS = { at_expiry: 'At expiry', estimated_now: 'Estimated now' }

const chartCanvas = ref(null)
let chartInstance = null

const ariaLabel = computed(() => 'Profit and loss at expiry across index levels' + (props.spot ? `; spot ${props.spot}` : ''))

// Colours come from the design tokens (style.css), read at draw time; '' falls back to chart.js defaults (jsdom).
const token = (name) => (typeof window !== 'undefined' && window.getComputedStyle ? window.getComputedStyle(document.documentElement).getPropertyValue(name).trim() : '')

// Drawing only: chart.js needs numbers to place a point. Nothing here is displayed.
// GC-BM F-8 (Sensibull S-012): ONE continuous line through every sent point (no null, so no gap where the P&L
// changes sign between two sent points, e.g. Estimated Now, which has no 0-P&L level). Each segment is coloured from
// the signs of its two SENT strings (signOf reads text, no number is compared): profit, loss, or neither for a run at
// 0.00 (issue 297 item 4: the 0.00 plateau is on neither line). A segment that crosses zero takes a vertical gradient
// split at the zero pixel, so the part above the axis is green and the part below red; a pixel, never a money value.
const lineData = (points) => points.map((p) => ({ x: Number(p.level), y: Number(p.pnl) }))

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
  // G-065 round 2 (REQ-148 AC-6): the previous reply's curve goes FIRST, so a reply with no curve for its view (At
  // Expiry on legs of two expiries) never leaves the old line on screen
  if (chartInstance) chartInstance.destroy()
  chartInstance = null
  if (!chartCanvas.value || !props.points.length) return

  const ctx = chartCanvas.value.getContext ? chartCanvas.value.getContext('2d') : null
  const colours = { profit: token('--color-profit'), loss: token('--color-loss'), flat: token('--color-ink-muted') || '#5b6470' }
  const grid = token('--color-line')

  chartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels: props.points.map((p) => p.level),
      datasets: [
        {
          label: 'P&L', data: lineData(props.points), borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, tension: 0,
          spanGaps: false, borderColor: colours.profit,
          segment: { borderColor: segmentColour(pointSigns(props.points), colours, (chart) => crossingGradient(chart, colours)) },
          fill: { target: 'origin', above: token('--color-profit-soft'), below: token('--color-loss-soft') },
        },
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
        tooltip: { enabled: false }, // G-051: the DOM tooltip in the template (mouse and keyboard) replaces it
      },
      scales: {
        x: { type: 'linear', display: true, grid: { display: false }, ticks: { maxTicksLimit: 8, font: { size: 10 } } },
        y: { display: true, grid: grid ? { color: grid } : {}, ticks: { font: { size: 10 } } },
      },
    },
    plugins: [spotLine],
  })
}

// ---- G-051 hover: snap to a SENT point and show its strings ----
const plot = ref(null)
const tipEl = ref(null)
const index = ref(null) // the hovered point's index in props.points, or null
const tipWidth = ref(0)

const box = () => plot.value?.getBoundingClientRect?.() ?? { left: 0, width: 0, height: 0 }
const areaOf = () => chartInstance?.chartArea ?? { left: 0, right: box().width, top: 0, bottom: box().height }
const firstLevel = () => Number(props.points[0].level)
const lastLevel = () => Number(props.points[props.points.length - 1].level)
// The index level under a canvas x pixel (chart.js's own scale; a linear stand-in over the sent range when none).
const levelAt = (x) => {
  const sx = chartInstance?.scales?.x
  if (sx?.getValueForPixel) return sx.getValueForPixel(x)
  const a = areaOf()
  return a.right > a.left ? firstLevel() + ((x - a.left) / (a.right - a.left)) * (lastLevel() - firstLevel()) : firstLevel()
}
const pixelAt = (level) => {
  const sx = chartInstance?.scales?.x
  if (sx?.getPixelForValue) return sx.getPixelForValue(level)
  const a = areaOf()
  const span = lastLevel() - firstLevel()
  return span ? a.left + ((level - firstLevel()) / span) * (a.right - a.left) : a.left
}
// The nearest SENT level to a value; an exact tie takes the lower level. Selection only: no value is made up.
const nearestIndex = (value) => {
  let best = null
  props.points.forEach((p, i) => {
    const lv = Number(p.level)
    const d = Math.abs(lv - value)
    if (best === null || d < best.d || (d === best.d && lv < best.lv)) best = { i, d, lv }
  })
  return best ? best.i : null
}
// The % of an index level from spot, one decimal: a ratio of two reply levels, not money. '' when there is no spot.
const pctFromSpot = (level) => {
  const spot = Number(props.spot)
  if (!props.spot || !spot) return ''
  const pct = ((Number(level) - spot) / spot) * 100
  const text = Math.abs(pct).toFixed(1)
  return `${text === '0.0' ? '' : pct > 0 ? '+' : '-'}${text}%`
}

const hovered = computed(() => {
  const p = index.value === null ? null : props.points[index.value]
  if (!p) return null
  const pct = pctFromSpot(p.level)
  const label = VIEW_LABELS[props.view]
  // the table's display string for this level (same reply); else the point's own display text (a strike level,
  // GC-BM F-8, is no table column); else its pnl text, regrouped as text only
  const pnl = props.pnlText?.[p.level] ?? p.display ?? groupMoney(p.pnl)
  return {
    title: `At ${groupMoney(p.level)}${pct ? ` (${pct})` : ''}`,
    lines: label ? [{ view: props.view, label, pnl }] : [],
    x: pixelAt(Number(p.level)),
    area: areaOf(),
  }
})
// The tooltip's left edge, kept inside the chart area at both ends.
const tipLeft = computed(() => {
  const h = hovered.value
  if (!h) return 0
  const w = tipWidth.value
  return Math.max(h.area.left, Math.min(h.x - w / 2, h.area.right - w))
})
const show = (i) => {
  index.value = i
  nextTick(() => {
    tipWidth.value = tipEl.value?.offsetWidth ?? 0
  })
}
const hide = () => {
  index.value = null
}
const startIndex = () => nearestIndex(props.spot ? Number(props.spot) : firstLevel())
const onMove = (e) => {
  if (!props.points.length) return hide()
  show(nearestIndex(levelAt(e.clientX - box().left)))
}
const onFocus = () => {
  if (props.points.length) show(startIndex())
}
const onKey = (e) => {
  if (!props.points.length || (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight')) return
  e.preventDefault()
  const from = index.value ?? startIndex()
  show(Math.max(0, Math.min(props.points.length - 1, from + (e.key === 'ArrowRight' ? 1 : -1))))
}

// A new reply (or none: NOT_CONNECTED) drops the hover, so no number from an older answer stays on screen.
watch(() => props.points, hide)
watch(() => [props.points, props.spot], createChart, { deep: true })
onMounted(createChart)
onUnmounted(() => {
  if (chartInstance) chartInstance.destroy()
})
</script>
