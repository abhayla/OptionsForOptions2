<!-- The Execute screen (W-104; REQ-056 AC-1, REQ-073 AC-1/AC-3; ADR-054, ADR-097, ADR-003, ADR-008).
     1. Live first: the saved strategy's legs are followed on the platform's live socket (useStrategyLive, W-065: the
        server subscribes them in full mode). Execute is called only while the latest push is a live outcome for every
        leg; not live within LIVE_WAIT_MS -> the catalogue's not-live message, and Execute is never called.
     2. The owner picks entry or exit (the API gives no held flag, so both are offered; the route refuses the wrong one
        with its catalogue message). The reply's orders and cost are shown as the strings given.
     3. ADR-119 (3): the SERVER's market verdict (GET /execute/market-status: its own clock and holiday data) is read on
        load and each time the legs go live; unless it says "open" the two actions are disabled and the server's sentence
        is shown BEFORE any click. A failed read counts as unconfirmed. The browser's clock decides nothing.
     4. Kite's page opens only on the owner's click (BasketForm); then "Check with Zerodha" reads the result (ReturnCheck).
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
import { fetchSavedLegs } from '@/lib/saveDraft'
import { EVERY_TRADE_NOTE, LIVE_WAIT_MS, MARKET_UNCONFIRMED_PARTS, NOT_LIVE_PARTS, SEQUENCE_NOTE, isLiveOutcome, orderTypeText, planSentence, readableReply, readyText, riskLine } from '@/lib/execute'

const props = defineProps({ waitMs: { type: Number, default: LIVE_WAIT_MS } })

const route = useRoute()
const guided = computed(() => route.query.ux === 'guided') // the level, as the Builder reads it (?ux=); glosses and hidden tags at Guided
const narrow = ref(false) // a phone: the orders block starts collapsed
const lastAction = ref('ENTRY') // what the owner pressed: the reply carries the orders, not the action
const sentence = computed(() => (reply.value ? planSentence(reply.value, lastAction.value) : null))
const risk = computed(() => (reply.value ? riskLine(reply.value) : null)) // ADR-140: the server's tier, rendered; never computed here
const awaitingAcceptance = computed(() => !!reply.value && reply.value.basket == null) // EXCEPTIONAL: the server holds the basket back until accepted
const accepting = ref(false)
const strategyId = computed(() => (/^[1-9]\d{0,17}$/.test(String(route.params.id)) ? String(route.params.id) : null)) // an id string, never parsed
const phase = ref('loading') // loading | waiting-live | live | not-live | executing | prepared | error
const liveNow = ref(false)
const reply = ref(null)
const sent = ref(false)
const errorParts = ref(null)
let draft = null
let liveTimer = null

const live = useStrategyLive({
  onPush: (body) => {
    if (!draft || !matchesLegs(body, draft)) return // a push for another strategy is never read
    liveNow.value = isLiveOutcome(body)
    if (liveNow.value && (phase.value === 'waiting-live' || phase.value === 'not-live')) {
      clearTimeout(liveTimer)
      everLive.value = true
      errorParts.value = null // live again: the not-live message goes, the actions return
      phase.value = 'live'
      readMarket() // judged again by the server as the actions come back
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
const market = ref(null) // the server's verdict: { status: open|closed|unconfirmed|paused, message }; paused = the owner's kill switch (ADR-127); null until first read
const marketOpen = computed(() => market.value?.status === 'open')

async function readMarket() {
  try {
    const data = (await api.get('/execute/market-status', { params: { strategy_id: strategyId.value } })).data
    market.value = data && ['open', 'closed', 'unconfirmed', 'paused'].includes(data.status)
      ? { status: data.status, message: data.message ?? MARKET_UNCONFIRMED_PARTS,
          // ADR-128: the server's one line (its own catalogue text), only while paused and only for a strategy it knows holds units
          hint: data.status === 'paused' ? (data.paused_hint ?? null) : null }
      : { status: 'unconfirmed', message: MARKET_UNCONFIRMED_PARTS } // unreadable: fail closed
  } catch {
    market.value = { status: 'unconfirmed', message: MARKET_UNCONFIRMED_PARTS }
  }
}

function notLive() {
  errorParts.value = NOT_LIVE_PARTS
  phase.value = 'not-live'
}

onMounted(async () => {
  narrow.value = typeof window.matchMedia === 'function' && window.matchMedia('(max-width: 639px)').matches
  if (strategyId.value === null) {
    errorParts.value = NEUTRAL_PARTS
    phase.value = 'error'
    return
  }
  readMarket()
  try {
    draft = buildDraft(await fetchSavedLegs(api, strategyId.value))
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
  live.follow({ ...draft, ux_level: 'standard' })
})
onBeforeUnmount(() => clearTimeout(liveTimer))

async function prepare(action) {
  if (phase.value !== 'live' || !liveNow.value || !marketOpen.value) return // live first; and the server must say open
  phase.value = 'executing'
  errorParts.value = null
  try {
    const data = (await api.post(`/strategies/${strategyId.value}/execute`, { action })).data
    if (!readableReply(data)) throw new Error('unreadable basket') // fail closed: no form for a reply we cannot read
    lastAction.value = action
    reply.value = data
    phase.value = 'prepared'
  } catch (e) {
    errorParts.value = e?.parts ?? NEUTRAL_PARTS
    phase.value = liveNow.value ? 'live' : 'not-live' // the socket may have dropped while Execute was answering
  }
}

// ADR-140: "I accept this risk" asks the SERVER again with accept_risk; only its reply carries the basket. Nothing in the
// browser opens Kite on this click, and no browser flag is ever sent on to Kite.
async function acceptRisk() {
  if (accepting.value || !awaitingAcceptance.value || !liveNow.value || !marketOpen.value) return
  accepting.value = true
  errorParts.value = null
  try {
    const data = (await api.post(`/strategies/${strategyId.value}/execute`, { action: lastAction.value, accept_risk: true })).data
    if (!readableReply(data) || data.basket == null) throw new Error('unreadable basket') // an acceptance must yield a basket
    reply.value = data
  } catch (e) {
    errorParts.value = e?.parts ?? NEUTRAL_PARTS
  } finally {
    accepting.value = false
  }
}
</script>

<template>
  <section class="p-4" data-testid="execute-screen" :data-phase="phase">
    <h1 class="text-xl font-semibold" data-testid="page-title">Execute Strategy {{ strategyId ?? '' }}</h1>
    <p v-if="phase === 'loading' || phase === 'waiting-live'" data-testid="execute-waiting">Waiting for live prices for every leg...</p>
    <ErrorMessage v-if="errorParts" class="mt-2" :parts="errorParts" prefix="execute-error" />

    <ErrorMessage v-if="!reply && market && !marketOpen" class="mt-2" :parts="market.message" prefix="market-closed" />
    <p v-if="!reply && market && market.hint" class="mt-1" data-testid="paused-hint">{{ market.hint.what_happened }}</p>

    <div v-if="!reply && (phase === 'live' || phase === 'executing' || (phase === 'not-live' && everLive) || (market && !marketOpen))" class="mt-2 flex gap-2" data-testid="execute-actions">
      <button type="button" data-testid="prepare-entry" class="rounded border border-line px-3 py-1" :disabled="phase !== 'live' || !marketOpen" @click="prepare('ENTRY')">
        Prepare entry orders
      </button>
      <button type="button" data-testid="prepare-exit" class="rounded border border-line px-3 py-1" :disabled="phase !== 'live' || !marketOpen" @click="prepare('EXIT')">
        Prepare exit orders
      </button>
    </div>

    <template v-if="reply">
      <!-- EXECUTE-REVIEW reading order (design note S5): one plain sentence, margin + charges, max loss / profit, the orders
           (collapsed on a phone), then "Ready to execute" with the one sticky action. Server strings only (ADR-008). -->
      <p v-if="sentence" class="mt-4 text-base font-medium" data-testid="execute-sentence">{{ sentence }}</p>
      <p
        v-if="risk"
        class="mt-1 text-sm"
        :class="{ 'text-amber-700': risk.tier === 'ELEVATED', 'font-semibold text-red-700': risk.tier === 'EXCEPTIONAL' }"
        :role="risk.tier === 'EXCEPTIONAL' ? 'alert' : undefined"
        :data-tier="risk.tier"
        data-testid="execute-risk-line"
      >{{ risk.text }}</p>
      <button
        v-if="awaitingAcceptance && risk && risk.needsAcceptance"
        type="button"
        data-testid="accept-risk"
        class="mt-2 min-h-[44px] rounded border border-line px-3 py-1"
        :disabled="accepting || !liveNow || !marketOpen"
        @click="acceptRisk"
      >
        I accept this risk
      </button>
      <ExecuteCost v-if="reply.cost" :cost="reply.cost" :review="reply.review" />
      <p v-else class="mt-2 text-sm" data-testid="cost-unavailable">The cost of these orders is not available.</p>
      <details class="mt-3" :open="!narrow" data-testid="execute-orders-block">
        <summary class="min-h-[44px] cursor-pointer font-medium">Plan {{ reply.plan_number }}: orders for Kite's page</summary>
        <div class="overflow-x-auto" data-h-scroll>
          <table class="mt-1 text-sm" data-testid="execute-orders">
            <thead><tr><th>#</th><th>Side</th><th>Quantity</th><th>Contract</th><th>Order type</th><th>Price</th><th v-if="!guided">Tag</th></tr></thead>
            <tbody>
              <tr v-for="(o, i) in reply.orders" :key="o.tag" data-testid="execute-order">
                <td data-testid="order-seq">{{ i + 1 }}</td><td>{{ o.transaction_type }}</td><td>{{ o.quantity }}</td><td>{{ o.tradingsymbol }}</td>
                <td>{{ orderTypeText(o.order_type, guided) }}</td><td>{{ o.price }}</td><td v-if="!guided">{{ o.tag }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="mt-1 text-xs" data-testid="sequence-note">{{ SEQUENCE_NOTE }}</p>
      </details>
      <p class="mt-2 text-xs" data-testid="every-trade-note">{{ EVERY_TRADE_NOTE }}</p>
      <div v-if="!awaitingAcceptance" class="sticky bottom-0 mt-3 bg-white py-2 sm:static" data-testid="execute-ready-bar">
        <p class="font-medium" data-testid="execute-ready">{{ readyText(reply) }}</p>
        <BasketForm :reply="reply" :strategy-id="strategyId" @sent="sent = true" />
      </div>
      <ReturnCheck v-if="sent" :strategy-id="strategyId" />
    </template>
  </section>
</template>
