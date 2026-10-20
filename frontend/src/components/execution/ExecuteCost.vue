<!-- The Execute reply's `cost` and `review` blocks (W-104 on W-102; REQ-056 AC-5/AC-8, ADR-097, ADR-008; EXECUTE-REVIEW S5).
     Reading order (design note A4): margin (required vs available, labelled an estimate), charges, then max loss / max
     profit, then the net premium. Every value is the string the API gave: no amount is parsed, added or rounded here.
     Charges absent -> the server's own note is shown instead of a number. Funds and margin are Zerodha's figures. -->
<script setup>
import { istTime, maxLine } from '@/lib/displayFormat'
import { MARGIN_ESTIMATE_LABEL, NOT_READ } from '@/lib/execute'

defineProps({ cost: { type: Object, required: true }, review: { type: Object, default: null } })
</script>

<template>
  <div class="mt-2 text-sm" data-testid="execute-cost">
    <h2 class="font-medium">Margin</h2>
    <p class="text-xs" data-testid="margin-label">{{ MARGIN_ESTIMATE_LABEL }}</p>
    <dl class="grid grid-cols-2 gap-x-4 gap-y-1">
      <dt>Required</dt><dd data-testid="cost-margin">{{ cost.margin_required ?? NOT_READ }}</dd>
      <dt>Available</dt><dd data-testid="cost-funds">{{ cost.funds_available ?? NOT_READ }}</dd>
      <dt>Charges (estimate)</dt>
      <dd v-if="cost.charges != null" data-testid="cost-charges">{{ cost.charges }}</dd>
      <dd v-else data-testid="cost-charges-note">{{ cost.charges_note }}</dd>
      <dt>Figures read at</dt><dd data-testid="cost-read-at">{{ istTime(cost.figures_read_at) }}</dd>
    </dl>
    <dl class="mt-2 grid grid-cols-2 gap-x-4 gap-y-1" data-testid="execute-risk">
      <dt>Max loss</dt><dd data-testid="execute-max-loss">{{ maxLine(review, 'loss') }}</dd>
      <dt>Max profit</dt><dd data-testid="execute-max-profit">{{ maxLine(review, 'profit') }}</dd>
      <dt>Net premium (minus = paid)</dt><dd data-testid="cost-net-premium">{{ cost.net_premium }}</dd>
    </dl>
  </div>
</template>
