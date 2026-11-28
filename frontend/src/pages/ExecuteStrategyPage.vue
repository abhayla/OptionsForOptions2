<!-- The Execute screen (W-104; REQ-056 AC-1, REQ-073 AC-1/AC-3; ADR-054, ADR-097, ADR-003, ADR-008).
     1. Live first: the saved strategy's legs are followed on the platform's live socket (useStrategyLive, W-065: the
        server subscribes them in full mode). Execute is called only while the latest push is a live outcome for every
        leg; not live within LIVE_WAIT_MS -> the catalogue's not-live message, and Execute is never called.
     2. The owner picks entry or exit (the API gives no held flag, so both are offered; the route refuses the wrong one
        with its catalogue message). The reply's orders and cost are shown as the strings given.
     3. Kite's page opens only on the owner's click (BasketForm); then "Check with Zerodha" reads the result (ReturnCheck).
     New file, copy from: none (legacy-reuse row 149's BasketOrderModal builds the basket in the browser; ADR-054). -->
<script setup>
import PageHeader from '@/components/common/PageHeader.vue'
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
import { EXECUTE_UNKNOWN_TEXT, LIVE_WAIT_MS, NOT_LIVE_PARTS, basketFields, isLiveOutcome } from '@/lib/execute'
import { PAPER_STATE, paperPostOutcome } from '@/lib/tracking'
import { addLockFor, adoptedAddLock, bookOfRead, decideLock, dropAddLock, dropOrderKey, newRequestKey, onAddLocksChanged, orderKeyFor, saveAddLock, sentNow } from '@/lib/unknownLocks'

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

// I-182 (ADR-016 to ADR-019): the ONE lock rule (lib/unknownLocks.js) for a request of unknown outcome. The lock is kept per strategy for this browser (a reload and
// a second tab hold it too) and ends only by a good read of the saved strategy sent after the server's commit window (decideLock). The server refuses a repeat as well:
// this is the second line. Fail closed: a lock that cannot be read blocks.
const lockId = computed(() => `execute:${strategyId.value}`)
const lockTick = ref(0) // the lock store is not reactive: every write and every storage event of another tab bumps this
const locked = computed(() => { lockTick.value; return strategyId.value !== null && !!addLockFor(lockId.value) })
let lockOut = false // this page's own request is in flight: only its answer ends the lock
let gone = false // the page was closed: no timer is started or read made after it (Opus review F7)
// the unknown-outcome sentence is for a lock this page is NOT waiting an answer for (its own request in flight is a normal press, Opus review F3)
const lockedNote = computed(() => { lockTick.value; return locked.value && !lockOut })
let lockTimer = null
let lockChecking = false
async function checkLock() {
  if (lockChecking || lockOut || strategyId.value === null) return
  lockChecking = true
  try {
    const id = lockId.value
    if (!addLockFor(id) || !adoptedAddLock(id, Date.now())) return // no lock, or none this page can age yet
    const sentAt = sentNow() // the window is judged by when the read was SENT, by the one clock source (Opus review F5)
    try { await fetchSavedDraft(api, strategyId.value) } catch { return } // a failed read decides nothing
    const now = addLockFor(id) && adoptedAddLock(id, Date.now()) // the lock that is stored NOW (another tab may have replaced it)
    if (!now || lockOut) return
    const d = decideLock(now, bookOfRead({ kind: 'plan' }), sentAt) // an Execute request leaves no order in a book this page can read: a read past the window = not stored
    if (d.verdict === 'not_stored' || d.verdict === 'changed') { dropAddLock(id, now); lockTick.value++ } // the request key stays: a repeat press is the same request
  } finally { lockChecking = false }
}
const startLockTimer = () => { if (!gone && !lockTimer) lockTimer = setInterval(() => { if (!locked.value) { clearInterval(lockTimer); lockTimer = null } else checkLock() }, 5000) }
let offLocks = null
onMounted(() => {
  offLocks = onAddLocksChanged(() => { lockTick.value++; if (locked.value) startLockTimer() })
  if (locked.value) { startLockTimer(); checkLock() }
})
onBeforeUnmount(() => { gone = true; clearInterval(lockTimer); lockTimer = null; offLocks?.() })

async function prepare(action) {
  if (phase.value !== 'live' || !liveNow.value) return // the live socket must hold every leg first
  if (strategyId.value === null || lockOut || addLockFor(lockId.value)) return // an earlier request of unknown outcome: nothing is sent; the STORE is read at press time, not the cached value (Opus review F6)
  const lockKey = lockId.value // the lock id and the key id are fixed at the press: an answer that arrives after a route change still ends THIS strategy's lock (Opus review F2)
  phase.value = 'executing'
  errorParts.value = null
  const mine = guard.next('execute')
  // Group A R3: ONE key per user action (this press of this button for this saved revision): the same press repeated after an unknown outcome (also after a reload) sends the SAME key;
  // a decided answer (a reply, or a 4xx refusal) frees it, so the next press is a new action with a new key. Same rule as every order page (lib/unknownLocks.js orderKeyFor).
  const keyId = lockKey
  const key = orderKeyFor(keyId, JSON.stringify({ action, revision }), newRequestKey())
  const outAt = Date.now()
  const sig = JSON.stringify({ action, revision })
  lockOut = true
  saveAddLock(lockKey, { at: outAt, out: true, before: '', key: key ?? '', sig }) // written BEFORE the request goes out (a closed tab leaves it)
  lockTick.value++
  try {
    const data = (await api.post(`/strategies/${strategyId.value}/execute`, { action, revision, seq: mine.seq, ...(key ? { client_request_id: key } : {}) }, { signal: mine.signal })).data
    if (!guard.claim('execute', data, mine)) { dropOrderKey(keyId); dropAddLock(lockKey, { key: key ?? '', at: outAt }); return } // an older reply is dropped and logged, never shown: it was an answer, the action is over
    if (!basketFields(data)) throw new Error('unreadable basket') // fail closed: no form for a reply we cannot read: it counts as unknown (lock and key stay, Opus review F4)
    dropOrderKey(keyId) // the server answered and the reply is usable: the action is over
    dropAddLock(lockKey, { key: key ?? '', at: outAt }) // an answer: the lock ends with it
    reply.value = data
    phase.value = 'prepared'
  } catch (e) {
    if (!isSuperseded(e) && paperPostOutcome(e) === PAPER_STATE.REFUSED) dropAddLock(lockKey, { key: key ?? '', at: outAt }) // a definite refusal: nothing stored, the lock ends with the answer
    else saveAddLock(lockKey, { at: Date.now(), out: false, before: '', key: key ?? '', sig }) // unknown (no answer, 5xx, cancelled): `at` is now when the client gave up
    startLockTimer()
    if (!isSuperseded(e) && paperPostOutcome(e) === PAPER_STATE.REFUSED) dropOrderKey(keyId) // a 4xx the server itself answered (a cancelled or lost request keeps its key: it may have been prepared)
    if (isSuperseded(e) || !guard.isNewest('execute', mine)) return // cancelled or older: no error text, no state change
    reply.value = null // a refusal (e.g. 409 "Your plan changed") keeps no plan on screen
    errorParts.value = e?.parts ?? NEUTRAL_PARTS
    phase.value = liveNow.value ? 'live' : 'not-live' // the socket may have dropped while Execute was answering
    if (e?.status === 409) await rereadAfterConflict()
  } finally {
    lockOut = false
    lockTick.value++
    guard.settle('execute', mine)
  }
}
</script>

<template>
  <section data-testid="execute-screen" :data-phase="phase">
    <PageHeader parent="Strategies" :title="`Execute Strategy ${strategyName ?? strategyId ?? ''}`" />
    <p v-if="live.reconnecting.value" class="mt-2 text-sm font-medium" data-testid="live-reconnecting">{{ live.reconnectingText.value }}</p>
    <p v-if="phase === 'loading' || phase === 'waiting-live'" data-testid="execute-waiting">Waiting for live prices for every leg...</p>
    <ErrorMessage v-if="errorParts" class="mt-2" :parts="errorParts" prefix="execute-error" />
    <p v-if="lockedNote" class="mt-2 text-sm text-red-700" role="status" data-testid="execute-unknown-note">{{ EXECUTE_UNKNOWN_TEXT }}</p>

    <div v-if="!reply && (phase === 'live' || phase === 'executing' || (phase === 'not-live' && everLive))" class="mt-2 flex gap-2" data-testid="execute-actions">
      <button type="button" data-testid="prepare-entry" class="rounded border border-line px-3 py-1" :disabled="phase !== 'live' || locked" @click="prepare('ENTRY')">
        Prepare entry orders
      </button>
      <button type="button" data-testid="prepare-exit" class="rounded border border-line px-3 py-1" :disabled="phase !== 'live' || locked" @click="prepare('EXIT')">
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
