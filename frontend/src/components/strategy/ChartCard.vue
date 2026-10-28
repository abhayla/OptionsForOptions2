<!-- W-194 (ADR-193 UI-121..UI-127, ADR-194; UI study Region F + Revision 1; Sensibull S-012, S-014..S-017, S-122,
     S-123): the builder's tabbed chart card. Segmented tabs Payoff, P&L Table, Greeks, Strategy chart; the scenario
     switch and range (REQ-034 AC-6) sit in the card header because they drive both the graph and the full table.
       - Payoff: sub-tabs Graph (the PayoffChart) and Table (the scenario levels the reply sent, as rows; the CURRENT row
         highlighted; REQ-137's interval chooser and Show % are not built yet).
       - P&L Table (ADR-194): compact per-leg view first (Instrument | Planned entry | LTP | P&L | P&L %, the reply's own TOTAL
         row only when it sent one); a "Full table" switch on the same tab shows the REQ-035 StrategyTable unchanged,
         with the Bid/Ask Details block under it.
       - Greeks: per-leg Delta, Theta, Decay, Gamma, Vega, IV (REQ-145 AC-2 order) as the reply carries them, else the shared EmptyState.
       - Strategy chart: StrategyPriceChart (REQ-091; D-B40 / D-B41), asked only once the tab is open.
     Every value is a reply string (lib/chartCard.js); nothing is computed here (ADR-008). Panels stay mounted (v-show),
     so the chart draws once and switching tabs never re-asks the server. -->
<script setup>
import { computed, ref, useId } from 'vue'
import Card from '@/components/common/Card.vue'
import Tabs from '@/components/common/Tabs.vue'
import { panelId, tabId } from '@/components/common/tabIds.js'
import Chip from '@/components/common/Chip.vue'
import EmptyState from '@/components/states/EmptyState.vue'
import FigureHint from '@/components/common/FigureHint.vue'
import PayoffChart from './PayoffChart.vue'
import StrategyPriceChart from './StrategyPriceChart.vue'
import StrategyTable from './StrategyTable.vue'
import {
  COMPACT_COLUMNS, GREEK_COLUMNS, PAYOFF_STEPS, compactRows, greekModeHeading, greekRows, greekText, payoffLevelRows, payoffStepTable, signOf,
} from '@/lib/chartCard'

const props = defineProps({
  points: { type: Array, default: () => [] },
  spot: { type: String, default: '' },
  view: { type: String, default: '' }, // the reply's payoff.view (G-051: names the tooltip's curve)
  table: { type: Object, required: true },
  legs: { type: Array, default: null }, // the reply's legs: their lot_size turns a row's quantity into lots (D-B29)
  maxProfit: { type: String, default: null },
  maxLoss: { type: String, default: null },
  unavailableReason: { type: String, default: null }, // the reply's reason when the selected view has no curve
  // GC-UI b1 (REQ-083): the reply's both-curves, SD and OI blocks, its breakevens and its scenario grid, for the graph
  curves: { type: Object, default: null },
  breakevens: { type: Array, default: () => [] },
  sd: { type: Object, default: null },
  oi: { type: Object, default: null },
  zoom: { type: Object, default: null },
  // GC-UI b2 D-B24 / D-B25 (REQ-137 AC-1): the reply's `payoff_table` (rows at the server's step, both columns)
  payoffTable: { type: Object, default: null },
  // GC-UI step 5 (D-B40 / D-B41): the saved strategy's id, which the Strategy Chart tab asks the server about (null = unsaved)
  savedId: { type: Number, default: null },
})
// D-B10: the graph's Zoom asks the page for a new range; D-B24: the interval menu asks for a new payoff_step (the server
// makes the rows)
const emit = defineEmits(['zoom', 'payoff-step'])

const TABS = [
  { key: 'payoff', label: 'Payoff Graph' }, // GC-UI b1 D-B01 (Sensibull 012 tab labels)
  { key: 'pnl', label: 'P&L Table' },
  { key: 'greeks', label: 'Greeks' },
  { key: 'strategy-chart', label: 'Strategy Chart' },
]
const PAYOFF_VIEWS = [
  { key: 'graph', label: 'Payoff Graph' }, // D-B02 (Sensibull 012, 017)
  { key: 'table', label: 'Payoff Table' },
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

const showPct = ref(false) // D-B26 (REQ-137 AC-2): Show % adds the server's move_pct_display per row
const greekMode = ref('unit') // REQ-084 AC-8: one toggle, Per unit (default) or Per position
const compact = computed(() => compactRows(props.table, props.legs))
const greeks = computed(() => greekRows(props.table, props.legs))
const levels = computed(() => payoffLevelRows(props.table))
const stepTable = computed(() => payoffStepTable(props.payoffTable))
const pickStep = (e) => emit('payoff-step', e.target.value)
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
    </div>

    <!-- Payoff -->
    <div v-show="tab === 'payoff'" role="tabpanel" v-bind="link(VIEW, 'payoff')" class="p-4" data-testid="panel-payoff">
      <!-- GC-UI b1 D-B04 (Sensibull 012): ONE header row, sub-tabs left, controls right. Both curves show on the graph
           (D-B06), so the At Expiry / Estimated Now switch now picks only the table's scenario columns (REQ-034 AC-6
           keeps it, compact); the range is the graph's Zoom (D-B10). D-B33 / D-B38: Payoff tab only (inside its panel). -->
      <div class="mb-3 flex flex-wrap items-center justify-between gap-3" data-testid="payoff-header">
        <Tabs v-model="payoffView" :tabs="PAYOFF_VIEWS" label="Payoff views" :id-prefix="SUB" />
        <div data-testid="scenario-controls-slot"><slot name="controls" /></div>
      </div>
      <div v-show="payoffView === 'graph'" role="tabpanel" v-bind="link(SUB, 'graph')" data-testid="payoff-graph">
        <PayoffChart
          :points="points" :spot="spot" :view="view" :pnl-text="pnlByLevel" :unavailable-reason="unavailableReason"
          :curves="curves" :breakevens="breakevens" :sd="sd" :oi="oi" :zoom="zoom" @zoom="emit('zoom', $event)"
        />
      </div>
      <div v-show="payoffView === 'table'" role="tabpanel" v-bind="link(SUB, 'table')" data-testid="payoff-table">
        <!-- GC-UI b2 D-B24 / D-B25 / D-B26 (Sensibull 017): the server's payoff_table at the chosen interval, both columns
             (target date = now until B6/B7, and at expiry), the row nearest spot highlighted. Show % (D-B26) only prints the
             server's move_pct_display; the browser computes no percent (ADR-008). An older reply with no payoff_table
             falls back to the scenario-level rows below. -->
        <template v-if="stepTable">
          <div class="mb-2 flex items-center justify-end gap-4 text-sm text-ink-muted">
            <label v-if="stepTable.hasPct" class="flex items-center gap-2">
              <input v-model="showPct" type="checkbox" role="switch" :aria-checked="showPct ? 'true' : 'false'" data-testid="show-pct-switch" />
              Show %
            </label>
            <label class="flex items-center gap-2">
              Interval
              <select
                :value="stepTable.step ?? ''"
                class="rounded border border-line bg-surface px-2 py-0.5 text-ink"
                data-testid="payoff-step"
                @change="pickStep"
              >
                <option v-for="s in PAYOFF_STEPS" :key="s" :value="s">{{ s }}</option>
              </select>
            </label>
          </div>
          <table v-if="stepTable.available" class="w-full text-sm" data-testid="payoff-step-table">
            <thead>
              <tr class="border-b border-line text-left text-ink-muted">
                <th scope="col" class="py-2 font-medium" data-testid="payoff-step-head">Index level</th>
                <th v-for="c in stepTable.columns" :key="c.view" scope="col" class="py-2 text-right font-medium" data-testid="payoff-step-head">{{ c.label }}</th>
                <th v-if="showPct && stepTable.hasPct" scope="col" class="py-2 text-right font-medium" data-testid="payoff-step-pct-head">Move from spot</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="r in stepTable.rows"
                :key="r.level"
                :class="['border-b border-line', r.current ? 'bg-accent-soft font-semibold' : '']"
                :data-current="r.current ? 'true' : 'false'"
                data-testid="payoff-step-row"
              >
                <td class="py-1.5" data-testid="payoff-step-level">{{ r.levelText }}</td>
                <td
                  v-for="c in stepTable.columns"
                  :key="c.view"
                  :class="['py-1.5 text-right tabular-nums', toneOf(r.cells[c.view].value)]"
                  :data-field="c.view"
                >{{ r.cells[c.view].text }}</td>
                <td v-if="showPct && stepTable.hasPct" class="py-1.5 text-right tabular-nums" data-testid="payoff-step-pct">{{ r.pctText }}</td>
              </tr>
            </tbody>
          </table>
          <p v-if="stepTable.available && stepTable.notes.length" class="mt-2 text-xs text-ink-muted" data-testid="payoff-step-note">{{ stepTable.notes.join('; ') }}</p>
          <EmptyState
            v-if="!stepTable.available"
            :message="stepTable.reason ? `The payoff table is not available: ${stepTable.reason}` : 'The payoff table is not in this answer.'"
            data-testid="payoff-table-empty"
          />
        </template>
        <table v-else-if="levels" class="w-full text-sm">
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
                  <span data-testid="instrument-text">{{ r.text }}</span>
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
      <div v-if="greeks" class="mb-3 flex items-center justify-between gap-3">
        <span class="text-sm text-ink-muted" data-testid="greeks-mode-heading">{{ greekModeHeading(greeks, greekMode) }}</span>
        <div role="group" aria-label="Greeks units" class="inline-flex overflow-hidden rounded border border-line text-sm" data-testid="greeks-unit-toggle">
          <button
            type="button"
            :aria-pressed="greekMode === 'unit' ? 'true' : 'false'"
            :class="['px-3 py-1', greekMode === 'unit' ? 'bg-accent-soft font-semibold' : '']"
            data-testid="greeks-mode-unit"
            @click="greekMode = 'unit'"
          >Per unit</button>
          <button
            type="button"
            :aria-pressed="greekMode === 'position' ? 'true' : 'false'"
            :class="['px-3 py-1', greekMode === 'position' ? 'bg-accent-soft font-semibold' : '']"
            data-testid="greeks-mode-position"
            @click="greekMode = 'position'"
          >Per position</button>
        </div>
      </div>
      <table v-if="greeks" class="w-full text-sm" data-testid="greeks-table">
        <thead>
          <tr class="border-b border-line text-left text-ink-muted">
            <th scope="col" class="py-2 font-medium">Instrument</th>
            <th v-for="c in GREEK_COLUMNS" :key="c.id" scope="col" class="py-2 text-right font-medium" data-testid="greeks-head">{{ c.label }}<FigureHint v-if="c.id === 'decay'" id="decay" /></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in greeks" :key="r.rowId" :class="['border-b border-line', r.isTotal ? 'font-semibold' : '']" :data-row="r.rowId" data-testid="greeks-row">
            <td class="py-1.5">
              <span v-if="r.isTotal">Total</span>
              <span v-else class="inline-flex flex-wrap items-center gap-1.5">
                <Chip :kind="chipKind(r.side)" :label="chipLabel(r.side)" />
                <span data-testid="instrument-text">{{ r.text }}</span>
              </span>
            </td>
            <td v-for="c in GREEK_COLUMNS" :key="c.id" class="py-1.5 text-right tabular-nums" :data-field="c.id" data-testid="greeks-cell">{{ greekText(r.values[c.id], c.id, greekMode) }}</td>
          </tr>
        </tbody>
      </table>
      <EmptyState v-else message="Greeks for each leg are coming soon." data-testid="greeks-empty" />
    </div>

    <!-- Strategy chart (REQ-091 held for display rights) -->
    <div v-show="tab === 'strategy-chart'" role="tabpanel" v-bind="link(VIEW, 'strategy-chart')" class="p-4" data-testid="panel-strategy-chart">
      <StrategyPriceChart :strategy-id="savedId" :active="tab === 'strategy-chart'" />
    </div>
  </Card>
</template>
