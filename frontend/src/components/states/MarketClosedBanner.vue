<!-- GC-6 ST-MKT-CLOSED. Shows "Market closed. Prices are from <time>." The time is the server's ISO instant, formatted by the
     existing istTime helper. `disablesExecute` is read by the Execute screen (ADR-119); this banner places no order. -->
<script setup>
import { computed } from 'vue'
import { istTime } from '@/lib/displayFormat'
import { marketClosedText } from '@/lib/sharedStateText'
import { calendarMissingYear } from '@/lib/calendarNotice'

const props = defineProps({
  pricesAt: { type: String, default: null },
  // ADR-330 (36) (LR-Q18): the server's whole sentence for a trade with legs frozen at the close and legs first priced later;
  // printed as sent (ADR-008: the browser builds no sentence). Absent: the one-time sentence below.
  serverText: { type: String, default: null },
  disablesExecute: { type: Boolean, default: false },
})
const text = computed(() => props.serverText || marketClosedText(istTime(props.pricesAt)))
</script>

<template>
  <div v-if="!calendarMissingYear" role="status" class="rounded border border-line bg-surface p-3 text-sm" data-testid="market-closed-banner" :data-disables-execute="disablesExecute ? 'true' : 'false'">
    <span class="font-medium" data-testid="market-closed-text">{{ text }}</span>
  </div>
</template>
