<!-- ADR-193 UI-018: a modal dialog (Save, Charges; S-116). 420 px wide, 12 px radius, 32 px padding, 20 px/600 title,
     close "x" top right, the `actions` slot as a full-width pair at the bottom (secondary left, primary right).
     Esc, the "x" and an overlay click emit `close`; focus moves into the dialog and returns on close. -->
<script setup>
import { nextTick, ref, watch } from "vue";
import Icon from "./Icon.vue";
import { trapTab } from "./focusTrap.js";

const props = defineProps({
  open: { type: Boolean, required: true },
  title: { type: String, required: true },
});
const emit = defineEmits(["close"]);
const dialog = ref(null);
let returnTo = null;

watch(
  () => props.open,
  async (isOpen) => {
    if (isOpen) {
      returnTo = document.activeElement;
      await nextTick();
      dialog.value?.focus();
    } else if (returnTo && typeof returnTo.focus === "function") {
      returnTo.focus();
      returnTo = null;
    }
  },
  { immediate: true },
);
function onKey(e) {
  if (e.key === "Escape") {
    e.preventDefault();
    emit("close");
    return;
  }
  trapTab(e, dialog.value);
}
</script>

<template>
  <div
    v-if="open"
    class="fixed inset-0 z-50 flex items-center justify-center p-4"
    data-testid="modal-root"
    @keydown="onKey"
  >
    <div
      class="absolute inset-0 bg-ink/30"
      data-testid="modal-overlay"
      @click="emit('close')"
    />
    <div
      ref="dialog"
      role="dialog"
      aria-modal="true"
      :aria-label="title"
      tabindex="-1"
      class="relative w-[420px] max-w-full rounded-xl bg-surface p-8 shadow-drawer focus:outline-none"
      data-testid="modal"
    >
      <button
        type="button"
        class="absolute top-4 right-4 flex h-8 w-8 items-center justify-center rounded-md text-ink-muted hover:bg-surface-muted hover:text-ink"
        aria-label="Close"
        data-testid="modal-close"
        @click="emit('close')"
      >
        <Icon name="close" :size="18" />
      </button>
      <h2 class="pr-8 text-xl font-semibold text-ink" data-testid="modal-title">
        {{ title }}
      </h2>
      <div class="mt-4 text-sm text-ink"><slot /></div>
      <div
        v-if="$slots.actions"
        class="mt-6 grid grid-cols-2 gap-3"
        data-testid="modal-actions"
      >
        <slot name="actions" />
      </div>
    </div>
  </div>
</template>
