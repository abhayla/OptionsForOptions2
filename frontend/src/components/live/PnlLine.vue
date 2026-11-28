<!-- D-41 (ADR-320 point 5): one trade's P&L line on a Live card or a My Strategies row. The cell is lib/paperPnl's: the Positions
     page's figure, as the server sent it. States: value (figure + its label), paused (a dash and "prices not live"), failed (a dash
     and the sentence that it is not available), none / loading (nothing is drawn). Never a "Loading" text. -->
<script setup>
defineProps({ cell: { type: Object, default: null }, testid: { type: String, required: true } })
</script>

<template>
  <p v-if="cell && ['value', 'paused', 'failed'].includes(cell.kind)" class="text-sm" :data-testid="testid" :data-pnl-kind="cell.kind">
    P&amp;L <span class="font-semibold tabular-nums" :data-testid="`${testid}-figure`">{{ cell.text }}</span>
    <template v-if="cell.label">{{ ' ' }}{{ cell.label }}</template>
    <span v-if="cell.note" class="text-xs text-ink-muted" :data-testid="`${testid}-note`"> · {{ cell.note }}</span>
  </p>
</template>
