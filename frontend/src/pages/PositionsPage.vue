<!-- Positions pages, part 1 (W-111; REQ-044 AC-3, ADR-109 (2), ADR-027). Reads GET /api/positions once on load and shows
     QUANTITIES and the owning strategy's link only: no price, P&L, margin or Greek (part 2), no order button (every action
     routes back to the strategy). Outside lots are shown apart, as not part of any strategy. A refused read (no Zerodha
     session, failed read) shows the catalogue message, never an empty list. A PENDING contract (ADR-110: an open plan's
     orders are not final at Zerodha) shows the waiting line, Zerodha's quantity marked not yet confirmed, no own/outside
     split, and a link to the strategy's Execute screen where Check is. New file, copy from: none. -->
<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import api, { NEUTRAL_PARTS } from '@/services/api'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import { istTime } from '@/lib/displayFormat'

const route = useRoute()
const linked = route.meta.view === 'linked'
const loading = ref(true)
const result = ref(null)
const errorParts = ref(null)
// The page's own words, one home each (ADR-110 quotes the first two verbatim).
const WAITING = 'Order placed - waiting for Check with Zerodha'
const UNCONFIRMED = 'not yet confirmed'
const BLOCKED = 'blocked until its position matches Zerodha'

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
  <section class="p-4" data-testid="positions-page" :data-view="linked ? 'linked' : 'current'">
    <p class="text-xs text-ink-muted">{{ route.meta.parent }}</p>
    <h1 class="text-xl font-semibold" data-testid="page-title">{{ route.meta.title }}</h1>
    <p v-if="loading" class="mt-2" data-testid="positions-loading">Reading your positions from Zerodha.</p>
    <ErrorMessage v-else-if="errorParts" class="mt-2" :parts="errorParts" compact prefix="positions-error" />
    <div v-else-if="result" class="mt-2 text-sm">
      <p>Read from Zerodha at <span data-testid="positions-read-at">{{ istTime(result.read_at) }}</span>.</p>
      <p v-if="result.blocked" data-testid="positions-blocked">A strategy is {{ BLOCKED }}.</p>
      <p v-if="!result.contracts.length" class="mt-2" data-testid="positions-empty">
        Zerodha shows no open positions, and none of your strategies holds any.
      </p>
      <table v-else-if="!linked" class="mt-2" data-testid="positions-current">
        <thead><tr><th>Contract</th><th>Zerodha units</th><th>In strategies</th><th>Outside any strategy</th></tr></thead>
        <tbody>
          <tr v-for="c in result.contracts" :key="c.tradingsymbol" data-testid="position-row" :data-symbol="c.tradingsymbol">
            <td>{{ c.tradingsymbol }}</td>
            <td data-testid="position-zerodha">{{ c.zerodha_units }}</td>
            <td v-if="c.pending" colspan="2" data-testid="position-pending">
              <span data-testid="position-unconfirmed">({{ UNCONFIRMED }})</span>
              <span data-testid="position-waiting">{{ WAITING }}</span>:
              <RouterLink v-for="p in c.pending_plans" :key="`${p.strategy_id}-${p.plan_number}`" :to="`/strategy/${p.strategy_id}/execute`" class="underline" data-testid="position-pending-link">Strategy {{ p.strategy_id }}</RouterLink>
            </td>
            <template v-else>
              <td data-testid="position-own">{{ c.own_units }}</td>
              <td data-testid="position-outside">{{ c.outside_units }}</td>
            </template>
          </tr>
        </tbody>
      </table>
      <div v-else class="mt-2" data-testid="positions-linked">
        <div v-for="c in result.contracts" :key="c.tradingsymbol" class="mt-2" data-testid="position-row" :data-symbol="c.tradingsymbol">
          <h2 class="font-semibold">{{ c.tradingsymbol }}</h2>
          <div v-if="c.pending" data-testid="position-pending">
            <p data-testid="position-waiting">{{ WAITING }}</p>
            <p>Zerodha: <span data-testid="position-zerodha">{{ c.zerodha_units }}</span> units, <span data-testid="position-unconfirmed">{{ UNCONFIRMED }}</span>.</p>
            <ul>
              <li v-for="p in c.pending_plans" :key="`${p.strategy_id}-${p.plan_number}`">
                <RouterLink :to="`/strategy/${p.strategy_id}/execute`" class="underline" data-testid="position-pending-link">Strategy {{ p.strategy_id }}</RouterLink> ({{ BLOCKED }})
              </li>
            </ul>
          </div>
          <ul v-else>
            <li v-for="o in c.own" :key="o.strategy_id" data-testid="position-own-lots" :data-strategy="o.strategy_id">
              <RouterLink :to="`/strategy/${o.strategy_id}/execute`" class="underline" data-testid="position-strategy-link">Strategy {{ o.strategy_id }}</RouterLink>:
              <span data-testid="position-own-units">{{ o.units }}</span> units
              <span v-if="o.blocked" data-testid="position-own-blocked">({{ BLOCKED }})</span>
            </li>
          </ul>
          <p v-if="!c.pending && c.outside_units" data-testid="position-outside-lots">
            Not part of any strategy: <span data-testid="position-outside-units">{{ c.outside_units }}</span> units.
          </p>
        </div>
      </div>
    </div>
  </section>
</template>
