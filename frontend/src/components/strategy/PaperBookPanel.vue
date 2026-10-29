<!-- GC-TP step 3b2 (ADR-207 (2), REQ-109 AC-9; Sensibull Drafts Mode 274-279): the paper book under the Drafts Mode legs, with a
     Net Positions | Orderbook switch. Net Positions: per OPEN contract Lots, Avg, LTP, Booked, Unbooked, P&L (the book reply's
     texts as sent; lots = the net leg's whole lots, a count), an Exit with a lots box (1..open lots: a partial exit), and the
     closed contracts below with their booked P&L. Orderbook: the reply's orders in the reply's order (newest last): time IST,
     B/S, contract, qty, price, kind. "Exit all" and "Exit" only EMIT: the page turns them into edited legs, so the orders still
     come from paperOrdersFor (no second order-building path). No money is formed here (ADR-008). -->
<template>
  <section class="mt-3 text-sm" data-testid="paper-book">
    <div class="flex items-center gap-2">
      <div class="inline-flex rounded-md border border-line text-xs" role="group" aria-label="Paper book view" data-testid="paper-book-switch">
        <button type="button" class="rounded-l-md px-2 py-1" :class="view === 'net' ? 'bg-accent-soft font-medium text-accent' : ''" :aria-pressed="view === 'net' ? 'true' : 'false'" data-testid="book-tab-net" @click="view = 'net'">{{ NET_POSITIONS_LABEL }}</button>
        <button type="button" class="rounded-r-md px-2 py-1" :class="view === 'orders' ? 'bg-accent-soft font-medium text-accent' : ''" :aria-pressed="view === 'orders' ? 'true' : 'false'" data-testid="book-tab-orders" @click="view = 'orders'">{{ ORDERBOOK_LABEL }}</button>
      </div>
      <span class="flex-1"></span>
      <button v-if="open.length" type="button" class="h-8 rounded-lg border border-line px-3 font-medium" data-testid="paper-exit-all" @click="emit('exit-all')">{{ EXIT_ALL_LABEL }}</button>
    </div>

    <div v-if="view === 'net'" class="mt-2 overflow-x-auto">
      <table class="w-full text-xs" data-testid="net-table">
        <thead class="text-ink-muted">
          <tr><th class="text-left font-normal">Contract</th><th class="font-normal">Lots</th><th class="font-normal">Avg</th><th class="font-normal">LTP</th><th class="font-normal">Booked</th><th class="font-normal">Unbooked</th><th class="font-normal">P&amp;L</th><th></th></tr>
        </thead>
        <tbody>
          <tr v-for="p in open" :key="p.contract_id" class="border-t border-line" data-testid="net-row" :data-contract-id="p.contract_id">
            <td class="py-1 pr-2" data-testid="net-contract">{{ p.contract_text }}</td>
            <td class="num text-center" data-testid="net-lots">{{ lotsOf(p) }}</td>
            <td class="num text-right" data-testid="net-avg">{{ p.average_text ?? '-' }}</td>
            <td class="num text-right" data-testid="net-ltp">{{ p.ltp_text ?? '-' }}</td>
            <td class="num text-right" data-testid="net-booked">{{ p.booked_text }}</td>
            <td class="num text-right" data-testid="net-unbooked">{{ p.unbooked_text ?? '-' }}</td>
            <td class="num text-right" data-testid="net-pnl">{{ p.total_text ?? '-' }}</td>
            <td class="whitespace-nowrap pl-2 text-right">
              <input
                v-model="exitText[p.contract_id]" type="text" inputmode="numeric" class="h-7 w-10 rounded border border-line px-1 text-right"
                :aria-label="`Lots to exit for ${p.contract_text}`" data-testid="net-exit-lots"
              />
              <button type="button" class="ml-1 h-7 rounded border border-line px-2 disabled:opacity-50" :disabled="!exitLotsOk(exitText[p.contract_id], lotsOf(p))" data-testid="net-exit" @click="exitOne(p)">{{ EXIT_LABEL }}</button>
            </td>
          </tr>
        </tbody>
      </table>
      <ul v-if="closed.length" class="mt-2 text-xs text-ink-muted" data-testid="closed-list">
        <li v-for="p in closed" :key="p.contract_id" class="flex gap-2" data-testid="closed-row">
          <span class="flex-1" data-testid="closed-contract">{{ p.contract_text }}</span>
          <span>Closed, booked</span><span class="num" data-testid="closed-booked">{{ p.booked_text }}</span>
        </li>
      </ul>
    </div>

    <table v-else class="mt-2 w-full text-xs" data-testid="order-table">
      <thead class="text-ink-muted">
        <tr><th class="text-left font-normal">Time</th><th class="font-normal">B/S</th><th class="text-left font-normal">Contract</th><th class="font-normal">Qty</th><th class="font-normal">Price</th><th class="font-normal">Kind</th></tr>
      </thead>
      <tbody>
        <tr v-for="o in book.orders" :key="o.id" class="border-t border-line" data-testid="order-row">
          <td class="num py-1" data-testid="order-time">{{ istClock(o.placed_at) ?? '-' }}</td>
          <td class="text-center" data-testid="order-side">{{ o.side === 'BUY' ? 'B' : 'S' }}</td>
          <td data-testid="order-contract">{{ o.contract_text }}</td>
          <td class="num text-right" data-testid="order-qty">{{ o.quantity }}</td>
          <td class="num text-right" data-testid="order-price">{{ o.price_text }}</td>
          <td class="text-center" data-testid="order-kind">{{ kindText(o.kind) }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { istClock } from '@/lib/displayFormat'
import { EXIT_ALL_LABEL, EXIT_LABEL, NET_POSITIONS_LABEL, ORDERBOOK_LABEL, exitLotsFrom, exitLotsOk, openLots, paperKindLabel } from '@/lib/paperDrafts'

const props = defineProps({
  book: { type: Object, required: true }, // GET /paper/strategies/{id} as sent
  net: { type: Array, required: true }, // the net legs (netLegsFromBook): whole lots per open contract
})
const emit = defineEmits(['exit', 'exit-all'])

const view = ref('net')
const open = computed(() => props.book.positions.filter((p) => p.net_quantity !== 0))
const closed = computed(() => props.book.positions.filter((p) => p.net_quantity === 0))
const lotsOf = (p) => openLots(props.net, p.contract_id)
// the order's own kind in words ('open' is the first add)
const kindText = (kind) => (kind === 'open' ? 'Open' : paperKindLabel(kind))
// each lots box starts at the full open lots; a new book resets them
const exitText = ref({})
watch(() => props.net, (net) => { exitText.value = Object.fromEntries(net.map((l) => [l.contract_id, String(l.lots)])) }, { immediate: true })
function exitOne(p) {
  const lots = exitLotsFrom(exitText.value[p.contract_id], lotsOf(p)) // a count of lots, never money
  if (lots !== null) emit('exit', p.contract_id, lots)
}
</script>
