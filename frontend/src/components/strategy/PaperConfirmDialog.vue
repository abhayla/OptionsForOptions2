<!-- GC-TP step 2 (ADR-207 (1), REQ-109 AC-1; Sensibull "Add to Drafts", study 166-173): the confirm list of paper orders.
     One row per order: B/S, contract text, lots (editable, whole lots >= 1) and a price box (editable, default as given).
     Props are a list of orders {key, side, text, lots, lot_size, price, kind, contract_id}, not "legs of a strategy", so
     step 3 (Drafts Mode: add / exit orders) reuses it. The browser forms no money: a price goes out as the typed string;
     it only checks the step (above 0, multiple of 0.05) by whole paise from the text. The server refuses the same and its
     refusal text arrives in `error`. Confirm emits ONE `confirm` with the whole list; `busy` blocks a second press. -->
<template>
  <Modal :open="open" :title="title" fallback-focus="[data-testid='add-to-paper']" data-testid="paper-confirm" @close="emit('cancel')">
    <ul class="text-sm" data-testid="paper-orders">
      <li v-for="(row, i) in rows" :key="row.key" class="flex flex-wrap items-center gap-2 border-b border-line py-2" data-testid="paper-order">
        <Chip :kind="row.side === 'BUY' ? 'buy' : 'sell'" :label="row.side === 'BUY' ? 'B' : 'S'" />
        <!-- GC-TP step 3b2 (Sensibull Add to Drafts 166-173): each row says whether it adds to the position or exits it -->
        <span class="text-xs font-medium text-ink-muted" data-testid="paper-order-kind">{{ paperKindLabel(row.kind) }}</span>
        <span class="min-w-0 flex-1" data-testid="paper-order-text">{{ row.text }}</span>
        <label class="flex items-center gap-1">
          <span class="text-ink-muted">Lots</span>
          <input v-model="row.lots" :disabled="state === 'placed'" type="text" inputmode="numeric" class="h-9 w-14 rounded border border-line px-2 text-right" :aria-label="`Lots for ${row.text}`" data-testid="paper-lots" />
        </label>
        <!-- GC-ICGUIDE g21 (audit C10): the server prices an exit (live price, or the last close after hours), so it is text here -->
        <span v-if="row.kind === 'exit'" class="flex items-center gap-1" data-testid="paper-exit-price">
          <span class="text-ink-muted">Price</span>
          <span class="text-xs text-ink-muted">{{ row.price ? `about ${row.price}, ` : '' }}{{ PAPER_EXIT_PRICED_BY_SERVER_TEXT }}</span>
        </span>
        <label v-else class="flex items-center gap-1">
          <span class="text-ink-muted">Price</span>
          <input v-model="row.price" :disabled="state === 'placed'" type="text" inputmode="decimal" class="h-9 w-24 rounded border border-line px-2 text-right" :aria-label="`Price for ${row.text}`" data-testid="paper-price" />
          <!-- GC-TP step 3b1 (REQ-109 AC-4): an exit with no live price has an empty box, marked, and must be typed -->
          <span v-if="row.price_note" class="text-xs text-warn" data-testid="paper-price-note">{{ row.price_note }}</span>
        </label>
        <span v-if="reasons[i]" class="w-full text-xs text-warn" data-testid="paper-reason">{{ reasons[i] }}</span>
      </li>
    </ul>
    <p class="mt-3 text-xs text-ink-muted" data-testid="paper-not-real">{{ PAPER_NOT_REAL_TEXT }}</p>
    <!-- fix/paper-dialog-safe (ADR-017): a stored order is never offered again; an answer of unknown outcome sends the user to the
         Orderbook first and keeps Confirm locked for PAPER_UNKNOWN_HOLD_MS; a refusal (4xx: nothing stored) unlocks after an edit -->
    <p v-if="state === 'placed'" class="mt-2 text-sm font-medium" role="status" data-testid="paper-placed">{{ PAPER_PLACED_NOT_REFRESHED_TEXT }}</p>
    <p v-else-if="state === 'unknown'" class="mt-2 text-sm text-red-700" role="alert" data-testid="paper-unknown">
      {{ PAPER_UNKNOWN_TEXT }}
      <button type="button" class="ml-1 font-semibold text-accent underline" data-testid="paper-open-orderbook" @click="emit('orderbook')">{{ PAPER_OPEN_ORDERBOOK_LABEL }}</button>
    </p>
    <p v-else-if="error" class="mt-2 text-sm text-red-700" role="alert" data-testid="paper-error">{{ error }}</p>
    <template #actions>
      <button type="button" class="h-10 rounded-lg border border-line px-3 font-medium" data-testid="paper-cancel" @click="emit('cancel')">{{ state === 'placed' ? 'Close' : 'Cancel' }}</button>
      <button v-if="state !== 'placed'" type="button" class="h-10 rounded-lg bg-accent px-3 font-medium text-white disabled:opacity-50" :disabled="!canConfirm" data-testid="paper-confirm-button" @click="confirm">Confirm</button>
    </template>
  </Modal>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import Chip from '@/components/common/Chip.vue'
import Modal from '@/components/common/Modal.vue'
import {
  PAPER_EXIT_PRICED_BY_SERVER_TEXT, PAPER_NOT_REAL_TEXT, PAPER_OPEN_ORDERBOOK_LABEL, PAPER_PLACED_NOT_REFRESHED_TEXT, PAPER_PRICE_REASON, PAPER_LOTS_REASON, PAPER_UNKNOWN_HOLD_MS,
  PAPER_UNKNOWN_TEXT, paperLotsOk, paperPriceOk,
} from '@/lib/tracking'
import { paperDialogTitle, paperKindLabel } from '@/lib/paperDrafts'

const props = defineProps({
  open: { type: Boolean, default: false },
  orders: { type: Array, default: () => [] },
  busy: { type: Boolean, default: false },
  error: { type: String, default: '' },
  // fix/paper-dialog-safe: '' ready | 'refused' (4xx, shown in `error`) | 'unknown' (no answer / 5xx) | 'placed' (stored, refresh failed)
  state: { type: String, default: '' },
  holdMs: { type: Number, default: PAPER_UNKNOWN_HOLD_MS },
})
const emit = defineEmits(['confirm', 'cancel', 'orderbook'])

const rows = ref([])
watch(() => [props.open, props.orders], () => {
  if (props.open) rows.value = props.orders.map((o) => ({ ...o, lots: String(o.lots), price: String(o.price ?? '') }))
}, { immediate: true })

// GC-TP step 3b2: the title says what the list holds (adds, exits or both)
const title = computed(() => paperDialogTitle(props.orders))
const reasons = computed(() => rows.value.map((r) => (!paperLotsOk(r.lots) ? PAPER_LOTS_REASON : (r.kind !== 'exit' && !paperPriceOk(r.price)) ? PAPER_PRICE_REASON : '')))
const ready = computed(() => rows.value.length > 0 && reasons.value.every((r) => r === ''))

// the quantity is a count of units (whole lots x the lot size the order carries), not money
const unitsOf = (r) => r.lots * r.lot_size
const orderOf = (r) => ({ contract_id: r.contract_id, side: r.side, quantity: unitsOf(r), price: r.kind === 'exit' ? '0' : String(r.price).trim(), kind: r.kind }) // price: as typed; an exit's is the server's (ignored)

// the rows as they were when the server refused them: Confirm unlocks only once the user has changed something
const snapshot = () => JSON.stringify(rows.value.map((r) => [r.lots, r.price]))
const refusedAt = ref(null)
const held = ref(false)
let holdTimer = null
watch(() => props.state, (s) => {
  refusedAt.value = s === 'refused' ? snapshot() : null
  clearTimeout(holdTimer)
  held.value = s === 'unknown'
  if (held.value) holdTimer = setTimeout(() => { held.value = false }, props.holdMs)
}, { immediate: true })
onBeforeUnmount(() => clearTimeout(holdTimer))
const canConfirm = computed(() => {
  if (props.busy || !ready.value || props.state === 'placed' || held.value) return false
  return props.state !== 'refused' || refusedAt.value === null || snapshot() !== refusedAt.value
})

function confirm() {
  if (!canConfirm.value) return
  emit('confirm', rows.value.map(orderOf))
}
</script>
