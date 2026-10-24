<!-- Copied/adapted from abhayla/algochanakya@bf9faf7:frontend/src/components/strategy/StrategyFooter.vue (ADR-047).
     Changed: the spot is the API's string shown as given (currentSpot.toFixed(2) is removed); the time is shown in India
     time by the one formatter (W-072, ADR-086) - the legacy toLocaleString used the browser's zone and was removed. -->
<template>
  <div class="mt-4 flex items-center justify-between text-sm text-gray-500" data-testid="strategy-footer">
    <div class="flex items-center gap-4">
      <span v-if="currentSpot">
        {{ underlying }} level: <span class="font-medium text-gray-900">{{ currentSpot }}</span>
      </span>
    </div>
  </div>
</template>

<script setup>
defineProps({
  currentSpot: { type: String, default: '' },
  underlying: { type: String, default: 'NIFTY' },
})
</script>
