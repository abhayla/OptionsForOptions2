<!-- The Execute reply's `cost` block (W-104 on W-102; REQ-056 AC-8, ADR-097, ADR-008). Every value is the string the
     API gave: no amount is parsed, added or rounded here. Charges absent -> the server's own note is shown instead of a
     number. Funds and margin are Zerodha's figures (the planning estimate is not shown on this screen). New file. -->
<script setup>
import { istTime } from '@/lib/displayFormat'
import { NOT_READ } from '@/lib/execute'

defineProps({ cost: { type: Object, required: true } })
</script>

<template>
  <dl class="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm" data-testid="execute-cost">
    <dt>Net premium (minus = paid)</dt><dd data-testid="cost-net-premium">{{ cost.net_premium }}</dd>
    <dt>Charges</dt>
    <dd v-if="cost.charges != null" data-testid="cost-charges">{{ cost.charges }}</dd>
    <dd v-else data-testid="cost-charges-note">{{ cost.charges_note }}</dd>
    <dt>Funds available (Zerodha)</dt><dd data-testid="cost-funds">{{ cost.funds_available ?? NOT_READ }}</dd>
    <dt>Margin required (Zerodha)</dt><dd data-testid="cost-margin">{{ cost.margin_required ?? NOT_READ }}</dd>
    <dt>Figures read at</dt><dd data-testid="cost-read-at">{{ istTime(cost.figures_read_at) }}</dd>
  </dl>
</template>
