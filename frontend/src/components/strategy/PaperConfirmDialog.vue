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
          <input v-model="row.lots" :disabled="state === 'placed' || marketState === 'checking'" type="text" inputmode="numeric" class="h-9 w-14 rounded border border-line px-2 text-right" :aria-label="`Lots for ${row.text}`" data-testid="paper-lots" />
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
    <p v-if="armedUncheckedShown" class="mt-3 text-sm text-ink-muted" data-testid="paper-armed-exits-unchecked">{{ ARMED_UNCHECKED }}</p>
    <ul v-if="armedShown.length" class="mt-3 text-sm text-ink-muted" data-testid="paper-armed-exits">
      <li v-for="line in armedShown" :key="line" data-testid="paper-armed-exit">{{ line }}</li>
    </ul>
    <!-- GC-TRACK1 k10 (ADR-292): the strategy's first basket may be a condor already held at the user's broker -->
    <div v-if="firstBasket && rows.length && rows.every((r) => r.kind === 'open')" class="mt-3 text-sm" data-testid="held-form">
      <label class="flex items-center gap-2"><input v-model="heldOn" type="checkbox" data-testid="held-toggle" /> {{ HELD_LABEL }}</label>
      <div v-if="heldOn" class="mt-2 flex flex-wrap items-center gap-3">
        <label class="flex items-center gap-1"><span class="text-ink-muted">Entry date and time</span><input v-model="heldAt" type="datetime-local" class="h-9 rounded border border-line px-2" data-testid="held-entry-at" /></label>
        <label class="flex items-center gap-1"><span class="text-ink-muted">Broker</span><input v-model="heldBroker" type="text" maxlength="40" class="h-9 w-40 rounded border border-line px-2" data-testid="held-broker" /></label>
      </div>
    </div>
    <!-- Lane FA r2 I-17: one plain line on how old the exit price is (priceState.priceAgeLine); an entry-only dialog has none -->
    <p v-if="ageLine.text" class="mt-3 text-sm text-ink-muted" role="status" data-testid="paper-price-age" :data-state="ageLine.state">{{ ageLine.text }}</p>
    <!-- GC-ICFIX Issue 10 (ADR-256): the server's one factual line when this exit leaves a sold leg unprotected; Confirm stays enabled -->
    <!-- N-22 (same class as S-26): one always-rendered slot with a reserved height; the checking / risk / unchecked line comes and goes inside it, so the buttons below never move -->
    <div :class="rows.some((r) => r.kind === 'exit') ? 'min-h-[3.75rem]' : ''" class="mt-3" data-testid="paper-exit-slot">
      <p v-if="exitState === 'risk'" class="text-sm font-medium text-warn" role="status" data-testid="paper-exit-warning">{{ exitWarning }}</p>
      <!-- fail closed: a check that could not run is said so, never shown as "no risk"; Confirm is not locked by either line -->
      <p v-else-if="exitState === 'unchecked'" class="text-sm font-medium text-warn" role="status" data-testid="paper-exit-unchecked">{{ canConfirm ? PAPER_EXIT_UNCHECKED_TEXT : PAPER_EXIT_UNCHECKED_SHORT_TEXT }}</p>
      <p v-else-if="exitState === 'checking'" class="text-sm text-ink-muted" role="status" data-testid="paper-exit-checking">{{ PAPER_EXIT_CHECKING_TEXT }}</p>
    </div>
    <!-- ADR-330 (28), REQ-109 AC-1: prices not live: the owner's sentence is the label of the box the user ticks before Confirm -->
    <label v-if="notLiveLine" class="mt-3 flex items-start gap-2 text-sm font-medium text-warn" data-testid="paper-not-live">
      <input v-model="notLiveAck" type="checkbox" class="mt-1" data-testid="paper-not-live-ack" />{{ notLiveLine }}
    </label>
    <p v-if="note" class="mt-3 text-sm font-medium text-warn" role="status" data-testid="paper-discard-note">{{ note }}</p>
    <p class="mt-3 text-xs text-ink-muted" data-testid="paper-not-real">{{ PAPER_NOT_REAL_TEXT }}</p>
    <!-- fix/paper-dialog-safe (ADR-017): a stored order is never offered again; an answer of unknown outcome sends the user to the
         Orderbook first and keeps Confirm locked for PAPER_UNKNOWN_HOLD_MS; a refusal (4xx: nothing stored) unlocks after an edit -->
    <!-- GC-ICFIX Issue 6: these result lines sit in the frame's pinned status area (not the scrolling body), so they show with the buttons -->
    <!-- N-22: the status slot is always rendered (reserved height), so a result or error line fills it instead of adding a row above the buttons -->
    <template #status>
      <div ref="statusSlot" class="min-h-10" data-testid="paper-status-slot">
      <!-- I-18 (ADR-017): while the post runs; the line is about sending, never about done ("Exit placed on paper" stays the only done sentence) -->
      <p v-if="busy && state !== 'placed' && rows.some((r) => r.kind === 'exit')" class="text-sm text-ink-muted" role="status" data-testid="paper-placing">{{ EXIT_PLACING_TEXT }}</p>
      <p v-else-if="state === 'placed'" class="text-sm font-medium" role="status" data-testid="paper-placed">{{ PAPER_PLACED_NOT_REFRESHED_TEXT }}</p>
      <p v-else-if="state === 'unknown' || lockWindowOver" class="text-sm text-red-700" role="alert" data-testid="paper-unknown" :data-window-over="lockWindowOver ? 'yes' : 'no'">
        {{ lockWindowOver ? EXIT_UNKNOWN_AFTER_WINDOW_TEXT : PAPER_UNKNOWN_TEXT }}
        <button type="button" class="ml-1 font-semibold text-accent underline" data-testid="paper-open-orderbook" @click="emit('orderbook')">{{ PAPER_OPEN_ORDERBOOK_LABEL }}</button>
      </p>
      <p v-else-if="marketLine" class="text-sm text-red-700" role="alert" data-testid="paper-market-closed">{{ marketLine }}</p>
      <p v-else-if="error" class="text-sm text-red-700" role="alert" data-testid="paper-error">{{ error }}</p>
      <!-- Lane FA2 item 1 (ADR-330 (48)): the stops the move cancelled, told from the order reply alone (pending owner read) -->
      <ul v-if="stopLines.length" class="mt-1 text-sm font-medium text-warn" role="status" data-testid="paper-cancelled-stops">
        <li v-for="line in stopLines" :key="line" data-testid="paper-cancelled-stop">{{ line }}</li>
      </ul>
      <p v-if="stopsReplyUnreadable" class="mt-1 text-sm font-medium text-warn" role="status" data-testid="paper-stops-reply-unreadable">{{ STOP_REPLY_UNREADABLE_TEXT }}</p>
      </div>
    </template>
    <template #actions>
      <button type="button" class="h-10 rounded-lg border border-line px-3 font-medium" data-testid="paper-cancel" @click="emit('cancel')">{{ state === 'placed' ? 'Close' : 'Cancel' }}</button>
      <button v-if="state !== 'placed'" type="button" class="h-10 rounded-lg bg-accent px-3 font-medium text-white disabled:opacity-50" :disabled="!canConfirm" data-testid="paper-confirm-button" @click="confirm">Confirm</button>
    </template>
  </Modal>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import Chip from '@/components/common/Chip.vue'
import Modal from '@/components/common/Modal.vue'
import { monoAgeOfAt } from '@/lib/unknownLocks'
import {
  PAPER_EXIT_CHECKING_TEXT, PAPER_EXIT_PRICED_BY_SERVER_TEXT, PAPER_EXIT_UNCHECKED_TEXT, PAPER_EXIT_UNCHECKED_SHORT_TEXT, PAPER_NOT_REAL_TEXT, PAPER_OPEN_ORDERBOOK_LABEL, PAPER_PLACED_NOT_REFRESHED_TEXT, PAPER_LOTS_REASON, PAPER_UNKNOWN_HOLD_MS,
  PAPER_UNKNOWN_TEXT, HELD_LABEL, STOP_REPLY_UNREADABLE_TEXT, cancelledStopLines, EXIT_UNKNOWN_WINDOW_MS, EXIT_UNKNOWN_AFTER_WINDOW_TEXT, heldBlock, paperLotsOk, paperPriceOk, paperPriceReason,
} from '@/lib/tracking'
import { paperDialogTitle, paperKindLabel } from '@/lib/paperDrafts'
import api from '@/services/api'
import { EXIT_PLACING_TEXT } from '@/lib/usePaperExit'
import { isoMillis, istClock } from '@/lib/displayFormat'
import { clockReadingMs, priceAgeLine } from '@/lib/priceState'

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
  lockedAtMs: { type: Number, default: 0 }, // #870 page half: when the unknown reply came (ms); the 120 s window counts from then, not from this opening. 0 = from when the lock is first seen
  firstBasket: { type: Boolean, default: false }, // GC-TRACK1 k10: offer "Held at my broker" (the strategy's first basket only)
  strategyId: { type: [Number, String], default: '' }, // GC-ICFIX Issue 10: with it, exit rows ask the server whether the exit widens the maximum loss
  note: { type: String, default: '' }, // ADR-330 (59): the page's one line about a staged change an Exit all will discard (pending owner read)
  notLiveLine: { type: String, default: '' }, // ADR-330 (28): set while the page's prices are not live; Confirm waits for the tick
  nowMs: { type: Number, default: 0 }, // I-17: the clock the price age is told against (tests); 0 = the browser's, read when the dialog opens
  cancelledStops: { type: Array, default: null }, // FA2 item 1: the order reply's `cancelled_stops`; null = the reply had none / an old reply
  stopsReplyUnreadable: { type: Boolean, default: false }, // FA2 item 1: the reply could not be read, so what happened to the stop is unknown
  kind: { type: String, default: 'paper' }, // ADR-330 (10): 'paper' | 'real'; names what an exit confirmation exits, via paperDrafts.exitConfirmTitle
})
const emit = defineEmits(['confirm', 'cancel', 'orderbook'])

const rows = ref([])
const stopLines = computed(() => cancelledStopLines(props.cancelledStops))
watch(() => [props.open, props.orders], () => {
  if (props.open) rows.value = props.orders.map((o) => ({ ...o, lots: String(o.lots), price: String(o.price ?? '') }))
}, { immediate: true })

// D-09: the time of the quote an exit row shows (its own quote time from the book, India time); '' when the server gave none
const quoteClock = (row) => (row.price_at ? istClock(row.price_at) ?? '' : '')

// I-17: the age line, told against the time the dialog opened (or the `nowMs` prop)
const openedAtMs = ref(Date.now())
watch(() => props.open, (o) => { if (o) openedAtMs.value = Date.now() })
// fd2: the server's own clock (`server_time` on the market, exit-risk and armed-exits answers) is the one the age is told against; the browser's
// clock only measures the time since that answer. A server_time that is absent or not a time changes nothing (the browser clock, as before).
const serverClock = ref(null) // { serverMs, localMs }
function noteServerTime(data) {
  const ms = typeof data?.server_time === 'string' ? isoMillis(data.server_time) : null
  if (ms === null) return
  serverClock.value = { serverMs: ms, localMs: Date.now() }
  openedAtMs.value = Date.now()
}
const ageNowMs = computed(() => props.nowMs || clockReadingMs(serverClock.value, openedAtMs.value))
// FJ2-9 (O-P-01): a blocked exit says the page's one reason; FJ2-6 (ADR-330 (60), (63)): with the market closed the dialog says ONE thing, the server's closed line; "the server prices the exit when you confirm" would promise a confirm that cannot happen
const ageLine = computed(() => (marketState.value === 'closed' || props.blocked ? { state: '', text: '' } : priceAgeLine(rows.value, { nowMs: ageNowMs.value, notLive: !!props.notLiveLine })))

// GC-TP step 3b2: the title says what the list holds (adds, exits or both)
const title = computed(() => paperDialogTitle(props.orders, props.kind))
const reasons = computed(() => rows.value.map((r) => (!paperLotsOk(r.lots) ? PAPER_LOTS_REASON : (r.kind !== 'exit' && !paperPriceOk(r.price)) ? paperPriceReason(r.price) : '')))
const notLiveAck = ref(false)
// FA2 item 2: reset on the OPENING only; the line's text carries "as of HH:MM" and changes every minute, which must not un-tick the box
watch(() => props.open, () => { notLiveAck.value = false }) // each opening asks again
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
// ADR-330 (60) (owner 27 Nov evening; the same dialog for the builder, Positions and Exit all; pending owner read; FA2 item A: applied to Add to Paper too): the dialog asks the
// server's ONE market-state answer when it opens. Closed: the server's sentence is shown and Confirm is off (it wins over the not-live line).
// The answer cannot be read: Confirm stays off with MARKET_UNREADABLE_TEXT (fail closed; the server still refuses a closed-market exit, ADR-212).
const MARKET_UNREADABLE_TEXT = 'The market status could not be read. Try again in a moment.'
const MARKET_CLOSED_PLAIN = 'The market is closed.' // new wording, pending owner read: used only when the server sent no entries_sentence
const marketState = ref('') // '' (no exit row) | 'checking' | 'open' | 'closed' | 'unreadable'
const marketSentence = ref('')
let marketSeq = 0
const marketLine = computed(() => (marketState.value === 'closed' ? marketSentence.value : marketState.value === 'unreadable' ? MARKET_UNREADABLE_TEXT : ''))
// #872 (FA2): while open, the dialog asks again every MARKET_REASK_MS (09:14:50 stays grey after 09:15; 15:29:55 keeps Confirm on after 15:30).
// A timed re-ask is "background": no 'checking' flicker, and a failed or ambiguous answer keeps the last one (nothing new is said).
// The first ask of an opening and the ask at Confirm stay fail-closed (an unreadable answer turns Confirm off with MARKET_UNREADABLE_TEXT).
const MARKET_REASK_MS = 15000
async function askMarket(background = false) {
  const seq = ++marketSeq
  if (!props.open || !rows.value.length) { marketState.value = ''; marketSentence.value = ''; return }
  if (!background) { marketState.value = 'checking'; marketSentence.value = '' }
  try {
    const { data } = await api.get('/market/exit-state')
    if (seq !== marketSeq) return
    noteServerTime(data)
    if (data?.closed === false) { marketState.value = 'open'; marketSentence.value = '' }
    else if (data?.closed === true && !rows.value.some((r) => r.kind === 'exit')) { // FD3: an entry-only dialog (Add to Paper) says the ENTRIES wording; absent, the plain sentence (never the exits wording)
      marketState.value = 'closed'
      marketSentence.value = typeof data.entries_sentence === 'string' && data.entries_sentence.trim() ? data.entries_sentence : MARKET_CLOSED_PLAIN
    }
    else if (data?.closed === true && typeof data.sentence === 'string' && data.sentence) { marketState.value = 'closed'; marketSentence.value = data.sentence }
    else if (!background || marketState.value === 'checking') marketState.value = 'unreadable' // ambiguous or without its sentence: never a guess
  } catch { if (seq === marketSeq && (!background || marketState.value === 'checking')) marketState.value = 'unreadable' }
}
let marketTimer = null
const stopMarketTimer = () => { clearInterval(marketTimer); marketTimer = null }
watch(() => props.open && rows.value.length > 0, (on) => {
  stopMarketTimer()
  if (on) marketTimer = setInterval(() => { openedAtMs.value = Date.now(); askMarket(true) }, MARKET_REASK_MS) // the age line is told against the latest tick
}, { immediate: true })
onBeforeUnmount(stopMarketTimer)
const exitWarning = ref('')
const exitState = ref('')
let askSeq = 0
async function askExitRisk() {
  const seq = ++askSeq
  // the WHOLE basket (exits and entries) is judged on the legs after all of it; rows not yet valid wait for the user's edit
  const basket = props.open && props.strategyId && rows.value.some((r) => r.kind === 'exit') ? rows.value : []
  if (!basket.length) { exitState.value = ''; exitWarning.value = ''; return }
  // FJ2-4 (D-TG-2): a row not yet valid (an Add with no usable price: a leg moved to another expiry has no live or planned price) means no judgment can be asked yet;
  // the row's own reason says what to fix and Confirm is off by `ready`, so the dialog says nothing here instead of "Checking..." for ever
  if (basket.some((r) => !paperLotsOk(r.lots) || (r.kind !== 'exit' && !paperPriceOk(r.price)))) { exitState.value = ''; exitWarning.value = ''; return }
  exitState.value = 'checking'
  let state = 'unchecked'
  let line = ''
  try {
    const { data } = await api.get(`/paper/strategies/${props.strategyId}/exit-risk`, { params: { orders: JSON.stringify(basket.map(orderOf)) } })
    noteServerTime(data)
    if (data?.state === 'no') state = ''
    else if (data?.state === 'yes' && typeof data.warning_text === 'string' && data.warning_text) { state = 'risk'; line = data.warning_text }
  } catch { state = 'unchecked' }
  if (seq === askSeq) { exitState.value = state; exitWarning.value = line }
}
let openSeq = 0 // review F1: counts openings / new lists
watch(() => [props.open, props.orders], () => { openSeq += 1; askMarket() }, { immediate: true }) // once per opening / new list, not per typed edit
watch(() => [props.open, props.orders, props.strategyId, rows.value.map((r) => `${r.lots}/${r.price}`).join()], askExitRisk, { immediate: true })

// D-03 part B: the lines naming each armed index exit against the legs after these orders (the server words them). A read that
// fails shows "Could not check your armed exits."; rows not yet valid show nothing; the exit stays armed either way and the panel marks it after the change.
const ARMED_UNCHECKED = 'Could not check your armed exits.' // pending owner read (frontend text, pinned by paper-armed-exits.test.js)
const armedLines = ref([])
const armedUnchecked = ref(false)
let armedSeq = 0
// FJ2-4 + Opus round 2 (R2-1): the server judges every line on the legs after ALL the rows, so the question always carries the WHOLE basket, and a line is shown only for the very
// basket it was asked for (`armedSigAsked` = the rows' contract / side / lots / kind at the time of the ask). An Add with no usable price (a leg moved to another expiry has no live or
// planned price) is sent with the smallest tick, ARMED_ASK_TICK: the read-only question reads contracts, sides and units only, never a price, and that value is never shown or sent as an order.
const ARMED_ASK_TICK = '0.05'
const armedSigOf = (list) => list.map((r) => `${r.contract_id}|${r.side}|${String(r.lots).trim()}|${r.kind}`).join(';')
const armedSigNow = computed(() => armedSigOf(rows.value))
const armedSigAsked = ref('')
const armedOrderOf = (r) => ({ ...orderOf(r), price: r.kind === 'exit' ? '0' : paperPriceOk(r.price) ? String(r.price).trim() : ARMED_ASK_TICK })
const armedShown = computed(() => (armedSigAsked.value === armedSigNow.value ? armedLines.value : []))
const armedUncheckedShown = computed(() => armedUnchecked.value && armedSigAsked.value === armedSigNow.value)
async function askArmedExits() {
  const seq = ++armedSeq
  const basket = props.open && props.strategyId && rows.value.length && rows.value.every((r) => paperLotsOk(r.lots)) ? rows.value : []
  const sig = armedSigOf(basket)
  let lines = []
  let unchecked = false
  if (basket.length) {
    try {
      const { data } = await api.get(`/paper/strategies/${props.strategyId}/armed-exits`, { params: { orders: JSON.stringify(basket.map(armedOrderOf)) } })
      noteServerTime(data)
      if (Array.isArray(data?.lines)) lines = data.lines.filter((l) => typeof l === 'string' && l)
      else unchecked = true
    } catch { lines = []; unchecked = true }
  }
  if (seq === armedSeq) { armedLines.value = lines; armedUnchecked.value = unchecked; armedSigAsked.value = sig }
}
watch(() => [props.open, props.orders, props.strategyId, rows.value.map((r) => `${r.lots}/${r.price}`).join()], askArmedExits, { immediate: true })

// the rows as they were when the server refused them: Confirm unlocks only once the user has changed something. FJ r3 (FB2 F6): EVERY refused state of this opening is
// remembered (not only the last), so a second refusal keeps Confirm off and going back to an earlier refused list does not offer it again. A refusal is taken when the page's
// post ends (`busy` falls) with the state still 'refused'; a new opening, or any other state, starts again.
const snapshot = () => JSON.stringify([rows.value.map((r) => [r.lots, r.price]), notLiveAck.value]) // the tick changes the request too
const refusedSet = ref(new Set())
watch(() => props.busy, (b, was) => { if (was && !b && props.state === 'refused') refusedSet.value = new Set([...refusedSet.value, snapshot()]) }) // a post ended and the state is still refused: a refusal of THIS list
watch(() => props.open, (o) => { if (o) refusedSet.value = props.state === 'refused' ? new Set([snapshot()]) : new Set() }) // an opening that comes back as refused: this very list is the refused one
const held = ref(false)
let holdTimer = null
watch(() => props.state, (s) => {
  if (s === 'refused') refusedSet.value = new Set([...refusedSet.value, snapshot()])
  else refusedSet.value = new Set()
  clearTimeout(holdTimer)
  held.value = s === 'unknown'
  if (held.value) holdTimer = setTimeout(() => { held.value = false }, props.holdMs)
}, { immediate: true })
// #870: how long the lock has stood; after the server's longest commit window it is said plainly. Never an unlock: `locked` alone decides Confirm.
const lockWindowOver = ref(false)
// F1b (cloud walker, 28 Nov): the age of the lock is counted on the MONOTONIC clock, like the lock itself. The wall age is never trusted: a clock set forward said "Two minutes have passed" at once.
// A lock is stamped when this page first sees it (by its give-up time), so a dialog opened again later on the same page still counts from that first sight.
const seenAt = new Map()
const monoNow = () => { try { const n = globalThis.performance?.now?.(); return Number.isFinite(n) ? n : Date.now() } catch { return Date.now() } }
let windowTimer = null
watch(() => props.locked, (on) => {
  clearTimeout(windowTimer)
  lockWindowOver.value = false
  if (!on) return
  const k = props.lockedAtMs > 0 ? props.lockedAtMs : 0
  if (k === 0 || !seenAt.has(k)) seenAt.set(k, monoNow()) // no give-up time known: a new lock, counted from now
  const age = monoAgeOfAt(props.lockedAtMs) ?? monoNow() - seenAt.get(k) // the lock's own monotonic stamp on this page, else this dialog's first sight
  const left = EXIT_UNKNOWN_WINDOW_MS - age
  if (left <= 0) lockWindowOver.value = true
  else windowTimer = setTimeout(() => { lockWindowOver.value = true }, left)
}, { immediate: true })
onBeforeUnmount(() => { clearTimeout(holdTimer); clearTimeout(windowTimer) })
// I-18: the result line (done, refused, unknown, the page's re-read note) arrives in the pinned status slot; bring it into view
// (the dialog can be taller than a phone screen). Only when a result line exists, never for the empty slot.
const statusSlot = ref(null)
watch(() => [props.state, props.error], async ([s, e]) => {
  if (!s && !e) return
  await nextTick()
  statusSlot.value?.scrollIntoView?.({ block: 'nearest' })
})
const canConfirm = computed(() => {
  if (props.busy || props.blocked || marketState.value === 'checking' || marketState.value === 'closed' || marketState.value === 'unreadable' || exitState.value === 'checking' || (props.notLiveLine && !notLiveAck.value) || !ready.value || props.state === 'placed' || held.value || props.locked) return false
  return !(props.state === 'refused' && refusedSet.value.has(snapshot()))
})

// a UUID (version 4) from the browser's crypto; never a typed or guessed value
const newRequestKey = () => globalThis.crypto.randomUUID?.() ?? ([1e7] + -1e3 + -4e3 + -8e3 + -1e11).replace(/[018]/g, (c) => (c ^ (globalThis.crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (c / 4)))).toString(16))
async function confirm() {
  if (!canConfirm.value) return
  // #872 (ADR-330 (60), ADR-212): the market may have closed while this dialog sat open: ask the server's one answer again and send only on 'open'
  if (rows.value.length > 0) {
    const mine = openSeq // review F1: the opening this press belongs to; a cancel / reopen / new list in between makes the answer late
    openedAtMs.value = Date.now() // review F3: the age line is told against the time of the press
    await askMarket()
    if (mine !== openSeq || marketState.value !== 'open' || !canConfirm.value) return // review F2: whatever turned Confirm off meanwhile is honoured
  }
  // third argument: the not-live line was shown AND ticked (ADR-330 (28)); false otherwise
  const ticked = !!props.notLiveLine && notLiveAck.value === true
  // FA2 item 3 (ADR-017): ONE request key per Confirm (a UUID); the page is to send it as `client_request_id` and re-send only this same key for this Confirm (no page forwards it yet: RESULTS, For the owner lane 2)
  const requestKey = newRequestKey()
  if (heldActive.value) emit('confirm', rows.value.map(orderOf), heldBlock(heldAt.value, heldBroker.value), ticked, requestKey)
  else emit('confirm', rows.value.map(orderOf), null, ticked, requestKey)
}
</script>
