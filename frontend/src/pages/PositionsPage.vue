<!-- Positions pages, part 1 (W-111; REQ-044 AC-3, ADR-109 (2), ADR-027, ADR-138 (2)). Reads GET /api/positions once on
     load and shows QUANTITIES grouped by strategy, with each strategy's link: no price, P&L, margin or Greek (part 2), no
     order button (every action routes back to the strategy). ADR-138 (2): "strategy groups, strategy P&L, the mismatch
     badge and "N outside lots - view on Kite"; no copy of Kite's full position list" - so only contracts linked to a
     strategy are rows; units no strategy owns are one count with a link to Kite. A refused read (no Zerodha session,
     failed read) shows the catalogue message, never an empty list. A PENDING contract (ADR-110: an open plan's orders are
     not final at Zerodha) shows the waiting line, Zerodha's quantity marked not yet confirmed, no own split, and the link
     to the strategy's Execute screen where Check is. Both Positions menu items show this same strategy-grouped page.
     New file, copy from: none. -->
<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import api, { NEUTRAL_PARTS } from '@/services/api'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import Tabs from '@/components/common/Tabs.vue'
import EmptyState from '@/components/states/EmptyState.vue'
import { panelId, tabId } from '@/components/common/tabIds.js'
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'
import { istTime } from '@/lib/displayFormat'
import { KITE_POSITIONS_URL } from '@/lib/execute'
import { useOrderPath } from '@/lib/orderPath'

const route = useRoute()
const POSITION_TABS = [{ key: 'positions', label: 'Positions' }, { key: 'paper', label: 'Paper' }]
const tab = ref(route.query.tab === 'paper' ? 'paper' : 'positions')
// GC-TP 4b (F-69): with at least one open paper strategy and no Zerodha position, the page opens on Paper. The count is the
// server's rows (open_count above 0), read once; a tab the user (or the URL) chose is never moved.
const paperOpen = ref(0)
let chosen = route.query.tab !== undefined
let moving = false
watch(tab, () => { if (!moving) chosen = true }, { flush: 'sync' })
const paperOpenText = (n) => `${n} paper ${n === 1 ? 'strategy is' : 'strategies are'} open - see Paper.`
const NO_ZERODHA = 'No open Zerodha positions.'
const noReal = () => !!result.value && !result.value.strategies.length && !result.value.has_outside
// W-121 (REQ-073 AC-6, ADR-165): a link to the strategy's Execute screen is absent (not disabled) unless the server said
// the order path is on; off, the strategy is named in plain text.
const orderPathOn = useOrderPath()
const view = route.meta.view === 'linked' ? 'linked' : 'current'
const loading = ref(true)
const result = ref(null)
const errorParts = ref(null)
// The page's own words, one home each (ADR-110 quotes the first two verbatim).
const WAITING = 'Order placed - waiting for Check with Zerodha'
const UNCONFIRMED = 'not yet confirmed'
const BLOCKED = 'blocked until its position matches Zerodha'
// A pending contract's other holders are blocked too (ADR-110 + Q224); the answer names them in blocked_strategy_ids.
const HOLDERS = 'Every other strategy holding units on this contract is blocked too (listed above).'
const NO_ROW = 'No confirmed position of this strategy to show yet.'
const VIEW_ON_KITE = 'view on Kite'
const outsideText = (lots) => (lots === null ? 'Positions outside your strategies' : `${lots} outside ${lots === 1 ? 'lot' : 'lots'}`)

async function readPaperOpen() {
  try {
    const list = (await api.get('/paper/strategies')).data?.strategies
    paperOpen.value = Array.isArray(list) ? list.filter((x) => x && x.state !== 'EXITED' && x.open_count > 0).length : 0
  } catch {
    paperOpen.value = 0 // unreadable: the page stays as it was
  }
}
onMounted(async () => {
  await Promise.all([
    (async () => {
      try {
        result.value = (await api.get('/positions')).data
      } catch (e) {
        errorParts.value = e?.parts ?? NEUTRAL_PARTS
      } finally {
        loading.value = false
      }
    })(),
    readPaperOpen(),
  ])
  if (!chosen && paperOpen.value > 0 && noReal()) {
    moving = true
    tab.value = 'paper'
    moving = false
  }
})
</script>

<template>
  <!-- Owner 2026-10-30 (Sensibull 050 / 090): the shared header, a summary bar (read time left, outside lots right), then one
       card per strategy with its contracts in an aligned table (Contract | Your units | Zerodha | Status). -->
  <section data-testid="positions-page" :data-view="view">
    <PageHeader :parent="route.meta.parent ?? ''" :title="route.meta.title" />
    <!-- GC-BP step 6 (ADR-201 (2)): "Positions" = this page as it was; "Paper" = the shared paper list, which loads by
         itself and is never held up by the Zerodha read. Paper figures never appear in the Positions tab. -->
    <Tabs v-model="tab" :tabs="POSITION_TABS" label="Positions or paper trades" id-prefix="positions" />
    <div :id="panelId('positions', tab)" role="tabpanel" :aria-labelledby="tabId('positions', tab)" class="mt-4">
    <PaperStrategies v-if="tab === 'paper'" data-testid="positions-paper" />
    <template v-else>
    <p v-if="loading" class="text-sm text-ink-muted" data-testid="positions-loading">Reading your positions from Zerodha.</p>
    <ErrorMessage v-else-if="errorParts" :parts="errorParts" compact prefix="positions-error" />
    <div v-else-if="result" class="grid gap-4 text-sm">
      <div class="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 rounded-lg border border-line bg-surface px-4 py-3">
        <p class="text-ink-muted">Read from Zerodha at <span class="num font-medium text-ink" data-testid="positions-read-at">{{ istTime(result.read_at) }}</span>.</p>
        <p v-if="result.has_outside" data-testid="positions-outside">
          <span data-testid="positions-outside-count">{{ outsideText(result.outside_lots) }}</span> -
          <a :href="KITE_POSITIONS_URL" target="_blank" rel="noopener noreferrer" class="link" data-testid="positions-outside-kite">{{ VIEW_ON_KITE }}</a>
        </p>
      </div>
      <div v-if="result.blocked" class="rounded-lg border border-line bg-surface px-4 py-3" data-testid="positions-blocked">
        <p class="font-medium text-warn">A strategy is {{ BLOCKED }}.</p>
        <ul class="mt-1">
          <li v-for="id in result.blocked_strategy_ids" :key="id" data-testid="positions-blocked-strategy" :data-strategy="id">
            <RouterLink v-if="orderPathOn" :to="`/strategy/${id}/execute`" class="link" data-testid="positions-blocked-link">Strategy {{ id }}</RouterLink><span v-else>Strategy {{ id }}</span> ({{ BLOCKED }})
          </li>
        </ul>
      </div>
      <!-- GC-UI D-C40 (Sensibull 050): the shared empty state; the title is new text (owner read), the line is ours as before. -->
      <div v-if="!result.strategies.length && !result.has_outside" data-testid="positions-empty">
        <p v-if="paperOpen > 0" data-testid="positions-paper-open">{{ NO_ZERODHA }} {{ paperOpenText(paperOpen) }}</p>
        <EmptyState v-else title="No open positions" message="Zerodha shows no open positions, and none of your strategies holds any." />
      </div>
      <p v-else-if="!result.strategies.length" class="text-ink-muted" data-testid="positions-no-strategy">
        None of your strategies holds a position.
      </p>
      <section v-for="g in result.strategies" :key="g.strategy_id" class="overflow-hidden rounded-lg border border-line bg-surface" data-testid="position-group" :data-strategy="g.strategy_id">
        <h2 class="flex h-11 items-center gap-2 border-b border-line px-4 text-sm font-semibold">
          <RouterLink v-if="orderPathOn" :to="`/strategy/${g.strategy_id}/execute`" class="link" data-testid="position-strategy-link">Strategy {{ g.strategy_id }}</RouterLink><span v-else data-testid="position-strategy-name">Strategy {{ g.strategy_id }}</span>
          <span v-if="g.blocked" class="font-normal text-warn" data-testid="position-mismatch-badge">({{ BLOCKED }})</span>
        </h2>
        <p v-if="!g.contracts.length" class="px-4 py-3 text-ink-muted" data-testid="position-group-empty">{{ NO_ROW }}</p>
        <table v-else class="ui-table">
          <thead>
            <tr><th>Contract</th><th class="ui-num">Your units</th><th class="ui-num">Zerodha units</th><th>Status</th></tr>
          </thead>
          <tbody>
            <tr v-for="c in g.contracts" :key="c.tradingsymbol" data-testid="position-row" :data-symbol="c.tradingsymbol">
              <td class="font-medium">{{ c.tradingsymbol }}</td>
              <template v-if="c.pending">
                <td class="ui-num"><span data-testid="position-waiting">{{ WAITING }}</span> (plan <span data-testid="position-pending-plans">{{ c.pending_plans.join(', ') }}</span>)</td>
                <td class="ui-num"><span data-testid="position-zerodha">{{ c.zerodha_units }}</span></td>
                <td class="text-ink-muted"><span data-testid="position-unconfirmed">{{ UNCONFIRMED }}</span>. <span data-testid="position-pending-holders">{{ HOLDERS }}</span></td>
              </template>
              <template v-else>
                <td class="ui-num"><span data-testid="position-own-units">{{ c.units }}</span></td>
                <td class="ui-num"><span data-testid="position-zerodha">{{ c.zerodha_units }}</span></td>
                <td></td>
              </template>
            </tr>
          </tbody>
        </table>
      </section>
    </div>
    </template>
    </div>
  </section>
</template>
