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
import { fetchSavedLegs, strategyLabel } from '@/lib/saveDraft'
import { istTime, maxLine, nameFromPool } from '@/lib/displayFormat'
import Chip from '@/components/common/Chip.vue'
import MarketClosedBanner from '@/components/states/MarketClosedBanner.vue'
import { healthSentence } from '@/lib/dataHealthText'
import { useStrategyLive } from '@/composables/useStrategyLive'

// `start` false = waiting in the page's start queue (one card loads at a time); `settled` is emitted once, when this card
// got its first answer, failed, or has nothing to follow - the page then starts the next card.
const props = defineProps({ strategy: { type: Object, required: true }, start: { type: Boolean, default: true } })
const emit = defineEmits(['settled'])

const state = ref(props.start ? 'loading' : 'queued') // queued | loading | ready | unpriced | error
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
const notLive = ref(false) // issue #500: a leg's stored contract is no longer live; nothing is priced
const wasLive = ref(false) // a live push arrived at least once: from then on a socket that is not live pauses the card
let seq = 0 // only the newest REST answer is shown

const live = useStrategyLive({
  onPush: (body) => {
    if (gone) return
    seq++ // a REST answer still in flight is obsolete
    wasLive.value = true
    data.value = body
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

async function begin() {
  if (begun || gone) return
  begun = true
  state.value = 'loading'
  try {
    const legs = await fetchSavedLegs(api, props.strategy.id)
    if (gone) return
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
    if (gone) return
    errorParts.value = e?.parts ?? NEUTRAL_PARTS
    state.value = 'error'
    settle()
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
  live.stop()
})

// down, off, or (after it was live once) connecting again: old figures must not look live while the socket is not live (REQ-049 AC-4)
const down = computed(() => live.status.value === 'down' || live.status.value === 'off' || (wasLive.value && live.status.value !== 'live'))
const notConnected = computed(() => data.value?.state === 'NOT_CONNECTED')
// AC-6: a card with no live answer is paused; an unpriced card has nothing to follow.
// REQ-077 AC-9: FROM_ENTRIES (live data dropped, every leg has an entry) is paused monitoring too; the card shows its two labels only.
const fromEntries = computed(() => state.value === 'ready' && data.value?.state === 'FROM_ENTRIES')
const paused = computed(() => state.value === 'unpriced' || (state.value === 'ready' && (notConnected.value || fromEntries.value || down.value)))
const showFigures = computed(() => state.value === 'ready' && data.value?.state === 'COMPUTED' && !paused.value)
const refused = computed(() => state.value === 'ready' && data.value?.state === 'REFUSED')
const spotAt = computed(() => (data.value?.spot_at ? istTime(data.value.spot_at) : '-'))
const checkedAt = computed(() => istTime(data.value?.answered_at))
// REQ-151/152: the server's display strings ("+7,114", "−5,886") when it sent them; the raw-string line otherwise (unlimited, no maximum)
const moneyLine = (side) => data.value?.summary?.[`max_${side}_display`] ?? maxLine(data.value?.summary, side)
const maxProfit = computed(() => moneyLine('profit'))
const maxLoss = computed(() => moneyLine('loss'))
// ADR-177 / ADR-200 (2): a closed market is one banner with the price's own time; the fetch time and the stale noise are not shown
const closed = computed(() => data.value?.market_closed === true)
const breakevens = computed(() => (data.value?.summary?.breakevens_display ?? []).join(', '))
const hasLots = computed(() => (data.value?.legs ?? []).some((l) => l.lots != null))
const hasEntry = computed(() => (data.value?.legs ?? []).some((l) => (l.planned_entry_display ?? l.planned_entry) != null))
const legName = (leg) => nameFromPool(leg, [], data.value?.underlying) // never the raw trading symbol (issue 297, REQ-151)
// REQ-049 AC-4: any health other than `available` (also a missing one) is marked with its word.
// RD-045: the word is followed by one sentence with its reason (lib/dataHealthText.js).
const healthWord = (leg) => (closed.value ? null : leg.health === 'available' ? null : leg.health || 'unavailable')
</script>

<template>
  <article
class="rounded border border-line bg-surface p-4" data-testid="live-strategy-card" :data-strategy-id="strategy.id"
           :data-state="state" :data-paused="paused ? 'true' : 'false'" :data-live="live.status.value">
    <header class="flex flex-wrap items-baseline gap-2">
      <h2 class="text-base font-semibold" data-testid="live-strategy-title">{{ strategyLabel(strategy, `Draft ${strategy.id}`) }}, {{ strategy.underlying }}</h2>
      <span class="rounded bg-gray-100 px-1.5 text-xs text-ink-muted" data-testid="live-strategy-status">{{ strategy.status }}</span>
      <span v-if="paused" class="text-sm" data-testid="live-paused-badge">⏸ Monitoring paused</span>
      <span v-if="paused" class="inline-flex items-center gap-1 text-sm text-ink-muted" data-testid="live-health-dot" data-health="unknown">
        <span class="inline-block h-2 w-2 rounded-full bg-gray-400" aria-hidden="true"></span>Health unknown
      </span>
      <p v-if="state === 'ready' && data" class="ml-auto text-xs text-ink-muted" data-testid="live-checked-at">Checked at {{ checkedAt }}</p>
    </header>

    <p v-if="live.reconnecting.value" class="mt-2 text-sm font-medium" data-testid="live-reconnecting">{{ live.reconnectingText.value }}</p>
    <p v-if="state === 'queued'" class="mt-2 text-sm text-ink-muted" data-testid="live-queued">Waiting to start...</p>
    <p v-else-if="state === 'loading'" class="mt-2 text-sm text-ink-muted" data-testid="live-loading">Loading this strategy...</p>
    <ErrorMessage v-else-if="state === 'error'" class="mt-2" :parts="errorParts" compact prefix="live-error" data-testid="live-error" />
    <p v-else-if="state === 'unpriced'" class="mt-2 text-sm" data-testid="live-status-label" :data-not-live="notLive ? 'true' : 'false'">{{ notLive ? LEG_NOT_LIVE_LABEL : NOT_CONNECTED_LABEL }}</p>

    <template v-else>
      <p v-if="notConnected || refused || fromEntries" class="mt-2 text-sm font-medium" data-testid="live-status-label">{{ data.status_label }}</p>
      <p v-if="fromEntries && data.output_label" class="mt-1 text-sm" data-testid="live-output-label">{{ data.output_label }}</p>
      <p v-if="refused && data.reason" class="mt-1 text-sm" data-testid="live-reason">{{ data.reason }}</p>
      <p v-if="data && !showFigures" class="mt-1 text-sm text-ink-muted">No numbers are shown as live for this strategy.</p>
      <p v-if="!data" class="mt-2 text-sm text-ink-muted" data-testid="live-waiting">Waiting for the first answer...</p>

      <template v-if="showFigures">
        <p v-if="data.output_label" class="mt-2 text-sm" data-testid="live-output-label">{{ data.output_label }}</p>
        <MarketClosedBanner v-if="closed" class="mt-2" :prices-at="data.last_price_at" />
        <p class="mt-2 text-sm">{{ data.underlying }} <span class="font-semibold" data-testid="live-spot">{{ data.spot_level ?? '-' }}</span>
          <template v-if="!closed">at <span data-testid="live-spot-at">{{ spotAt }}</span></template></p>
        <p class="mt-1 text-xs text-ink-muted">
          <template v-if="breakevens"><span data-testid="live-breakevens">Breakeven: {{ breakevens }}</span> · </template>Max Profit: <span class="text-profit" data-testid="live-max-profit">{{ maxProfit }}</span> · Max Loss: <span class="text-loss" data-testid="live-max-loss">{{ maxLoss }}</span>
        </p>
        <table class="mt-2 w-full text-sm" data-testid="live-legs">
          <thead class="text-xs text-ink-muted">
            <tr><th class="text-left font-normal">Instrument</th><th v-if="hasLots" class="text-right font-normal">Lots</th><th v-if="hasEntry" class="text-right font-normal">Planned entry</th><th class="text-right font-normal">LTP</th></tr>
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
