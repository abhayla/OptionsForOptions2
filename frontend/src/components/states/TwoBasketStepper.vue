<!-- GC-6 ST-TWO-BASKET (ADR-117, REQ-056 AC-11). `state` is one of: 'buys' (step 1 current), 'buys_filled' (middle state),
     'buy_failed'. Sells are shown locked until Zerodha confirms the fills. Display only. -->
<script setup>
import { computed } from 'vue'
import { KITE_ORDER_BOOK_URL } from '@/lib/execute'
import { STEP_BUYS, STEP_SELLS, BUYS_FILLED_TEXT, BUY_FAILED_TEXT } from '@/lib/sharedStateText'

const props = defineProps({
  state: { type: String, default: 'buys', validator: (v) => ['buys', 'buys_filled', 'buy_failed'].includes(v) },
})
const message = computed(() => ({ buys_filled: BUYS_FILLED_TEXT, buy_failed: BUY_FAILED_TEXT })[props.state] ?? null)
</script>

<template>
  <div class="text-sm" data-testid="two-basket-stepper" :data-state="state">
    <ol class="space-y-1">
      <li data-testid="step-buys" :aria-current="state === 'buys' ? 'step' : undefined">{{ STEP_BUYS }}</li>
      <li data-testid="step-sells">{{ STEP_SELLS }}</li>
    </ol>
    <p v-if="message" class="mt-2 font-medium" role="status" data-testid="two-basket-message">
      <a v-if="state === 'buy_failed'" :href="KITE_ORDER_BOOK_URL" target="_blank" rel="noopener" data-testid="two-basket-kite-link" class="underline">{{ message }}</a>
      <template v-else>{{ message }}</template>
    </p>
  </div>
</template>
