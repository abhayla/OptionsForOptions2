<!-- Activity history of the SAVED strategy open in the Builder (REQ-070 AC-3, AC-5, ADR-118). Closed on first render; opened by the
     user. Each entry shows its time and the server's own change summary (quoted catalogue text, never rewritten here) and a
     Restore. Restore sends the revision this page holds; the reply's legs and revision replace what is on screen through the
     Builder's one open path ('open'); the server has already kept the replaced configuration as a new entry. After execution the
     server refuses (strategy_restore_after_execution): its message is shown and the list stays readable. -->
<script setup>
import { ref, watch } from "vue";
import api, { NEUTRAL_PARTS } from "@/services/api";
import ErrorMessage from "@/components/common/ErrorMessage.vue";
import { istTime } from "@/lib/displayFormat";
import {
  canRestore,
  NO_EARLIER_TEXT,
  fetchHistory,
  restoreEntry,
} from "@/lib/strategyActivity";

const props = defineProps({
  current: { type: Object, required: true }, // { id, revision, name } of the saved strategy on screen
});
const emit = defineEmits(["open"]);

const open = ref(false);
const entries = ref(null); // null = not read yet
const busy = ref(false);
const errorParts = ref(null);

async function load() {
  errorParts.value = null;
  try {
    entries.value = await fetchHistory(api, props.current.id);
  } catch (e) {
    errorParts.value = e?.parts ?? NEUTRAL_PARTS;
  }
}

function toggle() {
  open.value = !open.value;
  if (open.value) load();
}

// A save, a restore or an Undo changes the revision: an open panel is read again (the newest entry is the one just written).
watch(
  () => [props.current.id, props.current.revision],
  () => {
    if (open.value) load();
  },
);

async function restore(entry) {
  if (busy.value) return;
  const { id, revision } = props.current; // read BEFORE the await
  busy.value = true;
  errorParts.value = null;
  try {
    const {
      legs,
      revision: next,
      name,
    } = await restoreEntry(api, id, entry.seq, revision);
    emit("open", legs, id, next, name);
  } catch (e) {
    const parts = e?.parts ?? NEUTRAL_PARTS;
    if (e?.status === 404) await load(); // the entry is gone: the list is read again
    errorParts.value = parts;
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <section
    class="mt-4 rounded border border-line bg-surface p-4"
    data-testid="activity-panel"
  >
    <button
      type="button"
      class="text-sm font-medium underline"
      data-testid="activity-toggle"
      :aria-expanded="open"
      @click="toggle"
    >
      Activity history
    </button>
    <div v-if="open" class="mt-2 text-sm" data-testid="activity-body">
      <ErrorMessage
        v-if="errorParts"
        :parts="errorParts"
        compact
        prefix="activity-error"
        data-testid="activity-error"
      />
      <p v-if="entries && !entries.length" data-testid="activity-empty">
        {{ NO_EARLIER_TEXT }}
      </p>
      <ul
        v-else-if="entries"
        class="divide-y divide-line"
        data-testid="activity-list"
      >
        <li
          v-for="e in entries"
          :key="e.seq"
          class="flex flex-wrap items-center gap-2 py-1"
          data-testid="activity-entry"
          :data-seq="e.seq"
        >
          <span class="text-ink-muted" data-testid="activity-at">{{
            istTime(e.at)
          }}</span>
          <span data-testid="activity-summary">{{ e.change_summary }}</span>
          <button
            v-if="canRestore(e)"
            type="button"
            class="underline"
            :disabled="busy"
            :data-testid="`restore-${e.seq}`"
            @click="restore(e)"
          >
            Restore
          </button>
        </li>
      </ul>
    </div>
  </section>
</template>
