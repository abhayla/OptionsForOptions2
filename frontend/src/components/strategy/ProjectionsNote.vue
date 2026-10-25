<!-- REQ-136 (W-160) AC-3: the one standing note under the summary. Always visible when numbers are shown, never inside a hover. -->
<script setup>
import { PROJECTIONS_NOTE } from '@/lib/figureDefinitions'
</script>

<template>
  <p class="px-4 pt-2 text-xs text-ink-muted" data-testid="projections-note">{{ PROJECTIONS_NOTE }}</p>
</template>
