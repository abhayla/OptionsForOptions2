<!-- Strategy Builder, first slice (W-064; REQ-035, REQ-034 AC-1/AC-7/AC-8; ADR-008, ADR-068).
     Every number on this page is a string the outcome API returned (POST /api/strategies/outcome); the page parses no
     number to compute another. The draft strategy is the legs picked in the LegPicker (W-068: only contracts the
     catalogue API offers); a `draft` query (a JSON body of legs with planned entry and capture time) still opens a
     draft. The outcome API's leg model needs a planned entry, so only priced legs are sent; a leg without one stays in
     the picker's list with the not-connected wording. The UX level comes from `ux` (guided | standard | advanced).
     States: loading, computed, stale (computed with a labelled leg), not-connected, unpriced (legs, none priced),
     refused, error, no-draft.
     New file; the legacy StrategyBuilderView computes P&L and falls back on prices in the browser, so it is not copied. -->
<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api, { NEUTRAL_PARTS } from '@/services/api'
import StrategyTable from '@/components/strategy/StrategyTable.vue'
import PayoffChart from '@/components/strategy/PayoffChart.vue'
import SummaryCards from '@/components/strategy/SummaryCards.vue'
import StrategyHeader from '@/components/strategy/StrategyHeader.vue'
import StrategyActions from '@/components/strategy/StrategyActions.vue'
import AdvancedDetails from '@/components/strategy/AdvancedDetails.vue'
import { advancedDetails } from '@/lib/strategyTable'
import StrategyFooter from '@/components/strategy/StrategyFooter.vue'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import LegPicker from '@/components/strategy/LegPicker.vue'
import SaveDraftBar from '@/components/strategy/SaveDraftBar.vue'
import { NOT_CONNECTED_LABEL, buildDraft } from '@/lib/legPicker'
import { matchesLegs } from '@/lib/liveMatch'
import { nameFromPool } from '@/lib/displayFormat'
import { useStrategyLive } from '@/composables/useStrategyLive'

const route = useRoute()
const router = useRouter()
const state = ref('loading') // loading | computed | stale | not-connected | unpriced | refused | error | no-draft
const data = ref(null)
const errorParts = ref(NEUTRAL_PARTS)
const slow = ref(false)
let slowTimer = null

const uxLevel = computed(() => (['guided', 'standard', 'advanced'].includes(route.query.ux) ? route.query.ux : 'standard'))

function readDraft() {
  try {
    const d = JSON.parse(String(route.query.draft || ''))
    return d && typeof d === 'object' && Array.isArray(d.legs) ? d : null
  } catch {
    return null
  }
}

// The picked legs. A `draft` query seeds them (each already carries its planned entry and capture time).
function legsFromQuery() {
  const d = readDraft()
  if (!d) return []
  return d.legs.map((l, i) => ({
    id: `draft-${i}`,
    underlying: d.underlying,
    instrument_id: l.instrument_id,
    symbol: null,
    action: l.action,
    lots: l.lots,
    planned_entry: l.planned_entry ?? null,
    captured_at: l.captured_at ?? null,
    source: null,
  }))
}
const legs = ref(legsFromQuery())
let loadSeq = 0 // only the newest outcome answer is shown
// ADR-077: "not live" follows THIS page's own socket. Set when it drops, cleared by the next push it receives; while set,
// every outcome request says `fallback: true`, so the server answers the not-live message even when another socket
// (another tab, another user) still holds the same contracts.
let socketDropped = false

async function load() {
  const mine = ++loadSeq // every call invalidates the answers still in flight, also the ones that return early
  clearTimeout(slowTimer)
  slow.value = false
  const draft = buildDraft(legs.value)
  if (!draft) {
    state.value = legs.value.length ? 'unpriced' : 'no-draft'
    data.value = null
    return
  }
  const fallback = socketDropped
  // A fallback reload while the not-live message is already on screen keeps it there (no flicker through 'loading').
  if (!(fallback && state.value === 'not-connected')) state.value = 'loading'
  slowTimer = setTimeout(() => (slow.value = true), 3000)
  try {
    const res = await api.post('/strategies/outcome', { ...draft, ux_level: uxLevel.value, fallback })
    if (mine !== loadSeq) return
    applyOutcome(res.data)
  } catch (e) {
    if (mine !== loadSeq) return
    errorParts.value = e?.parts ?? NEUTRAL_PARTS
    state.value = 'error'
  } finally {
    if (mine === loadSeq) {
      clearTimeout(slowTimer)
      slow.value = false
    }
  }
}

// One outcome answer (REST or a live push) onto the page, as the server sent it: no number is computed here (ADR-008).
function applyOutcome(body) {
  data.value = body
  if (body.state === 'COMPUTED') state.value = body.legs.some((l) => l.label) ? 'stale' : 'computed'
  else if (body.state === 'NOT_CONNECTED') state.value = 'not-connected'
  else state.value = 'refused'
}

// W-065 (REQ-035 AC-4; ADR-068 (2), ADR-077): live numbers from the platform socket. A push replaces the page's answer
// and makes any REST answer still in flight obsolete; when the socket drops, the REST route answers, and its not-live
// label (REQ-049 AC-5's message with the last price time) is the server's text.
const live = useStrategyLive({
  onPush: (body) => {
    // A late push of the previous strategy (the socket was told the new one a moment ago) is dropped, never shown.
    if (!matchesLegs(body, buildDraft(legs.value))) return
    socketDropped = false
    loadSeq++
    clearTimeout(slowTimer)
    slow.value = false
    applyOutcome(body)
  },
  onDown: () => {
    socketDropped = true
    load()
  },
})
function syncLive() {
  const draft = buildDraft(legs.value)
  if (draft) live.follow({ ...draft, ux_level: uxLevel.value })
  else live.stop()
}

const setLegs = (next) => {
  legs.value = next
  load()
  syncLive()
}

onMounted(() => {
  load()
  syncLive()
})
watch(() => route.query.ux, () => {
  load()
  syncLive()
})
const setUx = (ux) => router.replace({ query: { ...route.query, ux } })
onBeforeUnmount(() => clearTimeout(slowTimer))

const showNumbers = computed(() => (state.value === 'computed' || state.value === 'stale') && data.value?.table)
const headerUnderlying = computed(() => data.value?.underlying ?? legs.value[0]?.underlying ?? '')
const maxProfit = computed(() => (data.value?.summary?.max_profit_unlimited ? 'Unlimited' : data.value?.summary?.max_profit ?? '-'))
const maxLoss = computed(() => (data.value?.summary?.max_loss_unlimited ? 'Unlimited' : data.value?.summary?.max_loss ?? '-'))
const advancedRows = computed(() => advancedDetails(data.value, uxLevel.value))
// A leg's contract name: from its own fields, else looked up from the page's draft legs by instrument id (ADR-086).
const nameOf = (leg) => nameFromPool(leg, legs.value, data.value?.underlying ?? headerUnderlying.value)
const staleLegs = computed(() => (data.value?.legs ?? []).filter((l) => l.label))
</script>

<template>
  <section data-testid="strategy-builder" :data-state="state" :data-ux="uxLevel" :data-live="live.status.value">
    <h1 class="text-xl font-semibold" data-testid="page-title">Strategy Builder</h1>
    <p class="mt-1 text-sm text-ink-muted">A draft strategy and what it could do at different index levels. This is for planning, not a recommendation.</p>

    <LegPicker :legs="legs" @update:legs="setLegs" />
    <SaveDraftBar :legs="legs" :rules-ref="String(route.query.rules_ref || '')" @open="setLegs" />

    <StrategyHeader v-if="state !== 'no-draft'" class="mt-3" :underlying="headerUnderlying" :ux-level="uxLevel" :is-loading="state === 'loading'" @update:ux-level="setUx" />

    <p v-if="state === 'loading'" class="mt-4" data-testid="state-loading">
      Working out the outcome...<span v-if="slow" data-testid="state-slow"> This is taking longer than usual.</span>
    </p>

    <p v-else-if="state === 'no-draft'" class="mt-4 text-ink-muted" data-testid="state-no-draft">No draft strategy is open. Add a leg above to start one.</p>

    <div v-else-if="state === 'unpriced'" class="mt-4 rounded border border-line bg-surface p-4" data-testid="state-unpriced">
      <p class="font-medium">{{ NOT_CONNECTED_LABEL }}</p>
      <p class="mt-1 text-sm text-ink-muted">No numbers are shown because none of the legs has a planned entry from live market data.</p>
    </div>

    <ErrorMessage v-else-if="state === 'error'" class="mt-4" :parts="errorParts" data-testid="state-error" />

    <div v-else-if="state === 'not-connected'" class="mt-4 rounded border border-line bg-surface p-4" data-testid="state-not-connected">
      <p class="font-medium" data-testid="status-label">{{ data.status_label }}</p>
      <p class="mt-1 text-sm text-ink-muted">No numbers are shown because there is no live market data to price this draft.</p>
      <ul class="mt-2 text-sm" data-testid="draft-legs">
        <li v-for="leg in data.legs" :key="leg.instrument_id">{{ leg.action }} {{ leg.lots }} lot, <span data-testid="leg-name">{{ nameOf(leg) }}</span>, planned entry {{ leg.planned_entry }}</li>
      </ul>
    </div>

    <div v-else-if="state === 'refused'" class="mt-4 rounded border border-line bg-surface p-4" data-testid="state-refused">
      <p class="font-medium" data-testid="status-label">{{ data.status_label }}</p>
      <p v-if="data.reason" class="mt-1 text-sm" data-testid="refused-reason">{{ data.reason }}</p>
      <p class="mt-1 text-sm text-ink-muted">No numbers are shown for this draft.</p>
    </div>

    <template v-if="showNumbers">
      <div v-if="data.output_label || staleLegs.length" class="mt-4 rounded border border-line bg-accent-soft p-3 text-sm" data-testid="data-health">
        <p v-if="data.output_label" data-testid="output-label">{{ data.output_label }}</p>
        <ul v-if="staleLegs.length">
          <li v-for="l in staleLegs" :key="l.instrument_id" data-testid="stale-leg">{{ nameOf(l) }}: {{ l.label }}</li>
        </ul>
      </div>

      <SummaryCards
        class="mt-4"
        :max-profit="maxProfit"
        :max-loss="maxLoss"
        :breakevens="data.summary.breakevens"
        :what-can-i-make="data.summary.what_can_i_make"
        :what-can-i-lose="data.summary.what_can_i_lose"
        :where-i-start-losing="data.summary.where_do_i_start_losing"
        :current-spot="data.spot_level"
        :underlying="data.underlying"
        :last-updated="data.valuation"
      />
      <p class="mt-2 text-sm text-ink-muted" data-testid="margin">{{ data.margin.reason }}</p>

      <div class="mt-4"><PayoffChart :points="data.payoff.points" /></div>
      <h2 class="mt-4 mb-1 text-sm font-medium">Outcome at each index level</h2>
      <StrategyTable
        :table="data.table"
        :ux-level="uxLevel"
        :max-profit="data.summary.max_profit_unlimited ? null : data.summary.max_profit"
        :max-loss="data.summary.max_loss_unlimited ? null : data.summary.max_loss"
      />
      <AdvancedDetails v-if="advancedRows" :rows="advancedRows" :name-of="nameOf" />
      <StrategyActions :has-legs="data.legs.length > 0" :is-loading="false" @recalculate="load" />
      <StrategyFooter :last-updated="data.valuation" :current-spot="data.spot_level" :underlying="data.underlying" />
    </template>
  </section>
</template>
