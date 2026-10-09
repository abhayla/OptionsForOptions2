<!-- Copied/adapted from abhayla/algochanakya@bf9faf7:frontend/src/components/strategy/StrategyActions.vue (ADR-047).
     Changed: only ReCalculate is kept. Add Row, Delete Selected, Import/Update Positions, Save, Share and Buy Basket
     Order are not in this slice (leg picker and Save Draft come with W-061; no standalone order entry, ADR-002). -->
<template>
  <div class="p-4 bg-gray-50 border-t flex flex-wrap items-center justify-between gap-4" data-testid="strategy-actions">
    <div class="flex items-center gap-2">
      <button
        type="button"
        data-testid="recalculate"
        :disabled="!hasLegs || isLoading"
        :class="[
          'px-4 py-2 text-sm font-medium rounded-lg transition-colors',
          hasLegs && !isLoading ? 'text-white bg-[#387ed1] hover:bg-[#2c6cb8]' : 'text-gray-400 bg-gray-200 cursor-not-allowed',
        ]"
        @click="$emit('recalculate')"
      >
        {{ isLoading ? 'Calculating...' : 'ReCalculate' }}
      </button>
    </div>
  </div>
</template>

<script setup>
defineProps({
  hasLegs: { type: Boolean, default: false },
  isLoading: { type: Boolean, default: false },
})

defineEmits(['recalculate'])
</script>
