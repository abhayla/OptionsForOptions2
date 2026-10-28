<!-- REQ-136 (W-160) AC-1/AC-2: an info mark beside a figure's label. The definition is DOM text from the one catalogue
     (lib/figureDefinitions.js), shown on mouse hover, keyboard focus or a tap; Escape or a second tap closes it. No title=
     attribute (touch screens never show one) and no v-html. An id the catalogue does not hold draws nothing.
     ADR-193 UI-017: restyled with tokens (subtle mark, dark tooltip, white 12 px text, max 280 px).
     GC-UI step 3b (ADR-202 (1), ADR-204, D-A37): the mark is the circled "?" form; `lines` adds the figure's own
     sentences (the plain-language lines, the exact value, a read time) after the definition, as DOM text. A hint whose id
     is not a catalogue figure draws only when it has a `label` and lines (for example the Important info note). -->
<script setup>
import { computed, ref } from "vue";
import { FIGURES } from "@/lib/figureDefinitions";

const props = defineProps({
  id: { type: String, required: true },
  lines: { type: Array, default: () => [] },
  label: { type: String, default: null },
});
const extra = computed(() => props.lines.filter((l) => typeof l === "string" && l !== ""));
const figure = computed(() => {
  if (Object.hasOwn(FIGURES, props.id)) return FIGURES[props.id];
  return props.label && extra.value.length ? { label: props.label, text: "" } : null;
});
const panelId = `figure-hint-${props.id}-${Math.random().toString(36).slice(2, 8)}`;

const hovered = ref(false);
const focused = ref(false);
const pinned = ref(false);
const open = computed(() => hovered.value || focused.value || pinned.value);

const onEnter = () => {
  hovered.value = true;
};
const onLeave = () => {
  hovered.value = false;
};
const onFocus = () => {
  focused.value = true;
};
const onBlur = () => {
  focused.value = false;
  pinned.value = false;
};
// A tap also hovers and focuses the mark, so closing by a second tap clears all three (else the panel stays open).
const onClick = () => {
  pinned.value = !pinned.value;
  if (!pinned.value) {
    focused.value = false;
    hovered.value = false;
  }
};
const onKey = (e) => {
  if (e.key === "Escape") {
    hovered.value = false;
    focused.value = false;
    pinned.value = false;
  }
};
</script>

<template>
  <span
    v-if="figure"
    class="relative inline-block align-middle"
    data-testid="figure-hint"
    :data-figure="id"
    @keydown="onKey"
  >
    <button
      type="button"
      class="ml-1 inline-flex h-4 w-4 items-center justify-center rounded-full text-ink-subtle hover:text-ink focus:outline-none focus:ring-2 focus:ring-accent"
      :aria-label="`What is ${figure.label}?`"
      :aria-expanded="open ? 'true' : 'false'"
      :aria-describedby="open ? panelId : undefined"
      data-testid="figure-hint-mark"
      data-icon="question"
      @pointerenter="onEnter"
      @pointerleave="onLeave"
      @focus="onFocus"
      @blur="onBlur"
      @click="onClick"
    >
      <svg
        class="h-4 w-4"
        viewBox="0 0 16 16"
        fill="none"
        stroke="currentColor"
        stroke-width="1.5"
        aria-hidden="true"
      >
        <circle cx="8" cy="8" r="6.5" />
        <path
          d="M6.2 6.3a1.9 1.9 0 1 1 2.5 1.8c-.5.2-.7.6-.7 1.1v.5M8 11.4v.01"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
    </button>
    <span
      v-if="open"
      :id="panelId"
      role="tooltip"
      class="absolute left-0 top-full z-20 mt-1 w-64 max-w-[min(280px,80vw)] rounded-md bg-ink-overlay p-2 text-xs font-normal normal-case text-surface"
      data-testid="figure-hint-text"
      ><span v-if="figure.text" class="block" data-testid="figure-hint-definition">{{
        figure.text
      }}</span
      ><span
        v-for="(line, i) in extra"
        :key="i"
        :class="figure.text || i ? 'mt-1 block' : 'block'"
        data-testid="figure-hint-line"
        >{{ line }}</span
      ></span
    >
  </span>
</template>
