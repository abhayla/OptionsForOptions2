<!-- GC-6 ST-EMPTY. Generic: a message and at most one next-step button (rendered only when `actionLabel` is given). -->
<script setup>
defineProps({
  message: { type: String, required: true },
  actionLabel: { type: String, default: null },
})
defineEmits(['action'])
</script>

<template>
  <div class="rounded border border-line bg-surface p-4 text-sm" data-testid="empty-state">
    <p data-testid="empty-state-message">{{ message }}</p>
    <button v-if="actionLabel" type="button" class="mt-3 min-h-[44px] rounded border border-line px-3" data-testid="empty-state-action" @click="$emit('action')">{{ actionLabel }}</button>
  </div>
</template>
