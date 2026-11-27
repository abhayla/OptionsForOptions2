<!-- P10 Wave 2 (ADR-330 (11), (13); ADR-008; ADR-003): the live "Plan watch" box. One row per trigger (profit target, loss stop, each
     adjustment rule, the Stops-panel index exits and leg stops): fires at / now / distance in rupees and percent / state. Every line,
     figure and reason is the server's (lib/planWatch, the one reader); this component only prints them with the app's rupee formatter.
     Refresh rides the host: it re-reads when `readTick` changes (the builder's book read, the Positions list read), but never
     sooner than PLAN_WATCH_MIN_READ_GAP_MS after the last read started, and never while one is unanswered (REQ-119 AC-3/AC-4).
     A slow or failed read after a good one keeps the last rows, marked updating / not current, with the server's as-of time. A figure the server sent as absent shows a dash and the reason, never 0.
     Decision support only: nothing here exits or places anything. -->
<template>
  <section ref="rootEl" class="rounded-lg border border-line bg-surface p-3 text-sm" data-testid="plan-watch" :data-currency="marked ? (notCurrent ? 'not_current' : 'updating') : 'current'" :data-compact="compact ? 'true' : 'false'" :data-strategy="strategyId">
    <h3 class="font-semibold" data-testid="plan-watch-title">Plan watch</h3>
    <!-- "Updating the numbers..." only ever sits over good rows (the mark under the table); with no good answer on screen a read in progress is "Loading" -->
    <p v-if="view === null || (view.state !== 'ok' && updating)" class="text-xs text-ink-muted" data-testid="plan-watch-loading">{{ LOADING_TEXT }}</p>
    <p v-else-if="view.state !== 'ok'" class="text-xs text-ink-muted" data-testid="plan-watch-message">{{ view.text }}</p>
    <template v-else>
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
            <td data-testid="pw-state">{{ STATE_TEXT[l.state] }}<span v-if="reasonOf(l)" class="block text-xs text-ink-muted" data-testid="pw-reason">{{ reasonOf(l) }}</span><span v-if="nextOf(l)" class="block text-xs text-ink-muted" data-testid="pw-next">{{ nextOf(l) }}</span></td>
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
              <td data-testid="pw-state">{{ STATE_TEXT[l.state] }}<span v-if="reasonOf(l)" class="block text-xs text-ink-muted" data-testid="pw-reason">{{ reasonOf(l) }}</span><span v-if="nextOf(l)" class="block text-xs text-ink-muted" data-testid="pw-next">{{ nextOf(l) }}</span></td>
            </tr>
          </tbody>
        </table>
      </template>
      <!-- ONE slot under the rows: the as-of line, or in its place the "updating / not current" mark (no layout shift per read) -->
      <p v-if="marked || (!compact && view.asOfText)" class="mt-1 text-xs text-ink-muted" data-testid="plan-watch-as-of">
        <span v-if="marked" data-testid="plan-watch-marked" :data-mark="notCurrent ? 'not_current' : 'updating'">{{ markedLine }}</span>
        <template v-else>{{ view.asOfText }}</template>
      </p>
    </template>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { PLAN_WATCH_COMPACT_READ_GAP_MS, PLAN_WATCH_MIN_READ_GAP_MS, readPlanWatch } from '@/lib/planWatch'
import { cancelPlanWatchRead, submitPlanWatchRead } from '@/lib/planWatchQueue'
import { rupeesText } from '@/lib/displayFormat'
import { PAUSED_TEXT } from '@/lib/priceState'
import { CHECK_STALE_TEXT } from '@/lib/sharedStateText'
import { PAPER_NO_FIGURE } from '@/lib/paperList'
import { saveStamp, savedSince } from '@/lib/planSaveClock'

// strategyId: the saved strategy. readTick: the host's own change signal (its last good book read); stale: the host says its last
// read failed, so every price-derived figure is paused (the one not-live wording of priceState). compact: the Positions row layout.
const props = defineProps({
  strategyId: { type: [Number, String], required: true },
  readTick: { type: null, default: null },
  stale: { type: Boolean, default: false },
  compact: { type: Boolean, default: false },
})
const NO_FIGURE = PAPER_NO_FIGURE
// new wording, pending owner read (27 Nov 2026): a FIRST read is queued or in flight (no catalogue or label had it)
const LOADING_TEXT = 'Loading the rule check...'
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
let reading = false // one request at a time per box: asks while it is unanswered are folded into ONE catch-up read (no stacking)
let queued = false // this box has a read waiting in the page queue (lib/planWatchQueue): a second ask is folded into it
let again = false
let againNow = false
let lastStart = null
let lastAnswer = null
let timer = null
let gone = false
const rootEl = ref(null)
const onScreen = ref(!props.compact || typeof IntersectionObserver === 'undefined') // no observer: treat as visible
const tabShown = ref(typeof document === 'undefined' || document.visibilityState === 'visible')
const active = () => !props.compact || (onScreen.value && tabShown.value)
const queueKey = Symbol('plan-watch-box')
let observer = null

// The builder's full box keeps the 15 s gap from the last START; a compact Positions row waits 60 s from its last ANSWER. Every read of
// every box goes through the one page queue (one in flight; compact reads also page-gapped; the full box goes first).
const gapMs = () => (props.compact ? PLAN_WATCH_COMPACT_READ_GAP_MS : PLAN_WATCH_MIN_READ_GAP_MS)
const lastMark = () => (props.compact ? lastAnswer : lastStart)

function clearTimer() { if (timer !== null) { clearTimeout(timer); timer = null } }
function drop() { clearTimer(); if (queued) { cancelPlanWatchRead(queueKey); queued = false; updating.value = false } }

function ask(now) {
  if (gone || !active()) return
  if (reading) { again = true; againNow = againNow || now; return }
  if (queued) return // coalesced: one queued read per box
  const wait = now || lastMark() === null ? 0 : lastMark() + gapMs() - Date.now()
  if (wait > 0) {
    if (timer === null) timer = setTimeout(() => { timer = null; ask(true) }, wait)
    return
  }
  clearTimer()
  queued = true
  updating.value = true // rows stay, marked "Updating the numbers..." while the read waits in the queue or is in flight
  submitPlanWatchRead(queueKey, props.compact ? 'compact' : 'full', run)
}
async function run() {
  queued = false
  reading = true
  lastStart = Date.now()
  const mine = ++seq
  const id = props.strategyId
  const stamp = saveStamp(id)
  updating.value = true
  try {
    const v = await readPlanWatch(id)
    if (gone || mine !== seq) return // unmounted, or the strategy changed meanwhile: the answer is ignored
    if (savedSince(id, stamp)) { again = true; againNow = true; return } // began before a save: dropped, a fresh read follows (plan-save-1127)
    if (v.state === 'superseded') return
    if (view.value?.state === 'ok' && (v.state === 'failed' || v.state === 'unavailable')) { notCurrent.value = true; return }
    view.value = v
    notCurrent.value = false
  } finally {
    reading = false
    lastAnswer = Date.now()
    if (!gone) updating.value = false
    if (!gone && again) { const now = againNow; again = false; againNow = false; ask(now) }
    else if (!gone && props.compact) ask(false) // the next compact read is due 60 s after this answer
  }
}
function syncActive() {
  if (gone) return
  if (active()) ask(false)
  else drop()
}
function onVisibility() { tabShown.value = document.visibilityState === 'visible'; syncActive() }
onMounted(() => {
  if (props.compact) {
    document.addEventListener('visibilitychange', onVisibility)
    tabShown.value = document.visibilityState === 'visible'
    if (typeof IntersectionObserver !== 'undefined' && rootEl.value) {
      observer = new IntersectionObserver((entries) => {
        const last = entries[entries.length - 1]
        if (last) { onScreen.value = last.isIntersecting; syncActive() }
      })
      observer.observe(rootEl.value)
    }
  }
  ask(true)
})
onBeforeUnmount(() => {
  gone = true
  clearTimer()
  cancelPlanWatchRead(queueKey)
  if (observer) observer.disconnect()
  if (props.compact) document.removeEventListener('visibilitychange', onVisibility)
})
watch(() => props.strategyId, () => {
  view.value = null; notCurrent.value = false; seq++
  clearTimer()
  if (queued) { cancelPlanWatchRead(queueKey); queued = false }
  lastAnswer = null; lastStart = null
  ask(true)
})
// a plan save of this strategy was stored: the rows stay marked "Updating" and a read that starts AFTER the save is made at once
watch(() => saveStamp(props.strategyId), () => { updating.value = true; ask(true) })
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
// A not-checked line shows the server's own sentence and its next step, placed, never composed. When the line's label already carries the
// sentence ("Stop: not being checked: <what_happened>") it is not repeated: only the next step goes under it.
const reasonOf = (l) => (props.stale ? PAUSED_TEXT : l.reason && l.label.includes(l.reason) ? null : l.reason)
const nextOf = (l) => (props.stale ? null : l.reasonNext)
</script>
