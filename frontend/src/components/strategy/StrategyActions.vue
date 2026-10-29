<!-- Copied/adapted from abhayla/algochanakya@bf9faf7:frontend/src/components/strategy/StrategyActions.vue (ADR-047).
     Changed: no ReCalculate (REQ-135 AC-3: prices are pushed, there is no manual refresh). Add Row, Delete Selected, Import/Update Positions, Save, Share and Buy Basket
     Order are not in this slice (leg picker and Save Draft come with W-061; no standalone order entry, ADR-002).
     W-104 (REQ-056 AC-1): "Execute Strategy" opens the Execute screen, only for a saved strategy (every order belongs
     to a strategy, ADR-002); an unsaved or edited-since-save draft shows no Execute action.
     W-121 (REQ-073 AC-6, ADR-165): and none while the server's order path is not "on" (absent, not disabled). -->
<template>
  <!-- GC-UI D-B47: the bar exists only when it holds an action; an empty one was a ~35 px grey band with two rules -->
  <div v-if="savedId && orderPathOn" class="p-4 bg-gray-50 border-t flex flex-wrap items-center justify-between gap-4" data-testid="strategy-actions">
    <div class="flex items-center gap-2">
      <RouterLink
        v-if="savedId && orderPathOn && brokerConnected && !executeRefusal"
        :to="`/strategy/${savedId}/execute`"
        data-testid="execute-strategy"
        class="px-4 py-2 text-sm font-medium rounded-lg border border-line"
      >
        Execute Strategy
      </RouterLink>
      <template v-else-if="savedId && orderPathOn">
        <button
          type="button"
          disabled
          data-testid="execute-strategy-disabled"
          :title="disabledReason"
          class="px-4 py-2 text-sm font-medium rounded-lg border border-line text-gray-400 cursor-not-allowed"
        >
          Execute Strategy
        </button>
        <span class="text-xs text-gray-600" data-testid="execute-strategy-reason">{{ disabledReason }}</span>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useOrderPath } from '@/lib/orderPath'
import { TRADE_NEEDS_BROKER_REASON, useBrokerConnected } from '@/lib/brokerConnected'

const props = defineProps({
  savedId: { type: Number, default: null },
  // W-148 (REQ-076 AC-7): the reason Execute is refused while any leg is unticked, or null. The tick is page state; the
  // Execute screen opens the SAVED strategy, which never carries it.
  executeRefusal: { type: String, default: null },
})

// W-121 (REQ-073 AC-6): Execute is offered only when the server said the order path is "on".
const orderPathOn = useOrderPath()
// REQ-015 AC-10 (RD-012): with no broker connected the action is shown disabled with its reason, before any click.
const brokerConnected = useBrokerConnected()
const disabledReason = computed(() => (brokerConnected.value ? props.executeRefusal : TRADE_NEEDS_BROKER_REASON))
</script>
