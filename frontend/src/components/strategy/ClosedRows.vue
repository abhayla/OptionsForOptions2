<!-- D-10 / D-63 (ADR-207 (2)): the paper reply's closed lifecycles, one rendering for the Net Positions Closed section and the P&L
     Table tab: contract, lots, entry, exit and each leg's own booked P&L (before charges), all as the reply sent them; no sum here.
     `prefix` names the test ids (closed-row, closed-entry ...), so two places on one page do not share them. -->
<template>
  <div v-if="rows.length">
    <p class="mt-2 text-xs text-ink-muted" :data-testid="`${prefix}-basis`">Closed: booked P&amp;L (before charges)</p>
    <table class="w-full text-xs text-ink-muted" :data-testid="`${prefix}-list`">
      <thead><tr><th class="text-left font-normal">Contract</th><th class="font-normal">Lots</th><th class="font-normal">Entry</th><th class="font-normal">Exit</th><th class="font-normal">Booked</th></tr></thead>
      <tbody>
        <tr v-for="c in rows" :key="c.opened_at + c.contract_id" class="border-t border-line" :data-testid="`${prefix}-row`">
          <td class="py-1 pr-2" :data-testid="`${prefix}-contract`"><span class="mr-1 font-semibold">{{ c.side === 'BUY' ? 'B' : 'S' }}</span>{{ c.contract_text }}</td>
          <td class="num text-center" :data-testid="`${prefix}-lots`">{{ c.lots ?? c.quantity }}</td>
          <td class="num text-right" :data-testid="`${prefix}-entry`">{{ c.average_entry_text }}</td>
          <td class="num text-right" :data-testid="`${prefix}-exit`">{{ c.average_exit_text }}<span v-if="c.reason_text" class="block text-[11px] font-normal text-ink-muted" :data-testid="`${prefix}-reason`">{{ c.reason_text }}</span></td>
          <td class="num text-right" :data-testid="`${prefix}-booked`">{{ c.booked_text }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
defineProps({
  rows: { type: Array, default: () => [] },
  prefix: { type: String, default: 'closed' },
})
</script>
