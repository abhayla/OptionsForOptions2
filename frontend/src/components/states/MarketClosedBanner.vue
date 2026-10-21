<!-- GC-6 ST-MKT-CLOSED. Shows "Market closed. Prices are from <time>." The time is the server's ISO instant, formatted by the
     existing istTime helper. `disablesExecute` is read by the Execute screen (ADR-119); this banner places no order. -->
<script setup>
import { computed } from 'vue'
import { istTime } from '@/lib/displayFormat'
import { marketClosedText } from '@/lib/sharedStateText'

const props = defineProps({
  pricesAt: { type: String, default: null },
  disablesExecute: { type: Boolean, default: false },
})
const text = computed(() => marketClosedText(istTime(props.pricesAt)))
</script>

<template>
  <div role="status" class="rounded border border-line bg-surface p-3 text-sm" data-testid="market-closed-banner" :data-disables-execute="disablesExecute ? 'true' : 'false'">
    <span class="font-medium" data-testid="market-closed-text">{{ text }}</span>
  </div>
</template>
