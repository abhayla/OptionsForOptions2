<!-- W-119 (REQ-024 AC-1..AC-8, REQ-026 AC-1..AC-7, REQ-028, REQ-068 AC-2/AC-4; ADR-003, ADR-008, ADR-056): Create Strategy.
     Two paths; the guided path runs Step 1 objective -> Step 2 market view -> Step 3 expiry (and, for "Not sure", the
     expected range from pick lists) -> Step 4 strategies you could consider. Each card's legs are the template's default
     shape on listed contracts (never substituted); its planned entries come from POST /api/strategies/planned-entry and
     its max profit, max loss and breakevens from POST /api/strategies/outcome (the one engine), shown exactly as sent.
     The range reading line uses the three ADR-122 texts (rule: ADR-121 (1)); the other range lines (REQ-026 AC-4/AC-8) wait on the legal review Q211/Q261: provisional. -->
<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api, { NEUTRAL_PARTS } from '@/services/api'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import { UNDERLYINGS } from '@/lib/legPicker'
import {
  CARDS_SHOWN, MARKET_VIEWS, OBJECTIVES, PATHS, RANGE_READINGS, expandTemplate, expiryLabels, matchTemplates, rangeLists, readingFromRange,
} from '@/lib/guided'

const TOTAL_STEPS = 4
const NO_LEVEL = 'The current level of this index is not available, so strategies cannot be set up yet.'
const NO_FIT = 'None of the strategies matched both your objective and your market view. These match your market view.'
const NONE_LISTED = 'No strategy in the library can be set up on the listed contracts of this expiry.'
const NOT_PRICED = 'Live data not connected — numbers not available'
const RANGE_NOTE = 'Your expected range is an input, not a prediction.'

const route = useRoute()
const router = useRouter()
const path = ref(null) // null | 'guided'
const step = ref(1)
const objective = ref(null)
const viewKey = ref(null)
const underlying = ref(UNDERLYINGS[0])
const templates = ref([])
const current = ref(null) // the index level as the server sent it (string) or null
const expiries = ref([])
const expiry = ref('')
const contracts = ref([])
const lower = ref(null)
const readingChoice = ref(null) // the user's own pick (ADR-121 (1): the user can change the reading); null = keep the derived one
const upper = ref(null)
const cards = ref([])
const showAll = ref(false)
const details = ref({})
const errorParts = ref(null)
const busy = ref(false)

const isKnow = computed(() => objective.value === 'know')
const notSure = computed(() => viewKey.value === 'not-sure')
const lists = computed(() => {
  if (current.value === null || !contracts.value.length) return null
  try { return rangeLists(current.value, contracts.value, underlying.value) } catch { return null }
})
const expiryLabel = computed(() => expiryLabels(expiries.value).find((e) => e.value === expiry.value)?.label ?? '')
const derivedReading = computed(() => {
  if (!notSure.value || current.value === null || lower.value === null || upper.value === null) return null
  try { return RANGE_READINGS.find((r) => r.key === readingFromRange(current.value, lower.value, upper.value)) } catch { return null }
})
const activeReading = computed(() => RANGE_READINGS.find((r) => r.key === readingChoice.value) ?? derivedReading.value)
const viewTag = computed(() => {
  if (isKnow.value) return null
  if (notSure.value) return activeReading.value?.tag ?? null
  return MARKET_VIEWS.find((v) => v.key === viewKey.value)?.tag ?? null
})
const matched = computed(() => (step.value === 4 ? matchTemplates(templates.value, objective.value, viewTag.value) : null))
const shownCards = computed(() => (showAll.value ? cards.value : cards.value.slice(0, CARDS_SHOWN)))
const heading = computed(() => (notSure.value
  ? `Based on your expected range of ${lower.value}–${upper.value} by ${expiryLabel.value}, here are strategies you could consider`
  : 'Strategies you could consider'))

async function read(fn) {
  try { return await fn() } catch (e) { errorParts.value = e?.parts ?? NEUTRAL_PARTS; return null }
}

onMounted(async () => {
  const list = await read(async () => (await api.get('/strategy-templates')).data?.templates)
  if (Array.isArray(list)) templates.value = list
})

function choosePath(key) {
  if (key === 'advanced') { router.push('/strategy/builder'); return } // REQ-024 AC-5: an empty Builder, same engine
  path.value = 'guided'
  step.value = 1
}

function chooseObjective(key) {
  objective.value = key
  step.value = key === 'know' ? 3 : 2 // REQ-024 AC-4: a known strategy skips discovery
  if (key === 'know') loadExpiries()
}

function chooseView(key) {
  viewKey.value = key
  step.value = 3
  loadExpiries()
}

async function loadExpiries() {
  errorParts.value = null
  const [ex, idx] = await Promise.all([
    read(async () => (await api.get(`/catalogue/${underlying.value}/expiries`)).data?.expiries),
    read(async () => (await api.get('/market/indices')).data?.indices),
  ])
  expiries.value = Array.isArray(ex) ? ex : []
  current.value = Array.isArray(idx) ? (idx.find((i) => i.underlying === underlying.value)?.value ?? null) : null
  expiry.value = ''
  contracts.value = []
}

async function chooseExpiry() {
  const list = await read(async () => (await api.get(`/catalogue/${underlying.value}/contracts?expiry=${expiry.value}`)).data?.contracts)
  contracts.value = Array.isArray(list) ? list : []
  lower.value = current.value // REQ-026 AC-3: both levels start at the current level
  upper.value = current.value
  readingChoice.value = null
}

async function priceCard(template, legs) {
  const card = { id: template.id, name: template.name, level: template.level, views: template.views, legs, summary: null, margin: null, priced: false }
  const entries = await read(async () => (await api.post('/strategies/planned-entry', { underlying: underlying.value, instrument_ids: legs.map((l) => l.instrument_id) })).data?.entries)
  if (!Array.isArray(entries)) return card
  const byId = Object.fromEntries(entries.map((e) => [`${e.exchange_segment}:${e.exchange_token}`, e]))
  if (legs.some((l) => !byId[l.instrument_id] || byId[l.instrument_id].planned_entry === null)) return card // never guessed
  card.legs = legs.map((l) => ({ ...l, planned_entry: byId[l.instrument_id].planned_entry, captured_at: byId[l.instrument_id].captured_at }))
  const out = await read(async () => (await api.post('/strategies/outcome', {
    underlying: underlying.value, ux_level: 'guided',
    legs: card.legs.map((l) => ({ instrument_id: l.instrument_id, action: l.action, lots: l.lots, planned_entry: l.planned_entry, captured_at: l.captured_at })),
  })).data)
  if (out?.summary) { card.summary = out.summary; card.margin = out.margin ?? null; card.priced = true }
  return card
}

async function showStrategies() {
  if (current.value === null) return
  step.value = 4
  busy.value = true
  showAll.value = false
  const fitting = matched.value.list.map((t) => [t, expandTemplate(t, contracts.value, current.value)]).filter(([, legs]) => legs)
  cards.value = await Promise.all(fitting.map(([t, legs]) => priceCard(t, legs)))
  busy.value = false
}

function back() {
  if (step.value === 1) { path.value = null; return }
  step.value = step.value === 3 && isKnow.value ? 1 : step.value - 1
}

function openInBuilder(card) {
  router.push({ path: '/strategy/builder', query: { ux: 'guided', draft: JSON.stringify({ underlying: underlying.value, legs: card.legs }) } })
}

const money = (v, unlimited) => (unlimited ? 'Unlimited' : v ?? '—')
</script>

<template>
  <section data-testid="create-strategy" :data-step="path ? step : 0">
    <p class="text-xs text-ink-muted" data-testid="page-parent">Strategies</p>
    <h1 class="text-xl font-semibold" data-testid="page-title">{{ route.meta.title }}</h1>
    <ErrorMessage v-if="errorParts" class="mt-4" :parts="errorParts" prefix="create-error" data-testid="create-error" />

    <div v-if="!path" class="mt-4 grid gap-3 sm:grid-cols-2">
      <button
v-for="p in PATHS" :key="p.key" type="button" class="min-h-[44px] w-full rounded border border-line bg-surface p-4 text-left"
              :data-testid="`path-${p.key}`" @click="choosePath(p.key)">
        <span class="block font-semibold">{{ p.title }}</span>
        <span class="block text-sm text-ink-muted">{{ p.subtitle }}</span>
      </button>
    </div>

    <template v-else>
      <div class="mt-3 flex items-center gap-3">
        <button type="button" class="min-h-[44px] rounded border border-line px-3" data-testid="step-back" @click="back">Back</button>
        <p class="text-sm" data-testid="step-indicator">Step {{ step }} of {{ TOTAL_STEPS }}</p>
      </div>

      <div v-if="step === 1" class="mt-4" data-testid="step-objective">
        <h2 class="text-lg font-semibold">What is your objective?</h2>
        <div class="mt-2 grid gap-2 sm:grid-cols-3">
          <button
v-for="o in OBJECTIVES" :key="o.key" type="button" class="min-h-[44px] w-full rounded border border-line bg-surface p-3 text-left"
                  data-testid="objective" :data-key="o.key" @click="chooseObjective(o.key)">{{ o.label }}</button>
        </div>
      </div>

      <div v-else-if="step === 2" class="mt-4" data-testid="step-view">
        <h2 class="text-lg font-semibold">What is your market view?</h2>
        <div class="mt-2 grid gap-2 sm:grid-cols-5">
          <button
v-for="v in MARKET_VIEWS" :key="v.key" type="button" class="min-h-[44px] w-full rounded border border-line bg-surface p-3 text-left"
                  data-testid="market-view" :data-key="v.key" @click="chooseView(v.key)">{{ v.label }}</button>
        </div>
      </div>

      <div v-else-if="step === 3" class="mt-4 grid gap-3" data-testid="step-expiry">
        <label class="grid gap-1 text-sm">Index
          <select v-model="underlying" class="min-h-[44px] rounded border border-line" data-testid="pick-underlying" @change="loadExpiries">
            <option v-for="u in UNDERLYINGS" :key="u" :value="u">{{ u }}</option>
          </select>
        </label>
        <label class="grid gap-1 text-sm">Expiry
          <select v-model="expiry" class="min-h-[44px] rounded border border-line" data-testid="pick-expiry" @change="chooseExpiry">
            <option value="" disabled>Choose an expiry</option>
            <option v-for="e in expiryLabels(expiries)" :key="e.value" :value="e.value">{{ e.label }}</option>
          </select>
        </label>
        <p v-if="current === null" class="text-sm" data-testid="no-level"><span class="font-semibold text-danger">Not available:</span> {{ NO_LEVEL }}</p>
        <template v-if="notSure && lists">
          <label class="grid gap-1 text-sm">Expected lower level
            <select v-model="lower" class="min-h-[44px] rounded border border-line" data-testid="pick-lower">
              <option v-for="v in lists.lower" :key="v" :value="v">{{ v }}</option>
            </select>
          </label>
          <label class="grid gap-1 text-sm">Expected upper level
            <select v-model="upper" class="min-h-[44px] rounded border border-line" data-testid="pick-upper">
              <option v-for="v in lists.upper" :key="v" :value="v">{{ v }}</option>
            </select>
          </label>
          <p class="text-xs text-ink-muted" data-testid="range-note">{{ RANGE_NOTE }}</p>
          <p v-if="derivedReading" class="text-sm font-medium" data-testid="range-reading">{{ derivedReading.text }}</p>
          <label v-if="derivedReading" class="grid gap-1 text-sm">Strategies will use this view
            <select v-model="readingChoice" class="min-h-[44px] rounded border border-line" data-testid="pick-reading">
              <option :value="null">{{ derivedReading.label }} (from your range)</option>
              <option v-for="r in RANGE_READINGS.filter((x) => x.key !== derivedReading.key)" :key="r.key" :value="r.key">{{ r.label }}</option>
            </select>
          </label>
        </template>
        <button
type="button" class="min-h-[44px] w-full rounded bg-accent px-4 text-white sm:w-auto" data-testid="show-strategies"
                :disabled="!expiry || !contracts.length || current === null" @click="showStrategies">Show strategies</button>
      </div>

      <div v-else class="mt-4" data-testid="step-results">
        <h2 class="text-lg font-semibold" data-testid="results-heading">{{ heading }}</h2>
        <p v-if="notSure" class="text-xs text-ink-muted" data-testid="range-note">{{ RANGE_NOTE }}</p>
        <p v-if="matched?.fallback" class="mt-1 text-sm" data-testid="no-fit">{{ NO_FIT }}</p>
        <p v-if="busy" class="mt-2 text-sm" data-testid="results-loading">Loading…</p>
        <p v-else-if="!cards.length" class="mt-2 text-sm" data-testid="none-listed">{{ NONE_LISTED }}</p>
        <ul class="mt-3 grid gap-3 sm:grid-cols-2">
          <li
v-for="c in shownCards" :key="c.id" class="rounded border border-line bg-surface p-3" data-testid="strategy-card"
              :data-template-id="c.id" :data-legs="JSON.stringify(c.legs)">
            <h3 class="font-medium" data-testid="card-name">{{ c.name }}</h3>
            <p class="text-xs text-ink-muted" data-testid="card-meta">{{ c.level }} · Market view: {{ c.views.join(', ') }}</p>
            <template v-if="c.priced">
              <p class="mt-1 text-sm">Max profit: <span data-testid="card-max-profit">{{ money(c.summary.max_profit, c.summary.max_profit_unlimited) }}</span></p>
              <p class="text-sm">Max loss: <span data-testid="card-max-loss">{{ money(c.summary.max_loss, c.summary.max_loss_unlimited) }}</span></p>
              <p class="text-sm">Breakevens: <span data-testid="card-breakevens">{{ c.summary.breakevens.join(', ') || '—' }}</span></p>
              <button
type="button" class="mt-1 min-h-[44px] text-sm underline" data-testid="card-details-toggle"
                      @click="details[c.id] = !details[c.id]">View details</button>
              <div v-if="details[c.id]" class="text-xs" data-testid="card-details">
                <p>{{ c.summary.what_can_i_lose }}</p>
                <p>{{ c.summary.what_can_i_make }}</p>
                <p>{{ c.summary.where_do_i_start_losing }}</p>
                <p v-if="c.margin">Margin: {{ c.margin.required ?? c.margin.message ?? '—' }}</p>
              </div>
            </template>
            <p v-else class="mt-1 text-sm" data-testid="card-not-priced"><span class="font-semibold text-warn">Not live:</span> {{ NOT_PRICED }}</p>
            <button
type="button" class="mt-2 min-h-[44px] w-full rounded border border-line px-3 sm:w-auto" data-testid="open-in-builder"
                    @click="openInBuilder(c)">Open in Strategy Builder</button>
          </li>
        </ul>
        <button
v-if="!showAll && cards.length > CARDS_SHOWN" type="button" class="mt-3 min-h-[44px] underline" data-testid="see-more"
                @click="showAll = true">See more</button>
      </div>
    </template>
  </section>
</template>
