<!-- Probability of profit (W-125; REQ-082 AC-1, AC-3, AC-5). HELD: rendered ONLY when GET /features lists
     `probability_of_profit` AND the outcome answer carries the figure ({percent} or {reason}); absent otherwise, never a
     placeholder. The percentage comes from the engine; the browser shows it as given. Never used to sort or rank. -->
<script setup>
import { computed } from 'vue'
import { useHeldFeature } from '@/lib/heldFeatures'
import { popText } from '@/lib/readyMade'
import FigureHint from '@/components/common/FigureHint.vue'

const props = defineProps({ pop: { type: Object, default: null } })
const on = useHeldFeature('probability_of_profit')
const text = computed(() => popText(props.pop))
</script>

<template>
  <!-- W-193 (UI-117): a label-value row in Block 2 of the summary card; absent while held, never a dash. -->
  <div v-if="on && text" class="flex min-h-7 items-center justify-between gap-2 text-sm" data-testid="pop-row">
    <span class="flex items-center text-ink-muted">POP<FigureHint id="probability_of_profit" /></span>
    <p class="text-right font-medium text-ink" data-testid="pop-figure">{{ text }}</p>
  </div>
</template>
