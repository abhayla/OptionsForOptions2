<!-- REQ-135: the old 'last updated' clock is gone (one 'Prices as of' stamp on the page); the extras row is new.
     Copied/adapted from abhayla/algochanakya@bf9faf7:frontend/src/components/strategy/SummaryCards.vue (ADR-047).
     Changed: every prop is the outcome API's string or sentence, shown as given (the legacy formatNum rounding is
     removed); a ratio is shown only as the server's string (the browser computes none).
     W-193 (ADR-193 UI study b.1 Region E): ONE card, three blocks split by 1 px lines. Block 2: Reward/Risk with the 1/x
     switch, POP (slot `pop`, absent while held), Time value, Intrinsic value. Block 3: slot `margin` (MarginLine).
     GC-UI step 3b (ADR-202 (1), ADR-204; Sensibull screens 011, 107, 124-128, 240): every money figure is the server's
     REQ-152 display string as sent ("+7,152", "−5,848"); Max Profit / Max Loss are small signed pills with the server's
     percent text inline (REQ-081 AC-9); the plain-language sentences (REQ-034 AC-7), the funds line (REQ-081 AC-10) and
     the exact value (REQ-152 AC-3) sit in each figure's "?", words unchanged; Breakeven reads
     "Breakeven [Target | Expiry] (?)" then the server's small value with its percent from spot (REQ-153); the
     "value of the options, not P&L" caption is in the Time value / Intrinsic value "?"; "estimated from spot" (ADR-061)
     is one small label beside the figures it qualifies (`estimateLabel`, the reply's output_label). -->
<template>
  <section
    class="@container rounded-lg border border-line bg-surface px-4 py-3"
    aria-label="Strategy summary"
    data-testid="summary-cards"
  >
    <div class="grid grid-cols-1 gap-3 @2xl:grid-cols-3 @2xl:gap-0">
      <!-- Block 1: Max Profit, Max Loss, Breakeven -->
      <div class="min-w-0 @2xl:pr-4" data-testid="summary-block-outcome">
        <p v-if="estimateLabel" class="mb-1 inline-block rounded bg-warn-soft px-1.5 text-[11px] text-ink" data-testid="output-label">{{ estimateLabel }}</p>
        <!-- GC-TP step 3b2 (REQ-109 AC-9; Sensibull Drafts Mode 278-279): in Drafts Mode the paper book's Profit left / Loss left
             come FIRST, each the book reply's text as sent; with the reply's extremes_reason they are absent and the reason said.
             The Max Profit / Max Loss below are then the book's original figures (the page passes them). -->
        <div v-if="left" class="mb-2 flex flex-nowrap items-start gap-x-3" data-testid="summary-left-row">
          <template v-if="!left.reason">
            <div class="min-w-0">
              <span class="text-xs text-ink-muted">{{ PROFIT_LEFT_LABEL }}</span>
              <div class="num mt-0.5 whitespace-nowrap rounded bg-profit-soft px-1.5 py-0.5 text-sm font-semibold text-profit" data-testid="profit-left">{{ left.profit ?? '-' }}</div>
            </div>
            <div class="min-w-0">
              <span class="text-xs text-ink-muted">{{ LOSS_LEFT_LABEL }}</span>
              <div class="num mt-0.5 whitespace-nowrap rounded bg-loss-soft px-1.5 py-0.5 text-sm font-semibold text-loss" data-testid="loss-left">{{ left.loss ?? '-' }}</div>
            </div>
          </template>
          <p v-else class="text-xs text-ink-muted" data-testid="extremes-reason">{{ left.reason }}</p>
        </div>
        <!-- GC-UI D-PX item 2: both pills in ONE row that never wraps (Sensibull sb-01: side by side); the percent is a smaller
             second line INSIDE its pill, so each pill is only as wide as its figure -->
        <div class="flex flex-nowrap items-start gap-x-3" data-testid="summary-pills-row">
          <div class="min-w-0">
            <span class="flex items-center text-xs text-ink-muted">Max Profit<FigureHint id="max_profit" :lines="[whatCanIMake, fundsLine, exactLine(maxProfitExact)]" /></span>
            <div class="mt-0.5 inline-flex flex-col items-start whitespace-nowrap rounded bg-profit-soft px-1.5 py-0.5 leading-tight text-profit" data-testid="max-profit-pill">
              <span class="num text-sm font-semibold" data-testid="max-profit">{{ maxProfit }}</span>
              <span v-if="fundsShare?.max_profit_text" class="text-[11px]">(<span data-testid="max-profit-percent">{{ fundsShare.max_profit_text }}</span>)</span>
            </div>
          </div>
          <div class="min-w-0">
            <span class="flex items-center text-xs text-ink-muted">Max Loss<FigureHint id="max_loss" :lines="[whatCanILose, fundsLine, exactLine(maxLossExact)]" /></span>
            <div class="mt-0.5 inline-flex flex-col items-start whitespace-nowrap rounded bg-loss-soft px-1.5 py-0.5 leading-tight text-loss" data-testid="max-loss-pill">
              <span class="num text-sm font-semibold" data-testid="max-loss">{{ maxLoss }}</span>
              <span v-if="fundsShare?.max_loss_text" class="text-[11px]">(<span data-testid="max-loss-percent">{{ fundsShare.max_loss_text }}</span>)</span>
            </div>
          </div>
        </div>
        <div class="mt-2 flex flex-wrap items-center gap-2" data-testid="breakeven-row">
          <span class="text-xs text-ink-muted">Breakeven</span>
          <div class="inline-flex rounded-md border border-line text-xs" role="group" aria-label="Breakeven at">
            <Tooltip text="Needs a target date: breakevens on a target date are not worked out yet." label="Target (not available: needs a target date)">
              <template #trigger>
                <span class="px-2 py-0.5 text-ink-subtle" aria-disabled="true" data-testid="breakeven-target">Target</span>
              </template>
            </Tooltip>
            <button type="button" class="rounded-r-md bg-accent-soft px-2 py-0.5 font-medium text-accent" aria-pressed="true" data-testid="breakeven-expiry">Expiry</button>
          </div>
          <FigureHint id="breakeven_expiry" :lines="[whereIStartLosing, exactLine(breakevensExact.join(', '))]" />
        </div>
        <div class="num mt-0.5 text-[13px] text-ink" data-testid="breakevens">{{ breakevens.length ? breakevens.join(', ') : '-' }}</div>
      </div>

      <!-- Block 2: Reward/Risk, POP, Time value, Intrinsic value (REQ-135 AC-4 / REQ-081 AC-3, AC-4: the server's strings,
           '-' with the server's reason when absent; an absent figure is not zero) -->
      <div class="min-w-0 @2xl:border-l @2xl:border-line @2xl:px-4" data-testid="summary-block-ratios">
        <dl v-if="showRatio || showValues" class="text-[13px]" data-testid="summary-extras">
          <div v-if="showRatio">
            <div class="flex min-h-6 items-center justify-between gap-2">
              <dt class="flex items-center text-ink-muted">
                <span data-testid="ratio-label">{{ flipped ? 'Risk/Reward' : 'Reward/Risk' }}</span>
                <FigureHint v-if="!flipped" id="reward_risk" />
                <button
                  type="button"
                  class="ml-2 rounded border border-line px-1.5 text-xs font-medium text-ink hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                  :aria-label="`Show ${flipped ? 'Reward/Risk' : 'Risk/Reward'}`"
                  :aria-pressed="flipped ? 'true' : 'false'"
                  data-testid="ratio-switch"
                  @click="flipped = !flipped"
                >1/x</button>
              </dt>
              <dd class="num font-medium text-ink" data-testid="reward-risk">{{ (flipped ? riskReward : rewardRisk) ?? '-' }}</dd>
            </div>
            <p v-if="rewardRiskReason" class="text-right text-xs text-ink-muted" data-testid="reward-risk-reason">({{ rewardRiskReason }})</p>
          </div>
          <slot name="pop" />
          <div v-if="showValues" data-testid="value-split">
            <div class="flex min-h-6 items-center justify-between gap-2">
              <dt class="flex items-center text-ink-muted">Time value<FigureHint v-if="timeValue != null" id="time_value" :lines="[valueLabel, exactLine(timeValueExact)]" /></dt>
              <dd class="num font-medium text-ink" data-testid="time-value">{{ displayOrDash(timeValue) }}</dd>
            </div>
            <div class="flex min-h-6 items-center justify-between gap-2">
              <dt class="flex items-center text-ink-muted">Intrinsic value<FigureHint v-if="intrinsicValue != null" id="intrinsic_value" :lines="[valueLabel, exactLine(intrinsicValueExact)]" /></dt>
              <dd class="num font-medium text-ink" data-testid="intrinsic-value">{{ displayOrDash(intrinsicValue) }}</dd>
            </div>
            <p v-if="valueReason" class="text-xs text-ink-muted" data-testid="value-reason">{{ valueReason }}</p>
          </div>
        </dl>
        <slot v-else name="pop" />
      </div>

      <!-- Block 3: Funds & Margins (MarginLine) -->
      <div class="contents" data-testid="summary-block-margin">
        <slot name="margin" />
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { istTime, groupMoney } from '@/lib/displayFormat'
import { displayOrDash, exactLine } from '@/lib/summaryFigures'
import FigureHint from '@/components/common/FigureHint.vue'
import Tooltip from '@/components/common/Tooltip.vue'
import { LOSS_LEFT_LABEL, PROFIT_LEFT_LABEL } from '@/lib/paperDrafts'
const props = defineProps({
  maxProfit: { type: String, default: '-' }, // summaryFigure(summary, 'profit'): the server's display string
  maxLoss: { type: String, default: '-' },
  maxProfitExact: { type: String, default: null }, // summary.max_profit as sent, for the "?" (REQ-152 AC-3)
  maxLossExact: { type: String, default: null },
  breakevens: { type: Array, default: () => [] }, // summary.breakevens_display as sent ("22,688 (−0.1%)")
  breakevensExact: { type: Array, default: () => [] }, // summary.breakevens as sent
  whatCanIMake: { type: String, default: '' },
  whatCanILose: { type: String, default: '' },
  whereIStartLosing: { type: String, default: '' },
  rewardRisk: { type: String, default: null },
  rewardRiskReason: { type: String, default: null },
  timeValue: { type: String, default: null }, // summary.time_value_display as sent
  timeValueExact: { type: String, default: null },
  intrinsicValue: { type: String, default: null }, // summary.intrinsic_value_display as sent
  intrinsicValueExact: { type: String, default: null },
  riskReward: { type: String, default: null },
  valueLabel: { type: String, default: null },
  valueReason: { type: String, default: null },
  fundsShare: { type: Object, default: null }, // summary.funds_share as sent (null unless Zerodha's funds were read)
  estimateLabel: { type: String, default: null }, // the reply's output_label ("estimated from spot", ADR-061)
  // GC-TP step 3b2: Drafts Mode only - { profit, loss, reason }: the paper book's profit_left_text / loss_left_text as sent, or
  // the words for its extremes_reason; null outside Drafts Mode (the summary is then unchanged)
  left: { type: Object, default: null },
})
// REQ-081 AC-10: the funds the percentages are of and when Zerodha was read, words unchanged, now in the "?" of both
// figures (ADR-202 (1)); absent with the percentages when funds could not be read. The funds figure has no server display
// string, so its digits are only regrouped as text (groupMoney, never parsed).
const fundsLine = computed(() => (props.fundsShare
  ? `Percentages are of Rs ${groupMoney(props.fundsShare.funds)} available funds, read ${istTime(props.fundsShare.read_at)}`
  : null))
// which of the server's two ratio strings is shown; never a calculation. A model the page owns (review 2), so a recompute
// keeps the user's 1/x choice; without a v-model it is this card's own state.
const flipped = defineModel('flipped', { type: Boolean, default: false })
const showRatio = computed(() => props.rewardRisk != null || props.rewardRiskReason != null)
const showValues = computed(() => props.timeValue != null || props.intrinsicValue != null || props.valueReason != null)
</script>
