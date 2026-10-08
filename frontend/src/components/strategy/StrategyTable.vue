<!-- The one strategy table (W-064; REQ-035 AC-1, AC-2, AC-3, AC-5). Draws the API's columns in the API's order; each
     cell is the API's own `display` text. Left columns are sticky; the current-level column is highlighted.
     New file (the legacy StrategyLegRow computes P&L at :229, so it is not copied; ADR-008). -->
<script setup>
import { computed } from 'vue'
import { columnsToRender, isCurrentColumn, cellText, STICKY_COUNT } from '@/lib/strategyTable'

const props = defineProps({
  table: { type: Object, required: true },
  uxLevel: { type: String, default: 'standard' },
})
const cols = computed(() => columnsToRender(props.table.columns, props.uxLevel))
</script>

<template>
  <div class="overflow-x-auto rounded border border-line bg-surface" data-testid="strategy-table-scroll">
    <table class="strategy-table min-w-full border-collapse text-sm" data-testid="strategy-table">
      <thead>
        <tr>
          <th
            v-for="(c, i) in cols"
            :key="c.id"
            scope="col"
            :class="['px-2 py-1 text-left font-medium', i < STICKY_COUNT ? `sticky-col sticky-col-${i}` : '', isCurrentColumn(c) ? 'current-col' : '']"
            :data-col="c.id"
            :data-current="isCurrentColumn(c) ? 'true' : 'false'"
            data-testid="col-head"
          >
            {{ c.label }}<span v-for="m in c.markers" :key="m" class="ml-1 text-xs text-ink-muted" data-testid="col-marker">{{ m }}</span>
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in table.rows" :key="row.row_id" :data-row="row.row_id" :class="row.row_id === 'TOTAL' ? 'font-semibold' : ''">
          <td
            v-for="(c, i) in cols"
            :key="c.id"
            :class="['px-2 py-1 whitespace-nowrap', i < STICKY_COUNT ? `sticky-col sticky-col-${i}` : '', isCurrentColumn(c) ? 'current-col' : '']"
            :data-col="c.id"
            :data-row="row.row_id"
            data-testid="cell"
          >
            {{ cellText(row, c) }}
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.strategy-table th,
.strategy-table td {
  border-bottom: 1px solid var(--color-line);
  background: var(--color-surface);
}
.sticky-col {
  position: sticky;
  z-index: 1;
  min-width: 4.5rem;
  max-width: 4.5rem;
}
.sticky-col-0 { left: 0; }
.sticky-col-1 { left: 4.5rem; }
.sticky-col-2 { left: 9rem; }
.current-col {
  background: var(--color-accent-soft) !important;
  box-shadow: inset 2px 0 0 var(--color-accent), inset -2px 0 0 var(--color-accent);
}
</style>
