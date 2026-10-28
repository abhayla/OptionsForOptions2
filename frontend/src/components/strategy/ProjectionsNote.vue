<!-- REQ-136 (W-160) AC-3: the one standing note under the summary. Always visible when numbers are shown, never inside a hover.
     W-193 (ADR-193 Revision 1 M4, UI-005): the "Important info" note directly under the summary card, always open, no
     collapse control. GC-UI step 3b (D-A43 part, ADR-202 (5)): one short note. The projections sentence REQ-136 AC-3
     requires stays visible, word for word; the planning sentence (ADR-003: for planning, not a recommendation; no rule
     requires it visible) is in the note's "?", words unchanged. Not collapsible and not moved (Sensibull's collapse and
     left-column place are not taken). -->
<script setup>
import { PROJECTIONS_NOTE } from "@/lib/figureDefinitions";
import FigureHint from "@/components/common/FigureHint.vue";

const PLANNING_SENTENCE =
  "A draft strategy and what it could do at different index levels. This is for planning, not a recommendation.";
</script>

<template>
  <section
    class="mt-2 rounded-lg border border-line bg-surface-muted px-3 py-2 text-xs text-ink-muted"
    aria-label="Important info"
    data-testid="important-info"
  >
    <p>
      <span class="inline-flex items-center font-semibold text-ink"
        >Important info<FigureHint id="important_info" label="Important info" :lines="[PLANNING_SENTENCE]"
      /></span>
      <span class="ml-1" data-testid="projections-note">{{ PROJECTIONS_NOTE }}</span>
    </p>
  </section>
</template>
