<!-- The Undo toast (ADR-271: the fixed bottom-centre toast of ADR-193, where the user clicked; same classes as Toast.vue, the flow owns the timer), the neutral notice and the refusal message of the shared Delete flow (REQ-070 AC-6). Lives in the list's
     owner, not in the row, because the row is gone once deleted. -->
<script setup>
import ErrorMessage from "@/components/common/ErrorMessage.vue";

defineProps({ flow: { type: Object, required: true } });
</script>

<template>
  <div
    v-if="flow.undo || flow.notice || flow.errorParts"
    class="mt-2 text-sm"
    data-testid="delete-status"
  >
    <p
      v-if="flow.undo"
      class="fixed bottom-6 left-1/2 z-50 flex max-w-[calc(100vw-32px)] -translate-x-1/2 items-center gap-4 rounded-lg bg-ink-overlay px-4 py-2.5 text-surface"
      role="status"
      aria-live="polite"
      data-testid="delete-toast"
    >
      <span>Strategy deleted.</span>
      <button
        type="button"
        class="font-semibold text-accent-soft underline"
        :disabled="flow.busy"
        data-testid="delete-undo"
        @click="flow.undoDelete()"
      >
        Undo
      </button>
    </p>
    <p v-if="flow.notice" data-testid="delete-notice">{{ flow.notice }}</p>
    <ErrorMessage
      v-if="flow.errorParts"
      :parts="flow.errorParts"
      compact
      prefix="delete-error"
      data-testid="delete-error"
    />
  </div>
</template>
