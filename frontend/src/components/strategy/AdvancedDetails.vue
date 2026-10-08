<!-- Advanced Details (REQ-035 AC-5): per-leg Bid and Ask, drawn only when the outcome response carries
     `advanced_details` (the API sends it at the Advanced level only). Every value is the API's string as given. -->
<script setup>
defineProps({ rows: { type: Array, required: true } })
</script>

<template>
  <section class="mt-4 rounded border border-line bg-surface p-3" data-testid="advanced-details">
    <h2 class="text-sm font-medium">Advanced details</h2>
    <div class="overflow-x-auto">
      <table class="mt-2 min-w-full text-sm">
        <thead>
          <tr class="text-left text-xs text-ink-muted">
            <th class="pr-4 font-medium">Contract</th><th class="pr-4 font-medium">Bid</th><th class="pr-4 font-medium">Ask</th><th class="font-medium">Quote</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in rows" :key="r.instrument_id" :data-leg="r.instrument_id">
            <td class="pr-4" data-testid="adv-symbol">{{ r.symbol ?? r.instrument_id }}</td>
            <td class="pr-4" data-testid="adv-bid">{{ r.bid ?? '-' }}</td>
            <td class="pr-4" data-testid="adv-ask">{{ r.ask ?? '-' }}</td>
            <td data-testid="adv-health">{{ r.health ?? '-' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
