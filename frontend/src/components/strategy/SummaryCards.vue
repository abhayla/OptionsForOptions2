<!-- Copied/adapted from abhayla/algochanakya@bf9faf7:frontend/src/components/strategy/SummaryCards.vue (ADR-047).
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
      <div class="text-xs text-yellow-600 mt-1">{{ lastUpdated }}</div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  maxProfit: { type: String, default: '-' },
  maxLoss: { type: String, default: '-' },
  breakevens: { type: Array, default: () => [] },
  whatCanIMake: { type: String, default: '' },
  whatCanILose: { type: String, default: '' },
  whereIStartLosing: { type: String, default: '' },
  currentSpot: { type: String, default: '' },
  underlying: { type: String, default: 'NIFTY' },
  lastUpdated: { type: String, default: '' },
})
</script>
