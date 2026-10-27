<!-- REQ-136 (W-160) AC-3: the one standing note under the summary. Always visible when numbers are shown, never inside a hover.
     W-193 (ADR-193 Revision 1 M4, UI-005): the "Important info" note directly under the summary card, always open, no
     collapse control. It holds the planning sentence that sat under the page title (ADR-003: for planning, not a
     recommendation) and the projections note. -->
<script setup>
import { PROJECTIONS_NOTE } from "@/lib/figureDefinitions";

const PLANNING_SENTENCE =
  "A draft strategy and what it could do at different index levels. This is for planning, not a recommendation.";
</script>

<template>
  <section
    class="mt-3 rounded-lg border border-line bg-surface-muted px-4 py-3 text-xs text-ink-muted"
    aria-label="Important info"
    data-testid="important-info"
  >
    <h3 class="text-[13px] font-semibold text-ink">Important info</h3>
    <p class="mt-1" data-testid="planning-note">{{ PLANNING_SENTENCE }}</p>
    <p class="mt-1" data-testid="projections-note">{{ PROJECTIONS_NOTE }}</p>
  </section>
</template>
