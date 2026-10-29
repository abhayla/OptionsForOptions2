<!-- GC-TP R-19a (REQ-144 AC-1..AC-5; Sensibull study screen 012 / 123, layout only): the Projected profit / Projected loss
     badge drawn on the payoff graph. Every word and number is the reply's own text (target.badge, made on the server,
     ADR-008): the label with its amount, the percent of margin needed or the reason it is absent, or "Projected figure not
     available" with its reason. After a failed request (`stale`) the old amount is not shown: a dash and the app's existing
     stale sentence stand in its place, never 0 or the old value. -->
<script setup>
import { computed } from 'vue'
import { healthSentence } from '@/lib/dataHealthText'

const props = defineProps({
  badge: { type: Object, default: null }, // the reply's target.badge (null: an older reply that has none)
  stale: { type: Boolean, default: false }, // the last target request failed or was superseded by a push
})
const STALE_TEXT = healthSentence('stale')
const state = computed(() => (props.stale || !props.badge ? 'none' : props.badge.state))
const tone = computed(() => ({ profit: 'text-profit', loss: 'text-loss' })[state.value] ?? 'text-ink-muted')
</script>

<template>
  <div
    class="pointer-events-none absolute right-3 top-2 max-w-[60%] rounded border border-line bg-surface/90 px-2 py-1 text-right text-sm"
    data-testid="target-badge" :data-state="state" :title="badge?.output_label || undefined"
  >
    <template v-if="state === 'none'">
      <div class="text-ink-muted" data-testid="target-badge-label">-</div>
      <div v-if="stale" class="text-xs text-warn" data-testid="target-badge-reason">{{ STALE_TEXT }}</div>
    </template>
    <template v-else>
      <div class="font-semibold tabular-nums" :class="tone" data-testid="target-badge-label">{{ badge.label }}</div>
      <div v-if="badge.reason" class="text-xs text-ink-muted" data-testid="target-badge-reason">{{ badge.reason }}</div>
      <div v-if="badge.percent_text" class="text-xs text-ink-muted tabular-nums" data-testid="target-badge-percent">{{ badge.percent_text }}</div>
      <div v-else-if="badge.percent_reason" class="text-xs text-ink-muted" data-testid="target-badge-percent-reason">{{ badge.percent_reason }}</div>
    </template>
  </div>
</template>
