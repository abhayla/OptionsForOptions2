<!-- Adapted from abhayla/algochanakya@bf9faf7:frontend/src/components/strategy/StrategyLegRow.vue (ADR-047).
     Changed: a read-only row drawn from the outcome API's row and columns, in the API's order. Removed: the editable
     selects and inputs (no leg picker in this slice), the checkbox, and the client-side exit P&L at legacy :229
     ((cmp - entry) * qty * multiplier), formatPnL, getPnLAtSpot and the spot-proximity highlight (the API flags the
     current column). Scenario cells use PnLCell; Action and Instrument keep the legacy BUY/SELL and CE/PE tags. -->
<template>
  <tr :class="['leg-row', rowClass]" :data-row="row.row_id">
    <template v-for="(c, i) in columns" :key="c.id">
      <PnLCell
        v-if="c.is_scenario_level"
        :class="[stickyClass(i), isCurrentColumn(c) ? 'current-col' : '']"
        :display="cellText(row, c)"
        :value="row.cells[c.id]?.value ?? null"
        :max-profit="maxProfit"
        :max-loss="maxLoss"
        :is-total="row.row_id === 'TOTAL'"
        :data-col="c.id"
        :data-row="row.row_id"
        data-testid="cell"
      />
      <td
        v-else
        :class="['px-2 py-1', stickyClass(i), isCurrentColumn(c) ? 'current-col' : '']"
        :data-col="c.id"
        :data-row="row.row_id"
        data-testid="cell"
      >
        <span v-if="c.id === 'action' || c.id === 'instrument'" :class="['tag', tagClass(c.id)]">{{ cellText(row, c) }}</span>
        <template v-else>{{ cellText(row, c) }}</template>
      </td>
    </template>
  </tr>
</template>

<script setup>
import { computed } from 'vue'
import PnLCell from './PnLCell.vue'
import { cellText, isCurrentColumn, STICKY_COUNT } from '@/lib/strategyTable'

const props = defineProps({
  row: { type: Object, required: true },
  columns: { type: Array, required: true },
  maxProfit: { type: String, default: null },
  maxLoss: { type: String, default: null },
})

const side = computed(() => props.row.cells.action?.value)
const rowClass = computed(() => {
  if (props.row.row_id === 'TOTAL') return 'total-row'
  return side.value === 'BUY' ? 'leg-buy' : side.value === 'SELL' ? 'leg-sell' : ''
})

const stickyClass = (i) => (i < STICKY_COUNT ? `sticky-col sticky-col-${i}` : '')
const tagClass = (id) => {
  const v = props.row.cells[id]?.value
  return { BUY: 'tag-buy', SELL: 'tag-sell', CE: 'tag-ce', PE: 'tag-pe' }[v] || ''
}
</script>
