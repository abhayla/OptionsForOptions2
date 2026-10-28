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
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import api, { NEUTRAL_PARTS } from '@/services/api'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import Tabs from '@/components/common/Tabs.vue'
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'
import { istTime } from '@/lib/displayFormat'
import { KITE_POSITIONS_URL } from '@/lib/execute'
import { useOrderPath } from '@/lib/orderPath'

const route = useRoute()
const POSITION_TABS = [{ key: 'positions', label: 'Positions' }, { key: 'paper', label: 'Paper' }]
const tab = ref(route.query.tab === 'paper' ? 'paper' : 'positions')
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

onMounted(async () => {
  try {
    result.value = (await api.get('/positions')).data
  } catch (e) {
    errorParts.value = e?.parts ?? NEUTRAL_PARTS
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <section class="p-4" data-testid="positions-page" :data-view="view">
    <p class="text-xs text-ink-muted">{{ route.meta.parent }}</p>
    <h1 class="text-xl font-semibold" data-testid="page-title">{{ route.meta.title }}</h1>
    <!-- GC-BP step 6 (ADR-201 (2)): "Positions" = this page as it was; "Paper" = the shared paper list, which loads by
         itself and is never held up by the Zerodha read. Paper figures never appear in the Positions tab. -->
    <Tabs v-model="tab" class="mt-2" :tabs="POSITION_TABS" label="Positions or paper trades" />
    <PaperStrategies v-if="tab === 'paper'" class="mt-2" data-testid="positions-paper" />
    <template v-else>
    <p v-if="loading" class="mt-2" data-testid="positions-loading">Reading your positions from Zerodha.</p>
    <ErrorMessage v-else-if="errorParts" class="mt-2" :parts="errorParts" compact prefix="positions-error" />
    <div v-else-if="result" class="mt-2 text-sm">
      <p>Read from Zerodha at <span data-testid="positions-read-at">{{ istTime(result.read_at) }}</span>.</p>
      <div v-if="result.blocked" data-testid="positions-blocked">
        <p>A strategy is {{ BLOCKED }}.</p>
        <ul>
          <li v-for="id in result.blocked_strategy_ids" :key="id" data-testid="positions-blocked-strategy" :data-strategy="id">
            <RouterLink v-if="orderPathOn" :to="`/strategy/${id}/execute`" class="underline" data-testid="positions-blocked-link">Strategy {{ id }}</RouterLink><span v-else>Strategy {{ id }}</span> ({{ BLOCKED }})
          </li>
        </ul>
      </div>
      <p v-if="!result.strategies.length && !result.has_outside" class="mt-2" data-testid="positions-empty">
        Zerodha shows no open positions, and none of your strategies holds any.
      </p>
      <p v-else-if="!result.strategies.length" class="mt-2" data-testid="positions-no-strategy">
        None of your strategies holds a position.
      </p>
      <div v-for="g in result.strategies" :key="g.strategy_id" class="mt-3" data-testid="position-group" :data-strategy="g.strategy_id">
        <h2 class="font-semibold">
          <RouterLink v-if="orderPathOn" :to="`/strategy/${g.strategy_id}/execute`" class="underline" data-testid="position-strategy-link">Strategy {{ g.strategy_id }}</RouterLink><span v-else data-testid="position-strategy-name">Strategy {{ g.strategy_id }}</span>
          <span v-if="g.blocked" class="ml-1" data-testid="position-mismatch-badge">({{ BLOCKED }})</span>
        </h2>
        <p v-if="!g.contracts.length" data-testid="position-group-empty">{{ NO_ROW }}</p>
        <ul v-else>
          <li v-for="c in g.contracts" :key="c.tradingsymbol" data-testid="position-row" :data-symbol="c.tradingsymbol">
            <span>{{ c.tradingsymbol }}</span>:
            <template v-if="c.pending">
              <span data-testid="position-waiting">{{ WAITING }}</span>
              (plan <span data-testid="position-pending-plans">{{ c.pending_plans.join(', ') }}</span>).
              Zerodha: <span data-testid="position-zerodha">{{ c.zerodha_units }}</span> units,
              <span data-testid="position-unconfirmed">{{ UNCONFIRMED }}</span>.
              <span data-testid="position-pending-holders">{{ HOLDERS }}</span>
            </template>
            <template v-else>
              <span data-testid="position-own-units">{{ c.units }}</span> units
              (Zerodha shows <span data-testid="position-zerodha">{{ c.zerodha_units }}</span> on this contract)
            </template>
          </li>
        </ul>
      </div>
      <p v-if="result.has_outside" class="mt-3" data-testid="positions-outside">
        <span data-testid="positions-outside-count">{{ outsideText(result.outside_lots) }}</span> -
        <a :href="KITE_POSITIONS_URL" target="_blank" rel="noopener noreferrer" class="underline" data-testid="positions-outside-kite">{{ VIEW_ON_KITE }}</a>
      </p>
    </div>
    </template>
  </section>
</template>
