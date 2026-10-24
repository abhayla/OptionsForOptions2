<!-- Details (REQ-035 AC-5): per-leg Bid and Ask, drawn whenever the outcome response carries
     `leg_quotes` (the API sends it for everyone, ADR-168). Every value is the API's string as given.
     REQ-034 AC-7: a native <details>, closed by default; the rows stay in the DOM. -->
<script setup>
import { healthSentence, missingReason } from '@/lib/dataHealthText'

defineProps({ rows: { type: Array, required: true }, nameOf: { type: Function, required: true } })
</script>

<template>
  <details class="mt-4 rounded border border-line bg-surface p-3" data-testid="advanced-details">
    <summary class="cursor-pointer text-sm font-medium">Details: bid and ask per leg</summary>
    <div class="overflow-x-auto" data-h-scroll>
      <table class="mt-2 min-w-full text-sm">
        <thead>
          <tr class="text-left text-xs text-ink-muted">
            <th class="pr-4 font-medium">Contract</th><th class="pr-4 font-medium">Bid</th><th class="pr-4 font-medium">Ask</th><th class="font-medium">Quote</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in rows" :key="r.instrument_id" :data-leg="r.instrument_id">
            <td class="pr-4" data-testid="adv-symbol">{{ nameOf(r) }}</td>
            <td class="pr-4" data-testid="adv-bid">{{ r.bid ?? missingReason(r, 'bid') }}</td>
            <td class="pr-4" data-testid="adv-ask">{{ r.ask ?? missingReason(r, 'ask') }}</td>
            <td data-testid="adv-health">{{ r.health ? (healthSentence(r.health) ?? 'Available') : healthSentence(null) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </details>
</template>
