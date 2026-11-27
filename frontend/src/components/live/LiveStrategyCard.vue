<!-- One saved strategy followed on the live outcome socket (W-113; REQ-049 AC-4/AC-5/AC-6, ADR-008, ADR-077).
     Every figure is a string the server sent, shown untouched; nothing is parsed or computed here. The strategy's own
     socket (useStrategyLive) pushes the server's outcome; when it drops, the REST outcome route answers with the server's
     own not-live label (this file writes no such sentence). Paused is per card: the latest answer is NOT_CONNECTED, or
     this card's socket is down or gave up. No order or execute control exists here (ADR-002).
     States: queued, loading, ready, unpriced (no leg carries a planned entry), error (the saved strategy would not load). -->
<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import api, { NEUTRAL_PARTS } from '@/services/api'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import { LEG_NOT_LIVE_LABEL, NOT_CONNECTED_LABEL, buildDraft } from '@/lib/legPicker'
import { fetchSavedLegs, strategyListLabel } from '@/lib/saveDraft'
import { PAPER_BOOK_UNREADABLE, readPaperBook } from '@/lib/paperDrafts'
import PnlLine from '@/components/live/PnlLine.vue'
import { CARD_LEGS_AS_SAVED_TEXT, CARD_QUEUED_TEXT } from '@/lib/sharedStateText'
import { isRunning, strategyStatusWord } from '@/lib/strategyStatus'
import { builderLinkOf, paperExitLinkOf, paperStopsLinkOf } from '@/lib/strategyLinks'
import { istTime, maxLine, nameFromPool } from '@/lib/displayFormat'
import { RouterLink } from 'vue-router'
import Chip from '@/components/common/Chip.vue'
import { PRICE_GREYED_CLASS } from '@/lib/priceState'
import { healthSentence } from '@/lib/dataHealthText'
import { ENTRY_PRICE_LABEL } from '@/lib/chartCard'
import { useStrategyLive } from '@/composables/useStrategyLive'
import MonitoringBadge from '@/components/common/MonitoringBadge.vue'
import { KIND_UNREAD_LINE } from '@/lib/positionKind'

// `start` false = waiting in the page's start queue (one card loads at a time); `settled` is emitted once, when this card
// got its first answer, failed, or has nothing to follow - the page then starts the next card.
const props = defineProps({ strategy: { type: Object, required: true }, start: { type: Boolean, default: true }, pnl: { type: Object, default: null }, monitoring: { type: Object, default: null }, quiet: { type: Boolean, default: false },
  greyed: { type: Boolean, default: false }, showLine: { type: Boolean, default: true } }) // ADR-330 (56): the page's priceScope decides both
const emit = defineEmits(['settled', 'closed', 'affected'])

const state = ref(props.start ? 'loading' : 'queued') // queued | loading | ready | unpriced | error
const legsAsSaved = ref(false)
let begun = false
let settledSent = false
const settle = () => {
  if (settledSent) return
  settledSent = true
  emit('settled')
}
const data = ref(null) // the newest outcome answer, as the server sent it
const errorParts = ref(NEUTRAL_PARTS)
let gone = false // set on unmount: a late push or answer is dropped
let draft = null
const expiredText = ref(null) // D-40: the server's sentence for a trade whose open legs are on expired contracts
// ADR-330 (56): this card has a contract with no price (and no server reason of its own): the page counts these (priceScope) and decides who says what
watch(() => state.value === 'unpriced' && expiredText.value === null, (v) => emit('affected', props.strategy.id, v), { immediate: true })
const notLive = ref(false) // issue #500: a leg's stored contract is no longer live; nothing is priced
const wasLive = ref(false) // a live push arrived at least once: from then on a socket that is not live pauses the card
let seq = 0 // only the newest REST answer is shown
// D-06/D-07 (ADR-008, ADR-263): a PAPER trade's max profit / max loss / breakevens / total are the paper reply's own figures (the
// ones the builder tiles read), never a second computation from the open legs. `paperBook` = the newest GET /paper/strategies/{id}
// answer; `bookFailed` = the newest read of it failed (dashes, never the open-legs outcome).
const paperBook = ref(null)
const bookFailed = ref(false)
let bookBusy = false
let bookReadAt = 0
const BOOK_REREAD_MS = 5000
async function rereadBook() {
  if (gone || !paperBook.value || bookBusy || Date.now() - bookReadAt < BOOK_REREAD_MS) return
  bookBusy = true
  try {
    const body = (await api.get(`/paper/strategies/${props.strategy.id}`)).data
    if (gone) return
    if (body && typeof body === 'object' && Array.isArray(body.orders)) { paperBook.value = body; bookFailed.value = false } else bookFailed.value = true
  } catch {
    if (!gone) bookFailed.value = true
  } finally {
    bookBusy = false
    bookReadAt = Date.now()
  }
}

const live = useStrategyLive({
  onPush: (body) => {
    if (gone) return
    seq++ // a REST answer still in flight is obsolete
    wasLive.value = true
    data.value = body
    rereadBook()
    settle()
  },
  onDown: async () => {
    if (gone || !draft) return
    settle()
    const mine = ++seq
    try {
      // ADR-077: `fallback: true` makes the server answer the not-live message even if another socket holds the contracts
      const res = await api.post('/strategies/outcome', { ...draft, fallback: true })
      if (gone || mine !== seq) return
      data.value = res.data
    } catch (e) {
      if (gone || mine !== seq) return
      data.value = null // never keep old numbers on screen after the socket dropped (REQ-049 AC-4)
      errorParts.value = e?.parts ?? NEUTRAL_PARTS
      state.value = 'error'
    }
  },
})

// D-41: a card never stays on "Loading this strategy...": if its first reads give no answer in this time it says it could not load
// (the client's own timeout is 10 s per request; a card makes several in a row). A late answer after that is dropped.
const LOADING_MAX_MS = 25000
let loadingTimer = null
let attempt = 0
function giveUpLoading(mine) {
  if (gone || mine !== attempt || state.value !== 'loading') return
  // the attempt stays valid: a read that succeeds later replaces this error with the figures
  errorParts.value = NEUTRAL_PARTS
  state.value = 'error'
  settle()
}
async function begin() {
  if (begun || gone) return
  begun = true
  const mine = ++attempt
  clearTimeout(loadingTimer)
  loadingTimer = setTimeout(() => giveUpLoading(mine), LOADING_MAX_MS)
  expiredText.value = null // D-40: a later begin() starts without the last expiry sentence
  state.value = 'loading'
  try {
    // issue 16: a running trade follows the legs it holds NOW (its paper book's net position), not the legs it was saved with
    const read = isRunning(props.strategy) ? await readPaperBook(api, props.strategy.id) : { kind: 'plan' }
    if (gone || mine !== attempt) return
    if (read.kind === 'unpriced') { // D-40: the open legs are on expired contracts; show the server's own reason, price nothing
      paperBook.value = read.book
      expiredText.value = serverText(read.book.unpriced_text) // only the expiry sentence; no other reason is borrowed
      notLive.value = true // with no sentence the card still says the contract is no longer live, never "not connected"
      state.value = 'unpriced'
      settle()
      return
    }
    const legs = read.kind === 'paper' ? read.net : await fetchSavedLegs(api, props.strategy.id)
    if (gone || mine !== attempt) return
    // a real trade has no practice book and the server sends no current-legs field for it: the saved legs, said plainly
    paperBook.value = read.kind === 'paper' ? read.book : null
    bookReadAt = Date.now()
    legsAsSaved.value = isRunning(props.strategy) && read.kind !== 'paper'
    draft = buildDraft(legs)
    if (!draft) {
      notLive.value = legs.some((l) => l.not_live)
      state.value = 'unpriced'
      settle()
      return
    }
    state.value = 'ready'
    live.follow({ ...draft })
  } catch (e) {
    if (gone || mine !== attempt) return
    errorParts.value = e?.parts ?? NEUTRAL_PARTS
    state.value = 'error'
    settle()
  } finally {
    if (mine === attempt && state.value !== 'loading') clearTimeout(loadingTimer)
  }
}
onMounted(() => {
  if (props.start) begin()
})
watch(() => props.start, (v) => {
  if (v) begin()
})
onBeforeUnmount(() => {
  gone = true
  clearTimeout(loadingTimer)
  live.stop()
})

// down, off, or (after it was live once) connecting again: old figures must not look live while the socket is not live (REQ-049 AC-4)
const down = computed(() => live.status.value === 'down' || live.status.value === 'off' || (wasLive.value && live.status.value !== 'live'))
const notConnected = computed(() => data.value?.state === 'NOT_CONNECTED')
// AC-6: a card with no live answer is paused; an unpriced card has nothing to follow.
// REQ-077 AC-9: FROM_ENTRIES (live data dropped, every leg has an entry) is paused monitoring too; the card shows its two labels only.
const fromEntries = computed(() => state.value === 'ready' && data.value?.state === 'FROM_ENTRIES')
const paused = computed(() => state.value === 'unpriced' || (state.value === 'ready' && (notConnected.value || fromEntries.value || down.value)))
// the worker's own answer says paused: its badge (with reason and since) replaces the card's local one
const serverPaused = computed(() => isRunning(props.strategy) && props.monitoring != null && props.monitoring.watch_state !== 'active')
const showFigures = computed(() => state.value === 'ready' && data.value?.state === 'COMPUTED' && !paused.value)
const refused = computed(() => state.value === 'ready' && data.value?.state === 'REFUSED')
const spotAt = computed(() => (data.value?.spot_at ? istTime(data.value.spot_at) : '-'))
const checkedAt = computed(() => istTime(data.value?.answered_at))
// REQ-151/152: the server's display strings ("+7,114", "−5,886") when it sent them; the raw-string line otherwise (unlimited, no maximum)
const moneyLine = (side) => data.value?.summary?.[`max_${side}_display`] ?? maxLine(data.value?.summary, side)
const dash = '-'
const serverText = (v) => (typeof v === 'string' && v.trim() !== '' ? v.trim() : v && typeof v === 'object' && typeof v.what_happened === 'string' ? v.what_happened : null)
const maxProfit = computed(() => (paperBook.value ? (bookFailed.value ? dash : paperBook.value.max_profit_text ?? dash) : moneyLine('profit')))
const maxLoss = computed(() => (paperBook.value ? (bookFailed.value ? dash : paperBook.value.max_loss_text ?? dash) : moneyLine('loss')))
// the paper reply's own basis sentences and the reason beside a dash (builder tile = this card: one source)
const figuresReason = computed(() => (!paperBook.value ? null : bookFailed.value ? PAPER_BOOK_UNREADABLE
  : paperBook.value.max_profit_text == null ? serverText(paperBook.value.extremes_reason_text) : null))
const figuresBasis = computed(() => (!paperBook.value || bookFailed.value ? [] : [serverText(paperBook.value.extremes_charges_text), serverText(paperBook.value.breakevens_basis_text)].filter(Boolean)))
// ADR-177 / ADR-200 (2): a closed market is one banner with the price's own time; the fetch time and the stale noise are not shown
const closed = computed(() => data.value?.market_closed === true)
// User test 2026-10-30: the page shows ONE market-closed banner (ADR-177); the card reports the closed state and price time
watch(closed, (now) => { if (now) emit('closed', data.value.last_price_at) })
const breakevens = computed(() => ((paperBook.value ? (bookFailed.value ? [] : paperBook.value.breakevens_display) : data.value?.summary?.breakevens_display) ?? []).join(', '))
const hasLots = computed(() => (data.value?.legs ?? []).some((l) => l.lots != null))
const hasEntry = computed(() => (data.value?.legs ?? []).some((l) => (l.planned_entry_display ?? l.planned_entry) != null))
// S-14: links only while the card is not in the error state; a Running (placed paper) strategy shows its fill as "Entry price"
// ADR-330 (19): name, then (#id, expiry) from the list reply's first leg
const listLabel = computed(() => strategyListLabel({ name: props.strategy.name, id: props.strategy.id, expiries: [props.strategy.first_leg?.expiry], fallback: `Draft ${props.strategy.id}` }))
const openLink = computed(() => (state.value === 'error' ? null : builderLinkOf(props.strategy.id)))
// ADR-330 (64): Exit and Stops only on a PAPER position; real and unreadable show the server's one line instead (fail closed)
const paperPosition = computed(() => props.strategy.position_kind === 'paper')
const kindLine = computed(() => (isRunning(props.strategy) && !paperPosition.value && props.strategy.position_kind !== 'none' ? props.strategy.position_kind_text || KIND_UNREAD_LINE : null))
const exitLink = computed(() => (state.value !== 'error' && isRunning(props.strategy) && paperPosition.value ? paperExitLinkOf(props.strategy.id) : null))
const stopsLink = computed(() => (state.value !== 'error' && isRunning(props.strategy) && paperPosition.value ? paperStopsLinkOf(props.strategy.id) : null))
const entryHead = computed(() => (isRunning(props.strategy) ? ENTRY_PRICE_LABEL : 'Planned entry'))
const legName = (leg) => nameFromPool(leg, [], data.value?.underlying) // never the raw trading symbol (issue 297, REQ-151)
// REQ-049 AC-4: any health other than `available` (also a missing one) is marked with its word.
// RD-045: the word is followed by one sentence with its reason (lib/dataHealthText.js).
const healthWord = (leg) => (closed.value ? null : leg.health === 'available' ? null : leg.health || 'unavailable')
</script>

<template>
  <article
class="rounded border border-line bg-surface p-4" :class="greyed ? PRICE_GREYED_CLASS : ''" data-testid="live-strategy-card" :data-strategy-id="strategy.id"
           :data-state="state" :data-paused="paused ? 'true' : 'false'" :data-live="live.status.value">
    <header class="flex flex-wrap items-baseline gap-2">
      <!-- S-14: the name opens the strategy (not in the error state); a running paper strategy also links to its Stops. Exit links to the Paper list, whose own exit dialog (the one exit door) opens; the card holds no exit code. -->
      <h2 class="text-base font-semibold"><component :is="openLink ? RouterLink : 'span'" v-bind="openLink ? { to: openLink, class: 'hover:underline', 'data-testid': 'live-strategy-open' } : {}"><span data-testid="live-strategy-title">{{ listLabel }}, {{ strategy.underlying }}</span></component></h2>
      <span class="rounded bg-gray-100 px-1.5 text-xs text-ink-muted" data-testid="live-strategy-status">{{ strategyStatusWord(strategy) }}</span>
      <!-- GC-MU A3 (ADR-230 (2)): the server's words for the open adjustment records; none at 0 or when unread -->
      <RouterLink v-if="strategy.open_opportunities_text" :to="{ path: '/positions/adjustment-opportunities', query: { strategy: String(strategy.id) } }" class="text-sm text-accent underline" data-testid="live-opportunity-mark">{{ strategy.open_opportunities_text }}</RouterLink>
      <RouterLink v-if="stopsLink" :to="stopsLink" class="text-sm text-accent underline" data-testid="live-strategy-stops">Stops</RouterLink>
      <RouterLink v-if="exitLink" :to="exitLink" class="text-sm text-accent underline" data-testid="live-strategy-exit">Exit</RouterLink>
      <span v-if="paused && !serverPaused" class="text-sm" data-testid="live-paused-badge">⏸ Monitoring paused</span>
      <!-- Lane Y item 1: the worker's own answer (REQ-115 AC-6), for a running trade whose card has no local pause of its own -->
      <MonitoringBadge v-if="isRunning(strategy)" :entry="monitoring" />
      <span v-if="paused && !serverPaused" class="inline-flex items-center gap-1 text-sm text-ink-muted" data-testid="live-health-dot" data-health="unknown">
        <span class="inline-block h-2 w-2 rounded-full bg-gray-400" aria-hidden="true"></span>Health unknown
      </span>
      <p v-if="state === 'ready' && data && !quiet" class="ml-auto text-xs text-ink-muted" data-testid="live-checked-at">Checked at {{ checkedAt }}</p>
    </header>

    <!-- D-41: the trade's P&L from the Positions page's function, in every state of the card (the page reads it once for all cards) -->
    <p v-if="kindLine" class="mt-2 text-sm" data-testid="live-position-kind-line">{{ kindLine }}</p>
    <PnlLine v-if="isRunning(strategy)" class="mt-2" :cell="pnl" testid="live-pnl" />
    <p v-if="legsAsSaved" class="mt-2 text-xs text-ink-muted" data-testid="live-legs-as-saved">{{ CARD_LEGS_AS_SAVED_TEXT }}</p>
    <p v-if="live.reconnecting.value" class="mt-2 text-sm font-medium" data-testid="live-reconnecting">{{ live.reconnectingText.value }}</p>
    <p v-if="state === 'queued'" class="mt-2 text-sm text-ink-muted" data-testid="live-queued">{{ CARD_QUEUED_TEXT }}</p>
    <p v-else-if="state === 'loading'" class="mt-2 text-sm text-ink-muted" data-testid="live-loading">Loading this strategy...</p>
    <ErrorMessage v-else-if="state === 'error'" class="mt-2" :parts="errorParts" compact prefix="live-error" data-testid="live-error" />
    <template v-else-if="state === 'unpriced'">
      <!-- ADR-330 (56): the generic "no price" sentence is the page notice's job when several strategies are affected; the server's own expiry reason always shows -->
      <p v-if="expiredText || showLine" class="mt-2 text-sm" data-testid="live-status-label" :data-not-live="notLive ? 'true' : 'false'">{{ expiredText ?? (notLive ? LEG_NOT_LIVE_LABEL : NOT_CONNECTED_LABEL) }}</p>
    </template>

    <template v-else>
      <p v-if="notConnected || refused || fromEntries" class="mt-2 text-sm font-medium" data-testid="live-status-label">{{ data.status_label }}</p>
      <p v-if="fromEntries && data.output_label" class="mt-1 text-sm" data-testid="live-output-label">{{ data.output_label }}</p>
      <p v-if="refused && data.reason" class="mt-1 text-sm" data-testid="live-reason">{{ data.reason }}</p>
      <p v-if="data && !showFigures" class="mt-1 text-sm text-ink-muted">No numbers are shown as live for this strategy.</p>
      <p v-if="!data" class="mt-2 text-sm text-ink-muted" data-testid="live-waiting">Waiting for the first answer...</p>

      <template v-if="showFigures">
        <p v-if="data.output_label" class="mt-2 text-sm" data-testid="live-output-label">{{ data.output_label }}</p>
        <p class="mt-2 text-sm">{{ data.underlying }} <span class="font-semibold" data-testid="live-spot">{{ data.spot_level ?? '-' }}</span>
          <template v-if="!closed">{{ ' ' }}at <span data-testid="live-spot-at">{{ spotAt }}</span></template></p>
        <p class="mt-1 text-xs text-ink-muted">
          <template v-if="breakevens"><span data-testid="live-breakevens">Breakeven: {{ breakevens }}</span> · </template>Max Profit: <span class="text-profit" data-testid="live-max-profit">{{ maxProfit }}</span> · Max Loss: <span class="text-loss" data-testid="live-max-loss">{{ maxLoss }}</span>
        </p>
        <p v-if="figuresReason" class="text-xs text-ink-muted" data-testid="live-figures-reason">{{ figuresReason }}</p>
        <p v-for="line in figuresBasis" :key="line" class="text-xs text-ink-muted" data-testid="live-figures-basis">{{ line }}</p>
        <table class="num-table mt-2 w-full text-sm" data-testid="live-legs">
          <thead class="text-xs text-ink-muted">
            <tr><th class="text-left font-normal">Instrument</th><th v-if="hasLots" class="text-right font-normal">Lots</th><th v-if="hasEntry" class="text-right font-normal">{{ entryHead }}</th><th class="text-right font-normal">LTP</th></tr>
          </thead>
          <tbody>
            <tr v-for="leg in data.legs" :key="leg.instrument_id" data-testid="live-leg" :data-health="leg.health ?? 'unavailable'">
              <td class="py-1"><Chip :kind="leg.action === 'BUY' ? 'buy' : 'sell'" :label="leg.action === 'BUY' ? 'B' : 'S'" /><span class="sr-only">{{ leg.action }}</span> {{ legName(leg) }}
                <span v-if="healthWord(leg)" class="ml-1 text-ink-muted" data-testid="live-leg-health">({{ healthWord(leg) }})</span>
                <span v-if="healthWord(leg)" class="block text-xs text-ink-muted" data-testid="live-leg-health-reason">{{ healthSentence(healthWord(leg)) }}</span></td>
              <td v-if="hasLots" class="text-right tabular-nums">{{ leg.lots ?? '-' }}</td>
              <td v-if="hasEntry" class="text-right tabular-nums">{{ leg.planned_entry_display ?? leg.planned_entry ?? '-' }}</td>
              <td class="text-right tabular-nums" data-testid="live-leg-ltp">{{ leg.ltp_display ?? leg.ltp ?? '-' }}</td>
            </tr>
          </tbody>
        </table>
      </template>
    </template>
  </article>
</template>
