<!-- REQ-081 AC-2 / ADR-167 (2): the round-trip charges by component, opened from a 'Charges' action on the Builder summary.
     Screen 022 lists them (Brokerage, STT, Exchange txn, GST, Stamp, SEBI, Total). Rewritten from the W-127 component: it is now
     closed by default and opens by button or keyboard. Every figure, the rates date and the 'estimate' label are the server's
     strings shown as sent; the browser adds nothing up (ADR-008). The curves and the table are before these charges. -->
<script setup>
import { ref } from "vue";
import FigureHint from "@/components/common/FigureHint.vue";

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
    <section
      v-if="open"
      id="charges-panel"
      class="mt-2 rounded border border-line bg-surface p-3 min-w-0 break-words"
      data-testid="charges-panel"
    >
      <h3 class="text-sm font-medium" data-testid="charges-label">
        Charges and taxes ({{ breakdown.label }})
      </h3>
      <p class="text-xs text-ink-muted">
        Entering and leaving every leg at its planned price. The payoff curves
        and the table are before these charges.
      </p>
      <dl class="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
        <div
          v-for="row in ROWS"
          :key="row.key"
          :data-testid="'charges-' + row.key"
        >
          <dt class="text-xs text-ink-muted">{{ row.label }}</dt>
          <dd>Rs {{ breakdown[row.key] }}</dd>
        </div>
      </dl>
      <p class="mt-2 text-sm font-medium" data-testid="charges-total">
        Total Rs {{ breakdown.total }}
      </p>
      <p class="text-xs text-ink-muted" data-testid="charges-rates-date">
        Rates read on {{ breakdown.rates_read_on }}
      </p>
    </section>
  </div>
</template>
