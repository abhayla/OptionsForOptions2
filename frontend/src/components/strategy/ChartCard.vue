<!-- W-194 (ADR-193 UI-121..UI-127, ADR-194; UI study Region F + Revision 1; Sensibull S-012, S-014..S-017, S-122,
     S-123): the builder's tabbed chart card. Segmented tabs Payoff, P&L Table, Greeks, Strategy chart; the scenario
     switch and range (REQ-034 AC-6) sit in the card header because they drive both the graph and the full table.
       - Payoff: sub-tabs Graph (the PayoffChart) and Table (the scenario levels the reply sent, as rows; the CURRENT row
         highlighted; REQ-137's interval chooser and Show % are not built yet).
       - P&L Table (ADR-194): compact per-leg view first (Instrument | Entry | LTP | P&L | P&L %, the reply's own TOTAL
         row only when it sent one); a "Full table" switch on the same tab shows the REQ-035 StrategyTable unchanged,
         with the Bid/Ask Details block under it.
       - Greeks: per-leg Delta, Gamma, Theta, Vega, IV as the reply carries them, else the shared EmptyState.
       - Strategy chart: EmptyState (REQ-091 held for display rights).
     Every value is a reply string (lib/chartCard.js); nothing is computed here (ADR-008). Panels stay mounted (v-show),
     so the chart draws once and switching tabs never re-asks the server. -->
<script setup>
import { computed, useId } from 'vue'
import Card from '@/components/common/Card.vue'
import Tabs from '@/components/common/Tabs.vue'
import { panelId, tabId } from '@/components/common/tabIds.js'
import Chip from '@/components/common/Chip.vue'
import EmptyState from '@/components/states/EmptyState.vue'
import PayoffChart from './PayoffChart.vue'
import StrategyTable from './StrategyTable.vue'
import { strikeLabel } from '@/lib/displayFormat'
import { COMPACT_COLUMNS, GREEK_COLUMNS, compactRows, greekRows, payoffLevelRows, signOf } from '@/lib/chartCard'

const props = defineProps({
  points: { type: Array, default: () => [] },
  spot: { type: String, default: '' },
  view: { type: String, default: '' }, // the reply's payoff.view (G-051: names the tooltip's curve)
  table: { type: Object, required: true },
  maxProfit: { type: String, default: null },
  maxLoss: { type: String, default: null },
})

const TABS = [
  { key: 'payoff', label: 'Payoff' },
  { key: 'pnl', label: 'P&L Table' },
  { key: 'greeks', label: 'Greeks' },
  { key: 'strategy-chart', label: 'Strategy chart' },
]
const PAYOFF_VIEWS = [
  { key: 'graph', label: 'Graph' },
  { key: 'table', label: 'Table' },
]
// The view choice is a model the page owns, so a recompute (which remounts the numbers block) keeps the user's tab.
// Review 6: the prefixes that link the view tabs and the Payoff sub-tabs to their panels
const uid = useId()
const VIEW = `chart-${uid}`
const SUB = `payoff-${uid}`
const link = (prefix, key) => ({ id: panelId(prefix, key), 'aria-labelledby': tabId(prefix, key) })
const tab = defineModel('tab', { type: String, default: 'payoff' })
const payoffView = defineModel('payoffView', { type: String, default: 'graph' })
const fullTable = defineModel('fullTable', { type: Boolean, default: false }) // ADR-194 (1): the compact view is the default

const compact = computed(() => compactRows(props.table))
const greeks = computed(() => greekRows(props.table))
const levels = computed(() => payoffLevelRows(props.table))
// G-051: the chart's tooltip shows, per level, the same display string as the Table row (one reply feeds both).
const pnlByLevel = computed(() => (levels.value ? Object.fromEntries(levels.value.map((r) => [r.id, r.pnl])) : null))

const chipKind = (side) => (side === 'BUY' ? 'buy' : side === 'SELL' ? 'sell' : 'state')
const chipLabel = (side) => (side === 'BUY' ? 'B' : side === 'SELL' ? 'S' : side ?? '')
const toneOf = (v) => ({ profit: 'text-profit', loss: 'text-loss' })[signOf(v)] ?? ''
</script>

<template>
  <Card class="mt-4" flush data-testid="chart-card">
    <div class="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3">
      <Tabs v-model="tab" :tabs="TABS" variant="segmented" label="Chart views" :id-prefix="VIEW" />
      <slot name="controls" />
    </div>

    <!-- Payoff -->
    <div v-show="tab === 'payoff'" role="tabpanel" v-bind="link(VIEW, 'payoff')" class="p-4" data-testid="panel-payoff">
      <Tabs v-model="payoffView" :tabs="PAYOFF_VIEWS" label="Payoff views" class="mb-3" :id-prefix="SUB" />
      <div v-show="payoffView === 'graph'" role="tabpanel" v-bind="link(SUB, 'graph')" data-testid="payoff-graph">
        <PayoffChart :points="points" :spot="spot" :view="view" :pnl-text="pnlByLevel" />
      </div>
      <div v-show="payoffView === 'table'" role="tabpanel" v-bind="link(SUB, 'table')" data-testid="payoff-table">
        <table v-if="levels" class="w-full text-sm">
          <thead>
            <tr class="border-b border-line text-left text-ink-muted">
              <th scope="col" class="py-2 font-medium">{{ table.scenario_heading?.[0] ?? 'Index level' }}</th>
              <th scope="col" class="py-2 text-right font-medium">{{ table.scenario_heading?.[1] ?? 'P&L' }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="r in levels"
              :key="r.id"
              :class="['border-b border-line', r.current ? 'bg-accent-soft font-semibold' : '']"
              :data-current="r.current ? 'true' : 'false'"
              data-testid="payoff-table-row"
            >
              <td class="py-1.5" data-testid="payoff-table-level">{{ r.level }}</td>
              <td :class="['py-1.5 text-right tabular-nums', toneOf(r.value)]" data-testid="payoff-table-pnl">{{ r.pnl }}</td>
            </tr>
          </tbody>
        </table>
        <EmptyState v-else message="The payoff at each index level is not in this answer." data-testid="payoff-table-empty" />
      </div>
    </div>

    <!-- P&L Table (ADR-194) -->
    <div v-show="tab === 'pnl'" role="tabpanel" v-bind="link(VIEW, 'pnl')" class="p-4" data-testid="panel-pnl">
      <div class="mb-3 flex items-center justify-end">
        <label class="flex items-center gap-2 text-sm text-ink-muted">
          <input v-model="fullTable" type="checkbox" role="switch" :aria-checked="fullTable ? 'true' : 'false'" data-testid="full-table-switch" />
          Full table
        </label>
      </div>
      <div v-show="!fullTable" data-testid="compact-view">
        <table v-if="compact" class="w-full text-sm" data-testid="compact-table">
          <thead>
            <tr class="border-b border-line text-left text-ink-muted">
              <th scope="col" class="py-2 font-medium">Instrument</th>
              <th v-for="c in COMPACT_COLUMNS" :key="c.id" scope="col" class="py-2 text-right font-medium" data-testid="compact-head">{{ c.label }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in compact" :key="r.rowId" :class="['border-b border-line', r.isTotal ? 'font-semibold' : '']" :data-row="r.rowId" data-testid="compact-row">
              <td class="py-1.5">
                <span v-if="r.isTotal">Total</span>
                <span v-else class="inline-flex flex-wrap items-center gap-1.5">
                  <Chip :kind="chipKind(r.side)" :label="chipLabel(r.side)" />
                  <span>{{ r.parts.quantity }}</span>
                  <span>{{ r.parts.expiry }}</span>
                  <span>{{ strikeLabel(r.parts.strike) }}</span>
                  <Chip kind="opt" :label="r.parts.instrument" />
                </span>
              </td>
              <td
                v-for="c in COMPACT_COLUMNS"
                :key="c.id"
                :class="['py-1.5 text-right tabular-nums', c.id === 'unrealized_pnl' || c.id === 'pnl_percent' ? toneOf(r.values[c.id].value) : '']"
                :data-field="c.id"
                data-testid="compact-cell"
              >{{ r.values[c.id].display }}</td>
            </tr>
          </tbody>
        </table>
        <EmptyState v-else message="The per-leg P&L is not in this answer. Open the full table to see every column." data-testid="compact-empty" />
      </div>
      <div v-show="fullTable" data-testid="full-view">
        <StrategyTable :table="table" :max-profit="maxProfit" :max-loss="maxLoss" />
        <slot name="details" />
      </div>
    </div>

    <!-- Greeks -->
    <div v-show="tab === 'greeks'" role="tabpanel" v-bind="link(VIEW, 'greeks')" class="p-4" data-testid="panel-greeks">
      <table v-if="greeks" class="w-full text-sm" data-testid="greeks-table">
        <thead>
          <tr class="border-b border-line text-left text-ink-muted">
            <th scope="col" class="py-2 font-medium">Instrument</th>
            <th v-for="c in GREEK_COLUMNS" :key="c.id" scope="col" class="py-2 text-right font-medium" data-testid="greeks-head">{{ c.label }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in greeks" :key="r.rowId" :class="['border-b border-line', r.isTotal ? 'font-semibold' : '']" :data-row="r.rowId" data-testid="greeks-row">
            <td class="py-1.5">
              <span v-if="r.isTotal">Total</span>
              <span v-else class="inline-flex flex-wrap items-center gap-1.5">
                <Chip :kind="chipKind(r.side)" :label="chipLabel(r.side)" />
                <span>{{ strikeLabel(r.parts.strike) }}</span>
                <Chip kind="opt" :label="r.parts.instrument" />
              </span>
            </td>
            <td v-for="c in GREEK_COLUMNS" :key="c.id" class="py-1.5 text-right tabular-nums" :data-field="c.id" data-testid="greeks-cell">{{ r.values[c.id].display }}</td>
          </tr>
        </tbody>
      </table>
      <EmptyState v-else message="Greeks for each leg are coming soon." data-testid="greeks-empty" />
    </div>

    <!-- Strategy chart (REQ-091 held for display rights) -->
    <div v-show="tab === 'strategy-chart'" role="tabpanel" v-bind="link(VIEW, 'strategy-chart')" class="p-4" data-testid="panel-strategy-chart">
      <EmptyState message="The strategy chart is coming soon." data-testid="strategy-chart-empty" />
    </div>
  </Card>
</template>
