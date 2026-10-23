<!-- Strategy Builder, first slice (W-064; REQ-035, REQ-034 AC-1/AC-7/AC-8; ADR-008, ADR-068).
     Every number on this page is a string the outcome API returned (POST /api/strategies/outcome); the page parses no
     number to compute another. The draft strategy is the legs picked in the LegPicker (W-068: only contracts the
     catalogue API offers); a `draft` query (a JSON body of legs with planned entry and capture time) still opens a
     draft. The outcome API's leg model needs a planned entry, so only priced legs are sent; a leg without one stays in
     the picker's list with the not-connected wording. One level for everyone (ADR-168): an old `ux` query is ignored.
     W-148 (REQ-076): leg rows with -/+, multiplier, tick; each edit is one POST /strategies/leg-edit and its reply is drawn.
     States: loading, computed, stale (computed with a labelled leg), not-connected, unpriced (legs, none priced), left-out,
     refused, error, no-draft.
     New file; the legacy StrategyBuilderView computes P&L and falls back on prices in the browser, so it is not copied. -->
<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import api, { NEUTRAL_PARTS } from '@/services/api'
import StrategyTable from '@/components/strategy/StrategyTable.vue'
import PayoffChart from '@/components/strategy/PayoffChart.vue'
import SummaryCards from '@/components/strategy/SummaryCards.vue'
import MarginLine from '@/components/strategy/MarginLine.vue'
import StrategyHeader from '@/components/strategy/StrategyHeader.vue'
import StrategyActions from '@/components/strategy/StrategyActions.vue'
import TrackingPanel from '@/components/strategy/TrackingPanel.vue'
import AdvancedDetails from '@/components/strategy/AdvancedDetails.vue'
import { legQuotes } from '@/lib/strategyTable'
import StrategyFooter from '@/components/strategy/StrategyFooter.vue'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import LegPicker from '@/components/strategy/LegPicker.vue'
import ReadyMadePanel from '@/components/strategy/ReadyMadePanel.vue'
import PopFigure from '@/components/strategy/PopFigure.vue'
import SaveDraftBar from '@/components/strategy/SaveDraftBar.vue'
import LegList from '@/components/strategy/LegList.vue'
import { applyEditReply, buildEditRequest, executeRefusal } from '@/lib/legEdit'
import { NOT_CONNECTED_LABEL, buildDraft } from '@/lib/legPicker'
import { matchesLegs } from '@/lib/liveMatch'
import { INVALID_LINK_PARTS, canonicalLegs } from '@/lib/draftLink'
import ScenarioControls from '@/components/strategy/ScenarioControls.vue'
import { DEFAULT_CHOICE, choiceFields, matchesChoice } from '@/lib/scenarioChoice'
import { istTime, maxLine, nameFromPool } from '@/lib/displayFormat'
import { ORDER_PATH_OFF_SENTENCE } from '@/lib/orderPath'
import { useCapabilities } from '@/lib/brokerCapabilities'
import { useStrategyLive } from '@/composables/useStrategyLive'
import MarketClosedBanner from '@/components/states/MarketClosedBanner.vue'

const route = useRoute()
const capabilities = useCapabilities() // REQ-117: the named broker flags; null until read, {} after a failure (all off)
const state = ref('loading') // loading | computed | stale | not-connected | unpriced | refused | error | no-draft
const data = ref(null)
const errorParts = ref(NEUTRAL_PARTS)
const errorAnsweredAt = ref(null) // the failed request's server answer time (its Date header), ADR-088
const slow = ref(false)
let slowTimer = null


function readDraft() {
  try {
    const d = JSON.parse(String(route.query.draft || ''))
    return d && typeof d === 'object' && Array.isArray(d.legs) ? d : null
  } catch {
    return null
  }
}

// The picked legs. A `draft` query seeds them (each already carries its planned entry and capture time). Every leg is
// canonicalized once here (W-073); a link with a leg that will not canonicalize is refused, never half-opened.
const draftQuery = readDraft()
const canonicalQueryLegs = draftQuery ? canonicalLegs(draftQuery.legs) : []
const linkRefused = ref(draftQuery !== null && canonicalQueryLegs === null)
function legsFromQuery() {
  if (!draftQuery || canonicalQueryLegs === null) return []
  return canonicalQueryLegs.map((l, i) => ({
    id: `draft-${i}`,
    underlying: draftQuery.underlying,
    instrument_id: l.instrument_id,
    symbol: null,
    action: l.action,
    lots: l.lots,
    planned_entry: l.planned_entry,
    captured_at: l.captured_at ?? null,
    source: null,
  }))
}
const legs = ref(legsFromQuery())
// W-090 (REQ-034 AC-4, AC-6): the scenario column and range the user picked; kept across every reload and push.
const choice = ref({ ...DEFAULT_CHOICE })
if (linkRefused.value) {
  state.value = 'error'
  errorParts.value = INVALID_LINK_PARTS
}
// W-148 (REQ-076): the leg-edit state. The shape name is the server's (null until a reply named it); `updating` marks the
// old numbers while an edit is pending; `editError` is the server's refusal of the last edit.
const shapeName = ref(null)
const hasReply = ref(false)
const updating = ref(false)
const editError = ref(null)
const allLeftOut = () => legs.value.length > 0 && legs.value.every((l) => l.included === false)
let editSeq = 0
let loadSeq = 0 // only the newest outcome answer is shown
// ADR-077: "not live" follows THIS page's own socket. Set when it drops, cleared by the next push it receives; while set,
// every outcome request says `fallback: true`, so the server answers the not-live message even when another socket
// (another tab, another user) still holds the same contracts.
let socketDropped = false

async function load() {
  if (linkRefused.value) return // a refused draft link sends no request (W-073)
  const mine = ++loadSeq // every call invalidates the answers still in flight, also the ones that return early
  clearTimeout(slowTimer)
  slow.value = false
  const draft = buildDraft(legs.value)
  if (!draft) {
    state.value = legs.value.length ? (allLeftOut() ? 'left-out' : 'unpriced') : 'no-draft'
    data.value = null
    return
  }
  const fallback = socketDropped
  // A fallback reload while the not-live message is already on screen keeps it there (no flicker through 'loading').
  if (!(fallback && state.value === 'not-connected')) state.value = 'loading'
  slowTimer = setTimeout(() => (slow.value = true), 3000)
  try {
    const res = await api.post('/strategies/outcome', { ...draft, ...choiceFields(choice.value), fallback })
    if (mine !== loadSeq) return
    applyOutcome(res.data)
  } catch (e) {
    if (mine !== loadSeq) return
    errorParts.value = e?.parts ?? NEUTRAL_PARTS
    errorAnsweredAt.value = e?.answered_at ?? null
    state.value = 'error'
  } finally {
    if (mine === loadSeq) {
      clearTimeout(slowTimer)
      slow.value = false
    }
  }
}

// Issue 297 item 1: a leg opened from a link carries only its instrument id; the answer carries the catalogue's contract
// fields for it, so the picker's rows take them from the answer (display only; the draft sent to the server is unchanged).
function nameLegsFrom(body) {
  const known = new Map((body.legs ?? []).filter((a) => a.expiry && a.instrument).map((a) => [a.instrument_id, a]))
  if (!legs.value.some((l) => !l.expiry && known.has(l.instrument_id))) return
  legs.value = legs.value.map((l) => {
    const a = known.get(l.instrument_id)
    return l.expiry || !a ? l : { ...l, expiry: a.expiry, instrument_type: a.instrument, strike: a.strike ?? null }
  })
}

// One outcome answer (REST or a live push) onto the page, as the server sent it: no number is computed here (ADR-008).
function applyOutcome(body) {
  data.value = body
  nameLegsFrom(body)
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
    if (!matchesLegs(body, buildDraft(legs.value)) || !matchesChoice(body, choice.value)) return
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
  if (linkRefused.value) return
  const draft = buildDraft(legs.value)
  if (draft) live.follow({ ...draft, ...choiceFields(choice.value) })
  else live.stop()
}

// W-104: the saved strategy behind the legs on screen (Save Draft or reopen); any edit makes the draft unsaved again.
const savedId = ref(null)
// W-122: the revision the page loaded or saved (Start tracking is based on it, never on a fresh read)
const savedRevision = ref(null)
const openSaved = (next, id, revision) => {
  setLegs(next)
  savedId.value = Number.isInteger(id) ? id : null
  savedRevision.value = savedId.value === null ? null : revision ?? null
}
const onSaved = (id, revision) => {
  savedId.value = id
  savedRevision.value = revision ?? null
}
const setLegs = (next) => {
  savedId.value = null
  savedRevision.value = null
  linkRefused.value = false
  legs.value = next
  hasReply.value = false // a new leg list has no reply yet: no name or Hedge mark is invented for it
  shapeName.value = null
  editError.value = null
  load()
  syncLive()
}

// W-121 (REQ-073 AC-6): the notice a redirect from an order page carries.
const orderPathNotice = computed(() => route.query.notice === 'order_path_off')
onMounted(() => {
  load()
  syncLive()
})
// REQ-076 AC-1/AC-4/AC-6/AC-8: ONE edit goes to the server; legs, name, marks and every number come from its reply.
// Only the tick leaves a saved draft saved (it is never part of the saved strategy, AC-7); any other edit makes it unsaved.
async function editLeg(edit) {
  const body = buildEditRequest(legs.value[0]?.underlying, legs.value, edit)
  if (!body) return
  const mine = ++editSeq
  updating.value = true
  editError.value = null
  try {
    const reply = (await api.post('/strategies/leg-edit', body)).data
    if (mine !== editSeq) return
    const keep = edit.control === 'include'
    legs.value = applyEditReply(legs.value, reply)
    if (!keep) {
      savedId.value = null
      savedRevision.value = null
    }
    shapeName.value = reply.shape_name ?? null
    hasReply.value = true
    loadSeq++ // the reply carries the numbers: an outcome request still in flight is obsolete
    clearTimeout(slowTimer)
    slow.value = false
    if (reply.outcome) applyOutcome(reply.outcome)
    else {
      data.value = null
      state.value = allLeftOut() ? 'left-out' : 'unpriced'
    }
    syncLive()
  } catch (e) {
    if (mine !== editSeq) return
    editError.value = e?.parts ?? NEUTRAL_PARTS
  } finally {
    if (mine === editSeq) updating.value = false
  }
}
const focusPicker = () => document.querySelector('[data-testid="leg-picker"]')?.scrollIntoView?.()
const refusal = computed(() => executeRefusal(legs.value))
const setChoice = (next) => {
  choice.value = next
  load()
  syncLive()
}
onBeforeUnmount(() => clearTimeout(slowTimer))

const showNumbers = computed(() => (state.value === 'computed' || state.value === 'stale') && data.value?.table)
const headerUnderlying = computed(() => data.value?.underlying ?? legs.value[0]?.underlying ?? '')
const maxProfit = computed(() => maxLine(data.value?.summary, 'profit'))
const maxLoss = computed(() => maxLine(data.value?.summary, 'loss'))
const legQuoteRows = computed(() => legQuotes(data.value))
// A leg's contract name: from its own fields, else looked up from the page's draft legs by instrument id (ADR-086).
const nameOf = (leg) => nameFromPool(leg, legs.value, data.value?.underlying ?? headerUnderlying.value)
// ADR-088 "Checked at": the SERVER's answer time per state, shown in India time; never the browser clock. Unpriced: the
// newest planned-entry answer that left a leg without a price; error: the failed answer's Date header; none -> unavailable.
const checkedAt = computed(() => {
  if (state.value === 'unpriced') {
    const times = legs.value.map((l) => l.checked_at).filter(Boolean).sort((a, b) => Date.parse(a) - Date.parse(b))
    return istTime(times.length ? times[times.length - 1] : null)
  }
  return istTime(state.value === 'error' ? errorAnsweredAt.value : data.value?.answered_at)
})
const staleLegs = computed(() => (data.value?.legs ?? []).filter((l) => l.label))
</script>

<template>
  <section data-testid="strategy-builder" :data-state="state" :data-live="live.status.value">
    <h1 class="text-xl font-semibold" data-testid="page-title">Strategy Builder</h1>
    <p class="mt-1 text-sm text-ink-muted">A draft strategy and what it could do at different index levels. This is for planning, not a recommendation.</p>

    <MarketClosedBanner v-if="data?.market_closed" class="mt-2" :prices-at="data.last_price_at" />
    <p v-if="live.reconnecting.value" class="mt-2 text-sm font-medium" data-testid="live-reconnecting">{{ live.reconnectingText.value }}</p>

    <p v-if="orderPathNotice" class="mt-2 text-sm text-ink-muted" data-testid="order-path-off-notice">{{ ORDER_PATH_OFF_SENTENCE }}</p>

    <LegPicker :legs="legs" @update:legs="setLegs" />
    <ReadyMadePanel :legs="legs" @update:legs="setLegs" />
    <SaveDraftBar :legs="legs" :rules-ref="String(route.query.rules_ref || '')" @open="openSaved" @saved="onSaved" />
    <LegList
      :legs="legs" :shape-name="shapeName" :has-reply="hasReply" :updating="updating" :error-parts="editError"
      @edit="editLeg" @add-leg="focusPicker" @pick-chain="focusPicker"
    />

    <StrategyHeader v-if="state !== 'no-draft'" class="mt-3" :underlying="headerUnderlying" :is-loading="state === 'loading'" />
    <ScenarioControls v-if="state !== 'no-draft'" :choice="choice" :scenario-label="data?.scenario?.label ?? ''" @update:choice="setChoice" />

    <p v-if="state === 'loading'" class="mt-4" data-testid="state-loading">
      Working out the outcome...<span v-if="slow" data-testid="state-slow"> This is taking longer than usual.</span>
    </p>

    <p v-else-if="state === 'no-draft'" class="mt-4 text-ink-muted" data-testid="state-no-draft">No draft strategy is open. Add a leg above to start one.</p>

    <div v-else-if="state === 'unpriced'" class="mt-4 rounded border border-line bg-surface p-4" data-testid="state-unpriced">
      <p class="font-medium">{{ NOT_CONNECTED_LABEL }}</p>
      <p class="mt-1 text-sm text-ink-muted">No numbers are shown because none of the legs has a planned entry from live market data.</p>
      <p class="mt-1 text-sm text-ink-muted" data-testid="checked-at">Checked at {{ checkedAt }}</p>
    </div>

    <div v-else-if="state === 'left-out'" class="mt-4 rounded border border-line bg-surface p-4" data-testid="state-left-out">
      <p class="font-medium">Every leg is left out of the numbers.</p>
      <p class="mt-1 text-sm text-ink-muted">Tick a leg to see the numbers.</p>
    </div>

    <div v-else-if="state === 'error'" class="mt-4">
      <ErrorMessage :parts="errorParts" data-testid="state-error" />
      <p class="mt-1 text-sm text-ink-muted" data-testid="checked-at">Checked at {{ checkedAt }}</p>
    </div>

    <div v-else-if="state === 'not-connected'" class="mt-4 rounded border border-line bg-surface p-4" data-testid="state-not-connected">
      <p class="font-medium" data-testid="status-label">{{ data.status_label }}</p>
      <p class="mt-1 text-sm text-ink-muted">No numbers are shown because there is no live market data to price this draft.</p>
      <p class="mt-1 text-sm text-ink-muted" data-testid="checked-at">Checked at {{ checkedAt }}</p>
      <ul class="mt-2 text-sm" data-testid="draft-legs">
        <li v-for="leg in data.legs" :key="leg.instrument_id">{{ leg.action }} {{ leg.lots }} lot, <span data-testid="leg-name">{{ nameOf(leg) }}</span>, planned entry {{ leg.planned_entry }}</li>
      </ul>
    </div>

    <div v-else-if="state === 'refused'" class="mt-4 rounded border border-line bg-surface p-4" data-testid="state-refused">
      <p class="font-medium" data-testid="status-label">{{ data.status_label }}</p>
      <p v-if="data.reason" class="mt-1 text-sm" data-testid="refused-reason">{{ data.reason }}</p>
      <p class="mt-1 text-sm text-ink-muted">No numbers are shown for this draft.</p>
      <p class="mt-1 text-sm text-ink-muted" data-testid="checked-at">Checked at {{ checkedAt }}</p>
    </div>

    <div v-if="showNumbers" :class="updating ? 'opacity-60' : ''" :data-updating="updating ? 'true' : 'false'" data-testid="numbers">
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
      <PopFigure :pop="data.probability_of_profit ?? null" />
      <MarginLine :margin="data.margin" :capabilities="capabilities" />

      <div class="mt-4"><PayoffChart :points="data.payoff.points" /></div>
      <h2 class="mt-4 mb-1 text-sm font-medium">Outcome at each index level</h2>
      <StrategyTable
        :table="data.table"
        :max-profit="data.summary.max_profit_unlimited ? null : data.summary.max_profit"
        :max-loss="data.summary.max_loss_unlimited ? null : data.summary.max_loss"
      />
      <AdvancedDetails v-if="legQuoteRows" :rows="legQuoteRows" :name-of="nameOf" />
      <StrategyActions :has-legs="data.legs.length > 0" :is-loading="false" :saved-id="savedId" :execute-refusal="refusal" @recalculate="load" />
      <TrackingPanel :saved-id="savedId" :saved-revision="savedRevision" />
      <StrategyFooter :last-updated="data.valuation" :current-spot="data.spot_level" :underlying="data.underlying" />
    </div>
  </section>
</template>
