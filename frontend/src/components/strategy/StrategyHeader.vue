<!-- Copied/adapted from abhayla/algochanakya@bf9faf7:frontend/src/components/strategy/StrategyHeader.vue (ADR-047).
     Changed: the nav links are dropped (the app header owns navigation); the underlying is shown, not switched (a
     draft's legs belong to one underlying until the leg picker exists); the P/L-mode toggle is replaced by the UX level
     selector (ADR-068: a request parameter, Standard by default); the loading indicator is kept. -->
<template>
  <div class="bg-white shadow rounded" data-testid="strategy-header">
    <div class="px-4 py-3 flex flex-wrap items-center justify-between gap-4">
      <div class="flex items-center gap-2">
        <span class="px-4 py-2 text-sm font-medium rounded-lg bg-[#387ed1] text-white" data-testid="header-underlying">{{ underlying }}</span>
      </div>

      <div class="flex items-center gap-4">
        <div class="flex items-center gap-2" role="group" aria-label="Detail level">
          <span class="text-sm text-gray-600">Detail level:</span>
          <button
            v-for="u in uxLevels"
            :key="u.key"
            type="button"
            :data-testid="`ux-${u.key}`"
            :aria-pressed="uxLevel === u.key"
            :class="[
              'px-3 py-1.5 text-sm font-medium rounded-lg transition-colors',
              uxLevel === u.key ? 'bg-[#387ed1] text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200',
            ]"
            @click="$emit('update:uxLevel', u.key)"
          >
            {{ u.label }}
          </button>
        </div>

        <div v-if="isLoading" class="flex items-center gap-2 text-blue-600">
          <svg class="animate-spin h-5 w-5" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          <span class="text-sm">Loading...</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  underlying: { type: String, required: true },
  uxLevel: { type: String, default: 'standard' },
  isLoading: { type: Boolean, default: false },
})

defineEmits(['update:uxLevel'])

const uxLevels = [
  { key: 'guided', label: 'Guided' },
  { key: 'standard', label: 'Standard' },
  { key: 'advanced', label: 'Advanced' },
]
</script>
