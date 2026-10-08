<!-- Strategy Builder, first slice (W-064; REQ-035, REQ-034 AC-1/AC-7/AC-8; ADR-008, ADR-068).
     Every number on this page is a string the outcome API returned (POST /api/strategies/outcome); the page parses no
     number to compute another. The draft strategy comes from the `draft` query (a JSON body of legs with planned entry
     and capture time); the UX level from `ux` (guided | standard | advanced, Standard by default).
     States: loading, computed, stale (computed with a labelled leg), not-connected, refused, error, no-draft.
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
import StrategyFooter from '@/components/strategy/StrategyFooter.vue'
import ErrorMessage from '@/components/common/ErrorMessage.vue'

const route = useRoute()
const router = useRouter()
const state = ref('loading') // loading | computed | stale | not-connected | refused | error | no-draft
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

async function load() {
  const draft = readDraft()
  if (!draft) {
    state.value = 'no-draft'
    return
  }
  state.value = 'loading'
  slowTimer = setTimeout(() => (slow.value = true), 3000)
  try {
    const res = await api.post('/strategies/outcome', { ...draft, ux_level: uxLevel.value })
    data.value = res.data
    if (data.value.state === 'COMPUTED') state.value = data.value.legs.some((l) => l.label) ? 'stale' : 'computed'
    else if (data.value.state === 'NOT_CONNECTED') state.value = 'not-connected'
    else state.value = 'refused'
  } catch (e) {
    errorParts.value = e?.parts ?? NEUTRAL_PARTS
    state.value = 'error'
  } finally {
    clearTimeout(slowTimer)
    slow.value = false
  }
}

onMounted(load)
watch(() => route.query.ux, load)
const setUx = (ux) => router.replace({ query: { ...route.query, ux } })
onBeforeUnmount(() => clearTimeout(slowTimer))

const showNumbers = computed(() => (state.value === 'computed' || state.value === 'stale') && data.value?.table)
const headerUnderlying = computed(() => data.value?.underlying ?? readDraft()?.underlying ?? '')
const maxProfit = computed(() => (data.value?.summary?.max_profit_unlimited ? 'Unlimited' : data.value?.summary?.max_profit ?? '-'))
const maxLoss = computed(() => (data.value?.summary?.max_loss_unlimited ? 'Unlimited' : data.value?.summary?.max_loss ?? '-'))
const staleLegs = computed(() => (data.value?.legs ?? []).filter((l) => l.label))
</script>

<template>
  <section data-testid="strategy-builder" :data-state="state" :data-ux="uxLevel">
    <h1 class="text-xl font-semibold" data-testid="page-title">Strategy Builder</h1>
    <p class="mt-1 text-sm text-ink-muted">A draft strategy and what it could do at different index levels. This is for planning, not a recommendation.</p>

    <StrategyHeader v-if="state !== 'no-draft'" class="mt-3" :underlying="headerUnderlying" :ux-level="uxLevel" :is-loading="state === 'loading'" @update:ux-level="setUx" />

    <p v-if="state === 'loading'" class="mt-4" data-testid="state-loading">
      Working out the outcome...<span v-if="slow" data-testid="state-slow"> This is taking longer than usual.</span>
    </p>

    <p v-else-if="state === 'no-draft'" class="mt-4 text-ink-muted" data-testid="state-no-draft">No draft strategy is open. Choosing legs arrives in a later release.</p>

    <ErrorMessage v-else-if="state === 'error'" class="mt-4" :parts="errorParts" data-testid="state-error" />

    <div v-else-if="state === 'not-connected'" class="mt-4 rounded border border-line bg-surface p-4" data-testid="state-not-connected">
      <p class="font-medium" data-testid="status-label">{{ data.status_label }}</p>
      <p class="mt-1 text-sm text-ink-muted">No numbers are shown because there is no live market data to price this draft.</p>
      <ul class="mt-2 text-sm" data-testid="draft-legs">
        <li v-for="leg in data.legs" :key="leg.instrument_id">{{ leg.action }} {{ leg.lots }} lot, {{ leg.instrument_id }}, planned entry {{ leg.planned_entry }}</li>
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
          <li v-for="l in staleLegs" :key="l.instrument_id" data-testid="stale-leg">{{ l.symbol }}: {{ l.label }}</li>
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
      <StrategyActions :has-legs="data.legs.length > 0" :is-loading="false" @recalculate="load" />
      <StrategyFooter :last-updated="data.valuation" :current-spot="data.spot_level" :underlying="data.underlying" />
    </template>
  </section>
</template>
