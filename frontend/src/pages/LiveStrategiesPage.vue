<!-- Live Strategies (W-113; REQ-049 AC-4..6, REQ-044 AC-2 part 1). Lists the saved strategies (GET /strategies) and gives
     each its own card, which follows it on the live outcome socket. The newest 20 by update time are shown. No number is
     read or computed here (ADR-008); there is no order or execute control (ADR-002). -->
<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import api, { NEUTRAL_PARTS } from '@/services/api'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import LiveStrategyCard from '@/components/live/LiveStrategyCard.vue'
import MarketClosedBanner from '@/components/states/MarketClosedBanner.vue'
import { LIVE_NOTHING_RUNNING_TEXT, STATUS_DRAFT, STATUS_RUNNING } from '@/lib/sharedStateText'
import { isCompleted, isRunning } from '@/lib/strategyStatus'
import { usePaperPnl } from '@/lib/paperPnl'
import { useMonitoringState } from '@/lib/monitoringState'
import { noteShownDate } from '@/lib/displayFormat'

const MAX_CARDS = 20
const pnl = usePaperPnl() // D-41: one read of the Positions page's paper list; each card shows its own figure
const RELEASE_MS = 8000 // a card that gives no answer in this time lets the next one start
const state = ref('loading') // loading | ready | error
const all = ref([])
const errorParts = ref(NEUTRAL_PARTS)
const closedAt = ref(null) // the last-price time a card reported while the market is closed (one banner per screen)

const stamp = (s) => Date.parse(s.updated_at) || 0 // sort key only
// ADR-259 / ADR-299: a completed trade is not followed here (it is listed on Completed Strategies); the rest is Running or Draft
const followed = computed(() => all.value.filter((s) => !isCompleted(s)))
const shown = computed(() => [...followed.value].sort((a, b) => stamp(b) - stamp(a)).slice(0, MAX_CARDS))
// Two groups, newest first inside each; an empty group is not shown. Start order is the order on screen.
const executed = computed(() => shown.value.filter(isRunning))
const drafts = computed(() => shown.value.filter((s) => !isRunning(s)))
const monitoring = useMonitoringState(() => executed.value.map((s) => s.id)) // Lane Y item 1: is the worker watching each running trade (one read)
const queue = computed(() => [...executed.value, ...drafts.value])
const startIndex = (s) => queue.value.indexOf(s)
// Cards start one at a time (the database role allows few connections): card i may start once i <= current.
const current = ref(0)
let timer = null
const release = (index) => {
  if (index === current.value) current.value++
}
watch(current, (i) => {
  clearTimeout(timer)
  if (i < queue.value.length) timer = setTimeout(() => release(i), RELEASE_MS)
})
const capped = computed(() => followed.value.length > MAX_CARDS)

onBeforeUnmount(() => clearTimeout(timer))
onMounted(async () => {
  try {
    all.value = noteShownDate((await api.get('/strategies')).data).strategies
    state.value = 'ready'
    if (queue.value.length) timer = setTimeout(() => release(0), RELEASE_MS)
  } catch (e) {
    errorParts.value = e?.parts ?? NEUTRAL_PARTS
    state.value = 'error'
  }
})
</script>

<template>
  <section data-testid="live-strategies" :data-state="state">
    <PageHeader parent="Strategies" title="Live Strategies" note="Your saved strategies followed on live market data. This is for monitoring, not a recommendation." note-testid="live-note" />
    <!-- User test 2026-10-30: one market-closed banner per screen (ADR-177), not one per card -->
    <MarketClosedBanner v-if="closedAt" class="mb-4" :prices-at="closedAt" />
    <p v-if="state === 'loading'" class="text-sm text-ink-muted" data-testid="live-list-loading">Loading your strategies...</p>
    <ErrorMessage v-else-if="state === 'error'" :parts="errorParts" data-testid="state-error" />
    <p v-else-if="!followed.length" class="rounded-lg border border-line bg-surface px-4 py-8 text-center text-sm text-ink-muted" data-testid="live-empty">
      <template v-if="all.length">{{ LIVE_NOTHING_RUNNING_TEXT }} Finished trades are on <router-link to="/strategies/completed-strategies" class="link">Completed Strategies</router-link>.</template>
      <template v-else>No saved strategies yet. Build one in the <router-link to="/strategy/builder" class="link">Strategy Builder</router-link>.</template>
    </p>
    <template v-else>
      <p v-if="capped" class="text-xs text-ink-muted" data-testid="live-capped">Showing the 20 most recent</p>
      <section v-if="executed.length" class="mt-4" data-testid="live-group-executed">
        <h2 class="text-sm font-semibold text-ink-muted">{{ STATUS_RUNNING }}</h2>
        <div class="mt-2 grid grid-cols-1 gap-4 lg:grid-cols-2">
          <LiveStrategyCard v-for="s in executed" :key="s.id" :strategy="s" :pnl="pnl.cellFor(s.id)" :monitoring="monitoring.entryOf(s.id)" :start="startIndex(s) <= current" @settled="release(startIndex(s))" @closed="(at) => { closedAt = at }" />
        </div>
      </section>
      <section v-if="drafts.length" class="mt-4" data-testid="live-group-drafts">
        <h2 class="text-sm font-semibold text-ink-muted">{{ STATUS_DRAFT }}</h2>
        <div class="mt-2 grid grid-cols-1 gap-4 lg:grid-cols-2">
          <LiveStrategyCard v-for="s in drafts" :key="s.id" :strategy="s" :pnl="pnl.cellFor(s.id)" :monitoring="monitoring.entryOf(s.id)" :start="startIndex(s) <= current" @settled="release(startIndex(s))" @closed="(at) => { closedAt = at }" />
        </div>
      </section>
    </template>
  </section>
</template>
