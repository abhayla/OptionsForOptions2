<!-- REQ-135: the old 'last updated' clock is gone (one 'Prices as of' stamp on the page); the extras row is new.
     Copied/adapted from abhayla/algochanakya@bf9faf7:frontend/src/components/strategy/SummaryCards.vue (ADR-047).
     Changed: every prop is the outcome API's string or sentence, shown as given (the legacy formatNum rounding is
     removed); the plain-language sentence stays visible under each figure (REQ-034 AC-7); a ratio is shown only as the
     server's string (the browser computes none).
     W-193 (ADR-193 UI study b.1 Region E, UI-116..UI-120, Revision 1 M1/M3): ONE card, three blocks split by 1 px lines.
     Block 1: Max Profit / Max Loss soft pills (percent of funds as the server's text), the plain sentences visible in 13 px
     muted text under them (the technical definition is in each "?"), the funds caption (REQ-081 AC-10), Breakeven with a
     Target | Expiry switch (Expiry = the server's breakevens; Target disabled until REQ-084 sends target-date figures).
     Block 2: Reward/Risk with the 1/x switch, POP (slot `pop`, absent while held), Time value, Intrinsic value.
     Block 3: slot `margin` (MarginLine: Funds & Margins; its shortfall message spans the card's full width once).
     The yellow index-level card is gone (yellow is a health colour, ADR-049; the spot is in the underlying bar). -->
<template>
  <section
    class="@container rounded-lg border border-line bg-surface p-4"
    aria-label="Strategy summary"
    data-testid="summary-cards"
  >
    <div class="grid grid-cols-1 gap-4 @2xl:grid-cols-3 @2xl:gap-0">
      <!-- Block 1: Max Profit, Max Loss, Breakeven -->
      <div class="min-w-0 @2xl:pr-4" data-testid="summary-block-outcome">
        <div class="grid grid-cols-2 gap-3">
          <div class="min-w-0">
            <span class="flex items-center text-[13px] text-ink-muted">Max Profit<FigureHint id="max_profit" /></span>
            <div class="mt-1 inline-flex flex-wrap items-baseline gap-1 rounded-md bg-profit-soft px-2 py-1 text-profit">
              <span class="num text-base font-semibold" data-testid="max-profit">{{ maxProfit }}</span>
              <span v-if="fundsShare?.max_profit_text" class="text-xs">(<span data-testid="max-profit-percent">{{ fundsShare.max_profit_text }}</span>)</span>
            </div>
            <p class="mt-1 text-[13px] text-ink-muted" data-testid="sum-make">{{ whatCanIMake }}</p>
          </div>
          <div class="min-w-0">
            <span class="flex items-center text-[13px] text-ink-muted">Max Loss<FigureHint id="max_loss" /></span>
            <div class="mt-1 inline-flex flex-wrap items-baseline gap-1 rounded-md bg-loss-soft px-2 py-1 text-loss">
              <span class="num text-base font-semibold" data-testid="max-loss">{{ maxLoss }}</span>
              <span v-if="fundsShare?.max_loss_text" class="text-xs">(<span data-testid="max-loss-percent">{{ fundsShare.max_loss_text }}</span>)</span>
            </div>
            <p class="mt-1 text-[13px] text-ink-muted" data-testid="sum-lose">{{ whatCanILose }}</p>
          </div>
        </div>
        <!-- REQ-081 AC-10 (Revision 1 M3): the funds the percentages are of, and when Zerodha was read; visible -->
        <p v-if="fundsShare" class="mt-2 min-w-0 break-words text-xs text-ink-muted" data-testid="funds-line">
          Percentages are of Rs {{ fundsShare.funds }} available funds, read {{ istTime(fundsShare.read_at) }}
        </p>
        <div class="mt-3 flex flex-wrap items-center gap-2">
          <span class="flex items-center text-[13px] text-ink-muted">Breakeven<FigureHint id="breakeven_expiry" /></span>
          <div class="inline-flex rounded-md border border-line text-xs" role="group" aria-label="Breakeven at">
            <Tooltip text="Needs a target date: breakevens on a target date are not worked out yet." label="Target (not available: needs a target date)">
              <template #trigger>
                <span class="px-2 py-0.5 text-ink-subtle" aria-disabled="true" data-testid="breakeven-target">Target</span>
              </template>
            </Tooltip>
            <button type="button" class="rounded-r-md bg-accent-soft px-2 py-0.5 font-medium text-accent" aria-pressed="true" data-testid="breakeven-expiry">Expiry</button>
          </div>
        </div>
        <div class="num mt-1 text-sm font-semibold text-ink" data-testid="breakevens">{{ breakevens.length ? breakevens.join(', ') : '-' }}</div>
        <p class="mt-1 text-[13px] text-ink-muted" data-testid="sum-start">{{ whereIStartLosing }}</p>
      </div>

      <!-- Block 2: Reward/Risk, POP, Time value, Intrinsic value (REQ-135 AC-4 / REQ-081 AC-3, AC-4: the server's strings,
           '-' with the server's reason when absent; an absent figure is not zero) -->
      <div class="min-w-0 @2xl:border-l @2xl:border-line @2xl:px-4" data-testid="summary-block-ratios">
        <dl v-if="showRatio || showValues" class="text-sm" data-testid="summary-extras">
          <div v-if="showRatio" class="py-1">
            <div class="flex min-h-7 items-center justify-between gap-2">
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
            <div class="flex min-h-7 items-center justify-between gap-2">
              <dt class="flex items-center text-ink-muted">Time value<FigureHint v-if="timeValue != null" id="time_value" /></dt>
              <dd class="num font-medium text-ink" data-testid="time-value">{{ timeValue ?? '-' }}</dd>
            </div>
            <div class="flex min-h-7 items-center justify-between gap-2">
              <dt class="flex items-center text-ink-muted">Intrinsic value<FigureHint v-if="intrinsicValue != null" id="intrinsic_value" /></dt>
              <dd class="num font-medium text-ink" data-testid="intrinsic-value">{{ intrinsicValue ?? '-' }}</dd>
            </div>
            <p v-if="valueLabel" class="text-xs text-ink-muted" data-testid="value-label">{{ valueLabel }}</p>
            <p v-if="valueReason" class="text-xs text-ink-muted" data-testid="value-reason">{{ valueReason }}</p>
          </div>
        </dl>
        <slot v-else name="pop" />
      </div>

      <!-- Block 3: Funds & Margins (MarginLine); its shortfall message is a second root that spans all three blocks -->
      <div class="contents" data-testid="summary-block-margin">
        <slot name="margin" />
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { istTime } from '@/lib/displayFormat'
import FigureHint from '@/components/common/FigureHint.vue'
import Tooltip from '@/components/common/Tooltip.vue'
const props = defineProps({
  maxProfit: { type: String, default: '-' },
  maxLoss: { type: String, default: '-' },
  breakevens: { type: Array, default: () => [] },
  whatCanIMake: { type: String, default: '' },
  whatCanILose: { type: String, default: '' },
  whereIStartLosing: { type: String, default: '' },
  rewardRisk: { type: String, default: null },
  rewardRiskReason: { type: String, default: null },
  timeValue: { type: String, default: null },
  intrinsicValue: { type: String, default: null },
  riskReward: { type: String, default: null },
  valueLabel: { type: String, default: null },
  valueReason: { type: String, default: null },
  fundsShare: { type: Object, default: null }, // summary.funds_share as sent (null unless Zerodha's funds were read)
})
const flipped = ref(false) // which of the server's two ratio strings is shown; never a calculation
const showRatio = computed(() => props.rewardRisk != null || props.rewardRiskReason != null)
const showValues = computed(() => props.timeValue != null || props.intrinsicValue != null || props.valueReason != null)
</script>
