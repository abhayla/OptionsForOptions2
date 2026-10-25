<!-- "How this trade works" (REQ-085 AC-7, AC-8; W-159). Shown once a leg-edit reply has named the shape: the bullets of the
     matched template (Learn home, src/lib/howItWorks.js) with the strikes and expiry the server sent; a Custom Strategy or a
     template with no bullets shows only the link to Learn. Nothing is computed here (ADR-008). -->
<script setup>
import { computed } from "vue";
import { HOW_LEARN_LINK, HOW_TITLE } from "@/lib/learnContent";
import { bulletsFor } from "@/lib/howItWorks";

const props = defineProps({
  shapeId: { type: String, default: null }, // the server's template id; null = Custom Strategy
  legs: { type: Array, required: true },
  underlying: { type: String, default: "" },
});
const bullets = computed(() =>
  bulletsFor(props.shapeId, props.legs, props.underlying),
);
</script>

<template>
  <div class="mt-3 text-sm" data-testid="how-this-trade-works">
    <h2 class="font-medium">{{ HOW_TITLE }}</h2>
    <ul v-if="bullets.length" class="list-disc pl-5" data-testid="how-bullets">
      <li v-for="b in bullets" :key="b" data-testid="how-bullet">{{ b }}</li>
    </ul>
    <router-link to="/learn" class="underline" data-testid="how-learn-link">{{
      HOW_LEARN_LINK
    }}</router-link>
  </div>
</template>
