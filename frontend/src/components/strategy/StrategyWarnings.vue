<!-- Strategy warnings area (REQ-085 AC-1, AC-5, AC-8; W-159, ADR-185). Draws the outcome answer's `warnings` exactly as sent:
     the text is the server's catalogue text, the browser builds none. An empty list shows the server's own
     `warnings_label`; an ABSENT list (not-live, waiting, refused, from-entries answers) shows nothing: absent is not
     "no warnings". -->
<script setup>
import { computed } from "vue";

const props = defineProps({
  warnings: { type: Array, default: null }, // the answer's strategy list; null/undefined = the answer sent none
  label: { type: String, default: null }, // the server's "No warnings for this strategy"
});
const list = computed(() =>
  Array.isArray(props.warnings)
    ? props.warnings.filter((w) => typeof w?.text === "string" && w.text !== "")
    : [],
);
const showLabel = computed(
  () =>
    Array.isArray(props.warnings) &&
    props.warnings.length === 0 &&
    typeof props.label === "string" &&
    props.label !== "",
);
</script>

<template>
  <div
    v-if="list.length || showLabel"
    class="mt-4 rounded border border-line p-3 text-sm"
    data-testid="strategy-warnings"
  >
    <ul v-if="list.length">
      <li
        v-for="(w, i) in list"
        :key="i"
        :data-code="w.code"
        data-testid="strategy-warning"
      >
        {{ w.text }}
      </li>
    </ul>
    <p v-else data-testid="no-warnings">{{ label }}</p>
  </div>
</template>
