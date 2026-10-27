<!-- ADR-193 UI-017 + Revision 1 (finding M6): a popover / tooltip whose trigger is a real, focusable button. Mouse hover
     or keyboard focus shows it, Enter/Space or a tap toggles it, Esc closes it. Text comes from `text`. A figure's
     definition is NOT shown through this part: REQ-136 keeps the figure catalogue readable only by FigureHint.vue (same
     trigger behaviour and look), so a figure label uses FigureHint and its text is never retyped. Dark fill, white 12 px
     text, max 280 px, 6 px radius. The `trigger` slot replaces the default "?" mark. -->
<script setup>
import { computed, ref } from "vue";
import Icon from "./Icon.vue";

const props = defineProps({
  text: { type: String, required: true },
  label: { type: String, default: "More information" },
});
const body = computed(() => props.text);
const panelId = `tooltip-${Math.random().toString(36).slice(2, 8)}`;
const hovered = ref(false);
const focused = ref(false);
const pinned = ref(false);
const open = computed(
  () => Boolean(body.value) && (hovered.value || focused.value || pinned.value),
);

function close() {
  hovered.value = false;
  focused.value = false;
  pinned.value = false;
}
function onPointerEnter(e) {
  if (e.pointerType === "mouse") hovered.value = true;
}
function onPointerLeave(e) {
  if (e.pointerType === "mouse") hovered.value = false;
}
// A tap or Enter/Space: toggle. Closing clears focus/hover too, else the panel would stay open.
function onClick() {
  pinned.value = !pinned.value;
  if (!pinned.value) {
    focused.value = false;
    hovered.value = false;
  }
}
function onKey(e) {
  if (e.key === "Escape") close();
}
</script>

<template>
  <span
    v-if="body"
    class="relative inline-block align-middle"
    data-testid="tooltip"
    @keydown="onKey"
  >
    <button
      type="button"
      class="inline-flex items-center justify-center rounded-full text-ink-subtle hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      :aria-label="label"
      :aria-expanded="open ? 'true' : 'false'"
      :aria-describedby="open ? panelId : undefined"
      data-testid="tooltip-trigger"
      @pointerenter="onPointerEnter"
      @pointerleave="onPointerLeave"
      @focus="focused = true"
      @blur="close"
      @click="onClick"
    >
      <slot name="trigger"><Icon name="info" :size="14" /></slot>
    </button>
    <span
      v-if="open"
      :id="panelId"
      role="tooltip"
      class="absolute top-full left-0 z-50 mt-1 w-max max-w-[min(280px,80vw)] rounded-md bg-ink-overlay px-2 py-1.5 text-xs leading-4 font-normal text-surface"
      data-testid="tooltip-text"
      >{{ body }}</span
    >
  </span>
</template>
