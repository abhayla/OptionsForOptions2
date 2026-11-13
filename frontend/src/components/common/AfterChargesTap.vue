<!-- GC-ICFIX u127 (ADR-263, ADR-008): wraps a figure shown "(after charges)" / "(before charges)". One tap, Enter or Space opens a
     small breakdown of server texts (lib/tracking afterFigure().breakdown): Before charges, Charges paid, Estimated charges to
     close, After charges - or, with no after figure, the before row and the server's reason. Escape or a click outside closes it.
     It opens BELOW the figure (absolute, top-full), never over it. No breakdown (paused, older reply) -> the slot only, no tap target.
     Nothing is computed here. -->
<script setup>
import { onBeforeUnmount, ref, watch } from "vue";

defineProps({ breakdown: { type: Object, default: null } });
const root = ref(null);
const open = ref(false);
const away = (e) => {
  if (root.value && !root.value.contains(e.target)) open.value = false;
};
watch(open, (v) => document[v ? "addEventListener" : "removeEventListener"]("click", away));
onBeforeUnmount(() => document.removeEventListener("click", away));
const onKey = (e) => {
  if (e.key === "Escape") open.value = false;
  else if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    open.value = !open.value;
  }
};
</script>

<template>
  <span v-if="breakdown" ref="root" class="relative inline-block" @keydown.esc="open = false">
    <span
      role="button"
      tabindex="0"
      class="cursor-pointer underline decoration-dotted underline-offset-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      :aria-expanded="open ? 'true' : 'false'"
      data-testid="after-tap"
      @click="open = !open"
      @keydown="onKey"
    ><slot /></span>
    <span
      v-if="open"
      class="absolute left-0 top-full z-20 mt-1 block w-max max-w-[min(280px,80vw)] rounded-md bg-ink-overlay p-2 text-left text-xs font-normal normal-case text-surface"
      data-testid="after-breakdown"
    >
      <span v-for="r in breakdown.rows" :key="r.id" class="block" :data-testid="`breakdown-${r.id}`">{{ r.label }}: {{ r.text }}</span>
      <span v-if="breakdown.reason" class="mt-1 block" data-testid="breakdown-reason">{{ breakdown.reason }}</span>
    </span>
  </span>
  <slot v-else />
</template>
