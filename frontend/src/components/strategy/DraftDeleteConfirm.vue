<!-- The single-row delete confirmation box (REQ-070 AC-6). One markup for both places it shows: inside the Builder's saved row
     (DraftDelete) and, on My Strategies, as its own full-width line below the row so Rename and Delete never move (S-04). -->
<script setup>
import { confirmText } from "@/lib/strategyActivity";

defineProps({
  row: { type: Object, required: true },
  flow: { type: Object, required: true },
});
</script>

<template>
  <span class="flex flex-wrap items-center gap-2" data-testid="delete-confirm-box">
    <span>{{ confirmText(row) }}</span>
    <button type="button" class="link" :disabled="flow.busy" data-testid="delete-confirm" @click="flow.confirm(row.id)">Delete</button>
    <button type="button" class="link" data-testid="delete-cancel" @click="flow.cancel()">Cancel</button>
  </span>
</template>
