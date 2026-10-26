<!-- ADR-193 UI-016: a drawer that slides over the page from the left (leg picker, S-032) or right (warnings S-234,
     funds S-053). White, full height under the 56 px top bar, drawer shadow, 56 px header (title + close "x"), optional
     64 px footer (`footer` slot). An overlay sits behind it; Esc, the "x" and an overlay click emit `close`. While open,
     focus moves inside and Tab / Shift+Tab stay inside; on close focus returns to what had it before. -->
<script setup>
import { nextTick, onBeforeUnmount, ref, watch } from "vue";
import Icon from "./Icon.vue";

const props = defineProps({
  open: { type: Boolean, required: true },
  title: { type: String, required: true },
  side: {
    type: String,
    default: "right",
    validator: (v) => ["left", "right"].includes(v),
  },
  width: { type: String, default: "420px" },
});
const emit = defineEmits(["close"]);
const panel = ref(null);
let returnTo = null;

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
function focusables() {
  return panel.value ? [...panel.value.querySelectorAll(FOCUSABLE)] : [];
}
function onKey(e) {
  if (e.key === "Escape") {
    e.preventDefault();
    emit("close");
    return;
  }
  if (e.key !== "Tab") return;
  const list = focusables();
  if (!list.length) {
    e.preventDefault();
    panel.value?.focus();
    return;
  }
  const first = list[0];
  const last = list[list.length - 1];
  if (
    e.shiftKey &&
    (document.activeElement === first || document.activeElement === panel.value)
  ) {
    e.preventDefault();
    last.focus();
  } else if (!e.shiftKey && document.activeElement === last) {
    e.preventDefault();
    first.focus();
  }
}
watch(
  () => props.open,
  async (isOpen) => {
    if (isOpen) {
      returnTo = document.activeElement;
      await nextTick();
      (focusables()[0] ?? panel.value)?.focus();
    } else if (returnTo && typeof returnTo.focus === "function") {
      returnTo.focus();
      returnTo = null;
    }
  },
  { immediate: true },
);
onBeforeUnmount(() => {
  if (returnTo && typeof returnTo.focus === "function") returnTo.focus();
});
</script>

<template>
  <div
    v-if="open"
    class="fixed inset-x-0 top-14 bottom-0 z-50"
    data-testid="drawer-root"
  >
    <div
      class="absolute inset-0 bg-ink/30"
      data-testid="drawer-overlay"
      @click="emit('close')"
    />
    <div
      ref="panel"
      role="dialog"
      aria-modal="true"
      :aria-label="title"
      tabindex="-1"
      class="absolute top-0 bottom-0 flex max-w-full flex-col bg-surface shadow-drawer focus:outline-none"
      :class="side === 'left' ? 'left-0' : 'right-0'"
      :style="{ width }"
      :data-side="side"
      data-testid="drawer"
      @keydown="onKey"
    >
      <header
        class="flex h-14 shrink-0 items-center justify-between border-b border-line px-4"
      >
        <h2 class="text-base font-semibold text-ink" data-testid="drawer-title">
          {{ title }}
        </h2>
        <button
          type="button"
          class="flex h-8 w-8 items-center justify-center rounded-md text-ink-muted hover:bg-surface-muted hover:text-ink"
          aria-label="Close"
          data-testid="drawer-close"
          @click="emit('close')"
        >
          <Icon name="close" :size="18" />
        </button>
      </header>
      <div class="min-h-0 flex-1 overflow-y-auto p-4"><slot /></div>
      <footer
        v-if="$slots.footer"
        class="flex h-16 shrink-0 items-center justify-end gap-2 border-t border-line px-4"
      >
        <slot name="footer" />
      </footer>
    </div>
  </div>
</template>
