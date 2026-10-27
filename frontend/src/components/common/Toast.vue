<!-- ADR-193 UI-019: a one-line confirmation toast ("Saved", "Legs cleared - Undo"), bottom centre, dark, 14 px; it emits
     `close` after `duration` ms (4 s). Confirmations only: an error is never a toast (UI-020, REQ-065 errors sit under
     the control that failed). Optional single action button (`actionLabel`, emits `action`). -->
<script setup>
import { onBeforeUnmount, watch } from "vue";

const props = defineProps({
  open: { type: Boolean, required: true },
  message: { type: String, required: true },
  actionLabel: { type: String, default: "" },
  duration: { type: Number, default: 4000 },
});
const emit = defineEmits(["close", "action"]);
let timer = null;

function clear() {
  if (timer) clearTimeout(timer);
  timer = null;
}
watch(
  () => [props.open, props.message],
  ([isOpen]) => {
    clear();
    if (isOpen) timer = setTimeout(() => emit("close"), props.duration);
  },
  { immediate: true },
);
onBeforeUnmount(clear);
</script>

<template>
  <div
    v-if="open"
    role="status"
    aria-live="polite"
    class="fixed bottom-6 left-1/2 z-50 flex max-w-[calc(100vw-32px)] -translate-x-1/2 items-center gap-4 rounded-lg bg-ink-overlay px-4 py-2.5 text-sm text-surface"
    data-testid="toast"
  >
    <span class="whitespace-nowrap" data-testid="toast-message">{{
      message
    }}</span>
    <button
      v-if="actionLabel"
      type="button"
      class="font-semibold text-accent-soft underline"
      data-testid="toast-action"
      @click="emit('action')"
    >
      {{ actionLabel }}
    </button>
  </div>
</template>
