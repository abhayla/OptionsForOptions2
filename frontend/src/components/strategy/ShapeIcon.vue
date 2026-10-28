<!-- GC-UI D-C04: the static payoff-shape icon on a ready-made card: green above the zero line, red below it. Artwork only
     (lib/readyMadeShapes.js), decorative (aria-hidden: the card name carries the meaning); an id with no shape draws nothing. -->
<script setup>
import { computed } from 'vue'
import { ZERO_Y, pointsAttr, shapePoints } from '@/lib/readyMadeShapes'

const props = defineProps({ id: { type: String, required: true } })
const points = computed(() => shapePoints(props.id))
const line = computed(() => (points.value ? pointsAttr(points.value) : ''))
const clip = (part) => `rm-clip-${part}-${props.id}`
</script>

<template>
  <svg v-if="points" viewBox="0 0 48 28" class="h-7 w-12" aria-hidden="true" data-testid="rm-card-icon">
    <defs>
      <clipPath :id="clip('up')"><rect x="0" y="0" width="48" :height="ZERO_Y" /></clipPath>
      <clipPath :id="clip('down')"><rect x="0" :y="ZERO_Y" width="48" :height="28 - ZERO_Y" /></clipPath>
    </defs>
    <line x1="0" :y1="ZERO_Y" x2="48" :y2="ZERO_Y" stroke="currentColor" stroke-width="0.75" class="text-line" />
    <polyline :points="line" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" class="text-profit" :clip-path="`url(#${clip('up')})`" />
    <polyline :points="line" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" class="text-loss" :clip-path="`url(#${clip('down')})`" />
  </svg>
</template>
