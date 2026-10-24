<!-- The Execute screen (W-104; REQ-056 AC-1, REQ-073 AC-1/AC-3; ADR-054, ADR-097, ADR-003, ADR-008).
     1. Live first: the saved strategy's legs are followed on the platform's live socket (useStrategyLive, W-065: the
        server subscribes them in full mode). Execute is called only while the latest push is a live outcome for every
        leg; not live within LIVE_WAIT_MS -> the catalogue's not-live message, and Execute is never called.
     2. The owner picks entry or exit (the API gives no held flag, so both are offered; the route refuses the wrong one
        with its catalogue message). The reply's orders and cost are shown as the strings given.
     3. Kite's page opens only on the owner's click (BasketForm); then "Check with Zerodha" reads the result (ReturnCheck).
     New file, copy from: none (legacy-reuse row 149's BasketOrderModal builds the basket in the browser; ADR-054). -->
<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import api, { NEUTRAL_PARTS } from '@/services/api'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import ExecuteCost from '@/components/execution/ExecuteCost.vue'
import BasketForm from '@/components/execution/BasketForm.vue'
import ReturnCheck from '@/components/execution/ReturnCheck.vue'
import { useStrategyLive } from '@/composables/useStrategyLive'
import { buildDraft } from '@/lib/legPicker'
import { matchesLegs } from '@/lib/liveMatch'
import { fetchSavedDraft, plainName } from '@/lib/saveDraft'
import { createNewestWins, isSuperseded } from '@/lib/newestWins'
import { LIVE_WAIT_MS, NOT_LIVE_PARTS, basketFields, isLiveOutcome } from '@/lib/execute'

const props = defineProps({ waitMs: { type: Number, default: LIVE_WAIT_MS } })

const route = useRoute()
const strategyId = computed(() => (/^[1-9]\d{0,17}$/.test(String(route.params.id)) ? String(route.params.id) : null)) // an id string, never parsed
const strategyName = ref(null) // REQ-134: the saved read's name (shown without its quotes); null keeps the id text
const phase = ref('loading') // loading | waiting-live | live | not-live | executing | prepared | error
const liveNow = ref(false)
const reply = ref(null)
const sent = ref(false)
const errorParts = ref(null)
let draft = null
let revision = null // W-151 (REQ-119 AC-5): the saved revision this review was loaded at; Execute names it
let liveTimer = null
const guard = createNewestWins() // REQ-119: a prepare reply that is not the newest request's is dropped

const live = useStrategyLive({
  onPush: (body) => {
    if (!draft || !matchesLegs(body, draft)) return // a push for another strategy is never read
    liveNow.value = isLiveOutcome(body)
    if (liveNow.value && (phase.value === 'waiting-live' || phase.value === 'not-live')) {
      clearTimeout(liveTimer)
      everLive.value = true
      errorParts.value = null // live again: the not-live message goes, the actions return
      phase.value = 'live'
    } else if (!liveNow.value && phase.value === 'live') {
      notLive()
    }
  },
  onDown: () => {
    liveNow.value = false
    if (phase.value === 'live') notLive() // dropped after going live: say so and disable, never a silent button
  },
})
const everLive = ref(false)

function notLive() {
  errorParts.value = NOT_LIVE_PARTS
  phase.value = 'not-live'
}

onMounted(async () => {
  if (strategyId.value === null) {
    errorParts.value = NEUTRAL_PARTS
    phase.value = 'error'
    return
  }
  try {
    const saved = await fetchSavedDraft(api, strategyId.value) // the one saved-strategy read: legs and revision
    revision = saved.revision
    strategyName.value = plainName(saved.name)
    draft = buildDraft(saved.legs)
  } catch (e) {
    errorParts.value = e?.parts ?? NEUTRAL_PARTS
    phase.value = 'error'
    return
  }
  if (!draft) return notLive() // no leg has a planned entry: nothing to follow live
  phase.value = 'waiting-live'
  liveTimer = setTimeout(() => {
    if (phase.value === 'waiting-live') notLive()
  }, props.waitMs)
  live.follow({ ...draft })
})
onBeforeUnmount(() => clearTimeout(liveTimer))

// REQ-119 AC-5 (23a MINOR 2): after the 409 the page keeps the old revision, so every retry would be refused until a reload.
// Re-read the saved strategy once (the page's own read) and take its revision and legs; the four-part message stays shown.
async function rereadAfterConflict() {
  try {
    const saved = await fetchSavedDraft(api, strategyId.value)
    const next = buildDraft(saved.legs)
    const changed = JSON.stringify(next) !== JSON.stringify(draft)
    revision = saved.revision
    draft = next
    if (changed) {
      // other legs than the ones reviewed: they are followed live again before Execute is offered
      liveNow.value = false
      if (!draft) return notLive()
      phase.value = 'waiting-live'
      clearTimeout(liveTimer)
      liveTimer = setTimeout(() => {
        if (phase.value === 'waiting-live') notLive()
      }, props.waitMs)
      live.follow({ ...draft })
    }
  } catch {
    // the re-read failed: the refusal stays on screen and the old revision stays refused by the server (fail closed)
  }
}

async function prepare(action) {
  if (phase.value !== 'live' || !liveNow.value) return // the live socket must hold every leg first
  phase.value = 'executing'
  errorParts.value = null
  const mine = guard.next('execute')
  try {
    const data = (await api.post(`/strategies/${strategyId.value}/execute`, { action, revision, seq: mine.seq }, { signal: mine.signal })).data
    if (!guard.claim('execute', data, mine)) return // an older reply is dropped and logged, never shown
    if (!basketFields(data)) throw new Error('unreadable basket') // fail closed: no form for a reply we cannot read
    reply.value = data
    phase.value = 'prepared'
  } catch (e) {
    if (isSuperseded(e) || !guard.isNewest('execute', mine)) return // cancelled or older: no error text, no state change
    reply.value = null // a refusal (e.g. 409 "Your plan changed") keeps no plan on screen
    errorParts.value = e?.parts ?? NEUTRAL_PARTS
    phase.value = liveNow.value ? 'live' : 'not-live' // the socket may have dropped while Execute was answering
    if (e?.status === 409) await rereadAfterConflict()
  } finally {
    guard.settle('execute', mine)
  }
}
</script>

<template>
  <section class="p-4" data-testid="execute-screen" :data-phase="phase">
    <h1 class="text-xl font-semibold" data-testid="page-title">Execute Strategy {{ strategyName ?? strategyId ?? '' }}</h1>
    <p v-if="live.reconnecting.value" class="mt-2 text-sm font-medium" data-testid="live-reconnecting">{{ live.reconnectingText.value }}</p>
    <p v-if="phase === 'loading' || phase === 'waiting-live'" data-testid="execute-waiting">Waiting for live prices for every leg...</p>
    <ErrorMessage v-if="errorParts" class="mt-2" :parts="errorParts" prefix="execute-error" />

    <div v-if="!reply && (phase === 'live' || phase === 'executing' || (phase === 'not-live' && everLive))" class="mt-2 flex gap-2" data-testid="execute-actions">
      <button type="button" data-testid="prepare-entry" class="rounded border border-line px-3 py-1" :disabled="phase !== 'live'" @click="prepare('ENTRY')">
        Prepare entry orders
      </button>
      <button type="button" data-testid="prepare-exit" class="rounded border border-line px-3 py-1" :disabled="phase !== 'live'" @click="prepare('EXIT')">
        Prepare exit orders
      </button>
    </div>

    <template v-if="reply">
      <h2 class="mt-4 font-medium">Plan {{ reply.plan_number }}: orders for Kite's page</h2>
      <table class="mt-1 text-sm" data-testid="execute-orders">
        <thead><tr><th>Side</th><th>Quantity</th><th>Contract</th><th>Order type</th><th>Price</th><th>Tag</th></tr></thead>
        <tbody>
          <tr v-for="o in reply.orders" :key="o.tag" data-testid="execute-order">
            <td>{{ o.transaction_type }}</td><td>{{ o.quantity }}</td><td>{{ o.tradingsymbol }}</td>
            <td>{{ o.order_type }}</td><td>{{ o.price }}</td><td>{{ o.tag }}</td>
          </tr>
        </tbody>
      </table>
      <ul class="mt-1 text-sm" data-testid="execute-planned-vs-limit">
        <li v-for="o in reply.orders" :key="o.tag" data-testid="execute-planned-line">
          {{ o.tradingsymbol }}:
          <template v-if="o.planned_price">Your planned price {{ o.planned_price }} - order limit {{ o.price }}</template>
          <template v-else>Order limit {{ o.price }}</template>
        </li>
      </ul>
      <ExecuteCost v-if="reply.cost" :cost="reply.cost" />
      <p v-else class="mt-2 text-sm" data-testid="cost-unavailable">The cost of these orders is not available.</p>
      <BasketForm :reply="reply" :strategy-id="strategyId" @sent="sent = true" />
      <ReturnCheck v-if="sent" :strategy-id="strategyId" />
    </template>
  </section>
</template>
