<!-- REQ-081 AC-2 / ADR-167 (2): the round-trip charges by component, opened from a 'Charges' action on the Builder summary.
     Screen 022 lists them (Brokerage, STT, Exchange txn, GST, Stamp, SEBI, Total). Rewritten from the W-127 component: it is now
     closed by default and opens by button or keyboard. Every figure, the rates date and the 'estimate' label are the server's
     strings shown as sent; the browser adds nothing up (ADR-008). The curves and the table are before these charges. -->
<script setup>
import { ref } from "vue";
import FigureHint from "@/components/common/FigureHint.vue";
import Modal from "@/components/common/Modal.vue";

defineProps({
  breakdown: { type: Object, required: true }, // charges_breakdown as sent; the parent draws nothing when it is null
});
const open = ref(false);
const ROWS = [
  { key: "brokerage", label: "Brokerage" },
  { key: "stt", label: "STT" },
  { key: "exchange_transaction", label: "Exchange transaction charges" },
  { key: "gst", label: "GST" },
  { key: "stamp", label: "Stamp duty" },
  { key: "sebi", label: "SEBI charges" },
];
</script>

<template>
  <div class="min-w-0" data-testid="charges-breakdown">
    <div class="flex flex-wrap items-center gap-1">
      <button
        type="button"
        class="text-sm underline text-accent"
        data-testid="charges-action"
        :aria-expanded="open ? 'true' : 'false'"
        aria-controls="charges-panel"
        @click="open = !open"
      >
        Charges
      </button>
      <FigureHint id="charges" />
    </div>
    <!-- W-192 UI-107 / screen 022: the breakdown opens in the shared Modal - total at top, one row per component, then
         the server's estimate label and rates date as footnotes. -->
    <Modal :open="open" title="Charges and taxes" @close="open = false">
      <section
        id="charges-panel"
        class="min-w-0 break-words"
        data-testid="charges-panel"
      >
        <p
          class="text-lg font-semibold text-ink"
          data-testid="charges-total"
        >Total Rs {{ breakdown.total }}</p>
        <dl class="mt-3 divide-y divide-line border-y border-line text-sm">
          <div
            v-for="row in ROWS"
            :key="row.key"
            class="flex items-center justify-between gap-4 py-2"
            :data-testid="'charges-' + row.key"
          >
            <dt class="text-ink-muted">{{ row.label }}</dt>
            <dd class="tabular-nums">Rs {{ breakdown[row.key] }}</dd>
          </div>
        </dl>
        <!-- ADR-167 (4): the server's exercise-STT sentence (rate and condition, no amount); outside the total, only when sent -->
        <p
          v-if="breakdown.exercise_stt_note"
          class="mt-2 text-xs text-ink-muted"
          data-testid="charges-exercise-stt"
        >
          {{ breakdown.exercise_stt_note }}
        </p>
        <p class="mt-3 text-xs text-ink-muted">
          <span data-testid="charges-label">Charges and taxes ({{ breakdown.label }})</span>: entering and leaving every
          leg at its planned price. The payoff curves and the table are before
          these charges.
        </p>
        <p class="text-xs text-ink-muted" data-testid="charges-rates-date">
          Rates read on {{ breakdown.rates_read_on }}
        </p>
      </section>
    </Modal>
  </div>
</template>
