<!-- Strategy Builder, first slice (W-064; REQ-035, REQ-034 AC-1/AC-7/AC-8; ADR-008, ADR-068).
     Every number on this page is a string the outcome API returned (POST /api/strategies/outcome); the page parses no
     number to compute another. The draft strategy is the legs picked in the LegPicker (W-068: only contracts the
     catalogue API offers); a `draft` query (a JSON body of legs with planned entry and capture time) still opens a
     draft. The outcome API's leg model needs a planned entry, so only priced legs are sent; a leg without one stays in
     the picker's list with the not-connected wording. One level for everyone (ADR-168): an old `ux` query is ignored.
     W-148 (REQ-076): leg rows with -/+, multiplier, tick; each edit is one POST /strategies/leg-edit and its reply is drawn.
     States: loading, computed, stale (computed with a labelled leg), not-connected, unpriced (legs, none priced), left-out,
     refused, error, no-draft.
     W-192 (ADR-193 UI study b.1 + Revision 1, ADR-195): two columns at 1100 px and up. Left (572 px, min 480, sticky, own
     scroll): Region A underlying bar, Region B strategy card (LegList) with its action row, Region C bottom tabs (inside
     SaveDraftBar), Region D prices stamp. Right: the existing state panels and numbers blocks, unchanged (PR-2b/PR-2c restyle
     them). Below 1100 px the regions stack A, B, right, C, D. No value here is computed: each is a server reply field.
     New file; the legacy StrategyBuilderView computes P&L and falls back on prices in the browser, so it is not copied. -->
<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api, { NEUTRAL_PARTS } from '@/services/api'
import StrategyTable from '@/components/strategy/StrategyTable.vue'
import PayoffChart from '@/components/strategy/PayoffChart.vue'
import SummaryCards from '@/components/strategy/SummaryCards.vue'
import MoneySummary from '@/components/strategy/MoneySummary.vue'
import MarginLine from '@/components/strategy/MarginLine.vue'
import ProjectionsNote from '@/components/strategy/ProjectionsNote.vue'
import StrategyHeader from '@/components/strategy/StrategyHeader.vue'
import StrategyActions from '@/components/strategy/StrategyActions.vue'
import TrackingPanel from '@/components/strategy/TrackingPanel.vue'
import AdvancedDetails from '@/components/strategy/AdvancedDetails.vue'
import { fetchSavedDraft } from '@/lib/saveDraft'
import { legQuotes } from '@/lib/strategyTable'
import StrategyFooter from '@/components/strategy/StrategyFooter.vue'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import Icon from '@/components/common/Icon.vue'
import LegPicker from '@/components/strategy/LegPicker.vue'
import ReadyMadePanel from '@/components/strategy/ReadyMadePanel.vue'
import PopFigure from '@/components/strategy/PopFigure.vue'
import ActivityPanel from '@/components/strategy/ActivityPanel.vue'
import SaveDraftBar from '@/components/strategy/SaveDraftBar.vue'
import LegList from '@/components/strategy/LegList.vue'
import { applyEditReply, buildEditRequest, controlsFrom, executeRefusal, CLEAR_UNDO_MS, EXECUTE_WAITS_FOR_LATEST, NO_CONTROLS } from '@/lib/legEdit'
import { createNewestWins, isSuperseded } from '@/lib/newestWins'
import { NOT_CONNECTED_LABEL, buildDraft } from '@/lib/legPicker'
import { matchesLegs } from '@/lib/liveMatch'
import { INVALID_LINK_PARTS, canonicalLegs } from '@/lib/draftLink'
import ScenarioControls from '@/components/strategy/ScenarioControls.vue'
import { DEFAULT_CHOICE, choiceFields, matchesChoice } from '@/lib/scenarioChoice'
import { istClock, istTime, maxLine, nameFromPool } from '@/lib/displayFormat'
import { ORDER_PATH_OFF_SENTENCE } from '@/lib/orderPath'
import { useCapabilities } from '@/lib/brokerCapabilities'
import { useStrategyLive } from '@/composables/useStrategyLive'
import MarketClosedBanner from '@/components/states/MarketClosedBanner.vue'

const route = useRoute()
const router = useRouter()
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
// W-158 (REQ-078 AC-2/AC-3): which of Shift / Width / Hedge work and the Shift total, exactly as the newest applied reply sent them.
const controls = ref(NO_CONTROLS)
const editError = ref(null)
const editErrorIndex = ref(null) // the leg of a refused typed price (its error shows under that field), else null
const allLeftOut = () => legs.value.length > 0 && legs.value.every((l) => l.included === false)
// W-151 (REQ-119): the one newest-wins rule (src/lib/newestWins.js) for the outcome and leg-edit requests of this page;
// the numbers are marked updating while the newest request of either kind has no applied reply (AC-4).
const guard = createNewestWins()
const updating = computed(() => guard.pending.outcome || guard.pending['leg-edit'])
// ADR-077: "not live" follows THIS page's own socket. Set when it drops, cleared by the next push it receives; while set,
// every outcome request says `fallback: true`, so the server answers the not-live message even when another socket
// (another tab, another user) still holds the same contracts.
let socketDropped = false

async function load() {
  if (linkRefused.value) return // a refused draft link sends no request (W-073)
  clearTimeout(slowTimer)
  slow.value = false
  const draft = buildDraft(legs.value)
  if (!draft) {
    guard.cancel('outcome') // every call invalidates the answers still in flight, also the ones that return early
    state.value = legs.value.length ? (allLeftOut() ? 'left-out' : 'unpriced') : 'no-draft'
    data.value = null
    return
  }
  const mine = guard.next('outcome') // aborts the outcome request still in flight
  const fallback = socketDropped
  const sentKey = inputsKey()
  // A fallback reload while the not-live message is already on screen keeps it there (no flicker through 'loading').
  if (!(fallback && state.value === 'not-connected')) state.value = 'loading'
  slowTimer = setTimeout(() => (slow.value = true), 3000)
  try {
    const res = await api.post('/strategies/outcome', { ...draft, ...choiceFields(choice.value), fallback, seq: mine.seq }, { signal: mine.signal })
    if (!guard.claim('outcome', res.data, mine)) return
    // A reply for legs or a choice that are no longer on screen is dropped and asked again; one for the inputs still on
    // screen is the answer to them (also when the server echoes its own spelling), so asking again could never end.
    if (!drawable(res.data) && sentKey !== inputsKey()) return reask('outcome', mine)
    applyOutcome(res.data)
  } catch (e) {
    if (isSuperseded(e) || !guard.isNewest('outcome', mine)) return // a cancelled or older request shows nothing (AC-3)
    errorParts.value = e?.parts ?? NEUTRAL_PARTS
    errorAnsweredAt.value = e?.answered_at ?? null
    state.value = 'error'
  } finally {
    if (guard.isNewest('outcome', mine)) {
      clearTimeout(slowTimer)
      slow.value = false
    }
    guard.settle('outcome', mine)
  }
}

// Issue 297 item 1: a leg opened from a link carries only its instrument id; the answer carries the catalogue's contract
// fields for it, so the picker's rows take them from the answer (display only; the draft sent to the server is unchanged).
function nameLegsFrom(body) {
  const known = new Map((body.legs ?? []).filter((a) => a.expiry && a.instrument).map((a) => [a.instrument_id, a]))
  if (!legs.value.some((l) => !l.expiry && known.has(l.instrument_id))) return
  legs.value = legs.value.map((l) => {
    const a = known.get(l.instrument_id)
    return l.expiry || !a ? l : { ...l, expiry: a.expiry, days_to_expiry: a.days_to_expiry ?? null, instrument_type: a.instrument, strike: a.strike ?? null }
  })
}

// REQ-119 AC-4: THE one rule for every place numbers are drawn (REST outcome reply, leg-edit reply's outcome, live push):
// they are drawn only when they were made for the legs AND the choice on screen now.
const inputsKey = () => JSON.stringify([buildDraft(legs.value), choiceFields(choice.value)])
function drawable(body) {
  return matchesLegs(body, buildDraft(legs.value)) && matchesChoice(body, choice.value)
}
// A reply that is not drawable is dropped (debug log); when it answered the newest outcome request, ask again for the
// current legs and choice (load() keeps the numbers marked updating and Execute disabled until that reply lands).
function reask(kind, ticket) {
  console.debug(`${kind} reply dropped: it does not match the legs and choice on screen`)
  if (guard.isNewest(kind, ticket)) load()
}

// One outcome answer (REST or a live push) onto the page, as the server sent it: no number is computed here (ADR-008).
function applyOutcome(body) {
  data.value = body
  nameLegsFrom(body)
  if (body.state === 'COMPUTED') state.value = body.legs.some((l) => l.label) ? 'stale' : 'computed'
  else if (body.state === 'FROM_ENTRIES') state.value = 'from-entries' // REQ-077 AC-9: At Expiry from the user's prices, nothing live
  else if (body.state === 'NOT_CONNECTED') state.value = 'not-connected'
  else state.value = 'refused'
}

// W-065 (REQ-035 AC-4; ADR-068 (2), ADR-077): live numbers from the platform socket. A push replaces the page's answer
// and makes any REST answer still in flight obsolete; when the socket drops, the REST route answers, and its not-live
// label (REQ-049 AC-5's message with the last price time) is the server's text.
const live = useStrategyLive({
  onPush: (body) => {
    // A late push of the previous strategy (the socket was told the new one a moment ago) is dropped, never shown.
    if (!drawable(body)) return
    socketDropped = false
    guard.cancel('outcome') // the push answers: an outcome request still in flight is obsolete
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
// REQ-134 AC-2: the saved strategy this screen is editing ({ id, revision, name }: the revision and name the page loaded or saved).
// Unlike savedId it SURVIVES edits, so Save after an edit updates that strategy (PUT with this revision) instead of creating a
// second row (RD-106). It is replaced on open/save, and dropped by Clear all (held for Undo).
const openStrategy = ref(null)
const openError = ref(null) // the catalogue message when ?strategy= cannot be opened; the screen is kept
// REQ-134 AC-5: the URL names the strategy (?strategy=<id>) so a reload opens it again; a `draft` link is dropped from it.
function nameInUrl(id) {
  const { draft: _link, ...rest } = route.query
  router.replace({ path: route.path, query: { ...rest, strategy: String(id) } })
}
const takeStrategy = (id, revision, name) => {
  openStrategy.value = Number.isInteger(id) ? { id, revision: revision ?? null, name: name ?? null } : null
  if (openStrategy.value) nameInUrl(id)
}
const openSaved = (next, id, revision, name) => {
  setLegs(next)
  savedId.value = Number.isInteger(id) ? id : null
  savedRevision.value = savedId.value === null ? null : revision ?? null
  takeStrategy(id, revision, name)
}
// REQ-134 AC-3: a rename from the bar changes only the shown name (the revision stays the one the page loaded).
const onRenamed = (id, name) => {
  if (openStrategy.value?.id === id) openStrategy.value = { ...openStrategy.value, name }
}
// REQ-070 AC-6: the strategy open here was deleted (from the saved list): the screen is a new unsaved strategy again, so a Save asks a
// name and POSTs instead of PUTting a hidden id. The legs stay on screen; the ?strategy= link is dropped.
const onDeleted = (id) => {
  if (openStrategy.value?.id !== id) return
  openStrategy.value = null
  savedId.value = null
  savedRevision.value = null
  const { strategy: _gone, ...rest } = route.query
  router.replace({ path: route.path, query: rest })
}
const onSaved = (id, revision, name) => {
  savedId.value = id
  savedRevision.value = revision ?? null
  takeStrategy(id, revision, name)
}
// AC-5: a reload of /strategy/builder?strategy=<id> reads the saved copy (legs and planned entries as saved, never today's prices).
const STRATEGY_ID = /^[1-9]\d{0,17}$/
async function openFromUrl() {
  const id = String(route.query.strategy ?? '')
  if (!STRATEGY_ID.test(id)) return
  const before = legs.value
  try {
    const saved = await fetchSavedDraft(api, id)
    if (legs.value !== before) return // the user changed the legs while the read was out: never overwrite them
    openSaved(saved.legs, saved.id, saved.revision, saved.name)
  } catch (e) {
    openError.value = e?.parts ?? NEUTRAL_PARTS // not found, unreadable, request failed: the screen stays as it is
  }
}
const setLegs = (next) => {
  dropUndo() // any new leg list supersedes an Undo still on offer: it can never restore over new legs
  savedId.value = null
  savedRevision.value = null
  linkRefused.value = false
  legs.value = next
  hasReply.value = false // a new leg list has no reply yet: no name or Hedge mark is invented for it
  shapeName.value = null
  controls.value = NO_CONTROLS // REQ-078 AC-9: a picker replacement (or any new leg list) ends the Shift total; the server cannot see it
  editError.value = null
  load()
  syncLive()
  readShape()
}
// REQ-076 AC-8: the shape name and Hedge marks come from the server on load and after Done, before any edit.
function readShape() {
  if (!linkRefused.value && legs.value.length >= 2) editLeg({ control: 'read' })
}
const removeLeg = (i) => setLegs(legs.value.filter((_, k) => k !== i))

// REQ-135 AC-1: Clear all legs. The legs (and the saved strategy they belong to) are held for CLEAR_UNDO_MS; the clear is
// an ordinary edit (the saved copy changes only on Save), exactly as removing the last leg is. One timer, not a recurring one.
const undoHeld = ref(null) // { legs, savedId, savedRevision, openStrategy } of the last clear, or null (expired, used, superseded, left)
let undoTimer = null
function dropUndo() {
  clearTimeout(undoTimer)
  undoHeld.value = null
}
function clearAll() {
  if (!legs.value.length) return
  const held = { legs: legs.value, savedId: savedId.value, savedRevision: savedRevision.value, openStrategy: openStrategy.value } // taken BEFORE setLegs([]) nulls them
  setLegs([])
  openStrategy.value = null // a cleared screen is a new strategy: the next Save asks a name
  undoHeld.value = held
  undoTimer = setTimeout(dropUndo, CLEAR_UNDO_MS)
}
function undoClear() {
  const held = undoHeld.value
  if (!held) return
  setLegs(held.legs) // drops the Undo, reloads the numbers and the live follow
  savedId.value = held.savedId
  savedRevision.value = held.savedRevision
  openStrategy.value = held.openStrategy
}

// W-121 (REQ-073 AC-6): the notice a redirect from an order page carries.
const orderPathNotice = computed(() => route.query.notice === 'order_path_off')
onMounted(() => {
  load()
  syncLive()
  readShape()
  openFromUrl()
})
// REQ-076 AC-1/AC-4/AC-6/AC-8: ONE edit goes to the server; legs, name, marks and every number come from its reply.
// Only the tick leaves a saved draft saved (it is never part of the saved strategy, AC-7); any other edit makes it unsaved.
// The server's leg-edit takes the view but has no range field: a custom range is never sent there (it is asked for by load()).
const editView = () => {
  const { view } = choiceFields(choice.value)
  return view ? { view } : {}
}
async function editLeg(edit) {
  const body = buildEditRequest(legs.value[0]?.underlying, legs.value, edit, controls.value.shiftTotal)
  if (!body) return
  const mine = guard.next('leg-edit') // aborts the edit still in flight
  editError.value = null
  editErrorIndex.value = null
  try {
    const reply = (await api.post('/strategies/leg-edit', { ...body, ...editView(), seq: mine.seq }, { signal: mine.signal })).data
    if (!guard.claim('leg-edit', reply, mine)) return
    if (edit.control === 'read') {
      // changes no leg and no number: only the contract ids, the name and the Hedge marks are taken (load() owns the outcome)
      if (Array.isArray(reply?.legs) && reply.legs.length === legs.value.length) {
        legs.value = applyEditReply(legs.value, reply)
        shapeName.value = reply.shape_name ?? null
        controls.value = controlsFrom(reply)
        hasReply.value = true
      }
      return
    }
    const keep = edit.control === 'include'
    legs.value = applyEditReply(legs.value, reply)
    if (!keep) {
      savedId.value = null
      savedRevision.value = null
    }
    shapeName.value = reply.shape_name ?? null
    controls.value = controlsFrom(reply) // the server's controls and Shift total (null after a step, Width or Hedge)
    hasReply.value = true
    // The embedded outcome is the server's At Expiry on its default range, so it is drawn only when it matches the legs and
    // choice on screen and no outcome request is pending (that one is never cancelled here: its reply is checked the same way).
    if (reply.outcome && drawable(reply.outcome) && !guard.pending.outcome) {
      guard.cancel('outcome')
      clearTimeout(slowTimer)
      slow.value = false
      applyOutcome(reply.outcome)
    } else if (!reply.outcome) {
      guard.cancel('outcome')
      clearTimeout(slowTimer)
      slow.value = false
      data.value = null
      state.value = allLeftOut() ? 'left-out' : 'unpriced'
    } else if (!guard.pending.outcome) {
      console.debug('leg-edit outcome dropped: it does not match the legs and choice on screen')
      load() // the numbers for the current legs and choice
    }
    syncLive()
  } catch (e) {
    if (isSuperseded(e) || !guard.isNewest('leg-edit', mine) || edit.control === 'read') return // a failed read leaves the page as load() drew it, no error text
    editError.value = e?.parts ?? NEUTRAL_PARTS
    editErrorIndex.value = edit.control === 'price' ? edit.index : null
  } finally {
    guard.settle('leg-edit', mine)
  }
}
const picker = ref(null)
// W-192 UI-108/UI-110: the inline add-leg form sits in the left column behind Add/Edit (open on an empty builder) until the
// PR-3 drawer replaces it. REQ-076 AC-5: Lots or Quantity is chosen in Region A's Settings popover (UI-103).
const pickerOpen = ref(legs.value.length === 0)
const settingsOpen = ref(false)
const legUnit = ref('lots')
// Edit / Reprice on a leg row: the picker's own edit form for that leg (same handler, same requests as before)
const openInPicker = (i) => {
  const leg = legs.value[i]
  if (!leg) return
  pickerOpen.value = true
  picker.value?.startEdit(leg)
}
const focusPicker = () => {
  pickerOpen.value = true
  document.querySelector('[data-testid="leg-picker"]')?.scrollIntoView?.()
}
// "..." menu items: History opens the existing activity panel; Start tracking goes to the existing tracking block (right column)
const showHistory = () => {
  const toggle = document.querySelector('[data-testid="activity-toggle"]')
  toggle?.scrollIntoView?.()
  toggle?.click()
}
const goToTracking = () => document.querySelector('[data-testid="tracking-panel"]')?.scrollIntoView?.()
// AC-4: Execute stays disabled, with its reason, until the latest outcome and edit reply has arrived
const refusal = computed(() => executeRefusal(legs.value) ?? (updating.value ? EXECUTE_WAITS_FOR_LATEST : null))
const setChoice = (next) => {
  choice.value = next
  load()
  syncLive()
}
onBeforeUnmount(() => {
  clearTimeout(slowTimer)
  clearTimeout(undoTimer)
})

const NO_LIVE_LEVEL = '—' // no live index price in this answer: the level card shows a dash, never a typed or centred number
const showNumbers = computed(() => ['computed', 'stale', 'from-entries'].includes(state.value) && data.value?.table)
const fromEntries = computed(() => state.value === 'from-entries')
const headerUnderlying = computed(() => data.value?.underlying ?? legs.value[0]?.underlying ?? '')
const maxProfit = computed(() => maxLine(data.value?.summary, 'profit'))
const maxLoss = computed(() => maxLine(data.value?.summary, 'loss'))
// REQ-077 AC-6: each leg's live LTP string from the outcome the page already has (a FROM_ENTRIES answer carries none)
const ltpById = computed(() => Object.fromEntries((data.value?.legs ?? []).filter((l) => l.ltp != null).map((l) => [l.instrument_id, l.ltp])))
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
// REQ-135 AC-3: the ONE 'Prices as of' stamp, from the answer's last_price_at. A stale answer shows its data-health label in
// place of the time; while the feed reconnects the reconnecting sentence (same helper, already on the page) is that label;
// while the market-closed banner shows, the banner carries the time. Nothing here when the answer has no price time.
const pricesStamp = computed(() => {
  const d = data.value
  if (!d || fromEntries.value || d.market_closed || live.reconnecting.value) return null
  const label = d.output_label || staleLegs.value[0]?.label
  if (label) return { kind: 'health', text: label }
  const at = istClock(d.last_price_at)
  return at ? { kind: 'time', text: `Prices as of ${at} IST` } : null
})
</script>

<template>
  <section data-testid="strategy-builder" :data-state="state" :data-live="live.status.value">
    <h1 class="text-xl font-semibold" data-testid="page-title">Strategy Builder</h1>
    <p class="mt-1 text-sm text-ink-muted">A draft strategy and what it could do at different index levels. This is for planning, not a recommendation.</p>

    <MarketClosedBanner v-if="data?.market_closed" class="mt-2" :prices-at="data.last_price_at" />
    <p v-if="orderPathNotice" class="mt-2 text-sm text-ink-muted" data-testid="order-path-off-notice">{{ ORDER_PATH_OFF_SENTENCE }}</p>

    <div class="mt-3 grid grid-cols-1 gap-4 min-[1100px]:grid-cols-[minmax(480px,572px)_minmax(0,1fr)]" data-testid="builder-columns">
      <div
        class="flex min-w-0 flex-col gap-4 max-[1099px]:contents min-[1100px]:sticky min-[1100px]:top-[72px] min-[1100px]:max-h-[calc(100vh-88px)] min-[1100px]:self-start min-[1100px]:overflow-y-auto"
        data-testid="builder-left"
      >
        <!-- Region A (UI-100, UI-103): the underlying and the outcome reply's spot level; day change omitted until REQ-139 sends it -->
        <div class="flex h-12 items-center justify-between rounded-lg border border-line bg-surface px-3 text-sm" data-testid="underlying-bar">
          <span class="flex items-center gap-2">
            <span class="font-semibold" data-testid="underlying-name">{{ headerUnderlying || '-' }}</span>
            <span class="font-semibold" data-testid="underlying-spot" :title="data?.output_label || undefined">{{ data?.spot_level ?? NO_LIVE_LEVEL }}</span>
          </span>
          <span class="relative">
            <button
              type="button" class="flex items-center gap-1 rounded border border-line px-2 py-1" aria-haspopup="dialog" :aria-expanded="settingsOpen ? 'true' : 'false'"
              data-testid="builder-settings" @click="settingsOpen = !settingsOpen" @keydown.esc="settingsOpen = false"
            ><Icon name="gear" :size="14" />Settings</button>
            <span v-show="settingsOpen" role="dialog" aria-label="Builder settings" class="absolute right-0 top-full z-20 mt-1 w-[320px] rounded-lg border border-line bg-surface p-3 shadow" data-testid="settings-popover" @keydown.esc="settingsOpen = false">
              <label class="flex items-center justify-between gap-2">Show legs as
                <select v-model="legUnit" class="rounded border border-line px-1" data-testid="lots-quantity-switch">
                  <option value="lots">Lots</option>
                  <option value="quantity">Quantity</option>
                </select>
              </label>
            </span>
          </span>
        </div>

        <ErrorMessage v-if="openError" :parts="openError" compact prefix="open-error" data-testid="open-error" />
        <!-- Region B (UI-104..UI-108) -->
        <LegList
          :legs="legs" :shape-name="shapeName" :has-reply="hasReply" :controls="controls" :updating="updating" :error-parts="editError" :error-index="editErrorIndex" :ltp-by-id="ltpById"
          :undo-offered="undoHeld !== null" :leg-unit="legUnit" :strategy-name="openStrategy?.name ?? null"
          @edit="editLeg" @edit-leg="openInPicker" @remove="removeLeg" @add-leg="focusPicker" @pick-chain="focusPicker" @clear-all="clearAll" @undo-clear="undoClear"
        >
          <template #money>
            <div v-if="showNumbers" :class="updating ? 'opacity-60' : ''"><MoneySummary class="!mt-0 !px-0" :net-premium="data.summary.net_premium ?? null" :charges="data.charges_breakdown ?? null" /></div>
          </template>
        </LegList>
        <div v-show="pickerOpen" data-testid="leg-picker-panel"><LegPicker ref="picker" :legs="legs" :show-leg-list="false" @update:legs="setLegs" /></div>
        <SaveDraftBar :legs="legs" :rules-ref="String(route.query.rules_ref || '')" :current="openStrategy" class="max-[1099px]:contents" @open="openSaved" @saved="onSaved" @renamed="onRenamed" @deleted="onDeleted">
          <template #add-edit>
            <button type="button" class="rounded border border-line px-3 py-1" :aria-expanded="pickerOpen ? 'true' : 'false'" data-testid="add-edit" @click="pickerOpen = !pickerOpen">Add/Edit</button>
          </template>
          <template #menu="{ close }">
            <button v-if="openStrategy" type="button" role="menuitem" data-testid="menu-activity" @click="close(); showHistory()">History</button>
            <button v-if="savedId" type="button" role="menuitem" data-testid="menu-start-tracking" @click="close(); goToTracking()">Start tracking</button>
          </template>
          <template #ready-made><ReadyMadePanel :legs="legs" @update:legs="setLegs" /></template>
        </SaveDraftBar>
        <ActivityPanel v-if="openStrategy" :current="openStrategy" @open="openSaved" />

        <!-- Region D (UI-150): the one prices stamp and the reconnecting line -->
        <div class="text-xs text-ink-muted max-[1099px]:order-3" data-testid="stamp-line">
          <p v-if="live.reconnecting.value" class="font-medium" data-testid="live-reconnecting">{{ live.reconnectingText.value }}</p>
          <p v-if="showNumbers && pricesStamp" data-testid="prices-as-of" :data-kind="pricesStamp.kind">{{ pricesStamp.text }}</p>
        </div>
      </div>

      <div class="min-w-0 max-[1099px]:order-1" data-testid="builder-right">
        <StrategyHeader v-if="state !== 'no-draft'" :underlying="headerUnderlying" :is-loading="state === 'loading'" />
        <ScenarioControls v-if="state !== 'no-draft'" :choice="choice" :scenario-label="data?.scenario?.label ?? ''" @update:choice="setChoice" />

        <p v-if="state === 'loading'" class="mt-4" data-testid="state-loading">
          Working out the outcome...<span v-if="slow" data-testid="state-slow"> This is taking longer than usual.</span>
        </p>

        <p v-else-if="state === 'no-draft'" class="mt-4 text-ink-muted" data-testid="state-no-draft">No draft strategy is open. Add a leg to start one.</p>

        <div v-else-if="state === 'unpriced'" class="mt-4 rounded border border-line bg-surface p-4" data-testid="state-unpriced">
          <p class="font-medium">{{ NOT_CONNECTED_LABEL }}</p>
          <p class="mt-1 text-sm text-ink-muted">No numbers are shown because not every leg has a planned entry from live market data.</p>
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
            <p v-if="fromEntries && data.status_label" data-testid="status-label">{{ data.status_label }}</p>
            <p v-if="data.output_label" data-testid="output-label">{{ data.output_label }}</p>
            <p v-if="fromEntries && data.centre_label" data-testid="centre-label">{{ data.centre_label }}</p>
            <p v-if="fromEntries && data.scenario && !data.scenario.available" data-testid="estimate-unavailable">{{ data.scenario.unavailable_reason }}</p>
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
            :current-spot="data.spot_level ?? NO_LIVE_LEVEL"
            :underlying="data.underlying"
            :reward-risk="data.summary.reward_risk ?? null"
            :reward-risk-reason="data.summary.reward_risk_reason ?? null"
            :time-value="data.summary.time_value ?? null"
            :intrinsic-value="data.summary.intrinsic_value ?? null"
            :risk-reward="data.summary.risk_reward ?? null"
            :value-label="data.summary.value_label ?? null"
            :value-reason="data.summary.value_reason ?? null"
            :funds-share="data.summary.funds_share ?? null"
          />
          <ProjectionsNote />
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
          <StrategyActions :saved-id="savedId" :execute-refusal="refusal" />
          <TrackingPanel :saved-id="savedId" :saved-revision="savedRevision" />
          <StrategyFooter :current-spot="data.spot_level ?? ''" :underlying="data.underlying" />
        </div>
      </div>
    </div>
  </section>
</template>
