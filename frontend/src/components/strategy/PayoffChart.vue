<!-- Copied/adapted from abhayla/algochanakya@bf9faf7:frontend/src/components/strategy/PayoffChart.vue (ADR-047).
     Changed: props are the outcome API's payoff points (level and pnl strings, as given) instead of number arrays;
     the tooltip shows the API's own strings; the numbers handed to chart.js are for drawing only.
     This file is on the no-client-maths scan's allowlist by name for that reason (tests/strategy-table.test.js).
     W-194 / GC-BM F-8, F-11: the expiry line is coloured by sign, a crossing segment split at the zero pixel.
     G-051 (REQ-083 AC-2): the hover is this component's own DOM tooltip (mouse and keyboard); it snaps to the nearest
     level the server SENT (a tie takes the lower level). No money value is parsed for display or computed between
     points (ADR-008). The % from spot is the one browser-computed figure: a ratio of two index levels the reply sent
     (the point shape is level / pnl / display: the reply carries no per-point percent), never money.
     GC-UI step 4 round b1 (REQ-083 AC-1..AC-7; Sensibull 012, 017, 018, 019, sb-02, layout only; our tokens):
       - both curves of ONE reply (`curves`, asked with both_views) on one chart, legend "At expiry" / "Estimated now"
         (REQ-083 AC-1 wording); a curve the reply marks unavailable is not drawn and its reason (for a calendar,
         ADR-143's line, which the server sends as the at-expiry reason) or its output label is shown small;
       - the hover shows both curves' own display strings at the nearest computed level, estimated first (AC-2);
       - no x-axis title (it was false on the Estimated curve), y titles "Profit / loss" and, with bars, "Open Interest";
       - the x domain is the first and last sent level (AC-7: the browser never extends a curve); Zoom in / out asks
         the engine for a wider or narrower range on the reply's own grid (start, end, step);
       - one solid "Current price: <spot>" marker, a mark at each summary.breakevens level;
       - hatched profit / loss zones; call / put OI bars per strike on the right axis, a null side draws no bar (AC-6),
         an "OI data at" strip that follows the hovered strike; SD band lines with a -2SD..2SD top axis (Fixed). -->
<template>
  <figure class="h-full" data-testid="payoff-chart">
    <div class="mb-1 flex flex-wrap items-center justify-between gap-3 text-xs text-ink-muted">
      <div class="flex flex-wrap items-center gap-4" data-testid="payoff-legend">
        <span v-for="c in shown" :key="c.view" class="flex items-center gap-1">
          <span :class="['inline-block h-0.5 w-4', c.view === 'estimated_now' ? 'bg-accent' : 'bg-profit']"></span>
          <span data-testid="payoff-legend-curve">{{ c.label }}</span>
        </span>
        <span v-if="sdText" data-testid="payoff-sd-mode">{{ sdText }}</span>
      </div>
      <div v-if="zoom && points0.length" role="group" aria-label="Zoom" class="inline-flex overflow-hidden rounded border border-line" data-testid="payoff-zoom">
        <button type="button" class="px-2 py-0.5 hover:text-ink" aria-label="Zoom out: a wider range" data-testid="payoff-zoom-out" @click="askZoom('out')">Zoom out</button>
        <button type="button" class="border-l border-line px-2 py-0.5 hover:text-ink" aria-label="Zoom in: a narrower range" data-testid="payoff-zoom-in" @click="askZoom('in')">Zoom in</button>
      </div>
    </div>
    <p v-if="notes.length" class="mb-1 text-xs text-ink-muted" data-testid="payoff-curve-note">{{ notes.join('; ') }}</p>
    <p v-if="!points0.length && unavailableReason" class="mb-2 text-sm text-ink-muted" data-testid="payoff-unavailable">{{ unavailableReason }}</p>
    <div
      ref="plot"
      class="relative h-72 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      tabindex="0"
      :aria-label="points0.length ? 'Payoff chart: use the left and right arrow keys to read each index level' : undefined"
      data-testid="payoff-plot"
      @mousemove="onMove"
      @mouseleave="hide"
      @focus="onFocus"
      @blur="hide"
      @keydown="onKey"
    >
      <canvas ref="chartCanvas" role="img" :aria-label="ariaLabel"></canvas>
      <span
        v-for="b in sdMarks"
        :key="b.label"
        class="pointer-events-none absolute top-0 -translate-x-1/2 text-[10px] text-ink-muted"
        :style="{ left: `${b.x}px` }"
        :data-level="b.level"
        data-testid="payoff-sd-label"
      >{{ b.label }}</span>
      <div
        v-if="spotMark"
        class="pointer-events-none absolute -translate-x-1/2 whitespace-nowrap rounded border border-line bg-surface px-1.5 text-[11px] text-ink"
        :style="{ left: `${spotMark.x}px`, top: `${spotMark.top}px` }"
        data-testid="payoff-current-price"
      >Current price: {{ spot }}</div>
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
    <div v-if="oi" class="mt-1 flex flex-wrap items-center gap-x-3 text-xs text-ink-muted">
      <template v-if="oiBars">
        <span class="tabular-nums text-ink" data-testid="payoff-oi-strip">{{ oiStrip }}</span>
        <span v-if="oi.read_at_display" data-testid="payoff-oi-read-at">{{ oi.read_at_display }}</span>
        <span v-if="oi.expiry_note" data-testid="payoff-oi-expiry-note">{{ oi.expiry_note }}</span>
      </template>
      <span v-else data-testid="payoff-oi-unavailable">{{ oi.unavailable_reason ? `${OI_NONE}: ${oi.unavailable_reason}` : OI_NONE }}</span>
    </div>
  </figure>
</template>

<script setup>
import { computed, nextTick, ref, watch, onMounted, onUnmounted } from 'vue'
import Chart from 'chart.js/auto'
import { hatchPattern, pointSigns, segmentColour } from '@/lib/payoffRegions'
import { groupMoney, strikeLabel } from '@/lib/displayFormat'
import { oiCompact } from '@/lib/legPicker'

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
  points: { type: Array, default: () => [] }, // the reply's payoff.points: drawn only when the reply has no `curves`
  spot: { type: String, default: '' }, // the reply's spot_level text, as sent ('' = no marker)
  view: { type: String, default: '' }, // the reply's payoff.view: names the one line of a reply without `curves`
  pnlText: { type: Object, default: null }, // { [level]: the table's display string } for the one line of `points`
  unavailableReason: { type: String, default: null }, // the reply's scenario.unavailable_reason when it has no curve
  curves: { type: Object, default: null }, // the reply's `curves` (both_views): { at_expiry, estimated_now }
  breakevens: { type: Array, default: () => [] }, // the reply's summary.breakevens (index levels as text)
  sd: { type: Object, default: null }, // the reply's standard_deviation block (sd_bands)
  oi: { type: Object, default: null }, // the reply's open_interest block (open_interest)
  zoom: { type: Object, default: null }, // { step, start, end } of the reply's scenario: the grid a zoom stays on
})
const emit = defineEmits(['zoom'])

// REQ-083 AC-1 wording ("At expiry", "Estimated on <date>", "now" until a target date exists: REQ-084, Later)
const CURVE_LABELS = { at_expiry: 'At expiry', estimated_now: 'Estimated now' }
const VIEWS = ['at_expiry', 'estimated_now']
const HOVER_ORDER = ['estimated_now', 'at_expiry'] // AC-2's example: the estimate first, then at expiry
const OI_NONE = 'OI not available for this expiry' // REQ-083 AC-6

// The curves to draw: the reply's `curves` (each only when available with points), else its one payoff line.
const shown = computed(() => {
  const c = props.curves
  if (c) return VIEWS.filter((v) => c[v]?.available && c[v].points?.length).map((v) => ({ view: v, label: CURVE_LABELS[v], points: c[v].points }))
  return props.points.length ? [{ view: props.view, label: CURVE_LABELS[props.view] ?? '', points: props.points, table: true }] : []
})
// The levels the hover walks: the first drawn curve's (the server sends both curves on the same levels).
const points0 = computed(() => shown.value[0]?.points ?? [])
// Small text under the legend: an unavailable curve's reason (a calendar: ADR-143's line) and a curve's output label.
const notes = computed(() => {
  const c = props.curves
  if (!c) return []
  const out = VIEWS.flatMap((v) => [c[v] && !c[v].available ? c[v].unavailable_reason : null, c[v]?.available ? c[v].output_label : null])
  // GC-UI b2 (b1 defect, Chrome 20:5x IST): each curve carries its own label, so "stale since 17:35 IST" and "stale since
  // 17:35 IST; estimated from spot" printed the stale part twice. Each "; " part is shown once, in the order sent.
  const parts = out.filter(Boolean).flatMap((s) => String(s).split(';').map((p) => p.trim()).filter(Boolean))
  return [...new Set(parts)]
})
const oiBars = computed(() => (props.oi?.available && props.oi.rows?.length ? props.oi.rows : null))
// GC-UI b2 (b1 defect, Chrome): the OI right axis printed raw counts ("8,000,000"); it now prints the contract count in
// the drawer's compact Indian units (80.0L, 1.00Cr) - the same helper, a display form of a count, not money
const oiTick = (value) => oiCompact(value)
const sdBands = computed(() => (props.sd?.available ? props.sd.bands ?? [] : []))
const sdText = computed(() => {
  if (!props.sd) return ''
  if (!props.sd.available) return props.sd.reason ? `SD bands: ${props.sd.reason}` : ''
  return props.sd.horizon_days ? `SD Fixed, ${props.sd.horizon_days} days` : 'SD Fixed'
})

const chartCanvas = ref(null)
let chartInstance = null
const drawTick = ref(0) // bumped after each draw, so the DOM marks re-read the new scale

const ariaLabel = computed(() => `Payoff chart: ${shown.value.map((c) => c.label).join(' and ') || 'no curve'}${props.spot ? `; current price ${props.spot}` : ''}`)

// Colours come from the design tokens (style.css), read at draw time; '' falls back to chart.js defaults (jsdom).
const token = (name) => (typeof window !== 'undefined' && window.getComputedStyle ? window.getComputedStyle(document.documentElement).getPropertyValue(name).trim() : '')

// Drawing only: chart.js needs numbers to place a point. Nothing here is displayed.
const lineData = (points) => points.map((p) => ({ x: Number(p.level), y: Number(p.pnl) }))
const barData = (rows, side) => rows.map((r) => ({ x: Number(r.strike), y: r[side] ?? null })) // null: no bar, never 0

// The spot line (solid) and the SD band lines (dashed); their words are DOM marks in the template.
const marks = {
  id: 'payoffMarks',
  afterDatasetsDraw(chart) {
    const { top, bottom, left, right } = chart.chartArea
    const ctx = chart.ctx
    const at = (level) => chart.scales.x.getPixelForValue(Number(level))
    const line = (x, colour, dash) => {
      if (!(x >= left && x <= right)) return
      ctx.save()
      ctx.setLineDash(dash)
      ctx.strokeStyle = colour
      ctx.lineWidth = 1
      ctx.beginPath()
      ctx.moveTo(x, top)
      ctx.lineTo(x, bottom)
      ctx.stroke()
      ctx.restore()
    }
    for (const b of sdBands.value) line(at(b.level), token('--color-ink-subtle') || '#8a929c', [3, 3])
    if (props.spot) line(at(props.spot), token('--color-ink') || '#1b1f24', [])
  },
}

const createChart = () => {
  // G-065 round 2 (REQ-148 AC-6): the previous reply's chart goes FIRST, so a reply with no curve never leaves the
  // old line on screen
  if (chartInstance) chartInstance.destroy()
  chartInstance = null
  if (!chartCanvas.value || !points0.value.length) return

  const ctx = chartCanvas.value.getContext ? chartCanvas.value.getContext('2d') : null
  const colours = { profit: token('--color-profit'), loss: token('--color-loss'), flat: token('--color-ink-muted') || '#5b6470' }
  const grid = token('--color-line')
  const bars = oiBars.value
  // beside the expiry curve the estimate is one accent line; drawn alone it keeps the profit / loss colours
  const accent = (c) => c.view === 'estimated_now' && shown.value.length > 1
  const curveSets = shown.value.map((c, i) => ({
    type: 'line', curve: c.view, label: c.label || 'P&L', data: lineData(c.points), borderWidth: 2, pointRadius: 0,
    pointHoverRadius: 4, tension: 0, spanGaps: false, order: 1,
    borderColor: accent(c) ? token('--color-accent') || '#2f5bff' : colours.profit,
    segment: accent(c) ? undefined : { borderColor: segmentColour(pointSigns(c.points), colours, (chart) => crossingGradient(chart, colours)) },
    // D-B15: only the first curve's zones are hatched (at expiry when it is drawn), so two fills never overlap
    fill: i === 0 ? { target: 'origin', above: hatchPattern(document, colours.profit || token('--color-profit-soft')), below: hatchPattern(document, colours.loss || token('--color-loss-soft')) } : false,
  }))
  const beSet = props.breakevens.length
    ? [{ type: 'line', label: 'Breakeven', data: props.breakevens.map((b) => ({ x: Number(b), y: 0 })), showLine: false, pointRadius: 5, pointStyle: 'triangle', pointBackgroundColor: token('--color-ink') || '#1b1f24', order: 0 }]
    : []
  const oiSets = bars
    ? [
        { type: 'bar', label: 'Call OI', yAxisID: 'y1', data: barData(bars, 'call_oi'), backgroundColor: token('--color-loss-soft') || '#fceded', borderColor: colours.loss, borderWidth: 1, barThickness: 6, order: 3 },
        { type: 'bar', label: 'Put OI', yAxisID: 'y1', data: barData(bars, 'put_oi'), backgroundColor: token('--color-profit-soft') || '#e7f6ee', borderColor: colours.profit, borderWidth: 1, barThickness: 6, order: 3 },
      ]
    : []

  chartInstance = new Chart(ctx, {
    type: 'line',
    data: { datasets: [...curveSets, ...beSet, ...oiSets] },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      parsing: true,
      layout: { padding: { top: 22 } }, // room for the SD top axis and the current-price box
      interaction: { mode: 'nearest', axis: 'x', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: { enabled: false }, // G-051: the DOM tooltip in the template (mouse and keyboard) replaces it
      },
      scales: {
        // D-B08: no x title; D-B11 / AC-7: the domain is the first and last SENT level, never wider
        x: { type: 'linear', min: firstLevel(), max: lastLevel(), display: true, grid: { display: false }, ticks: { maxTicksLimit: 8, font: { size: 10 } } },
        y: { display: true, title: { display: true, text: 'Profit / loss', font: { size: 11 } }, grid: grid ? { color: grid } : {}, ticks: { font: { size: 10 } } },
        y1: { display: !!bars, position: 'right', beginAtZero: true, title: { display: !!bars, text: 'Open Interest', font: { size: 11 } }, grid: { drawOnChartArea: false }, ticks: { font: { size: 10 }, callback: oiTick } },
      },
    },
    plugins: [marks],
  })
  drawTick.value++
}

// ---- hover: snap to a SENT point and show its strings ----
const plot = ref(null)
const tipEl = ref(null)
const index = ref(null) // the hovered point's index in points0, or null
const tipWidth = ref(0)

const box = () => plot.value?.getBoundingClientRect?.() ?? { left: 0, width: 0, height: 0 }
const areaOf = () => chartInstance?.chartArea ?? { left: 0, right: box().width, top: 0, bottom: box().height }
const firstLevel = () => Number(points0.value[0].level)
const lastLevel = () => Number(points0.value[points0.value.length - 1].level)
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
// The index in `list` of the entry whose level is nearest `value`; an exact tie takes the lower level. Selection
// only (index levels and strikes, never money): no value is made up.
const nearestBy = (list, value, levelOf) => {
  let best = null
  list.forEach((p, i) => {
    const lv = Number(levelOf(p))
    const d = Math.abs(lv - value)
    if (best === null || d < best.d || (d === best.d && lv < best.lv)) best = { i, d, lv }
  })
  return best ? best.i : null
}
const nearestIndex = (value) => nearestBy(points0.value, value, (p) => p.level)
// The % of an index level from spot, one decimal: a ratio of two reply levels, not money. '' when there is no spot.
const pctFromSpot = (level) => {
  const spot = Number(props.spot)
  if (!props.spot || !spot) return ''
  const pct = ((Number(level) - spot) / spot) * 100
  const text = Math.abs(pct).toFixed(1)
  return `${text === '0.0' ? '' : pct > 0 ? '+' : '-'}${text}%`
}

const hovered = computed(() => {
  const p = index.value === null ? null : points0.value[index.value]
  if (!p) return null
  const pct = pctFromSpot(p.level)
  const lvl = Number(p.level)
  const lines = HOVER_ORDER.flatMap((v) => shown.value.filter((c) => c.view === v))
    .flatMap((c) => {
      // the same computed level on that curve (same reply, same levels); a curve without it shows no line
      const q = c.points.find((x) => x.level === p.level)
      if (!q || !c.label) return []
      // a one-line reply prefers the table's display string for the level (same reply); else the point's own
      const pnl = (c.table ? props.pnlText?.[q.level] : null) ?? q.display ?? groupMoney(q.pnl)
      return [{ view: c.view, label: c.label, pnl }]
    })
  return { title: `At ${groupMoney(p.level)}${pct ? ` (${pct})` : ''}`, lines, x: pixelAt(lvl), area: areaOf(), level: lvl }
})
// The tooltip's left edge, kept inside the chart area at both ends.
const tipLeft = computed(() => {
  const h = hovered.value
  if (!h) return 0
  const w = tipWidth.value
  return Math.max(h.area.left, Math.min(h.x - w / 2, h.area.right - w))
})

// ---- DOM marks over the canvas (their words; the lines are drawn by the marks plugin) ----
const inArea = (x) => {
  const a = areaOf()
  return x >= a.left && x <= a.right
}
const sdMarks = computed(() => {
  void drawTick.value
  if (!points0.value.length) return []
  return sdBands.value.map((b) => ({ label: b.label, level: b.level, x: pixelAt(Number(b.level)) })).filter((b) => inArea(b.x))
})
const spotMark = computed(() => {
  void drawTick.value
  if (!props.spot || !points0.value.length) return null
  const x = pixelAt(Number(props.spot))
  return inArea(x) ? { x, top: areaOf().top } : null
})
// D-B17: the OI row of the hovered strike (nearest listed strike), else the one nearest spot, else the first.
const oiStrip = computed(() => {
  const rows = oiBars.value
  if (!rows) return ''
  const at = hovered.value ? hovered.value.level : props.spot ? Number(props.spot) : null
  const r = rows[at === null ? 0 : nearestBy(rows, at, (x) => x.strike)]
  return `OI data at ${strikeLabel(r.strike)} | Call OI ${r.call_oi_display} | Put OI ${r.put_oi_display}`
})

// ---- D-B10 / AC-7: Zoom asks the engine for a new range on the reply's own grid; nothing is drawn by the browser ----
const zoomRange = (dir) => {
  const step = Number(props.zoom?.step)
  const s = Number(props.zoom?.start)
  const e = Number(props.zoom?.end)
  if (!(step > 0) || !(e > s)) return null
  const k = Math.max(1, Math.floor((e - s) / step / 4)) // a quarter of the range, in whole steps
  const ns = dir === 'in' ? s + k * step : s - k * step
  const ne = dir === 'in' ? e - k * step : e + k * step
  if (!(ne - ns >= 2 * step) || !(ns > 0)) return null
  return { rangeStart: String(ns), rangeEnd: String(ne) }
}
const askZoom = (dir) => {
  const r = zoomRange(dir)
  if (r) emit('zoom', r)
}

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
  if (!points0.value.length) return hide()
  show(nearestIndex(levelAt(e.clientX - box().left)))
}
const onFocus = () => {
  if (points0.value.length) show(startIndex())
}
const onKey = (e) => {
  if (!points0.value.length || (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight')) return
  e.preventDefault()
  const from = index.value ?? startIndex()
  show(Math.max(0, Math.min(points0.value.length - 1, from + (e.key === 'ArrowRight' ? 1 : -1))))
}

// A new reply (or none: NOT_CONNECTED) drops the hover, so no number from an older answer stays on screen.
watch(points0, hide)
watch(() => [points0.value, props.spot, props.breakevens, props.sd, props.oi], createChart, { deep: true })
onMounted(createChart)
onUnmounted(() => {
  if (chartInstance) chartInstance.destroy()
})
</script>
