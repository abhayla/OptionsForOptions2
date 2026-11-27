<!-- ADR-330 (56): the ONE price notice for a price screen whose page mounts none of its own (route meta.priceNotice). Pages that
     mount their own notice (Home strip, Positions, Live Strategies, Index view) are never flagged, so the notice never shows twice.
     Reads the page-level index answer once (GET /market/indices, the one reader); no price maths here (ADR-008). -->
<script setup>
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import PriceNotice from '@/components/states/PriceNotice.vue'
import { readAnswer } from '@/composables/useIndexLive'

const route = useRoute()
const answer = ref(null)
watch(() => route.meta?.priceNotice === true, async (on) => {
  answer.value = on ? await readAnswer(false) : null
}, { immediate: true })
</script>

<template>
  <PriceNotice v-if="route.meta?.priceNotice === true" class="mb-4" :answer="answer" />
</template>
