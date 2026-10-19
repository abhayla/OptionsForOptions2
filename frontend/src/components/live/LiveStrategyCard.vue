<!-- One saved strategy followed on the live outcome socket (W-113; REQ-049 AC-4/AC-5/AC-6, ADR-008, ADR-077).
     Every figure is a string the server sent, shown untouched; nothing is parsed or computed here. The strategy's own
     socket (useStrategyLive) pushes the server's outcome; when it drops, the REST outcome route answers with the server's
     own not-live label (this file writes no such sentence). Paused is per card: the latest answer is NOT_CONNECTED, or
     this card's socket is down or gave up. No order or execute control exists here (ADR-002).
     States: loading, ready, unpriced (no leg carries a planned entry), error (the saved strategy would not load). -->
<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import api, { NEUTRAL_PARTS } from '@/services/api'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import { NOT_CONNECTED_LABEL, buildDraft } from '@/lib/legPicker'
import { fetchSavedLegs } from '@/lib/saveDraft'
import { istTime } from '@/lib/displayFormat'
import { useStrategyLive } from '@/composables/useStrategyLive'

const props = defineProps({ strategy: { type: Object, required: true } })

const state = ref('loading') // loading | ready | unpriced | error
const data = ref(null) // the newest outcome answer, as the server sent it
const errorParts = ref(NEUTRAL_PARTS)
let gone = false // set on unmount: a late push or answer is dropped
let draft = null
let seq = 0 // only the newest REST answer is shown

const live = useStrategyLive({
  onPush: (body) => {
    if (gone) return
    seq++ // a REST answer still in flight is obsolete
    data.value = body
  },
  onDown: async () => {
    if (gone || !draft) return
    const mine = ++seq
    try {
      // ADR-077: `fallback: true` makes the server answer the not-live message even if another socket holds the contracts
      const res = await api.post('/strategies/outcome', { ...draft, ux_level: 'standard', fallback: true })
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

onMounted(async () => {
  try {
    const legs = await fetchSavedLegs(api, props.strategy.id)
    if (gone) return
    draft = buildDraft(legs)
    if (!draft) {
      state.value = 'unpriced'
      return
    }
    state.value = 'ready'
    live.follow({ ...draft, ux_level: 'standard' })
  } catch (e) {
    if (gone) return
    errorParts.value = e?.parts ?? NEUTRAL_PARTS
    state.value = 'error'
  }
})
onBeforeUnmount(() => {
  gone = true
  live.stop()
})

const down = computed(() => live.status.value === 'down' || live.status.value === 'off')
const notConnected = computed(() => data.value?.state === 'NOT_CONNECTED')
// AC-6: a card with no live answer is paused; an unpriced card has nothing to follow.
const paused = computed(() => state.value === 'unpriced' || (state.value === 'ready' && (notConnected.value || down.value)))
const showFigures = computed(() => state.value === 'ready' && data.value?.state === 'COMPUTED' && !paused.value)
const refused = computed(() => state.value === 'ready' && data.value?.state === 'REFUSED')
const spotAt = computed(() => (data.value?.spot_at ? istTime(data.value.spot_at) : '-'))
const checkedAt = computed(() => istTime(data.value?.answered_at))
const maxProfit = computed(() => (data.value?.summary?.max_profit_unlimited ? 'Unlimited' : data.value?.summary?.max_profit ?? '-'))
const maxLoss = computed(() => (data.value?.summary?.max_loss_unlimited ? 'Unlimited' : data.value?.summary?.max_loss ?? '-'))
// REQ-049 AC-4: any health other than `available` (also a missing one) is marked with its word.
const healthWord = (leg) => (leg.health === 'available' ? null : leg.health || 'unavailable')
</script>

<template>
  <article
class="rounded border border-line bg-surface p-4" data-testid="live-strategy-card" :data-strategy-id="strategy.id"
           :data-state="state" :data-paused="paused ? 'true' : 'false'" :data-live="live.status.value">
    <header class="flex flex-wrap items-center gap-2">
      <h2 class="text-base font-medium" data-testid="live-strategy-title">Draft {{ strategy.id }}, {{ strategy.underlying }}</h2>
      <span class="text-sm text-ink-muted" data-testid="live-strategy-status">{{ strategy.status }}</span>
      <span v-if="paused" class="text-sm" data-testid="live-paused-badge">⏸ Monitoring paused</span>
      <span v-if="paused" class="inline-flex items-center gap-1 text-sm text-ink-muted" data-testid="live-health-dot" data-health="unknown">
        <span class="inline-block h-2 w-2 rounded-full bg-gray-400" aria-hidden="true"></span>Health unknown
      </span>
    </header>

    <p v-if="state === 'loading'" class="mt-2 text-sm text-ink-muted" data-testid="live-loading">Loading this strategy...</p>
    <ErrorMessage v-else-if="state === 'error'" class="mt-2" :parts="errorParts" compact prefix="live-error" data-testid="live-error" />
    <p v-else-if="state === 'unpriced'" class="mt-2 text-sm" data-testid="live-status-label">{{ NOT_CONNECTED_LABEL }}</p>

    <template v-else>
      <p v-if="notConnected || refused" class="mt-2 text-sm font-medium" data-testid="live-status-label">{{ data.status_label }}</p>
      <p v-if="refused && data.reason" class="mt-1 text-sm" data-testid="live-reason">{{ data.reason }}</p>
      <p v-if="data && !showFigures" class="mt-1 text-sm text-ink-muted">No numbers are shown as live for this strategy.</p>
      <p v-if="data" class="mt-1 text-sm text-ink-muted" data-testid="live-checked-at">Checked at {{ checkedAt }}</p>
      <p v-else class="mt-2 text-sm text-ink-muted" data-testid="live-waiting">Waiting for the first answer...</p>

      <template v-if="showFigures">
        <p v-if="data.output_label" class="mt-2 text-sm" data-testid="live-output-label">{{ data.output_label }}</p>
        <p class="mt-2 text-sm">{{ data.underlying }} level <span class="font-medium" data-testid="live-spot">{{ data.spot_level ?? '-' }}</span>
          at <span data-testid="live-spot-at">{{ spotAt }}</span></p>
        <p class="mt-1 text-sm">Max profit <span data-testid="live-max-profit">{{ maxProfit }}</span>, max loss <span data-testid="live-max-loss">{{ maxLoss }}</span></p>
        <ul class="mt-2 text-sm" data-testid="live-legs">
          <li v-for="leg in data.legs" :key="leg.instrument_id" data-testid="live-leg" :data-health="leg.health ?? 'unavailable'">
            {{ leg.action }} {{ leg.symbol }}: <span data-testid="live-leg-ltp">{{ leg.ltp ?? '-' }}</span>
            <span v-if="healthWord(leg)" class="ml-1 text-ink-muted" data-testid="live-leg-health">({{ healthWord(leg) }})</span>
          </li>
        </ul>
      </template>
    </template>
  </article>
</template>
