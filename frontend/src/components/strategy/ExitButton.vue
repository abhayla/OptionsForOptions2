<!-- Phase 4 (modular doors), F2: one Exit button for every paper screen. `blocked` / `reason` come from usePaperExit (the failed-read
     and changed-elsewhere gate); `extraDisabled` is the screen's own rule (a bad lots box, nothing ticked). The reason line is the
     sentence, as sent by the gate, under the button (test id paper-exit-reason). Attributes (test ids, class, click) go to the button. -->
<template>
  <span class="contents">
    <button v-bind="$attrs" type="button" class="disabled:cursor-not-allowed disabled:opacity-50" :disabled="blocked || extraDisabled">
      <slot />
    </button>
    <p v-if="showReason && reason" class="text-xs text-ink-muted" data-testid="paper-exit-reason">{{ reason }}</p>
  </span>
</template>

<script setup>
defineOptions({ inheritAttrs: false })
defineProps({
  blocked: { type: Boolean, default: false },
  reason: { type: String, default: null },
  extraDisabled: { type: Boolean, default: false },
  showReason: { type: Boolean, default: true },
})
</script>
