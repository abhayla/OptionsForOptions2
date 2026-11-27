<!-- P10 Wave 2 (ADR-330 (11), (13); ADR-008; ADR-003): the live "Plan watch" box. One row per trigger (profit target, loss stop, each
     adjustment rule, the Stops-panel index exits and leg stops): fires at / now / distance in rupees and percent / state. Every line,
     figure and reason is the server's (lib/planWatch, the one reader); this component only prints them with the app's rupee formatter.
     Refresh rides the host: it re-reads when `readTick` changes (the builder's book read, the Positions list read), but never
     sooner than PLAN_WATCH_MIN_READ_GAP_MS after the last read started, and never while one is unanswered (REQ-119 AC-3/AC-4).
     A slow or failed read after a good one keeps the last rows, marked updating / not current, with the server's as-of time. A figure the server sent as absent shows a dash and the reason, never 0.
     Decision support only: nothing here exits or places anything. -->
<template>
  <section class="rounded-lg border border-line bg-surface p-3 text-sm" data-testid="plan-watch" :data-currency="marked ? (notCurrent ? 'not_current' : 'updating') : 'current'" :data-compact="compact ? 'true' : 'false'" :data-strategy="strategyId">
    <h3 class="font-semibold" data-testid="plan-watch-title">Plan watch</h3>
    <p v-if="view === null" class="text-xs text-ink-muted" data-testid="plan-watch-loading">Reading the plan watch...</p>
    <p v-else-if="view.state !== 'ok'" class="text-xs text-ink-muted" data-testid="plan-watch-message">{{ view.text }}</p>
    <template v-else>
      <p v-if="marked" class="text-xs text-ink-muted" data-testid="plan-watch-marked" :data-mark="notCurrent ? 'not_current' : 'updating'">{{ markedLine }}</p>
      <p v-if="view.planState === 'no_plan'" class="text-ink-muted" data-testid="plan-watch-no-plan">{{ view.noPlanText }}</p>
      <p v-if="view.pausedText" class="text-ink-muted" data-testid="plan-watch-paused">{{ view.pausedText }}</p>
      <p v-if="view.empty && view.planState === 'planned'" class="text-ink-muted" data-testid="plan-watch-empty">{{ EMPTY_TEXT }}</p>
      <table v-if="view.planLines.length" class="mt-1 w-full" data-testid="plan-watch-plan">
        <thead><tr class="text-left text-xs text-ink-muted"><th scope="col">Trigger</th><th scope="col">Fires at</th><th scope="col">Now</th><th scope="col">Distance</th><th scope="col">State</th></tr></thead>
        <tbody>
          <tr v-for="l in view.planLines" :key="l.key" class="align-top" :class="{ 'opacity-60': marked }" data-testid="plan-watch-line" :data-key="l.key" :data-state="l.state">
            <td data-testid="pw-label">{{ l.label }}</td>
            <td class="tabular-nums" data-testid="pw-fires">{{ shown(l, l.firesAt) }}</td>
            <td class="tabular-nums" data-testid="pw-now">{{ stale ? NO_FIGURE : shown(l, l.now) }}</td>
            <td class="tabular-nums" data-testid="pw-distance">{{ stale ? NO_FIGURE : distanceText(l) }}</td>
            <td data-testid="pw-state">{{ STATE_TEXT[l.state] }}<span v-if="reasonOf(l)" class="block text-xs text-ink-muted" data-testid="pw-reason">{{ reasonOf(l) }}</span></td>
          </tr>
        </tbody>
      </table>
      <template v-if="view.armedLines.length">
        <p v-if="view.armedHeading" class="mt-2 text-xs font-medium text-ink-muted" data-testid="plan-watch-armed-heading">{{ view.armedHeading }}</p>
        <table class="mt-1 w-full" data-testid="plan-watch-armed">
          <tbody>
            <tr v-for="l in view.armedLines" :key="l.key" class="align-top" :class="{ 'opacity-60': marked }" data-testid="plan-watch-line" :data-key="l.key" :data-state="l.state">
              <td data-testid="pw-label">{{ l.label }}</td>
              <td class="tabular-nums" data-testid="pw-fires">{{ shown(l, l.firesAt) }}</td>
              <td class="tabular-nums" data-testid="pw-now">{{ stale ? NO_FIGURE : shown(l, l.now) }}</td>
              <td class="tabular-nums" data-testid="pw-distance">{{ stale ? NO_FIGURE : distanceText(l) }}</td>
              <td data-testid="pw-state">{{ STATE_TEXT[l.state] }}<span v-if="reasonOf(l)" class="block text-xs text-ink-muted" data-testid="pw-reason">{{ reasonOf(l) }}</span></td>
            </tr>
          </tbody>
        </table>
      </template>
      <p v-if="!compact && !marked && view.asOfText" class="mt-1 text-xs text-ink-muted" data-testid="plan-watch-as-of">{{ view.asOfText }}</p>
    </template>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { PLAN_WATCH_MIN_READ_GAP_MS, readPlanWatch } from '@/lib/planWatch'
import { rupeesText } from '@/lib/displayFormat'
import { PAUSED_TEXT } from '@/lib/priceState'
import { CHECK_STALE_TEXT } from '@/lib/sharedStateText'
import { PAPER_NO_FIGURE } from '@/lib/paperList'

// strategyId: the saved strategy. readTick: the host's own change signal (its last good book read); stale: the host says its last
// read failed, so every price-derived figure is paused (the one not-live wording of priceState). compact: the Positions row layout.
const props = defineProps({
  strategyId: { type: [Number, String], required: true },
  readTick: { type: null, default: null },
  stale: { type: Boolean, default: false },
  compact: { type: Boolean, default: false },
})
const NO_FIGURE = PAPER_NO_FIGURE
const EMPTY_TEXT = 'Nothing to watch yet.'
const UPDATING_TEXT = 'Updating the numbers...' // the one existing "updating" wording (LegList); REQ-119 AC-4
const STATE_TEXT = { watching: 'Watching', fired: 'Fired', not_applicable: 'Not applicable', not_computable: 'Not checked', paused: 'Paused' }

// view: the last answer worth showing (null before the first). A slow read (`updating`) or a failed one after a good answer
// (`notCurrent`) keeps the last good rows, marked, with the server's own as-of time; the first-load / not-available states stay
// for a screen that never had an answer.
const view = ref(null)
const updating = ref(false)
const notCurrent = ref(false)
const marked = computed(() => view.value?.state === 'ok' && (updating.value || notCurrent.value))
const markedLine = computed(() => [notCurrent.value ? CHECK_STALE_TEXT : UPDATING_TEXT, view.value?.asOfText].filter(Boolean).join(' '))
let seq = 0
let reading = false // one request at a time: asks while it is unanswered are folded into ONE catch-up read (no stacking)
let again = false
let againNow = false
let lastStart = null
let timer = null
let gone = false

function ask(now) {
  if (gone) return
  if (reading) { again = true; againNow = againNow || now; return }
  const wait = now || lastStart === null ? 0 : lastStart + PLAN_WATCH_MIN_READ_GAP_MS - Date.now()
  if (wait > 0) {
    if (timer === null) timer = setTimeout(() => { timer = null; ask(true) }, wait)
    return
  }
  run()
}
async function run() {
  reading = true
  lastStart = Date.now()
  const mine = ++seq
  const id = props.strategyId
  updating.value = view.value !== null
  try {
    const v = await readPlanWatch(id)
    if (gone || mine !== seq) return // unmounted, or the strategy changed meanwhile
    if (v.state === 'superseded') return
    if (view.value?.state === 'ok' && (v.state === 'failed' || v.state === 'unavailable')) { notCurrent.value = true; return }
    view.value = v
    notCurrent.value = false
  } finally {
    reading = false
    updating.value = false
    if (again && !gone) { const now = againNow; again = false; againNow = false; ask(now) }
  }
}
onMounted(() => ask(true))
onBeforeUnmount(() => { gone = true; if (timer !== null) clearTimeout(timer); timer = null })
watch(() => props.strategyId, () => {
  view.value = null; notCurrent.value = false; seq++
  if (timer !== null) { clearTimeout(timer); timer = null }
  ask(true)
})
watch(() => props.readTick, (t, old) => { if (t !== old) ask(false) })

// the server's figure as text in the line's unit: rupees with Indian grouping; index points and percent as sent; null is a dash
const shown = (l, v) => {
  if (v === null) return NO_FIGURE
  if (l.unit === 'pnl_rupees' || l.unit === 'option_price') return rupeesText(v)
  if (l.unit === 'index_points') return `${rupeesText(v).replace('₹', '')} pts`
  if (l.unit === 'percent') return `${v}%`
  return v
}
const distanceText = (l) => {
  if (l.distanceRs === null && l.distancePct === null) return NO_FIGURE
  const rs = l.distanceRs === null ? '' : shown(l, l.distanceRs)
  const pct = l.distancePct === null ? '' : `${l.distancePct}%`
  return rs && pct ? `${rs} (${pct})` : rs || pct
}
const reasonOf = (l) => (props.stale ? PAUSED_TEXT : l.reason)
</script>
