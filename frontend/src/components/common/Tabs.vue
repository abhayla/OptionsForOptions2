<!-- ADR-193 UI-012: two tab kinds. `segmented` = a 36 px pill group, active tab accent fill + white text (S-012
     "Payoff Graph"); `underline` = 14 px/500 text, active tab accent text + 2 px underline (S-012 "Payoff Table").
     role="tablist"; arrow keys, Home and End move the selection; only the selected tab is in the Tab order. -->
<script setup>
import { ref, useId } from "vue";
import { panelId, tabId } from "./tabIds.js";

const props = defineProps({
  tabs: { type: Array, required: true }, // [{ key, label }]
  modelValue: { type: String, required: true },
  variant: {
    type: String,
    default: "underline",
    validator: (v) => ["segmented", "underline"].includes(v),
  },
  label: { type: String, default: "" },
  // Review 6: each tab names the panel it controls (aria-controls) and each panel names its tab (aria-labelledby) through
  // tabId / panelId(idPrefix, key); a page with its own panels passes the prefix it uses for them.
  idPrefix: { type: String, default: "" },
});
const prefix = props.idPrefix || `tabs-${useId()}`;
const emit = defineEmits(["update:modelValue"]);
const buttons = ref([]);

function select(i) {
  const n = props.tabs.length;
  const tab = props.tabs[(i + n) % n];
  emit("update:modelValue", tab.key);
  buttons.value[(i + n) % n]?.focus();
}
function onKey(e, i) {
  const moves = {
    ArrowRight: i + 1,
    ArrowDown: i + 1,
    ArrowLeft: i - 1,
    ArrowUp: i - 1,
    Home: 0,
    End: props.tabs.length - 1,
  };
  if (e.key in moves) {
    e.preventDefault();
    select(moves[e.key]);
  }
}
</script>

<template>
  <div
    role="tablist"
    :aria-label="label || undefined"
    :class="
      variant === 'segmented'
        ? 'inline-flex h-9 rounded-full border border-line bg-surface p-0.5'
        : 'flex gap-6 border-b border-line'
    "
    :data-variant="variant"
    data-testid="tabs"
  >
    <button
      v-for="(t, i) in tabs"
      :id="tabId(prefix, t.key)"
      :key="t.key"
      ref="buttons"
      type="button"
      role="tab"
      :aria-controls="panelId(prefix, t.key)"
      :aria-selected="t.key === modelValue ? 'true' : 'false'"
      :tabindex="t.key === modelValue ? 0 : -1"
      :class="
        variant === 'segmented'
          ? [
              'rounded-full px-4 text-sm font-medium',
              t.key === modelValue
                ? 'bg-accent text-surface'
                : 'text-ink-muted hover:text-ink',
            ]
          : [
              '-mb-px border-b-2 pb-2 text-sm font-medium',
              t.key === modelValue
                ? 'border-accent text-accent'
                : 'border-transparent text-ink-muted hover:text-ink',
            ]
      "
      :data-testid="`tab-${t.key}`"
      @click="emit('update:modelValue', t.key)"
      @keydown="onKey($event, i)"
    >
      {{ t.label }}
    </button>
  </div>
</template>
