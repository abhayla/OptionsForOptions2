<!-- Probability of profit (W-125; REQ-082 AC-1, AC-3, AC-5). HELD: rendered ONLY when GET /features lists
     `probability_of_profit` AND the outcome answer carries the figure ({percent} or {reason}); absent otherwise, never a
     placeholder. The percentage comes from the engine; the browser shows it as given. Never used to sort or rank. -->
<script setup>
import { computed } from 'vue'
import { useHeldFeature } from '@/lib/heldFeatures'
import { popText } from '@/lib/readyMade'

const props = defineProps({ pop: { type: Object, default: null } })
const on = useHeldFeature('probability_of_profit')
const text = computed(() => popText(props.pop))
</script>

<template>
  <p v-if="on && text" class="mt-2 text-sm" data-testid="pop-figure">{{ text }}</p>
</template>
