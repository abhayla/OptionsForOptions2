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
          <span class="text-xs text-ink-muted">{{ row.price ? `about ${row.price}${quoteClock(row) ? ', as of ' + quoteClock(row) : ''}, ` : '' }}{{ PAPER_EXIT_PRICED_BY_SERVER_TEXT }}</span>
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
    <!-- D-03 part B (ADR-317 (7)): the server's one line per armed index exit, judged on the legs after these orders; nothing is moved -->
    <p v-if="armedUnchecked" class="mt-3 text-sm text-ink-muted" data-testid="paper-armed-exits-unchecked">{{ ARMED_UNCHECKED }}</p>
    <ul v-if="armedLines.length" class="mt-3 text-sm text-ink-muted" data-testid="paper-armed-exits">
      <li v-for="line in armedLines" :key="line" data-testid="paper-armed-exit">{{ line }}</li>
    </ul>
    <!-- GC-TRACK1 k10 (ADR-292): the strategy's first basket may be a condor already held at the user's broker -->
    <div v-if="firstBasket && rows.length && rows.every((r) => r.kind === 'open')" class="mt-3 text-sm" data-testid="held-form">
      <label class="flex items-center gap-2"><input v-model="heldOn" type="checkbox" data-testid="held-toggle" /> {{ HELD_LABEL }}</label>
      <div v-if="heldOn" class="mt-2 flex flex-wrap items-center gap-3">
        <label class="flex items-center gap-1"><span class="text-ink-muted">Entry date and time</span><input v-model="heldAt" type="datetime-local" class="h-9 rounded border border-line px-2" data-testid="held-entry-at" /></label>
        <label class="flex items-center gap-1"><span class="text-ink-muted">Broker</span><input v-model="heldBroker" type="text" maxlength="40" class="h-9 w-40 rounded border border-line px-2" data-testid="held-broker" /></label>
      </div>
    </div>
    <!-- GC-ICFIX Issue 10 (ADR-256): the server's one factual line when this exit leaves a sold leg unprotected; Confirm stays enabled -->
    <!-- N-22 (same class as S-26): one always-rendered slot with a reserved height; the checking / risk / unchecked line comes and goes inside it, so the buttons below never move -->
    <div :class="rows.some((r) => r.kind === 'exit') ? 'min-h-[3.75rem]' : ''" class="mt-3" data-testid="paper-exit-slot">
      <p v-if="exitState === 'risk'" class="text-sm font-medium text-warn" role="status" data-testid="paper-exit-warning">{{ exitWarning }}</p>
      <!-- fail closed: a check that could not run is said so, never shown as "no risk"; Confirm is not locked by either line -->
      <p v-else-if="exitState === 'unchecked'" class="text-sm font-medium text-warn" role="status" data-testid="paper-exit-unchecked">{{ PAPER_EXIT_UNCHECKED_TEXT }}</p>
      <p v-else-if="exitState === 'checking'" class="text-sm text-ink-muted" role="status" data-testid="paper-exit-checking">{{ PAPER_EXIT_CHECKING_TEXT }}</p>
    </div>
    <!-- ADR-330 (28), REQ-109 AC-1: prices not live: the owner's sentence is the label of the box the user ticks before Confirm -->
    <label v-if="notLiveLine" class="mt-3 flex items-start gap-2 text-sm font-medium text-warn" data-testid="paper-not-live">
      <input v-model="notLiveAck" type="checkbox" class="mt-1" data-testid="paper-not-live-ack" />{{ notLiveLine }}
    </label>
    <p class="mt-3 text-xs text-ink-muted" data-testid="paper-not-real">{{ PAPER_NOT_REAL_TEXT }}</p>
    <!-- fix/paper-dialog-safe (ADR-017): a stored order is never offered again; an answer of unknown outcome sends the user to the
         Orderbook first and keeps Confirm locked for PAPER_UNKNOWN_HOLD_MS; a refusal (4xx: nothing stored) unlocks after an edit -->
    <!-- GC-ICFIX Issue 6: these result lines sit in the frame's pinned status area (not the scrolling body), so they show with the buttons -->
    <!-- N-22: the status slot is always rendered (reserved height), so a result or error line fills it instead of adding a row above the buttons -->
    <template #status>
      <div class="min-h-10" data-testid="paper-status-slot">
      <p v-if="state === 'placed'" class="text-sm font-medium" role="status" data-testid="paper-placed">{{ PAPER_PLACED_NOT_REFRESHED_TEXT }}</p>
      <p v-else-if="state === 'unknown'" class="text-sm text-red-700" role="alert" data-testid="paper-unknown">
        {{ PAPER_UNKNOWN_TEXT }}
        <button type="button" class="ml-1 font-semibold text-accent underline" data-testid="paper-open-orderbook" @click="emit('orderbook')">{{ PAPER_OPEN_ORDERBOOK_LABEL }}</button>
      </p>
      <p v-else-if="error" class="text-sm text-red-700" role="alert" data-testid="paper-error">{{ error }}</p>
      </div>
    </template>
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
  PAPER_EXIT_CHECKING_TEXT, PAPER_EXIT_PRICED_BY_SERVER_TEXT, PAPER_EXIT_UNCHECKED_TEXT, PAPER_NOT_REAL_TEXT, PAPER_OPEN_ORDERBOOK_LABEL, PAPER_PLACED_NOT_REFRESHED_TEXT, PAPER_LOTS_REASON, PAPER_UNKNOWN_HOLD_MS,
  PAPER_UNKNOWN_TEXT, HELD_LABEL, heldBlock, paperLotsOk, paperPriceOk, paperPriceReason,
} from '@/lib/tracking'
import { paperDialogTitle, paperKindLabel } from '@/lib/paperDrafts'
import api from '@/services/api'
import { istClock } from '@/lib/displayFormat'

const props = defineProps({
  open: { type: Boolean, default: false },
  orders: { type: Array, default: () => [] },
  busy: { type: Boolean, default: false },
  blocked: { type: Boolean, default: false }, // ADR-328 (4): the page's blocked rule (read failed / trade changed elsewhere): no Confirm
  error: { type: String, default: '' },
  // fix/paper-dialog-safe: '' ready | 'refused' (4xx, shown in `error`) | 'unknown' (no answer / 5xx) | 'placed' (stored, refresh failed)
  state: { type: String, default: '' },
  holdMs: { type: Number, default: PAPER_UNKNOWN_HOLD_MS },
  locked: { type: Boolean, default: false }, // Lane U r1 (ADR-016/017/019): an unknown outcome is unresolved: Confirm stays off until the page's re-read decides (never a timer)
  firstBasket: { type: Boolean, default: false }, // GC-TRACK1 k10: offer "Held at my broker" (the strategy's first basket only)
  strategyId: { type: [Number, String], default: '' }, // GC-ICFIX Issue 10: with it, exit rows ask the server whether the exit widens the maximum loss
  notLiveLine: { type: String, default: '' }, // ADR-330 (28): set while the page's prices are not live; Confirm waits for the tick
  kind: { type: String, default: 'paper' }, // ADR-330 (10): 'paper' | 'real'; names what an exit confirmation exits, via paperDrafts.exitConfirmTitle
})
const emit = defineEmits(['confirm', 'cancel', 'orderbook'])

const rows = ref([])
watch(() => [props.open, props.orders], () => {
  if (props.open) rows.value = props.orders.map((o) => ({ ...o, lots: String(o.lots), price: String(o.price ?? '') }))
}, { immediate: true })

// D-09: the time of the quote an exit row shows (its own quote time from the book, India time); '' when the server gave none
const quoteClock = (row) => (row.price_at ? istClock(row.price_at) ?? '' : '')

// GC-TP step 3b2: the title says what the list holds (adds, exits or both)
const title = computed(() => paperDialogTitle(props.orders, props.kind))
const reasons = computed(() => rows.value.map((r) => (!paperLotsOk(r.lots) ? PAPER_LOTS_REASON : (r.kind !== 'exit' && !paperPriceOk(r.price)) ? paperPriceReason(r.price) : '')))
const notLiveAck = ref(false)
watch(() => [props.open, props.notLiveLine], () => { notLiveAck.value = false }) // each opening asks again
const heldOn = ref(false)
const heldAt = ref('')
const heldBroker = ref('')
const heldActive = computed(() => props.firstBasket && heldOn.value && rows.value.every((r) => r.kind === 'open'))
const ready = computed(() => rows.value.length > 0 && reasons.value.every((r) => r === '') && (!heldActive.value || heldAt.value !== ''))

// the quantity is a count of units (whole lots x the lot size the order carries), not money
const unitsOf = (r) => r.lots * r.lot_size
const orderOf = (r) => ({ contract_id: r.contract_id, side: r.side, quantity: unitsOf(r), price: r.kind === 'exit' ? '0' : String(r.price).trim(), kind: r.kind }) // price: as typed; an exit's is the server's (ignored)

// GC-ICFIX Issue 10 (ADR-256): the screen compares nothing; it shows the server's line when `widens` is true. Fail closed: a read that fails or answers
// something unusable shows "could not check" (exitState 'unchecked'); while it runs, 'checking'; no exit row: '' (nothing).
const exitWarning = ref('')
const exitState = ref('')
let askSeq = 0
async function askExitRisk() {
  const seq = ++askSeq
  // the WHOLE basket (exits and entries) is judged on the legs after all of it; rows not yet valid wait for the user's edit
  const basket = props.open && props.strategyId && rows.value.some((r) => r.kind === 'exit') ? rows.value : []
  if (!basket.length) { exitState.value = ''; exitWarning.value = ''; return }
  if (basket.some((r) => !paperLotsOk(r.lots) || (r.kind !== 'exit' && !paperPriceOk(r.price)))) { exitState.value = 'checking'; exitWarning.value = ''; return }
  exitState.value = 'checking'
  let state = 'unchecked'
  let line = ''
  try {
    const { data } = await api.get(`/paper/strategies/${props.strategyId}/exit-risk`, { params: { orders: JSON.stringify(basket.map(orderOf)) } })
    if (data?.state === 'no') state = ''
    else if (data?.state === 'yes' && typeof data.warning_text === 'string' && data.warning_text) { state = 'risk'; line = data.warning_text }
  } catch { state = 'unchecked' }
  if (seq === askSeq) { exitState.value = state; exitWarning.value = line }
}
watch(() => [props.open, props.orders, props.strategyId, rows.value.map((r) => `${r.lots}/${r.price}`).join()], askExitRisk, { immediate: true })

// D-03 part B: the lines naming each armed index exit against the legs after these orders (the server words them). A read that
// fails shows "Could not check your armed exits."; rows not yet valid show nothing; the exit stays armed either way and the panel marks it after the change.
const ARMED_UNCHECKED = 'Could not check your armed exits.' // pending owner read (frontend text, pinned by paper-armed-exits.test.js)
const armedLines = ref([])
const armedUnchecked = ref(false)
let armedSeq = 0
async function askArmedExits() {
  const seq = ++armedSeq
  const basket = props.open && props.strategyId && rows.value.length && ready.value ? rows.value : []
  let lines = []
  let unchecked = false
  if (basket.length) {
    try {
      const { data } = await api.get(`/paper/strategies/${props.strategyId}/armed-exits`, { params: { orders: JSON.stringify(basket.map(orderOf)) } })
      if (Array.isArray(data?.lines)) lines = data.lines.filter((l) => typeof l === 'string' && l)
      else unchecked = true
    } catch { lines = []; unchecked = true }
  }
  if (seq === armedSeq) { armedLines.value = lines; armedUnchecked.value = unchecked }
}
watch(() => [props.open, props.orders, props.strategyId, rows.value.map((r) => `${r.lots}/${r.price}`).join()], askArmedExits, { immediate: true })

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
  if (props.busy || props.blocked || exitState.value === 'checking' || (props.notLiveLine && !notLiveAck.value) || !ready.value || props.state === 'placed' || held.value || props.locked) return false
  return props.state !== 'refused' || refusedAt.value === null || snapshot() !== refusedAt.value
})

function confirm() {
  if (!canConfirm.value) return
  // third argument: the not-live line was shown AND ticked (ADR-330 (28)); false otherwise
  const ticked = !!props.notLiveLine && notLiveAck.value === true
  if (heldActive.value) emit('confirm', rows.value.map(orderOf), heldBlock(heldAt.value, heldBroker.value), ticked)
  else emit('confirm', rows.value.map(orderOf), null, ticked)
}
</script>
