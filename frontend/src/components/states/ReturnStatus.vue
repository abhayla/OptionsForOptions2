<!-- GC-6 ST-RETURN (REQ-073, F-41). Status of the return from Kite. `status`: idle | checking | done | no_change | failed.
     The button that starts the check keeps the wording "Check with Zerodha". The "done" outcome reads RETURN_DONE_TEXT (ADR-129);
     the caller's default slot, if any, renders below it as an optional extra. Failed shows the caller's `failed` slot + Retry. -->
<script setup>
import { CHECK_WITH_ZERODHA, RETURN_CHECKING, RETURN_NO_CHANGE, RETRY_LABEL, RETURN_DONE_TEXT } from '@/lib/sharedStateText'

defineProps({
  status: { type: String, default: 'idle', validator: (v) => ['idle', 'checking', 'done', 'no_change', 'failed'].includes(v) },
})
defineEmits(['check', 'retry'])
</script>

<template>
  <div class="text-sm" data-testid="return-status" :data-status="status">
    <button v-if="status === 'idle'" type="button" class="min-h-[44px] rounded border border-line px-3" data-testid="return-status-check" @click="$emit('check')">{{ CHECK_WITH_ZERODHA }}</button>
    <p v-else-if="status === 'checking'" role="status" data-testid="return-status-checking">{{ RETURN_CHECKING }}</p>
    <div v-else-if="status === 'done'" data-testid="return-status-done"><p data-testid="return-status-done-text">{{ RETURN_DONE_TEXT }}</p><slot /></div>
    <p v-else-if="status === 'no_change'" role="status" data-testid="return-status-no-change">{{ RETURN_NO_CHANGE }}</p>
    <div v-else data-testid="return-status-failed">
      <slot name="failed" />
      <button type="button" class="min-h-[44px] rounded border border-line px-3" data-testid="return-status-retry" @click="$emit('retry')">{{ RETRY_LABEL }}</button>
    </div>
  </div>
</template>
