<!-- REQ-135: the old 'last updated' clock is gone (one 'Prices as of' stamp on the page); the extras row is new.
     Copied/adapted from abhayla/algochanakya@bf9faf7:frontend/src/components/strategy/SummaryCards.vue (ADR-047).
     Changed: every prop is the outcome API's string or sentence, shown as given (the legacy formatNum rounding is
     removed); the plain-language sentence comes first in each card (REQ-034 AC-7); the Risk/Reward card is dropped (a
     ratio would be client maths and the API sends none); four cards, responsive columns. -->
<template>
  <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 p-4 bg-gray-50 border-t border-gray-200" data-testid="summary-cards">
    <!-- Max Profit -->
    <div class="bg-white rounded-xl border border-green-200 p-4 shadow-sm">
      <div class="flex items-center gap-2 mb-2">
        <div class="w-8 h-8 rounded-lg bg-green-100 flex items-center justify-center">
          <svg class="w-4 h-4 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"/>
          </svg>
        </div>
        <span class="text-xs font-medium text-gray-500 uppercase">Max Profit</span>
        <FigureHint id="max_profit" />
      </div>
      <p class="text-sm" data-testid="sum-make">{{ whatCanIMake }}</p>
      <div class="mt-1 text-xl font-bold text-green-600" data-testid="max-profit">{{ maxProfit }}</div>
    </div>

    <!-- Max Loss -->
    <div class="bg-white rounded-xl border border-red-200 p-4 shadow-sm">
      <div class="flex items-center gap-2 mb-2">
        <div class="w-8 h-8 rounded-lg bg-red-100 flex items-center justify-center">
          <svg class="w-4 h-4 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 17h8m0 0V9m0 8l-8-8-4 4-6-6"/>
          </svg>
        </div>
        <span class="text-xs font-medium text-gray-500 uppercase">Max Loss</span>
        <FigureHint id="max_loss" />
      </div>
      <p class="text-sm" data-testid="sum-lose">{{ whatCanILose }}</p>
      <div class="mt-1 text-xl font-bold text-red-600" data-testid="max-loss">{{ maxLoss }}</div>
    </div>

    <!-- Breakeven -->
    <div class="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
      <div class="flex items-center gap-2 mb-2">
        <div class="w-8 h-8 rounded-lg bg-gray-100 flex items-center justify-center">
          <svg class="w-4 h-4 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8h16M4 16h16"/>
          </svg>
        </div>
        <span class="text-xs font-medium text-gray-500 uppercase">Breakeven</span>
        <FigureHint id="breakeven_expiry" />
      </div>
      <p class="text-sm" data-testid="sum-start">{{ whereIStartLosing }}</p>
      <div class="mt-1 text-lg font-bold text-gray-800" data-testid="breakevens">{{ breakevens.length ? breakevens.join(', ') : '-' }}</div>
    </div>

    <!-- Current Spot -->
    <div class="bg-gradient-to-br from-yellow-50 to-amber-50 rounded-xl border-2 border-yellow-300 p-4 shadow-sm">
      <div class="flex items-center gap-2 mb-2">
        <div class="w-8 h-8 rounded-lg bg-yellow-200 flex items-center justify-center">
          <div class="w-2 h-2 rounded-full bg-yellow-500"></div>
        </div>
        <span class="text-xs font-medium text-yellow-700 uppercase">{{ underlying }} level</span>
      </div>
      <div class="text-2xl font-bold text-yellow-700" data-testid="spot-level">{{ currentSpot }}</div>
    </div>
    <!-- REQ-135 AC-4: Reward/Risk with its reason, Time value, Intrinsic value: the server's strings, each hidden when absent -->
    <dl v-if="showRatio || timeValue != null || intrinsicValue != null" class="sm:col-span-2 lg:col-span-4 flex flex-wrap gap-6 text-sm" data-testid="summary-extras">
      <div v-if="showRatio"><dt class="inline text-gray-500">Reward/Risk: </dt><FigureHint id="reward_risk" /><dd class="inline font-medium" data-testid="reward-risk">{{ rewardRisk ?? '-' }}</dd>
        <span v-if="rewardRiskReason" class="text-gray-500" data-testid="reward-risk-reason"> ({{ rewardRiskReason }})</span></div>
      <div v-if="timeValue != null"><dt class="inline text-gray-500">Time value: </dt><FigureHint id="time_value" /><dd class="inline font-medium" data-testid="time-value">{{ timeValue }}</dd></div>
      <div v-if="intrinsicValue != null"><dt class="inline text-gray-500">Intrinsic value: </dt><FigureHint id="intrinsic_value" /><dd class="inline font-medium" data-testid="intrinsic-value">{{ intrinsicValue }}</dd></div>
    </dl>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import FigureHint from '@/components/common/FigureHint.vue'
const props = defineProps({
  maxProfit: { type: String, default: '-' },
  maxLoss: { type: String, default: '-' },
  breakevens: { type: Array, default: () => [] },
  whatCanIMake: { type: String, default: '' },
  whatCanILose: { type: String, default: '' },
  whereIStartLosing: { type: String, default: '' },
  currentSpot: { type: String, default: '' },
  underlying: { type: String, default: 'NIFTY' },
  rewardRisk: { type: String, default: null },
  rewardRiskReason: { type: String, default: null },
  timeValue: { type: String, default: null },
  intrinsicValue: { type: String, default: null },
})
const showRatio = computed(() => props.rewardRisk != null || props.rewardRiskReason != null)
</script>
