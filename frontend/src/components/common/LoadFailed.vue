<!-- GC-ICFIX u112 (ADR-295 (3)): the one "could not load, retry" state for any panel whose read can fail or time out. The
     sentence and the button label come from the caller (shared-state texts); ids are `<prefix>-error` and `<prefix>-retry`. -->
<script setup>
import { RETRY_LABEL } from '@/lib/sharedStateText'

defineProps({ text: { type: String, required: true }, prefix: { type: String, required: true } })
defineEmits(['retry'])
</script>

<template>
  <div role="alert" class="flex items-center gap-2 text-sm text-red-700">
    <p :data-testid="`${prefix}-error`">{{ text }}</p>
    <button type="button" class="rounded border border-line bg-surface px-2 py-1 text-xs font-medium text-ink" :data-testid="`${prefix}-retry`" @click="$emit('retry')">{{ RETRY_LABEL }}</button>
  </div>
</template>
