<!-- P10 Wave 2 (ADR-330 (11), (13); ADR-008; ADR-003): the live "Plan watch" box. One row per trigger (profit target, loss stop, each
     adjustment rule, the Stops-panel index exits and leg stops): fires at / now / distance in rupees and percent / state. Every line,
     figure and reason is the server's (lib/planWatch, the one reader); this component only prints them with the app's rupee formatter.
     Refresh rides the host: it re-reads when `readTick` changes (the builder's book read, the Positions list read), no timer here.
     A failed read clears the lines (no old figure). A figure the server sent as absent shows a dash and the reason, never 0.
     Decision support only: nothing here exits or places anything. -->
<template>
  <section class="rounded-lg border border-line bg-surface p-3 text-sm" data-testid="plan-watch" :data-compact="compact ? 'true' : 'false'" :data-strategy="strategyId">
    <h3 class="font-semibold" data-testid="plan-watch-title">Plan watch</h3>
    <p v-if="view === null" class="text-xs text-ink-muted" data-testid="plan-watch-loading">Reading the plan watch...</p>
    <p v-else-if="view.state !== 'ok'" class="text-xs text-ink-muted" data-testid="plan-watch-message">{{ view.text }}</p>
    <template v-else>
      <p v-if="view.planState === 'no_plan'" class="text-ink-muted" data-testid="plan-watch-no-plan">{{ view.noPlanText }}</p>
      <p v-if="view.pausedText" class="text-ink-muted" data-testid="plan-watch-paused">{{ view.pausedText }}</p>
      <p v-if="view.empty && view.planState === 'planned'" class="text-ink-muted" data-testid="plan-watch-empty">{{ EMPTY_TEXT }}</p>
      <table v-if="view.planLines.length" class="mt-1 w-full" data-testid="plan-watch-plan">
        <thead><tr class="text-left text-xs text-ink-muted"><th scope="col">Trigger</th><th scope="col">Fires at</th><th scope="col">Now</th><th scope="col">Distance</th><th scope="col">State</th></tr></thead>
        <tbody>
          <tr v-for="l in view.planLines" :key="l.key" class="align-top" data-testid="plan-watch-line" :data-key="l.key" :data-state="l.state">
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
            <tr v-for="l in view.armedLines" :key="l.key" class="align-top" data-testid="plan-watch-line" :data-key="l.key" :data-state="l.state">
              <td data-testid="pw-label">{{ l.label }}</td>
              <td class="tabular-nums" data-testid="pw-fires">{{ shown(l, l.firesAt) }}</td>
              <td class="tabular-nums" data-testid="pw-now">{{ stale ? NO_FIGURE : shown(l, l.now) }}</td>
              <td class="tabular-nums" data-testid="pw-distance">{{ stale ? NO_FIGURE : distanceText(l) }}</td>
              <td data-testid="pw-state">{{ STATE_TEXT[l.state] }}<span v-if="reasonOf(l)" class="block text-xs text-ink-muted" data-testid="pw-reason">{{ reasonOf(l) }}</span></td>
            </tr>
          </tbody>
        </table>
      </template>
      <p v-if="!compact && view.asOfText" class="mt-1 text-xs text-ink-muted" data-testid="plan-watch-as-of">{{ view.asOfText }}</p>
    </template>
  </section>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import { readPlanWatch } from '@/lib/planWatch'
import { rupeesText } from '@/lib/displayFormat'
import { PAUSED_TEXT } from '@/lib/priceState'
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
const STATE_TEXT = { watching: 'Watching', fired: 'Fired', not_applicable: 'Not applicable', not_computable: 'Not checked', paused: 'Paused' }

const view = ref(null)
let seq = 0
async function reread() {
  const mine = ++seq
  const id = props.strategyId
  const v = await readPlanWatch(id)
  if (mine !== seq) return // a newer read replaced this one
  if (v.state === 'superseded') return
  view.value = v
}
onMounted(reread)
watch(() => props.strategyId, () => { view.value = null; reread() })
watch(() => props.readTick, (t, old) => { if (t !== old) reread() })

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
