<!-- Charges and taxes, shown ONCE (W-127; ADR-167). Follows Sensibull screen 022 (Charges: Total = Brokerage + STT + Exchange
     txn + GST + Stamp + SEBI). Every curve and scenario value on the page is BEFORE these; the figures are the server's
     strings from the ADR-082 (1) rate table, shown as sent (no browser arithmetic). -->
<template>
  <section class="rounded border border-line bg-surface p-3" data-testid="charges-breakdown">
    <h3 class="text-sm font-medium">Charges and taxes (estimate)</h3>
    <p class="text-xs text-ink-muted">
      Entering and leaving every leg at its planned price. The payoff curves and the table above are before these charges.
    </p>
    <dl class="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-3">
      <div v-for="row in ROWS" :key="row.key" :data-testid="'charges-' + row.key">
        <dt class="text-xs text-ink-muted">{{ row.label }}</dt>
        <dd>{{ breakdown[row.key] }}</dd>
      </div>
    </dl>
    <p class="mt-2 text-sm font-medium" data-testid="charges-total">Total {{ breakdown.total }}</p>
  </section>
</template>

<script setup>
defineProps({
  breakdown: { type: Object, required: true }, // charges_breakdown as sent
})
const ROWS = [
  { key: 'brokerage', label: 'Brokerage' },
  { key: 'stt', label: 'STT' },
  { key: 'exchange_transaction', label: 'Exchange transaction charges' },
  { key: 'gst', label: 'GST' },
  { key: 'stamp', label: 'Stamp duty' },
  { key: 'sebi', label: 'SEBI charges' },
]
</script>
