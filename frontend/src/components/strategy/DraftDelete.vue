<!-- Delete control of ONE saved-strategy row, shared by My Strategies and the Builder's saved list (REQ-070 AC-6, ADR-118).
     Delete appears only when the server said can_delete is true; otherwise the refusal text takes its place (a missing field is
     false). The flow (confirm, Undo, errors) is one object made by useDeleteFlow in lib/strategyActivity.js. -->
<script setup>
import Icon from "@/components/common/Icon.vue";
import { computed } from "vue";
import { strategyLabel } from "@/lib/saveDraft";
import {
  DELETE_CONFIRM_TEXT,
  DELETE_REFUSED_TEXT,
  canDelete,
} from "@/lib/strategyActivity";

const props = defineProps({
  row: { type: Object, required: true },
  flow: { type: Object, required: true },
  // GC-UI 6b D-C12: the Builder's Saved rows show a bin icon (named "Delete") instead of the text link
  icon: { type: Boolean, default: false },
});
// the row is named so a screen reader hears WHICH strategy the bin acts on
const rowName = computed(() => strategyLabel(props.row, `Draft ${props.row.id}`));
</script>

<template>
  <span v-if="!canDelete(row) && icon" class="relative inline-flex">
    <!-- the refusal: focusable (aria-disabled, not disabled), its reason read as the description and shown on focus -->
    <button
      type="button"
      class="peer text-ink-muted"
      aria-disabled="true"
      data-testid="delete-refused"
      :aria-label="`Delete ${rowName} (not available)`"
      :aria-describedby="`delete-refused-reason-${row.id}`"
      :title="DELETE_REFUSED_TEXT"
    >
      <Icon name="trash" :size="16" />
    </button>
    <span
      :id="`delete-refused-reason-${row.id}`"
      role="tooltip"
      class="pointer-events-none absolute right-0 top-full z-10 hidden w-max max-w-56 rounded border border-line bg-surface p-1 text-xs text-ink peer-focus:block"
      data-testid="delete-refused-reason"
      >{{ DELETE_REFUSED_TEXT }}</span
    >
  </span>
  <span v-else-if="!canDelete(row)" class="text-ink-muted" data-testid="delete-refused">{{ DELETE_REFUSED_TEXT }}</span>
  <button
    v-else-if="flow.confirming !== row.id"
    type="button"
    :class="icon ? 'underline' : 'link'"
    :disabled="flow.busy"
    :data-testid="`delete-${row.id}`"
    :aria-label="icon ? `Delete ${rowName}` : undefined"
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
      class="link"
      :disabled="flow.busy"
      data-testid="delete-confirm"
      @click="flow.confirm(row.id)"
    >
      Delete
    </button>
    <button
      type="button"
      class="link"
      data-testid="delete-cancel"
      @click="flow.cancel()"
    >
      Cancel
    </button>
  </span>
</template>
