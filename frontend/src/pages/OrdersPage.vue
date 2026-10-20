<!-- The Orders screen (GC-6 ORDERS-SCREEN; ADR-135 four states, ADR-138 (1) one line per strategy order + a link to Kite's
     order book, ADR-130 empty state, ADR-079 the page load re-reads Zerodha: GET /api/orders does that ONE read-only
     read on the server). The browser spells the state the server decided; it computes nothing. A line the server could
     not confirm shows the catalogue message and "Check with Zerodha" instead of a state. New file, copy from: none. -->
<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import api, { NEUTRAL_PARTS } from '@/services/api'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import EmptyState from '@/components/states/EmptyState.vue'
import ReturnCheck from '@/components/execution/ReturnCheck.vue'
import { KITE_ORDER_BOOK_URL } from '@/lib/execute'
import { CREATE_STRATEGY_LABEL, EMPTY_MESSAGE, KITE_LINK_LABEL, NEEDS_CHECK_TEXT, stateText } from '@/lib/orders'

const route = useRoute()
const orders = ref(null)
const errorParts = ref(null)

async function load() {
  errorParts.value = null
  try {
    orders.value = (await api.get('/orders')).data.orders
  } catch (e) {
    orders.value = null
    errorParts.value = e?.parts ?? NEUTRAL_PARTS
  }
}
onMounted(load)
</script>

<template>
  <section class="p-4" data-testid="orders-screen">
    <h1 class="text-xl font-semibold" data-testid="page-title">Orders</h1>
    <p v-if="route.meta.note" class="mt-1 text-ink-muted" data-testid="page-note">{{ route.meta.note }}</p>
    <a
:href="KITE_ORDER_BOOK_URL" target="_blank" rel="noopener noreferrer" data-testid="kite-order-book-link"
       class="mt-2 inline-flex min-h-[44px] items-center underline">{{ KITE_LINK_LABEL }}</a>
    <ErrorMessage v-if="errorParts" class="mt-2" :parts="errorParts" prefix="orders-error" />
    <EmptyState
v-else-if="orders !== null && orders.length === 0" class="mt-2" :message="EMPTY_MESSAGE"
                :action-label="CREATE_STRATEGY_LABEL" action-to="/strategies/create-strategy" />
    <ul v-else-if="orders !== null" class="mt-2 space-y-2" data-testid="orders-list">
      <li
v-for="(line, i) in orders" :key="`${line.strategy_id}-${line.plan_number}-${i}`"
          class="rounded border border-line bg-surface p-3 text-sm" data-testid="order-line"
          :data-state="line.state ?? (line.needs_reconciliation ? 'reconciliation' : 'unconfirmed')">
        <p class="font-medium" data-testid="order-what">{{ line.transaction_type }} {{ line.ordered_quantity }} {{ line.tradingsymbol }}</p>
        <p data-testid="order-which">Strategy {{ line.strategy_id }}, plan {{ line.plan_number }} ({{ line.action }})</p>
        <p v-if="line.state" data-testid="order-state">{{ stateText(line) }}</p>
        <template v-else-if="line.could_not_confirm">
          <ErrorMessage v-if="line.message" class="mt-1" :parts="line.message" compact prefix="order-unconfirmed" />
          <ReturnCheck :strategy-id="String(line.strategy_id)" @checked="load" />
        </template>
        <template v-else-if="line.needs_reconciliation">
          <p data-testid="order-reconcile">{{ NEEDS_CHECK_TEXT }}</p>
          <ReturnCheck :strategy-id="String(line.strategy_id)" @checked="load" />
        </template>
      </li>
    </ul>
  </section>
</template>
