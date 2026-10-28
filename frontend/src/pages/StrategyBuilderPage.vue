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
     them). W-193 (PR-2b): the summary card (Region E) heads the numbers, the Important info note sits under it.
     Below 1100 px the regions stack A, B, right, C, D. No value here is computed: each is a server reply field.
     New file; the legacy StrategyBuilderView computes P&L and falls back on prices in the browser, so it is not copied. -->
<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useOutsideClose } from '@/composables/useOutsideClose'
import api, { NEUTRAL_PARTS } from '@/services/api'
import ChartCard from '@/components/strategy/ChartCard.vue'
import LowerCard from '@/components/strategy/LowerCard.vue'
import SummaryCards from '@/components/strategy/SummaryCards.vue'
import MoneySummary from '@/components/strategy/MoneySummary.vue'
import MarginLine from '@/components/strategy/MarginLine.vue'
import ProjectionsNote from '@/components/strategy/ProjectionsNote.vue'
import StrategyActions from '@/components/strategy/StrategyActions.vue'
import TrackingPanel from '@/components/strategy/TrackingPanel.vue'
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'
import AdvancedDetails from '@/components/strategy/AdvancedDetails.vue'
import { fetchSavedDraft } from '@/lib/saveDraft'
import { legQuotes } from '@/lib/strategyTable'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import Icon from '@/components/common/Icon.vue'
import LegPicker from '@/components/strategy/LegPicker.vue'
import ReadyMadePanel from '@/components/strategy/ReadyMadePanel.vue'
import { UNDERLYINGS } from '@/lib/underlyings'
import PopFigure from '@/components/strategy/PopFigure.vue'
import ActivityPanel from '@/components/strategy/ActivityPanel.vue'
import Drawer from '@/components/common/Drawer.vue'
import SaveDraftBar from '@/components/strategy/SaveDraftBar.vue'
import LegList from '@/components/strategy/LegList.vue'
import { applyEditReply, buildEditRequest, controlsFrom, executeRefusal, CLEAR_UNDO_MS, EXECUTE_WAITS_FOR_LATEST, NO_CONTROLS } from '@/lib/legEdit'
import { createNewestWins, isSuperseded } from '@/lib/newestWins'
import { NOT_CONNECTED_LABEL, buildDraft } from '@/lib/legPicker'
import { matchesLegs } from '@/lib/liveMatch'
import { INVALID_LINK_PARTS, canonicalLegs } from '@/lib/draftLink'
import ScenarioControls from '@/components/strategy/ScenarioControls.vue'
import { CHART_FLAGS, DEFAULT_CHOICE, choiceFields, matchesChoice } from '@/lib/scenarioChoice'
import { istClock, istTime, nameFromPool } from '@/lib/displayFormat'
import { summaryFigure } from '@/lib/summaryFigures'
import { ORDER_PATH_OFF_SENTENCE } from '@/lib/orderPath'
import { useCapabilities } from '@/lib/brokerCapabilities'
import { useStrategyLive } from '@/composables/useStrategyLive'
import { NOT_LIVE_LABEL as INDEX_NOT_LIVE, headerLevel, useIndexAnswer } from '@/composables/useIndexLive'
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
let draftQuery = readDraft()
let canonicalQueryLegs = draftQuery ? canonicalLegs(draftQuery.legs) : []
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
    close_at: typeof l.close_at === 'string' ? l.close_at : null, // ADR-197: a draft link keeps the close label
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
  // Review 2: numbers already on screen stay mounted (marked updating) while the new answer is worked out, so the
  // scenario switch keeps focus, the page does not jump and the chart is not rebuilt.
  keepNumbers.value = showNumbers.value
  if (!(fallback && state.value === 'not-connected')) state.value = 'loading'
  slowTimer = setTimeout(() => (slow.value = true), 3000)
  try {
    const res = await api.post('/strategies/outcome', { ...draft, ...choiceFields(choice.value), ...CHART_FLAGS, fallback, seq: mine.seq }, { signal: mine.signal })
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
  if (draft) live.follow({ ...draft, ...choiceFields(choice.value), ...CHART_FLAGS })
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
    if (String(route.query.strategy ?? '') !== id) return // F-4: the URL moved on while the read was out
    if (legs.value !== before) return // the user changed the legs while the read was out: never overwrite them
    openSaved(saved.legs, saved.id, saved.revision, saved.name)
  } catch (e) {
    openError.value = e?.parts ?? NEUTRAL_PARTS // not found, unreadable, request failed: the screen stays as it is
  }
}
// F-4: the page stays mounted when only the query changes (App.vue's router-view is unkeyed), so a new ?strategy= / ?draft= is
// opened here through the same paths a fresh load uses. The ?strategy= the page itself writes after Save names the open strategy
// already, so it is not read again. Unsaved edits are replaced, exactly as the Saved tab's Open does (openSaved, no prompt).
watch(() => route.query.strategy, (v) => {
  if (!v || String(openStrategy.value?.id) === String(v)) return
  openError.value = null
  openFromUrl()
})
watch(() => route.query.draft, (v) => {
  if (!v) return // dropped from the URL by Save
  draftQuery = readDraft()
  canonicalQueryLegs = draftQuery ? canonicalLegs(draftQuery.legs) : []
  const refused = draftQuery !== null && canonicalQueryLegs === null
  openStrategy.value = null
  openError.value = null
  setLegs(legsFromQuery())
  if (refused) {
    linkRefused.value = true
    state.value = 'error'
    errorParts.value = INVALID_LINK_PARTS
  }
})
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
  index.start() // the page holds the index itself (its own socket), so an empty builder still has a spot
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
// W-195 (ADR-193 UI-200): the leg picker is the left slide-in drawer, opened by Add/Edit or the empty state's buttons; the
// inline add-leg form is gone from the left column. REQ-076 AC-5: Lots or Quantity is chosen in Region A's Settings popover.
const pickerOpen = ref(false)
const pickerFolded = ref(false) // GC-UI 6c D-C35: the drawer was folded away by "Show Editor"
const settingsOpen = ref(false)
const settingsRoot = ref(null)
const settingsButton = ref(null)
async function closeSettings() {
  if (!settingsOpen.value) return
  settingsOpen.value = false
  await nextTick()
  settingsButton.value?.focus?.()
}
useOutsideClose(() => settingsOpen.value, () => settingsRoot.value, closeSettings)
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
}
// GC-UI 3a D-A07: the tick-all box runs the existing per-leg include edit once per leg that differs, one after another
// (each edit's reply is drawn before the next is sent, so no edit cancels another); no include rule of its own
async function includeAll(included) {
  for (let i = 0; i < legs.value.length; i++) {
    if ((legs.value[i]?.included !== false) !== included) await editLeg({ control: 'include', index: i, included })
    if (editError.value) return // a refused edit stops the run with its reason shown; nothing further is sent
  }
}
// W-195 review 7: "Pick from Option Chain" is not a second Add leg: it opens the drawer on the Strikes tab
const pickFromChain = () => {
  picker.value?.showStrikes()
  pickerOpen.value = true
}
// "..." menu items: History opens the existing activity panel in the shared right Drawer (UI-108); Start tracking goes to the
// existing tracking block (right column)
const historyOpen = ref(false)
const showHistory = () => {
  historyOpen.value = true
}
// a restore from the drawer opens that configuration through the one open path and closes the drawer
const restoreFromHistory = (legsIn, id, revision, name) => {
  historyOpen.value = false
  openSaved(legsIn, id, revision, name)
}
const goToTracking = () => document.querySelector('[data-testid="tracking-panel"]')?.scrollIntoView?.()
// AC-4: Execute stays disabled, with its reason, until the latest outcome and edit reply has arrived
const refusal = computed(() => executeRefusal(legs.value) ?? (updating.value ? EXECUTE_WAITS_FOR_LATEST : null))
const setChoice = (next) => {
  choice.value = next
  load()
  syncLive()
}
// GC-UI b1 D-B10 (REQ-083 AC-7): the graph's Zoom is a new range pick; the engine sends the points for it
const zoomTo = (range) => setChoice({ ...choice.value, ...range })
// GC-UI b2 D-B24 (REQ-137 AC-1): the payoff table's interval menu is a pick too; the engine makes the rows at that step
const stepTo = (payoffStep) => setChoice({ ...choice.value, payoffStep })
// the reply's scenario grid a zoom stays on (null: no zoom offered, nothing guessed)
const zoomGrid = computed(() => {
  const sc = data.value?.scenario
  return sc?.step && sc.start && sc.end ? { step: sc.step, start: sc.start, end: sc.end } : null
})
onBeforeUnmount(() => {
  clearTimeout(slowTimer)
  clearTimeout(undoTimer)
})

const index = useIndexAnswer()
const indexLevel = computed(() => headerLevel(data.value?.spot_level, index.shownValue(index.rowFor(headerUnderlying.value || pickUnderlying.value))))
// ADR-200 (2): the page's one market-closed banner. With an outcome reply it follows that reply; with none (no legs yet,
// the drawer priced from the last close) it follows the index answer the page already holds (its own socket / REST read)
const closedBanner = computed(() => {
  if (data.value) return data.value.market_closed ? { at: data.value.last_price_at } : null
  const a = index.answer.value
  return a?.market_closed === true ? { at: a.last_price_at ?? null } : null
})
const NO_LIVE_LEVEL = '—' // no live index price in this answer: the level card shows a dash, never a typed or centred number
// W-194 (ADR-194): the chart card's tab, Payoff sub-view and Full table switch, kept across recomputes.
const chartTab = ref('payoff')
const chartPayoffView = ref('graph')
const chartFullTable = ref(false)
// Review 2: true while a reload runs over numbers that were on screen when it started (load() sets it); any other state
// change draws its own block, so this only matters during 'loading'.
const keepNumbers = ref(false)
const showNumbers = computed(() => (['computed', 'stale', 'from-entries'].includes(state.value) || (state.value === 'loading' && keepNumbers.value)) && !!data.value?.table)
const keptWhileLoading = computed(() => state.value === 'loading' && showNumbers.value)
// Review 2: the summary card's Reward/Risk or Risk/Reward choice, owned here so a recompute never resets it
const ratioFlipped = ref(false)
const fromEntries = computed(() => state.value === 'from-entries')
const pickUnderlying = ref('NIFTY')
const headerUnderlying = computed(() => data.value?.underlying ?? legs.value[0]?.underlying ?? '')
// REQ-077 AC-6: each leg's live LTP string from the outcome the page already has (a FROM_ENTRIES answer carries none)
const ltpById = computed(() => Object.fromEntries((data.value?.legs ?? []).filter((l) => l.ltp != null).map((l) => [l.instrument_id, l.ltp])))
// GC-UI D-PX (REQ-152 AC-2): the server's two-decimal price texts by instrument id; the browser prints these, never the values
const priceTextById = computed(() => Object.fromEntries((data.value?.legs ?? []).map((l) => [l.instrument_id, { ltp_display: l.ltp_display ?? null, planned_entry_display: l.planned_entry_display ?? null }])))
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
  // D-A42: the output label is shown once, beside the summary figures; only a stale leg's label stands in for the time
  const label = staleLegs.value[0]?.label
  if (label) return { kind: 'health', text: label }
  const at = istClock(d.last_price_at)
  return at ? { kind: 'time', text: `Prices as of ${at} IST` } : null
})
</script>

<template>
  <section data-testid="strategy-builder" :data-state="state" :data-live="live.status.value">
    <!-- W-193 (UI-005): the visible title block is gone (the top bar breadcrumb names the page); the heading stays for screen
         readers. The planning sentence moved into the Important info note under the summary card. -->
    <h1 class="sr-only" data-testid="page-title">Strategy Builder</h1>

    <MarketClosedBanner v-if="closedBanner" class="mt-2" :prices-at="closedBanner.at" />
    <p v-if="orderPathNotice" class="mt-2 text-sm text-ink-muted" data-testid="order-path-off-notice">{{ ORDER_PATH_OFF_SENTENCE }}</p>

    <div class="mt-3 grid grid-cols-1 gap-4 min-[1100px]:grid-cols-[minmax(480px,572px)_minmax(0,1fr)]" data-testid="builder-columns">
      <div
        class="flex min-w-0 flex-col gap-4 max-[1099px]:contents min-[1100px]:sticky min-[1100px]:top-[72px] min-[1100px]:max-h-[calc(100vh-88px)] min-[1100px]:self-start min-[1100px]:overflow-y-auto"
        data-testid="builder-left"
      >
        <!-- Region A (UI-100, UI-103): the underlying and the outcome reply's spot level; day change omitted until REQ-139 sends it -->
        <!-- GC-UI 3a D-A01: the index sits in a field with a magnifier inside it; Settings is a separate boxed button beside it -->
        <div class="flex h-12 items-center gap-2 text-sm" data-testid="underlying-bar">
          <span class="flex h-10 min-w-0 flex-1 items-center gap-2 rounded-lg border border-line bg-surface px-3" data-testid="underlying-field">
            <span class="text-ink-muted" data-testid="underlying-search-icon"><Icon name="search" :size="16" /></span>
            <span v-if="headerUnderlying" class="font-semibold" data-testid="underlying-name">{{ headerUnderlying }}</span>
            <!-- an empty builder chooses its underlying here (Region A owns it; the Ready-made tab reads it) -->
            <select v-else v-model="pickUnderlying" class="h-8 rounded border border-line px-1 font-semibold" aria-label="Underlying" data-testid="underlying-select">
              <option v-for="u in UNDERLYINGS" :key="u" :value="u">{{ u }}</option>
            </select>
            <span class="font-semibold" data-testid="underlying-spot" :title="data?.output_label || (indexLevel === null && index.notLive() ? INDEX_NOT_LIVE : undefined)">{{ indexLevel ?? NO_LIVE_LEVEL }}</span>
          </span>
          <span ref="settingsRoot" class="relative" @keydown.esc="closeSettings">
            <button
              ref="settingsButton" type="button" class="flex h-10 items-center gap-1 rounded-lg border border-line bg-surface px-3" aria-haspopup="dialog" :aria-expanded="settingsOpen ? 'true' : 'false'"
              data-testid="builder-settings" @click="settingsOpen ? closeSettings() : (settingsOpen = true)"
            ><Icon name="gear" :size="14" />Settings</button>
            <span v-show="settingsOpen" role="dialog" aria-label="Builder settings" class="absolute right-0 top-full z-20 mt-1 w-[320px] rounded-lg border border-line bg-surface p-3 shadow" data-testid="settings-popover">
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
          :legs="legs" :shape-name="shapeName" :has-reply="hasReply" :controls="controls" :updating="updating" :error-parts="editError" :error-index="editErrorIndex" :ltp-by-id="ltpById" :price-text-by-id="priceTextById"
          :undo-offered="undoHeld !== null" :leg-unit="legUnit" :strategy-name="openStrategy?.name ?? null"
          @edit="editLeg" @edit-leg="openInPicker" @include-all="includeAll" @remove="removeLeg" @add-leg="focusPicker" @pick-chain="pickFromChain" @clear-all="clearAll" @undo-clear="undoClear"
        >
          <template #money>
            <div v-if="showNumbers" :class="updating ? 'opacity-60' : ''"><MoneySummary class="!mt-0 !px-0" :net-premium="data.summary.net_premium ?? null" :charges="data.charges_breakdown ?? null" /></div>
          </template>
        </LegList>
        <SaveDraftBar :legs="legs" :rules-ref="String(route.query.rules_ref || '')" :current="openStrategy" class="max-[1099px]:contents" @open="openSaved" @saved="onSaved" @renamed="onRenamed" @deleted="onDeleted">
          <template #add-edit>
            <button type="button" class="h-10 flex-1 basis-0 rounded-lg border border-line font-medium" aria-haspopup="dialog" :aria-expanded="pickerOpen ? 'true' : 'false'" data-testid="add-edit" @click="pickerOpen = !pickerOpen">Add/Edit</button>
          </template>
          <template #menu="{ close }">
            <button v-if="openStrategy" type="button" role="menuitem" data-testid="menu-activity" @click="close(); showHistory()">History</button>
            <button v-if="savedId" type="button" role="menuitem" data-testid="menu-start-tracking" @click="close(); goToTracking()">Start tracking</button>
          </template>
          <template #ready-made><ReadyMadePanel :legs="legs" :underlying="headerUnderlying || pickUnderlying" @update:legs="setLegs" /></template>
          <!-- GC-BP step 6: the Tracked tab is the shared paper list; it reads (and polls) only while that tab is shown -->
          <template #tracked="{ active }"><PaperStrategies v-if="active" compact /></template>
        </SaveDraftBar>
        <!-- W-195 (ADR-193 UI-200): the leg picker is a left slide-in drawer; it stays mounted while shut so Edit can open
             it on a leg and a half-made selection survives a close -->
        <!-- GC-UI 6c D-C20: no title bar (S-032: the picker's own header row is the top line); the width stays 520 px so the
             strike grid keeps the 470 px D-C27 fits in. D-C35: the "Show Editor" edge tab folds the drawer away to see the
             builder; the "Show Strikes" tab at the page edge brings it back with the picks kept (the picker stays mounted). -->
        <Drawer :open="pickerOpen" title="Add or edit legs" side="left" width="520px" persist bare @close="pickerOpen = false; pickerFolded = false">
          <div class="h-full" data-testid="leg-picker-panel"><LegPicker ref="picker" :legs="legs" :show-leg-list="false" :active="pickerOpen" :page-underlying="headerUnderlying || pickUnderlying" :last-close="closedBanner ? indexLevel : null" :closed-at="closedBanner?.at ?? null" @update:legs="setLegs" @done="pickerOpen = false; pickerFolded = false" /></div>
          <template #edge>
            <button type="button" class="rounded-r-md bg-warn-soft px-1 py-3 text-xs font-semibold text-ink shadow-menu [writing-mode:vertical-rl]" data-testid="show-editor" @click="pickerOpen = false; pickerFolded = true">Show Editor &gt;&gt;</button>
          </template>
        </Drawer>
        <button
          v-if="pickerFolded && !pickerOpen" type="button" class="fixed left-0 top-1/2 z-40 -translate-y-1/2 rounded-r-md bg-warn-soft px-1 py-3 text-xs font-semibold text-ink shadow-menu [writing-mode:vertical-rl]"
          data-testid="show-strikes" @click="pickerOpen = true; pickerFolded = false"
        >&lt;&lt; Show Strikes</button>
        <Drawer :open="historyOpen && !!openStrategy" title="Strategy history" side="right" @close="historyOpen = false">
          <ActivityPanel v-if="historyOpen && openStrategy" :current="openStrategy" in-drawer @open="restoreFromHistory" />
        </Drawer>

        <!-- Region D (UI-150): the one prices stamp and the reconnecting line -->
        <div class="text-xs text-ink-muted max-[1099px]:order-3" data-testid="stamp-line">
          <p v-if="live.reconnecting.value" class="font-medium" data-testid="live-reconnecting">{{ live.reconnectingText.value }}</p>
          <p v-if="showNumbers && pricesStamp" data-testid="prices-as-of" :data-kind="pricesStamp.kind">{{ pricesStamp.text }}</p>
        </div>
      </div>

      <div class="min-w-0 max-[1099px]:order-1" data-testid="builder-right">
        <!-- W-194: with numbers on screen the scenario switch and range sit in the chart card header; without them
             (loading, error, refused...) they stay here, so a pick that led to an error can still be changed back. -->
        <ScenarioControls v-if="state !== 'no-draft' && !showNumbers" :choice="choice" :scenario-label="data?.scenario?.label ?? ''" :estimate-note="data?.output_label ?? ''" @update:choice="setChoice" />

        <p v-if="state === 'loading' && keptWhileLoading" class="sr-only" data-testid="state-loading" data-kept="true">Working out the outcome...</p>
        <p v-else-if="state === 'loading'" class="mt-4" data-testid="state-loading">
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
            <li v-for="leg in data.legs" :key="leg.instrument_id">{{ leg.action }} {{ leg.lots }} lot, <span data-testid="leg-name">{{ nameOf(leg) }}</span>, planned entry {{ leg.planned_entry_display ?? '—' }}</li>
          </ul>
        </div>

        <div v-else-if="state === 'refused'" class="mt-4 rounded border border-line bg-surface p-4" data-testid="state-refused">
          <p class="font-medium" data-testid="status-label">{{ data.status_label }}</p>
          <p v-if="data.reason" class="mt-1 text-sm" data-testid="refused-reason">{{ data.reason }}</p>
          <p class="mt-1 text-sm text-ink-muted">No numbers are shown for this draft.</p>
          <p class="mt-1 text-sm text-ink-muted" data-testid="checked-at">Checked at {{ checkedAt }}</p>
        </div>

        <div v-if="showNumbers" :class="updating || keptWhileLoading ? 'opacity-60' : ''" :data-updating="updating || keptWhileLoading ? 'true' : 'false'" data-testid="numbers">
          <!-- UI study Region E: the data-health strip at the top of the summary, now only for stale legs and the
               from-entries labels. GC-UI step 3b (D-A42, ADR-202 (3)): the price data label ("estimated from spot",
               ADR-061: never silent) is one small label inside the summary beside the figures it qualifies
               (SummaryCards estimateLabel), not a full-width banner, and is not repeated in the foot stamp. It is also
               the tooltip beside the Estimated Now switch, where the estimate is chosen. -->
          <div v-if="staleLegs.length || (fromEntries && (data.status_label || data.centre_label || (data.scenario && !data.scenario.available)))" class="mt-4 rounded-lg border border-line bg-warn-soft px-3 py-2 text-[13px]" data-testid="data-health">
            <p v-if="fromEntries && data.status_label" data-testid="status-label">{{ data.status_label }}</p>
            <p v-if="fromEntries && data.centre_label" data-testid="centre-label">{{ data.centre_label }}</p>
            <p v-if="fromEntries && data.scenario && !data.scenario.available" data-testid="estimate-unavailable">{{ data.scenario.unavailable_reason }}</p>
            <ul v-if="staleLegs.length">
              <li v-for="l in staleLegs" :key="l.instrument_id" data-testid="stale-leg">{{ nameOf(l) }}: {{ l.label }}</li>
            </ul>
          </div>

          <SummaryCards
            v-model:flipped="ratioFlipped"
            class="mt-4"
            :max-profit="summaryFigure(data.summary, 'profit')"
            :max-loss="summaryFigure(data.summary, 'loss')"
            :max-profit-exact="data.summary.max_profit ?? null"
            :max-loss-exact="data.summary.max_loss ?? null"
            :breakevens="data.summary.breakevens_display ?? []"
            :breakevens-exact="data.summary.breakevens ?? []"
            :what-can-i-make="data.summary.what_can_i_make"
            :what-can-i-lose="data.summary.what_can_i_lose"
            :where-i-start-losing="data.summary.where_do_i_start_losing"
            :reward-risk="data.summary.reward_risk ?? null"
            :reward-risk-reason="data.summary.reward_risk_reason ?? null"
            :time-value="data.summary.time_value_display ?? null"
            :time-value-exact="data.summary.time_value ?? null"
            :intrinsic-value="data.summary.intrinsic_value_display ?? null"
            :intrinsic-value-exact="data.summary.intrinsic_value ?? null"
            :estimate-label="data.output_label || null"
            :risk-reward="data.summary.risk_reward ?? null"
            :value-label="data.summary.value_label ?? null"
            :value-reason="data.summary.value_reason ?? null"
            :funds-share="data.summary.funds_share ?? null"
          >
            <template #pop><PopFigure :pop="data.probability_of_profit ?? null" /></template>
            <template #margin><MarginLine :margin="data.margin" :capabilities="capabilities" /></template>
          </SummaryCards>
          <ProjectionsNote />

          <!-- W-194 (ADR-193 Region F, ADR-194): the tabbed chart card. The scenario switch and range sit in its header
               (they drive the graph and the full table); the full REQ-035 table and its Bid/Ask Details are on the
               P&L Table tab behind the Full table switch. -->
          <ChartCard
            v-model:tab="chartTab"
            v-model:payoff-view="chartPayoffView"
            v-model:full-table="chartFullTable"
            :points="data.payoff.points"
            :view="data.payoff.view ?? ''"
            :unavailable-reason="data.scenario && !data.scenario.available ? data.scenario.unavailable_reason : null"
            :spot="data.spot_level ?? ''"
            :table="data.table"
            :legs="data.legs ?? null"
            :max-profit="data.summary.max_profit_unlimited ? null : data.summary.max_profit"
            :max-loss="data.summary.max_loss_unlimited ? null : data.summary.max_loss"
            :curves="data.curves ?? null"
            :breakevens="data.summary.breakevens ?? []"
            :sd="data.standard_deviation ?? null"
            :oi="data.open_interest ?? null"
            :zoom="zoomGrid"
            :payoff-table="data.payoff_table ?? null"
            :saved-id="savedId"
            :saved-revision="savedRevision"
            @zoom="zoomTo"
            @payoff-step="stepTo"
          >
            <template #controls>
              <ScenarioControls :choice="choice" :scenario-label="data?.scenario?.label ?? ''" :estimate-note="data?.output_label ?? ''" @update:choice="setChoice" />
            </template>
            <template #details>
              <AdvancedDetails v-if="legQuoteRows" :rows="legQuoteRows" :name-of="nameOf" />
            </template>
          </ChartCard>
          <LowerCard :table="data.table" :legs="data.legs ?? null" :sd="data.standard_deviation ?? null" />
          <StrategyActions :saved-id="savedId" :execute-refusal="refusal" />
          <TrackingPanel :saved-id="savedId" :saved-revision="savedRevision" :legs="data.legs ?? null" />
        </div>
      </div>
    </div>
  </section>
</template>
