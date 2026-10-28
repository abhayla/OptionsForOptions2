<!-- GC-UI step 5 (D-B40, D-B41; REQ-091; Sensibull screens 016, 216, 217, sb-06, layout only; our tokens, ADR-193): the
     Strategy Chart tab body. Two lines from the server's price-history `points`: "Strategy Price" on the left axis (a null
     point is a gap, drawn as a break, never joined) and the future (`future_label`) on the right axis. "Invert Price"
     re-requests with invert=true; the browser flips nothing (ADR-008). x axis = the minute index of the points, so closed
     hours and overnight gaps take no width; the ticks print each point's own time. Values go to chart.js as the strings
     the server sent; the tooltip prints the server's `display`. as_of, source and notes print under the chart. -->
<template>
  <section data-testid="price-chart">
    <p v-if="!strategyId" class="text-sm text-ink-muted" data-testid="price-chart-unsaved">{{ UNSAVED }}</p>
    <template v-else>
      <div class="mb-2 flex items-center justify-end">
        <label class="flex items-center gap-2 text-sm text-ink-muted">
          <input v-model="invert" type="checkbox" role="switch" :aria-checked="invert ? 'true' : 'false'" data-testid="invert-price" />
          {{ INVERT_LABEL }}
        </label>
      </div>
      <p v-if="held" class="text-sm text-ink-muted" data-testid="price-chart-held">{{ held }}</p>
      <p v-else-if="error" role="alert" class="text-sm text-ink-muted" data-testid="price-chart-error">{{ error }}</p>
      <p v-else-if="loading && !reply" class="text-sm text-ink-muted" data-testid="price-chart-loading">{{ LOADING }}</p>
      <template v-else-if="reply">
        <p v-if="reason" class="text-sm text-ink-muted" data-testid="price-chart-reason">{{ reason }}</p>
        <div v-else class="relative h-72" data-testid="price-chart-plot">
          <canvas ref="canvas" role="img" :aria-label="`${LEFT_AXIS_TITLE} and ${reply.future_label}`"></canvas>
        </div>
        <p v-if="asOf || reply.source" class="mt-2 text-xs text-ink-muted" data-testid="price-chart-asof">{{ [asOf, reply.source].filter(Boolean).join(' - ') }}</p>
        <p v-if="notes.length" class="mt-1 text-xs text-ink-muted" data-testid="price-chart-notes">{{ notes.join('; ') }}</p>
      </template>
    </template>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import Chart from 'chart.js/auto'
import api from '@/services/api'
import { INVERT_LABEL, LEFT_AXIS_TITLE, LOADING, SWITCHED_OFF, UNSAVED, asOfText, pointText, reasonOf, seriesOf } from '@/lib/priceChart'

// S5-3: a cold open waits on several Kite calls one after another; the client's global 10 s would cancel it.
const PRICE_HISTORY_TIMEOUT_MS = 60000
const TIMED_OUT = 'The strategy chart is taking longer than usual. Please try again in a moment.' // pending owner read

const props = defineProps({
  strategyId: { type: Number, default: null }, // the saved strategy's id; null = not saved, nothing to ask
  active: { type: Boolean, default: true }, // the tab is open: ask only then (the card keeps panels mounted)
})

const invert = ref(false)
const reply = ref(null)
const loading = ref(false)
const held = ref('')
const error = ref('')
const canvas = ref(null)
let chart = null
let seq = 0
let asked = '' // the request last sent: reopening the tab never re-asks the same thing

const reason = computed(() => (reply.value ? reasonOf(reply.value) : null))
const asOf = computed(() => (reply.value ? asOfText(reply.value.as_of) : null))
const notes = computed(() => (Array.isArray(reply.value?.notes) ? reply.value.notes : []))

const token = (name) => (typeof window !== 'undefined' && window.getComputedStyle ? window.getComputedStyle(document.documentElement).getPropertyValue(name).trim() : '')

function drop() {
  if (chart) { chart.destroy(); chart = null }
}

function draw() {
  drop()
  const r = reply.value
  if (!r || reason.value || !canvas.value) return
  const ctx = canvas.value.getContext?.('2d') ?? null
  const { strategy, future } = seriesOf(r.points)
  const accent = token('--color-accent') || '#1d4ed8'
  const ink = token('--color-ink-muted') || '#6b7280'
  const grid = token('--color-line')
  const pts = r.points
  const shown = (i, key) => pts[i]?.[key]?.display ?? '-'
  chart = new Chart(ctx, {
    type: 'line',
    data: {
      datasets: [
        { label: LEFT_AXIS_TITLE, yAxisID: 'y', data: strategy, borderColor: accent, borderWidth: 1.5, pointRadius: 0, spanGaps: false, parsing: true },
        { label: r.future_label, yAxisID: 'y1', data: future, borderColor: ink, borderWidth: 1.5, pointRadius: 0, spanGaps: false, parsing: true },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: true, position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } },
        tooltip: {
          callbacks: {
            title: (items) => pointText(pts[items[0]?.dataIndex]?.t),
            label: (item) => `${item.dataset.label}: ${shown(item.dataIndex, item.datasetIndex === 0 ? 'strategy' : 'future')}`,
          },
        },
      },
      scales: {
        x: {
          type: 'linear', display: true, grid: { display: false },
          ticks: { maxTicksLimit: 8, font: { size: 10 }, callback: (v) => pointText(pts[v]?.t) },
        },
        y: { display: true, position: 'left', title: { display: true, text: LEFT_AXIS_TITLE, font: { size: 11 } }, grid: grid ? { color: grid } : {}, ticks: { font: { size: 10 } } },
        y1: { display: true, position: 'right', title: { display: true, text: r.future_label, font: { size: 11 } }, grid: { drawOnChartArea: false }, ticks: { font: { size: 10 } } },
      },
    },
  })
}

async function load() {
  if (!props.strategyId || !props.active) return
  const key = `${props.strategyId}|${invert.value}`
  if (key === asked && (reply.value || held.value)) return
  asked = key
  const mine = ++seq
  loading.value = true
  held.value = ''
  error.value = ''
  try {
    const { data } = await api.get(`/strategies/${props.strategyId}/price-history`, { params: { invert: invert.value }, timeout: PRICE_HISTORY_TIMEOUT_MS })
    if (mine !== seq) return // a newer request is out: the older answer is dropped
    reply.value = data
  } catch (e) {
    if (mine !== seq || e?.superseded) return
    reply.value = null
    drop()
    if (e?.status === 409) held.value = e?.parts?.what_happened || SWITCHED_OFF
    else if (e?.code === 'ECONNABORTED') error.value = TIMED_OUT
    else error.value = e?.message || 'Something went wrong. Please try again.'
  } finally {
    if (mine === seq) loading.value = false
  }
}

watch(() => [props.strategyId, props.active, invert.value], load, { immediate: true })
watch(reply, async () => { await nextTick(); draw() })
onBeforeUnmount(drop)
</script>
