<!-- ADR-330 (10) (replaces ADR-201 (2)): the two totals of the one Positions list, "Real P&L" and "Paper P&L", side by side and
     NEVER added together (ADR-008: no P&L arithmetic in the browser). Real P&L is the server's `pnl_text` printed as sent, only
     when GET /positions served it; today it does not, so it is a dash with the reason (the server does not price Zerodha positions).
     Paper P&L is the figure PaperStrategies emitted (its after-charges total text) plus its closed-strategies line, as sent. -->
<script setup>
import { computed } from 'vue'
import { PAPER_NO_FIGURE, PAPER_PAUSED } from '@/lib/paperList'
import { signOf } from '@/lib/chartCard'
import AfterChargesTap from '@/components/common/AfterChargesTap.vue'

const props = defineProps({
  realPnlText: { type: String, default: null },
  paper: { type: Object, default: null },
})
const NO_FIGURE = PAPER_NO_FIGURE // one home for the dash (lib/paperList)
const REAL_NOT_SHOWN = 'Real P&L is not shown yet: the server does not price Zerodha positions.'
const realServed = computed(() => typeof props.realPnlText === 'string' && props.realPnlText.trim() !== '')
const paperFig = computed(() => {
  const p = props.paper
  if (!p) return { text: NO_FIGURE, reason: null, basis: null }
  // stale first: a failed FIRST read has no list (not loaded) but PaperStrategies still says it is paused; same text, from the summary
  if (p.stale) return { text: NO_FIGURE, reason: PAPER_PAUSED, basis: null }
  if (!p.loaded) return { text: NO_FIGURE, reason: null, basis: null }
  const a = p.totalAfter
  if (!a || a.text === null || a.text === undefined) return { text: NO_FIGURE, reason: a?.reason ?? null, basis: null }
  return { text: a.text, reason: a.reason ?? null, basis: a.label || null, breakdown: a.breakdown ?? null } // "(before charges)" comes with the server's reason
})
// the same profit/loss colour classes as the list's Total P&L (PaperStrategies toneOf); no colour while paused (figure is a dash)
const tone = computed(() => ({ profit: 'text-profit', loss: 'text-loss' })[signOf(String(paperFig.value.text ?? '').replace(/,/g, '').replace('−', '-'))] ?? '')
</script>

<template>
  <div class="grid gap-4 sm:grid-cols-2" data-testid="positions-totals">
    <div class="rounded-lg border border-line bg-surface px-4 py-3">
      <p class="text-xs text-ink-muted">Real P&amp;L</p>
      <p class="text-lg font-semibold" data-testid="totals-real">{{ realServed ? realPnlText : NO_FIGURE }}</p>
      <p v-if="!realServed" class="text-xs text-ink-muted" data-testid="totals-real-reason">{{ REAL_NOT_SHOWN }}</p>
    </div>
    <div class="rounded-lg border border-dashed border-accent bg-surface px-4 py-3">
      <p class="text-xs text-ink-muted">Paper P&amp;L</p>
      <p class="text-lg font-semibold" :class="tone" data-testid="totals-paper"><AfterChargesTap :breakdown="paperFig.breakdown ?? null">{{ paperFig.text }}</AfterChargesTap></p>
      <p v-if="paperFig.basis" class="text-xs text-ink-muted" data-testid="totals-paper-basis">{{ paperFig.basis }}</p>
      <p v-if="paperFig.reason" class="text-xs text-ink-muted" data-testid="totals-paper-reason">{{ paperFig.reason }}</p>
      <p v-if="paper && paper.loaded && paper.closedNote" class="text-xs text-ink-muted" data-testid="totals-paper-closed-note">{{ paper.closedNote }}</p>
    </div>
  </div>
</template>
