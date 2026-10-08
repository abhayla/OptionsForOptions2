<!-- Copied/adapted from abhayla/algochanakya@bf9faf7:frontend/src/components/strategy/StrategyFooter.vue (ADR-047).
     Changed: the time and the spot are the API's strings shown as given (the legacy toLocaleString date formatting and
     currentSpot.toFixed(2) are removed). -->
<template>
  <div class="mt-4 flex items-center justify-between text-sm text-gray-500" data-testid="strategy-footer">
    <div class="flex items-center gap-4">
      <span v-if="lastUpdated">Priced at: <span data-testid="footer-valuation">{{ lastUpdated }}</span></span>
      <span v-else>Not calculated yet</span>
    </div>
    <div class="flex items-center gap-4">
      <span v-if="currentSpot">
        {{ underlying }} level: <span class="font-medium text-gray-900">{{ currentSpot }}</span>
      </span>
    </div>
  </div>
</template>

<script setup>
defineProps({
  lastUpdated: { type: String, default: '' },
  currentSpot: { type: String, default: '' },
  underlying: { type: String, default: 'NIFTY' },
})
</script>
