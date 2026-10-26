<!-- ADR-193 UI-014: `[-] value [+]` as one 32 px group (S-107 strike "- 22550 +"). Presentation only: it emits
     `decrement` / `increment` and shows the value it is given; the caller (and the server) decide the next value, so no
     number is computed here (ADR-008). -->
<script setup>
defineProps({
  value: { type: [String, Number], required: true },
  label: { type: String, required: true },
  disabled: { type: Boolean, default: false },
  disabledReason: { type: String, default: '' },
})
const emit = defineEmits(['decrement', 'increment'])
</script>

<template>
  <div class="inline-flex h-8 items-center gap-0.5" role="group" :aria-label="label" :title="disabled ? disabledReason : undefined" data-testid="stepper">
    <button
      type="button"
      class="flex h-7 w-7 items-center justify-center rounded-md border border-line bg-surface text-ink disabled:opacity-40"
      :aria-label="`Decrease ${label}`"
      :disabled="disabled"
      data-testid="stepper-decrement"
      @click="emit('decrement')"
    >
      &minus;
    </button>
    <span class="num w-16 text-center text-sm text-ink" aria-live="polite" data-testid="stepper-value">{{ value }}</span>
    <button
      type="button"
      class="flex h-7 w-7 items-center justify-center rounded-md border border-line bg-surface text-ink disabled:opacity-40"
      :aria-label="`Increase ${label}`"
      :disabled="disabled"
      data-testid="stepper-increment"
      @click="emit('increment')"
    >
      +
    </button>
  </div>
</template>
