<!-- Delete control of ONE saved-strategy row, shared by My Strategies and the Builder's saved list (REQ-070 AC-6, ADR-118).
     Delete appears only when the server said can_delete is true; otherwise the refusal text takes its place (a missing field is
     false). The flow (confirm, Undo, errors) is one object made by useDeleteFlow in lib/strategyActivity.js. -->
<script setup>
import Icon from "@/components/common/Icon.vue";
import {
  DELETE_CONFIRM_TEXT,
  DELETE_REFUSED_TEXT,
  canDelete,
} from "@/lib/strategyActivity";

defineProps({
  row: { type: Object, required: true },
  flow: { type: Object, required: true },
  // GC-UI 6b D-C12: the Builder's Saved rows show a bin icon (named "Delete") instead of the text link
  icon: { type: Boolean, default: false },
});
</script>

<template>
  <span
    v-if="!canDelete(row)"
    class="text-ink-muted"
    data-testid="delete-refused"
    :title="icon ? DELETE_REFUSED_TEXT : undefined"
    ><template v-if="icon"><Icon name="trash" :size="16" /></template
    ><template v-else>{{ DELETE_REFUSED_TEXT }}</template></span
  >
  <button
    v-else-if="flow.confirming !== row.id"
    type="button"
    class="underline"
    :disabled="flow.busy"
    :data-testid="`delete-${row.id}`"
    :aria-label="icon ? 'Delete' : undefined"
    :title="icon ? 'Delete' : undefined"
    @click="flow.ask(row.id)"
  >
    <Icon v-if="icon" name="trash" :size="16" />
    <template v-else>Delete</template>
  </button>
  <span
    v-else
    class="flex flex-wrap items-center gap-2"
    data-testid="delete-confirm-box"
  >
    <span>{{ DELETE_CONFIRM_TEXT }}</span>
    <button
      type="button"
      class="underline"
      :disabled="flow.busy"
      data-testid="delete-confirm"
      @click="flow.confirm(row.id)"
    >
      Delete
    </button>
    <button
      type="button"
      class="underline"
      data-testid="delete-cancel"
      @click="flow.cancel()"
    >
      Cancel
    </button>
  </span>
</template>
