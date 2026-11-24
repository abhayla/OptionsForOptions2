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

    <!-- GC-TP step 8b (REQ-109 AC-10; Sensibull Drafts Mode 278-279): the strategy's Charges beside its P&L, each the book reply's
         text as sent; the Charges are never added to or taken from the P&L, and an absent one is a dash (never 0). -->
    <HeldNote class="mt-2" :held="book.held" note />
    <p v-if="asOfLine" class="mt-2 text-xs text-ink-muted" data-testid="book-as-of">{{ asOfLine }}</p>
    <!-- u126 (REQ-109 AC-5): the read time of the answer these figures come from (the reply's answered_at, never the browser clock) -->
    <p v-if="contractsChanged" class="mt-2 text-xs text-red-700" data-testid="book-contracts-changed">{{ CONTRACTS_CHANGED_TEXT }}</p>
    <p v-if="readAt" class="mt-2 text-xs text-ink-muted" data-testid="book-read-at">As of {{ readAt }} IST</p>
    <dl class="mt-2 flex gap-6 text-xs" data-testid="book-strip">
      <!-- GC-ICFIX u123 (ADR-263): the headline total is the server's after-charges text, labelled; else the before text, labelled, with the reason -->
      <div>
        <dt class="text-ink-muted" data-testid="book-total-label">Total P&amp;L {{ total.label }}</dt>
        <dd class="num text-sm font-semibold" data-testid="book-total"><AfterChargesTap :breakdown="total.breakdown">{{ total.text ?? '-' }}</AfterChargesTap></dd>
        <p v-if="total.reason" class="max-w-xs text-ink-muted" data-testid="book-after-reason">{{ total.reason }}</p>
      </div>
      <!-- D-14: the line says which charges it shows: those paid, and beside them the estimate to close now (both inside the total) -->
      <div>
        <dt class="text-ink-muted" data-testid="book-charges-label">Charges paid</dt>
        <dd class="num text-sm font-semibold" data-testid="book-charges">{{ book.charges_text ?? '-' }}</dd>
      </div>
      <div v-if="book.charges_to_close_text">
        <dt class="text-ink-muted" data-testid="book-charges-close-label">Estimated cost to close</dt>
        <dd class="num text-sm font-semibold" data-testid="book-charges-close">{{ book.charges_to_close_text }}</dd>
      </div>
    </dl>

    <div v-if="view === 'net'" class="mt-2 overflow-x-auto">
      <table class="w-full text-xs" data-testid="net-table">
        <thead class="text-ink-muted">
          <!-- GC-ICFIX round 2 (F2): the server sends no after-charges form per contract: Booked / Unbooked / P&L are before charges, said once -->
          <tr><th colspan="4"></th><th colspan="3" class="font-normal" data-testid="net-basis">(before charges)</th><th></th></tr>
          <tr><th class="text-left font-normal">Contract</th><th class="font-normal">Lots</th><th class="font-normal">Avg</th><th class="font-normal">LTP</th><th class="font-normal">Booked</th><th class="font-normal">Unbooked</th><th class="font-normal">P&amp;L</th><th></th></tr>
        </thead>
        <tbody>
          <tr v-for="p in open" :key="p.contract_id" class="border-t border-line" data-testid="net-row" :data-contract-id="p.contract_id">
            <td class="py-1 pr-2" data-testid="net-contract">{{ p.contract_text }}</td>
            <td class="num text-center" data-testid="net-lots">{{ lotsOf(p) }}</td>
            <td class="num text-right" data-testid="net-avg">{{ p.average_text ?? '-' }}</td>
            <td class="num text-right"><span data-testid="net-ltp">{{ p.ltp_text ?? '-' }}</span><span v-if="p.ltp_text" class="ml-1 text-ink-muted" data-testid="net-ltp-at">{{ istClock(p.price_at ?? null) ?? 'time n/a' }}</span></td>
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
      <!-- D-10 (ADR-207 (2)): the Closed section: each closed lifecycle with its entry, exit and its own booked P&L (before charges);
           a contract bought back and opened again has a row here AND its open row above, whose Booked starts at 0 -->
      <ClosedRows :rows="closedRows" />
      <p v-if="book.closed_text" class="mt-2 text-xs font-semibold" data-testid="closed-result">{{ book.closed_text }}</p>
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
import { CONTRACTS_CHANGED_TEXT, afterFigure, pausedText } from '@/lib/tracking'
import AfterChargesTap from '@/components/common/AfterChargesTap.vue'
import { withAsOf } from '@/lib/paperList'
import ClosedRows from '@/components/strategy/ClosedRows.vue'
import HeldNote from '@/components/strategy/HeldNote.vue'
import { EXIT_ALL_LABEL, EXIT_LABEL, NET_POSITIONS_LABEL, ORDERBOOK_LABEL, exitLotsFrom, exitLotsOk, openLots, paperKindLabel } from '@/lib/paperDrafts'

const props = defineProps({
  book: { type: Object, required: true }, // GET /paper/strategies/{id} as sent
  net: { type: Array, required: true }, // the net legs (netLegsFromBook): whole lots per open contract
  readFailed: { type: Boolean, default: false },
  contractsChanged: { type: Boolean, default: false },
  showOrders: { type: Number, default: 0 }, // fix/paper-dialog-safe: a bump switches to the Orderbook view (the unknown-outcome link)
})
const emit = defineEmits(['exit', 'exit-all'])

// GC-ICFIX round 2 (F4): this panel no longer reads. The page makes the ONE read (usePaperBookRead) and passes the reply as `book`,
// the same reply the tracking box's total and the P&L table TOTAL row show. `readFailed`: the last read failed (the figures stay).
// `contractsChanged`: the new reply's open contracts differ from the shown ones (it is taken; the net legs need a reload).
// the paused sentence (REQ-109 AC-5) from the book's as_of; a failed read says the same with the last good answer's time
const asOfLine = computed(() => {
  if (props.readFailed) return pausedText(props.book.answered_at ?? null)
  return props.book.state === 'PAUSED' || props.book.state === 'NOT_CONNECTED' ? pausedText(props.book.as_of ?? null) : null
})

const readAt = computed(() => istClock(props.book.answered_at ?? null))

const pausedSentence = () => { const s = props.book.pause_reason_text; return typeof s === 'string' && s.trim() !== '' ? withAsOf(s.trim(), props.book.as_of) : null }
const total = computed(() => afterFigure(props.book, props.book.total_text ?? null, pausedSentence()))

const view = ref(props.showOrders > 0 ? 'orders' : 'net')
watch(() => props.showOrders, (n) => { if (n > 0) view.value = 'orders' })
const open = computed(() => props.book.positions.filter((p) => p.net_quantity !== 0))
const closedRows = computed(() => (Array.isArray(props.book.closed) ? props.book.closed : []))
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
