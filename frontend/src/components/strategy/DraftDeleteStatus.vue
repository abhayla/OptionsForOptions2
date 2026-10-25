<!-- The Undo toast, the neutral notice and the refusal message of the shared Delete flow (REQ-070 AC-6). Lives in the list's
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
      class="flex items-center gap-2"
      data-testid="delete-toast"
    >
      <span>Strategy deleted.</span>
      <button
        type="button"
        class="underline"
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
