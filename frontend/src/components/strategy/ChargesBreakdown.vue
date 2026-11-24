<!-- REQ-081 AC-2 / ADR-167 (2): the round-trip charges by component, opened from a 'Charges' action on the Builder summary.
     Screen 022 lists them (Brokerage, STT, Exchange txn, GST, Stamp, SEBI, Total). Rewritten from the W-127 component: it is now
     closed by default and opens by button or keyboard. Every figure, the rates date and the 'estimate' label are the server's
     strings shown as sent; the browser adds nothing up (ADR-008). The curves and the table are before these charges. -->
<script setup>
import { ref } from "vue";
import FigureHint from "@/components/common/FigureHint.vue";
import Icon from "@/components/common/Icon.vue";
import Modal from "@/components/common/Modal.vue";
import { groupMoney } from "@/lib/displayFormat";

defineProps({
  breakdown: { type: Object, default: null }, // charges_breakdown as sent (a plan); the parent draws nothing when both are null
  // D-13/D-14 round 2 (ADR-306, ADR-263): in Drafts Mode the paper reply's own charges, as sent: { paid, toClose, total, sentence }.
  // `total` is the reply's extremes_charges (what is inside Max Profit / Max Loss); null when those are before charges.
  paper: { type: Object, default: null },
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
        class="inline-flex items-center gap-1 text-sm underline text-accent"
        data-testid="charges-action"
        :aria-expanded="open ? 'true' : 'false'"
        aria-controls="charges-panel"
        @click="open = !open"
      >
        <span data-testid="charges-icon"><Icon name="calculator" :size="14" /></span>Charges
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
        <template v-if="paper">
          <p v-if="paper.total" class="text-lg font-semibold text-ink" data-testid="charges-total">Total Rs {{ groupMoney(paper.total) }}</p>
          <dl class="mt-3 divide-y divide-line border-y border-line text-sm">
            <div class="flex items-center justify-between gap-4 py-2" data-testid="charges-paper-paid">
              <dt class="text-ink-muted">Charges paid</dt><dd class="tabular-nums">{{ paper.paid }}</dd>
            </div>
            <div v-if="paper.toClose" class="flex items-center justify-between gap-4 py-2" data-testid="charges-paper-close">
              <dt class="text-ink-muted">Estimated cost to close</dt><dd class="tabular-nums">{{ paper.toClose }}</dd>
            </div>
          </dl>
          <p v-if="paper.total" class="mt-3 text-xs text-ink-muted" data-testid="charges-paper-basis">
            Charges paid and the estimated cost to close at the live price; Max Profit and Max Loss are after them.
          </p>
          <p v-if="paper.sentence" class="mt-1 text-xs text-ink-muted" data-testid="charges-paper-sentence">{{ paper.sentence }}</p>
        </template>
        <template v-else>
        <p
          class="text-lg font-semibold text-ink"
          data-testid="charges-total"
        >Total Rs {{ groupMoney(breakdown.total) }}</p>
        <dl class="mt-3 divide-y divide-line border-y border-line text-sm">
          <div
            v-for="row in ROWS"
            :key="row.key"
            class="flex items-center justify-between gap-4 py-2"
            :data-testid="'charges-' + row.key"
          >
            <dt class="text-ink-muted">{{ row.label }}</dt>
            <dd class="tabular-nums">Rs {{ groupMoney(breakdown[row.key]) }}</dd>
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
          these charges; Max Profit and Max Loss are after them.
        </p>
        <p class="text-xs text-ink-muted" data-testid="charges-rates-date">
          Rates read on {{ breakdown.rates_read_on }}
        </p>
        </template>
      </section>
    </Modal>
  </div>
</template>
