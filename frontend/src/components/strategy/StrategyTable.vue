<!-- The one strategy table (W-064; REQ-035 AC-1, AC-2, AC-3, AC-5). Draws the API's columns in the API's order; each
     cell is the API's own `display` text (rows are StrategyLegRow, scenario cells PnLCell). Left columns are sticky and
     the current-level column is highlighted (styles: src/assets/styles/strategy-table.css, copied/adapted from
     abhayla/algochanakya@bf9faf7 per ADR-047; the structure follows the legacy StrategyBuilderView table block). -->
<script setup>
import { computed } from 'vue'
import '@/assets/styles/strategy-table.css'
import StrategyLegRow from './StrategyLegRow.vue'
import { columnsToRender, isCurrentColumn, STICKY_COUNT } from '@/lib/strategyTable'

const props = defineProps({
  table: { type: Object, required: true },
  uxLevel: { type: String, default: 'standard' },
  maxProfit: { type: String, default: null },
  maxLoss: { type: String, default: null },
})
const cols = computed(() => columnsToRender(props.table.columns))
</script>

<template>
  <div class="strategy-table-wrapper">
    <div class="table-scroll" data-testid="strategy-table-scroll">
      <table class="strategy-table" data-testid="strategy-table">
        <thead>
          <tr>
            <th
              v-for="(c, i) in cols"
              :key="c.id"
              scope="col"
              :class="[i < STICKY_COUNT ? `sticky-col sticky-col-${i}` : '', isCurrentColumn(c) ? 'current-col' : '']"
              :data-col="c.id"
              :data-current="isCurrentColumn(c) ? 'true' : 'false'"
              data-testid="col-head"
            >
              {{ c.label }}<span v-for="m in c.markers" :key="m" class="ml-1 text-xs" data-testid="col-marker">{{ m }}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <StrategyLegRow v-for="row in table.rows" :key="row.row_id" :row="row" :columns="cols" :max-profit="maxProfit" :max-loss="maxLoss" />
        </tbody>
      </table>
    </div>
  </div>
</template>
