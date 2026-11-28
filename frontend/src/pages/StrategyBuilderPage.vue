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
import { computed, nextTick, onBeforeUnmount, onMounted, provide, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useOutsideClose } from '@/composables/useOutsideClose'
import api, { NEUTRAL_PARTS, STRATEGY_NOT_FOUND_CODE } from '@/services/api'
import ChartCard from '@/components/strategy/ChartCard.vue'
import LowerCard from '@/components/strategy/LowerCard.vue'
import SummaryCards from '@/components/strategy/SummaryCards.vue'
import MoneySummary from '@/components/strategy/MoneySummary.vue'
import MarginLine from '@/components/strategy/MarginLine.vue'
import ProjectionsNote from '@/components/strategy/ProjectionsNote.vue'
import StrategyActions from '@/components/strategy/StrategyActions.vue'
import TrackingPanel from '@/components/strategy/TrackingPanel.vue'
import PlanWatch from '@/components/strategy/PlanWatch.vue'
import MonitoringBadge from '@/components/common/MonitoringBadge.vue'
import { useMonitoringState } from '@/lib/monitoringState'
import AdjustSteps from '@/components/strategy/AdjustSteps.vue'
import { ADD_TO_PAPER_LABEL, PAPER_PLACED_NOT_REFRESHED_TEXT, PAPER_STATE, addToPaper as postPaperOrders, STOP_REPLY_UNREADABLE_TEXT, cancelledStopLines, paperPostOutcome } from '@/lib/tracking'
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'
import ExitButton from '@/components/strategy/ExitButton.vue'
import LoadFailed from '@/components/common/LoadFailed.vue'
import { ADD_UNKNOWN_TEXT, PAPER_REREAD_FAILED_TEXT, UNKNOWN_EXIT_READ_AFTER_MS, closedBannerFor } from '@/lib/sharedStateText'
import {
  DISCARD_LABEL, PAPER_BOOK_UNREADABLE, PAPER_MODE_LABEL, PAPER_PENDING_UNREADABLE, PAPER_REREAD_DELAYS_MS, REVIEW_AND_ADD_LABEL, confirmRowsFor, paperOrdersFor, pendingText, readPaperBook,
  legsAfterExit, exitOnlyOrders, paperFillKey, paperLeftOf, paperChargesOf, stagedChangeIds, stagedExitIds,
} from '@/lib/paperDrafts'
import { withAsOf } from '@/lib/paperList'
import PaperBookPanel from '@/components/strategy/PaperBookPanel.vue'
import { paperLegsOf, paperPnlBlock, usePaperBookRead } from '@/lib/usePaperBookRead'
import { notLiveEntryLine, usePriceFreshness } from '@/lib/priceState'
import { exitEndText, exitLegsNotLive, legsNoPrice, refusalText, usePaperExit } from '@/lib/usePaperExit'
import { createExitRecords } from '@/lib/exitRecord'
import { adoptedExitLock, bookOfNet, decideLock, dropExitLock, dropOrderKey, exitLockFor, exitUnitsOf, expectedKeyOf, onExitLocksChanged, orderKeyFor, saveExitLock } from '@/lib/unknownLocks'
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'
import PaperStops from '@/components/strategy/PaperStops.vue'
import { STOP_OFFER_LABEL, legStopsGone, triggerListOf, triggersPath } from '@/lib/paperTriggers'
import AdjustCompare from '@/components/strategy/AdjustCompare.vue'
import { opportunitiesFromQuery, picksFromQuery } from '@/lib/adjustDrawer'
import AdvancedDetails from '@/components/strategy/AdvancedDetails.vue'
import { UNSAVED_RELOAD_NOTE, fetchSavedDraft } from '@/lib/saveDraft'
import { legQuotes } from '@/lib/strategyTable'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import Icon from '@/components/common/Icon.vue'
import LegPicker from '@/components/strategy/LegPicker.vue'
import ReadyMadePanel from '@/components/strategy/ReadyMadePanel.vue'
import { UNDERLYINGS } from '@/lib/underlyings'
import PopFigure from '@/components/strategy/PopFigure.vue'
import ActivityPanel from '@/components/strategy/ActivityPanel.vue'
import Drawer from '@/components/common/Drawer.vue'
import Modal from '@/components/common/Modal.vue'
import { sameLegs } from '@/lib/legDoor'
import { useLegDoor } from '@/composables/useLegDoor'
import DuplicateLegDialog from '@/components/strategy/DuplicateLegDialog.vue'
import { netKeyOf, useBuilderHold } from '@/stores/builderHold'
import { useChainSelection } from '@/stores/chainSelection'
import { unsavedCount, useLeaveBuilder } from '@/composables/useLeaveBuilder'
import LeaveBuilderDialog from '@/components/strategy/LeaveBuilderDialog.vue'
import { replacePrompt } from '@/lib/readyMade'
import SaveDraftBar from '@/components/strategy/SaveDraftBar.vue'
import LegList from '@/components/strategy/LegList.vue'
import { paperLegListPrices } from '@/lib/chartCard'
import { applyEditReply, buildEditRequest, controlsFrom, moveKey, MAX_STEPS, MOVE_CONTROLS, RELATIVE_CONTROLS, executeRefusal, CLEAR_UNDO_SECONDS_KEY, LEG_REMOVED, MULTIPLIER_MAX_KEY, EXECUTE_WAITS_FOR_LATEST, NO_CONTROLS, CLOSED_TRADE_TEXT, emptyListKind } from '@/lib/legEdit'
import { createNewestWins, isSuperseded } from '@/lib/newestWins'
import { NOT_CONNECTED_LABEL, buildDraft } from '@/lib/legPicker'
import { matchesLegs } from '@/lib/liveMatch'
import { INVALID_LINK_PARTS, canonicalLegs } from '@/lib/draftLink'
import ScenarioControls from '@/components/strategy/ScenarioControls.vue'
import TargetBlock from '@/components/strategy/TargetBlock.vue'
import { OPEN_LEGS_ONLY_BEFORE_CHARGES_TEXT, OPEN_LEGS_ONLY_TEXT, bookedFields, dateStops, debounced, firstExpiry, targetFields } from '@/lib/targetBlock'
import { CHART_FLAGS, DEFAULT_CHOICE, choiceFields, matchesChoice } from '@/lib/scenarioChoice'
import { contractName, istClock, istTime, nameFromPool } from '@/lib/displayFormat'
import { summaryFigure } from '@/lib/summaryFigures'
import { ORDER_PATH_OFF_SENTENCE } from '@/lib/orderPath'
import { useCapabilities } from '@/lib/brokerCapabilities'
import { useSettingsValues } from '@/stores/settingsValues'
import { LOT_CHOICES_KEY, MAX_LOTS_KEY } from '@/lib/legPicker'
import { useStrategyLive } from '@/composables/useStrategyLive'
import { NOT_LIVE_LABEL as INDEX_NOT_LIVE, headerLevel, useIndexAnswer } from '@/composables/useIndexLive'
import MarketClosedBanner from '@/components/states/MarketClosedBanner.vue'

const route = useRoute()
const router = useRouter()
const served = useSettingsValues() // REQ-167 AC-5: the lot caps and the multiplier cap are served, never typed
served.load()
// F6 (Phase 5): the page's ONE door asks every add-or-move question; the picker and its forms reach it by inject('legDoor').
const door = useLegDoor({ maxLots: () => served.integer(MAX_LOTS_KEY) })
provide('legDoor', door)
const cancelDuplicate = () => door.cancel() // D-60: a question about replaced legs closes (its edit settles as Cancel)
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
// ADR-329 (1): the legs the builder held across an Option Chain trip come back (once). ?adjust= or a ?strategy= naming ANOTHER
// strategy name another thing to open, so the hold is dropped and today's open path runs. A ?strategy= naming the held strategy
// (browser Back to the entry it was opened by) is that strategy's own link: the hold comes back and the book is not read over it.
const builderHold = useBuilderHold()
let heldBack = null
const urlStrategy = route.query.strategy
const heldStrategyId = builderHold.held ? String(builderHold.held.paperId ?? builderHold.held.openStrategy?.id ?? '') : ''
const heldForUrl = urlStrategy !== undefined && route.query.adjust === undefined && heldStrategyId !== '' && heldStrategyId === String(urlStrategy)
if (urlStrategy !== undefined && !heldForUrl || route.query.adjust !== undefined) builderHold.clear()
else heldBack = builderHold.take()
const legs = ref(heldBack ? heldBack.legs : legsFromQuery())
// GC-ADJ1 step 3 (REQ-156): `?adjust=<strategy id>` opens the approach compare instead of the builder's two columns.
const adjustId = computed(() => (/^\d+$/.test(String(route.query.adjust ?? '')) ? String(route.query.adjust) : null))
const pickedIds = computed(() => picksFromQuery(route.query.pick)) // the approaches ticked in the Review adjustment drawer
const opportunityIds = computed(() => opportunitiesFromQuery(route.query.opp)) // GC-ADJ2 5: records the prepare acts on
// REQ-163 AC-1: the suggestion records the prepared basket acted on travel in the URL (`acted=41,42`), so a reload between
// Open in builder and Confirm keeps them; sent once with the paper orders, then dropped. Validated as whole positive
// numbers only: the server alone decides whether each may be named (owner, strategy, acted on, not yet named).
const actedSuggestionIds = computed(() => opportunitiesFromQuery(route.query.acted))
// REQ-112: how many orders the prepared basket held (`basket=4`, set by prepare, travels with `acted`); sent with the
// paper orders so the server can tell completed from partly completed. Anything but a whole 1..64 is not sent.
const preparedBasketLegs = computed(() => { const n = String(route.query.basket ?? ''); return /^(?:[1-9]|[1-5]\d|6[0-4])$/.test(n) ? n : null }) // stays a string like the ids: the server's model reads it as a whole number
// D-25 (ADR-326 (1)): a Take profit basket names its approach (`approach=A-24`, set by prepare, travels with `acted`) so the
// server asks the same build path that offered it; only A-24 / A-25 are ever sent, anything else in the URL is ignored.
const preparedApproachId = computed(() => { const a = String(route.query.approach ?? ''); return a === 'A-24' || a === 'A-25' ? a : null })
const prepareApproach = (a) => whileOpening(() => prepareApproachRead(a)) // item 11: the card says loading, not "No legs yet", while the book read is out
async function prepareApproachRead({ legs: next, suggestionIds = [], basketLegs = 0, exit = false, approachId = null }) { // the chosen approach's legs become the builder's legs; no order is placed
  const { adjust: _gone, pick: _picks, opp: _opp, acted: _acted, basket: _basket, approach: _approach, ...rest } = route.query
  const acted = opportunitiesFromQuery(suggestionIds.join(','))
  const size = Number.isInteger(basketLegs) && basketLegs > 0 && basketLegs <= 64 ? { basket: String(basketLegs) } : {}
  const id = adjustId.value
  const take = approachId === 'A-24' || approachId === 'A-25' ? { approach: approachId } : {}
  await router.replace({ query: acted.length ? { ...rest, acted: acted.join(','), ...size, ...take } : { ...rest, ...take } }) // awaited: nameInUrl below spreads it
  // ADR-207 (2), live 2026-11-06 (strategy 88, A-11): a strategy with a paper book is edited in ITS Drafts Mode, never as a new
  // unlinked draft (whose Add to Paper would open a second position). A full exit takes the book's Exit all path; any other
  // approach's after-legs become the edited legs, so the pending changes are paperOrdersFor(net, after-legs) (the exit + add
  // orders), reviewed in the same confirm list. A book that cannot be read is said; no unlinked draft is opened instead.
  let read
  try {
    read = id ? await readPaperBook(api, id) : { kind: 'plan' }
  } catch (e) {
    openError.value = unreadableParts(e)
    return
  }
  if (read.kind === 'paper') {
    enterDrafts(read.book.strategy_id ?? Number(id), read)
    if (exit) exitAllPaper()
    else setLegs(keepHeldFills(read.net, next))
    return
  }
  setLegs(next) // no paper book to edit (a plan only): the approach's legs show as the builder's legs
}
// a contract the approach keeps unchanged (same side, same lots) stays the net leg the book loaded (its paper average, R-11),
// so the held legs are not repriced at the approach's entry; every other leg is the approach's own.
function keepHeldFills(net, next) {
  const held = new Map(net.map((l) => [l.contract_id, l]))
  return next.map((l) => {
    const h = held.get(l.contract_id)
    return h && h.action === l.action && h.lots === l.lots && h.lot_size === l.lot_size ? { ...h } : l
  })
}
// a 404/409 to a basket naming records: a refused record (or the strategy gone or changed); the same ids would be
// refused on every retry. A 422 (price, contract) is fixed by the user and keeps them.
const ACTED_REFUSED = new Set([404, 409])
// awaited: a later URL write (nameInUrl after the book re-read) spreads route.query and would put the ids back
async function dropActed({ withApproach = false } = {}) { // the basket answered its records, or the server refused them: never sent again
  if (route.query.acted === undefined && !(withApproach && route.query.approach !== undefined)) return
  // a refused record keeps the approach (the retry is asked again); a stored basket answers it once
  const { acted: _acted, basket: _basket, approach: gone, ...rest } = route.query
  if (!withApproach && gone !== undefined) rest.approach = gone
  await router.replace({ path: route.path, query: rest })
}
// W-090 (REQ-034 AC-4, AC-6): the scenario column and range the user picked; kept across every reload and push.
const choice = ref({ ...DEFAULT_CHOICE })
if (linkRefused.value) {
  state.value = 'error'
  errorParts.value = INVALID_LINK_PARTS
}
// W-148 (REQ-076): the leg-edit state. The shape name is the server's (null until a reply named it); `updating` marks the
// old numbers while an edit is pending; `editError` is the server's refusal of the last edit.
const shapeName = ref(heldBack?.shapeName ?? null)
const hasReply = ref(false)
// W-158 (REQ-078 AC-2/AC-3): which of Shift / Width / Hedge work and the Shift total, exactly as the newest applied reply sent them.
const controls = ref(NO_CONTROLS)
const editError = ref(null)
const editErrorIndex = ref(null) // the leg of a refused typed price (its error shows under that field), else null
const allLeftOut = () => legs.value.length > 0 && legs.value.every((l) => l.included === false)
// W-151 (REQ-119): the one newest-wins rule (src/lib/newestWins.js) for the outcome and leg-edit requests of this page;
// the numbers are marked updating while the newest request of either kind has no applied reply (AC-4).
const guard = createNewestWins()
// GC-TP step 6b (REQ-084 AC-1): the what-if target the user set. Only target_level / target_at ever go out for it (analysis only,
// AC-6); the figures shown are the reply's `target` block, kept (marked stale) when a later request fails or a live push lands.
const targetPick = ref({ level: '', dateIndex: 0 })
const targetShown = ref(null)
const targetStale = ref(false)
const targetNotLiveText = ref('') // D-37: the latest reply's own sentence when its prices are not live; '' after a failed request or any other reply
const dateStopList = computed(() => dateStops(data.value?.valuation, firstExpiry(data.value?.legs)))
// GC-LIVE R-26: a pick goes to BOTH answer paths: the live socket's follow message (so every push of the new version
// carries the target block, refreshed as prices move) and one REST request (the answer while the socket is not live).
// Before, only REST carried the pick: a push (about once a second) cancelled the target request in flight and, carrying
// no figures, marked the last ones "Stale", so in market hours a pick froze or was never answered.
const loadSoon = debounced(() => {
  syncLive()
  load()
})
const pickTarget = (patch) => {
  targetPick.value = { ...targetPick.value, ...patch } // both back at spot / now: no target field is sent
  loadSoon()
}
// GC-TP R-18 (ADR-209, Sensibull 020): the chart card's Add Booked P&L switch, ON by default; a toggle is a new target request
// (same debounce; the request guard drops the older reply by its id)
const includeBooked = ref(true)
const pickBooked = (on) => {
  includeBooked.value = on
  loadSoon()
}
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
  const target = targetFields(targetPick.value, dateStopList.value)
  const booked = bookedFields(paper.value?.book?.strategy_id, includeBooked.value) // R-18: the Add Booked P&L switch; the id is the server book's own (a paper strategy only)
  const prevState = state.value
  const fallback = socketDropped
  const sentKey = inputsKey()
  // A fallback reload while the not-live message is already on screen keeps it there (no flicker through 'loading').
  // Review 2: numbers already on screen stay mounted (marked updating) while the new answer is worked out, so the
  // scenario switch keeps focus, the page does not jump and the chart is not rebuilt.
  keepNumbers.value = showNumbers.value
  if (!(fallback && state.value === 'not-connected')) state.value = 'loading'
  slowTimer = setTimeout(() => (slow.value = true), 3000)
  try {
    const res = await api.post('/strategies/outcome', { ...draft, ...choiceFields(choice.value), ...CHART_FLAGS, ...target, ...booked, fallback, seq: mine.seq }, { signal: mine.signal })
    if (!guard.claim('outcome', res.data, mine)) return
    // A reply for legs or a choice that are no longer on screen is dropped and asked again; one for the inputs still on
    // screen is the answer to them (also when the server echoes its own spelling), so asking again could never end.
    if (!drawable(res.data) && sentKey !== inputsKey()) return reask('outcome', mine)
    applyOutcome(res.data)
  } catch (e) {
    if (isSuperseded(e) || !guard.isNewest('outcome', mine)) return // a cancelled or older request shows nothing (AC-3)
    if ((target.target_level || target.target_at) && targetShown.value && data.value && prevState !== 'loading') {
      targetStale.value = true // a failed target request keeps the last good figures, marked stale
      targetNotLiveText.value = '' // a failure says nothing about the prices: no not-live sentence
      state.value = prevState
      return
    }
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
  targetNotLiveText.value = typeof body.target_not_live_text === 'string' ? body.target_not_live_text : '' // D-37: only what this reply says
  const moved = !!targetPick.value.level || targetPick.value.dateIndex > 0
  if (body.target && (body.target.kind || !moved)) { // figures for the pick, or nothing picked: the reply's block as sent
    targetShown.value = body.target
    targetStale.value = false
  } else if (moved && targetShown.value) {
    targetStale.value = true // an answer for the current version with no figures (not connected, refused): the last figures stay, marked
  } else {
    targetShown.value = body.target ?? null
  }
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
  // GC-LIVE R-26: the follow message carries the same target and Add Booked P&L fields as the REST request, so the
  // server computes the target block in every push (ADR-008: the browser computes none)
  const target = targetFields(targetPick.value, dateStopList.value)
  const booked = bookedFields(paper.value?.book?.strategy_id, includeBooked.value)
  if (draft) live.follow({ ...draft, ...choiceFields(choice.value), ...CHART_FLAGS, ...target, ...booked })
  else live.stop()
}

// W-104: the saved strategy behind the legs on screen (Save Draft or reopen); any edit makes the draft unsaved again.
const savedId = ref(heldBack?.savedId ?? null)
// W-122: the revision the page loaded or saved (kept for the chart's version)
const savedRevision = ref(heldBack?.savedRevision ?? null)
// REQ-134 AC-2: the saved strategy this screen is editing ({ id, revision, name }: the revision and name the page loaded or saved).
// Unlike savedId it SURVIVES edits, so Save after an edit updates that strategy (PUT with this revision) instead of creating a
// second row (RD-106). It is replaced on open/save, and dropped by Clear all (held for Undo).
const openStrategy = ref(heldBack?.openStrategy ?? null)
// ADR-330 (58): the saved strategy whose orders are real (the server says Running and it has no paper book); only the page's own read of THIS strategy sets it
const realTradeId = ref(null)
const tradeMode = computed(() => (!paper.value && realTradeId.value !== null && realTradeId.value === savedId.value ? 'real' : 'paper'))
const openError = ref(null) // the catalogue message when ?strategy= cannot be opened; the screen is kept
const openNotFound = ref(null) // the openError that said "strategy not found" (the Open My Strategies button shows only while it is the one on screen)
// REQ-134 AC-5: the URL names the strategy (?strategy=<id>) so a reload opens it again; a `draft` link is dropped from it.
function nameInUrl(id) {
  const { draft: _link, ...rest } = route.query
  router.replace({ path: route.path, query: { ...rest, strategy: String(id) } })
}
// u502: serverLegs = the legs the server holds for it (a successful load, or the legs a successful Save sent); null = not known, and Save then stays on
const takeStrategy = (id, revision, name, serverLegs = null) => {
  openStrategy.value = Number.isInteger(id) ? { id, revision: revision ?? null, name: name ?? null, serverLegs } : null
  if (openStrategy.value) nameInUrl(id)
}
const openSaved = (next, id, revision, name) => {
  setLegs(next)
  savedId.value = Number.isInteger(id) ? id : null
  savedRevision.value = savedId.value === null ? null : revision ?? null
  takeStrategy(id, revision, name, legs.value.map((l) => ({ ...l })))
}
// REQ-134 AC-3: a rename from the bar changes only the shown name (the revision stays the one the page loaded).
const onRenamed = (id, name) => {
  if (openStrategy.value?.id === id) openStrategy.value = { ...openStrategy.value, name }
}
// REQ-070 AC-6: the strategy open here was deleted (from the saved list): the screen is a new unsaved strategy again, so a Save asks a
// name and POSTs instead of PUTting a hidden id. The legs stay on screen; the ?strategy= link is dropped.
const onDeleted = (id) => {
  if (openStrategy.value?.id !== id) return
  leaveDrafts()
  openStrategy.value = null
  savedId.value = null
  savedRevision.value = null
  const { strategy: _gone, ...rest } = route.query
  router.replace({ path: route.path, query: rest })
}
const onSaved = (id, revision, name, sent = null) => {
  savedId.value = id
  savedRevision.value = revision ?? null
  takeStrategy(id, revision, name, Array.isArray(sent) ? sent : null)
}
// AC-5: a reload of /strategy/builder?strategy=<id> reads the saved copy (legs and planned entries as saved, never today's prices).
const STRATEGY_ID = /^[1-9]\d{0,17}$/
// GC-TP step 3b1 (ADR-207 (2), REQ-109 AC-9; F-65, F-66): Drafts Mode. A strategy with paper orders opens as its NET position
// (`paper` holds the book and the net legs) and every edit after that only changes the legs on screen; the ONLY way an edit
// reaches the server is the list paperOrdersFor(net, legs) gives, reviewed in the confirm dialog. Save / Save As / Add to Paper
// are not offered (SaveDraftBar paper-mode). A book that cannot be read is said plainly; the plan is never shown in its place.
const paper = ref(null) // { id, book, net } while in Drafts Mode, else null
// ADR-330 (49), round 2: a per-leg Exit posts ITS exit only. `legOnly` = { net, id, lots } while its dialog is open; `keepStaged` = that plus
// the screen legs at Confirm, put back over the re-read net ONLY when it is the net the exit should leave (restoreStaged); else the sentence.
let legOnly = null
let keepStaged = null
const stagedNote = ref('')
// ADR-330 (59) (owner 27 Nov evening; all sentences pending owner read): Exit all while a change is staged and not sent. `exitAllWaiting` = { legs, names }:
// the screen legs as the user left them and the changed legs' names; set while the Exit all dialog is open, handed to `exitUnknown` when its POST ends unknown.
const exitAllWaiting = ref(null)
const DISCARD_WARNING = (names) => `Exit all closes every open leg. The change waiting on ${names} is not sent and will be discarded.`
const DISCARDED_TEXT = (names) => `The change waiting on ${names} was discarded.`
const KEPT_UNTIL_KNOWN_TEXT = (names) => `The change waiting on ${names} was not sent; it is kept until the exit's outcome is known.`
const BACK_UNCHANGED_TEXT = (names) => `The exit was not stored. The change waiting on ${names} is back, unchanged.`
const netKey = (rows) => (rows ?? []).map((l) => `${l.contract_id}|${l.action}|${l.lots}`).sort().join(';')
const NOT_KEPT_TEXT = (names) => `The change waiting on ${names} was not kept because the trade changed; stage it again.`
function restoreStaged(newNet, allowNotStored = false) { // allowNotStored: the Orderbook link after an unknown outcome (the exit may not have been stored)
  const rec = keepStaged
  keepStaged = null
  if (!rec) return
  const expected = legsAfterExit(rec.net, rec.net, rec.id, rec.lots)
  if (!expected || JSON.stringify(rec.snapshot) === JSON.stringify(expected)) return // nothing was staged beside the exit
  if (netKey(newNet) === netKey(expected)) { // the net the exit should leave: the other legs' edits come back, the exited contract's row is the re-read's
    const nrow = (newNet ?? []).find((l) => l.contract_id === rec.id)
    const out = []
    let placed = false
    for (const l of rec.snapshot) {
      if (l.contract_id !== rec.id) { out.push(l); continue }
      if (!placed && nrow) out.push({ ...nrow })
      placed = true
    }
    if (!placed && nrow) out.push({ ...nrow })
    setLegs(out)
    return
  }
  if (allowNotStored && netKey(newNet) === netKey(rec.net)) { // not stored (ADR-017): the other legs' edits come back, the exit does NOT stay staged; only a fresh Exit click sends it
    const nrow = (newNet ?? []).find((l) => l.contract_id === rec.id)
    const out = []
    let placed = false
    for (const l of rec.snapshot) {
      if (l.contract_id !== rec.id) { out.push(l); continue }
      if (!placed && nrow) out.push({ ...nrow })
      placed = true
    }
    if (!placed && nrow) out.push({ ...nrow })
    setLegs(out)
    return
  }
  let names = ''
  try {
    const diff = paperOrdersFor(expected, rec.snapshot)
    names = diff ? confirmRowsFor(diff, paper.value.book, contractName, {}).map((r) => r.text).filter(Boolean).join(', ') : ''
  } catch { names = '' }
  stagedNote.value = NOT_KEPT_TEXT(names || 'your edited legs') // nothing is put back: no add is ever built over a net that is not the expected one
}
// N-48: every leg of the paper book is closed (it has closed lifecycles, none open): Completed, nothing to add to (ADR-002)
const paperCompleted = computed(() => { const b = paper.value?.book; return !!b && Array.isArray(b.closed) && b.closed.length > 0 && Array.isArray(b.positions) && b.positions.every((p) => p.net_quantity === 0) })
// item 8: the ONE shared answer (legEdit.emptyListKind) also decides the right-hand empty text: a closed trade says so
const rightKind = computed(() => emptyListKind({ legs: legs.value, held: [], loading: opening.value, done: paperCompleted.value, failed: !!openError.value }))
const pendingOrders = computed(() => (paper.value ? paperOrdersFor(paper.value.net, legs.value) : []))
const paperRows = ref([])
const paperDialog = ref(false)
const paperBusy = ref(false)
const paperError = ref('')
const paperState = ref(PAPER_STATE.READY) // fix/paper-dialog-safe: the dialog's answer state (tracking.js PAPER_STATE)
// orders were stored but the book could not be re-read: the net on screen is stale, so its diff (the pending orders) would
// re-offer what was just placed. Until a book is read again nothing is offered for review.
const paperStale = ref(false)
const showOrdersTick = ref(0) // bumped to switch the book panel to its Orderbook view
const unreadableParts = (e) => ({ ...(e?.parts ?? NEUTRAL_PARTS), what_happened: PAPER_BOOK_UNREADABLE })
const copyLegs = (net) => net.map((l) => ({ ...l }))
function enterDrafts(id, read) {
  if (String(id) !== String(rereadId)) cancelReread() // another strategy opens: a re-read of the old one ends here
  paperContractsChanged.value = false // a good read of the book: a poll's earlier "contracts changed" mark is out of date
  paperStale.value = false
  if (addUnknown && netKey(read.net) !== addUnknown.net) { addUnknown = null; dropOrderKey(id) } // a read shows the book moved: the earlier add was stored, the unknown is decided
  paper.value = { id, book: read.book, net: read.net }
  openSaved(copyLegs(read.net), id, null, read.book.name ?? null)
  restoreExitLock(id, read)
}
// F1 second path: this page instance was opened (or reloaded) while an exit of unknown outcome from an earlier instance is still undecided: the lock comes back, and this very read
// may decide it (book moved = stored; unchanged only past the commit window); otherwise the re-reads go on until the server's answer decides
function restoreExitLock(id, read) {
  if (exitUnknown.value) { takeNewerGiveUp(); return }
  if (paperBusy.value || !exitLockFor(id)) return // this instance's own post is out: its lock is its own, not an earlier instance's
  const rec = adoptedExitLock(id, Date.now()) // the 130 s rule counts from the give-up (a post that was still out: from now)
  const attempt = exitRec.begin(EXIT_KEY, rec.names)
  exitRec.settle(EXIT_KEY, attempt, 'unknown')
  const waiting = rec.waiting && Array.isArray(rec.waiting.legs) ? rec.waiting : null // ADR-330 (59): the Exit all's staged change comes back with the lock (lib/unknownLocks.js)
  exitUnknown.value = { id, attempt, names: rec.names, waiting, at: rec.at ?? Date.now(), lock: rec }
  if (waiting) stagedNote.value = KEPT_UNTIL_KNOWN_TEXT(waiting.names)
  if (!decideUnknownExit(read.net, id, read.sentAt)) void recheckUnknownExit()
}
// Lane FJ item 1c: a lock written by ANOTHER tab of this browser while this book is open: it holds here too (its Confirm sends nothing); this tab's own re-reads decide it
// F4: another tab that gave up on the same exit LATER moves the give-up time on (the 130 s rule runs from the last give-up)
function takeNewerGiveUp() {
  const u = exitUnknown.value
  const l = u ? exitLockFor(u.id) : null
  if (l && !l.malformed && !l.out && Number.isFinite(l.at) && l.at > u.at) { u.at = l.at; u.lock = l }
}
function adoptForeignLock() {
  if (!paper.value) return
  if (exitUnknown.value) { takeNewerGiveUp(); return }
  if (paperBusy.value || !exitLockFor(paper.value.id)) return
  const rec = adoptedExitLock(paper.value.id, Date.now())
  const attempt = exitRec.begin(EXIT_KEY, rec.names)
  exitRec.settle(EXIT_KEY, attempt, 'unknown')
  exitUnknown.value = { id: paper.value.id, attempt, names: rec.names, waiting: null, at: rec.at ?? Date.now(), lock: rec }
  void recheckUnknownExit()
}
let offLocks = null
onMounted(() => { offLocks = onExitLocksChanged(adoptForeignLock) })
onBeforeUnmount(() => { offLocks?.() })
const leaveDrafts = () => { addUnknown = null; stagedNote.value = ''; paper.value = null; paperStale.value = false; cancelReread(); clearStopOffer() }
// GC-ICFIX round 2 (F4): the page's ONE read of the paper book per refresh; its reply feeds the paper panel, the tracking box's total and
// the P&L table TOTAL row (one moment, one text). An orders re-read (paperStale) is not overwritten by it.
const { readFailed: paperReadFailed, contractsChanged: paperContractsChanged } = usePaperBookRead({
  key: () => paper.value?.book?.strategy_id ?? null,
  book: () => paper.value?.book ?? null,
  onBook: (b) => { if (paper.value && !paperStale.value) paper.value = { ...paper.value, book: b } },
})
// F1: the page's book-read state through the one freshness rule (priceState). Phase 4 (D-05, ADR-328 (4)): the Exit buttons of the
// book panel read it (usePaperExit), and so do the handlers below: no exit is built from old prices (a failed read) or from an old net
// (the contracts changed elsewhere). The panel says which, in the words of priceState.
// ADR-330 (28): the same rule for Add to Paper. The builder answer is live only when it computed with no labelled (stale) leg and the
// market is open and the feed is not reconnecting; anything else is not live and the confirm list says so.
const index = useIndexAnswer() // the page's index answer: with the reply it decides closed / not (priceState.priceNow)
const { live: pricesLive, now: pricesNow } = usePriceFreshness({
  reply: () => data.value, answer: () => index.answer.value, pageState: () => state.value, reconnecting: () => live.reconnecting.value,
})
const { readFailed: paperBookFailed } = usePriceFreshness({
  readFailed: paperReadFailed,
  held: () => paper.value?.book ?? null,
  serverState: () => paper.value?.book?.state,
})
// N-04 / N-05: the ONE blocked rule (the book panel's own usePaperExit, same inputs): per-leg Exit, Exit all and "Review and add" all
// read exitGate.blocked, so they are disabled in exactly the same states; the reason line is the one the panel shows under Exit all.
// Lane U hotfix 27 Nov (A-H #209): an open dialog's EXIT rows are judged on the latest good book too (exitLegsNotLive, the one rule), not only a failed read
const dialogLegsNotLive = () => { const b = paper.value?.book; return paperDialog.value && !!b && exitLegsNotLive(b.state, b.positions?.map((p) => ({ id: p.contract_id, live: p.price_state === 'live' })), paperRows.value.filter((r) => r.kind === 'exit').map((r) => r.contract_id)) }
const exitGate = usePaperExit({ readFailed: paperReadFailed, held: () => paper.value?.book ?? null, changed: paperContractsChanged, notLive: dialogLegsNotLive, unresolved: () => !!exitUnknown.value && String(exitUnknown.value.id) === String(paper.value?.book?.strategy_id ?? paper.value?.id) })
const exitBlocked = exitGate.blocked
// Lane U2 (ADR-017, ADR-016..019): set when an Exit's POST ended with an unknown outcome; { attempt, names, before, expected } until a good re-read of the book decides it
const exitUnknown = ref(null)
let addUnknown = null // Opus review F2 (ADR-016..019): { net } of the book when an ADD-only post got no answer; Review and add is refused until a read shows the book changed (or the book is left and reopened)
const exitOrigin = ref(false) // the pending edits came from Exit all or a per-leg Exit; stays true until they are posted or discarded (ADR-328 (4))
// P10: the strategy the Plan watch reads: the saved id, or in Drafts Mode (savedId stays null there) the paper book's own integer id
const planWatchId = computed(() => (Number.isInteger(savedId.value) ? savedId.value : Number.isInteger(paper.value?.book?.strategy_id) ? paper.value.book.strategy_id : null))
const monitoring = useMonitoringState(() => (planWatchId.value ? [planWatchId.value] : [])) // Lane Y item 1: one read
const paperTotal = computed(() => (paper.value ? paperPnlBlock(paper.value.book, paperBookFailed.value) : null))
function reviewPending(fromExit = false, only = null, info = null) { // the "Review and add" button passes its click event: only `true` marks an Exit; `only`: ADR-330 (49), a leg's own exit rows
  const shown = only ?? pendingOrders.value
  if (!paper.value || paperStale.value || !shown?.length) return
  if (fromExit === true) exitOrigin.value = true // never reset here: "Review and add" of Exit edits is still an Exit
  if (exitBlocked.value) return // post nothing; the panel's reason line says why
  if (addUnknown && !shown.some((o) => o?.kind === 'exit')) { stagedNote.value = ADD_UNKNOWN_TEXT; return } // the last add may be stored: never offered again unread
  paperError.value = ''
  stagedNote.value = ''
  legOnly = only ? info : null // ADR-330 (49): the open dialog is one leg's own exit
  exitRec.clear(EXIT_KEY)
  paperState.value = PAPER_STATE.READY
  paperRows.value = confirmRowsFor(shown, paper.value.book, contractName, livePriceById.value)
  cancelledStops.value = null // item 2: a new dialog starts with no word about stops
  stopsReplyUnreadable.value = false
  paperDialog.value = true
}
watch(pendingOrders, (o) => { if (!o?.length) exitOrigin.value = false }) // posted, discarded or edited back: no Exit edits are left
const discardPending = () => { stagedNote.value = ''; if (paper.value) setLegs(copyLegs(paper.value.net)) }
// GC-TP step 3b2 (Sensibull Drafts Mode 274-279): Exit all / a (partial) Exit only EDIT the legs (none / the contract less N lots),
// then open the same confirm list: the orders are paperOrdersFor(net, legs) like every other edit, never built here.
let legsBeforeExit = null // the legs as the user left them just before the first Exit click: what a cancelled Exit dialog restores
const markExit = () => { if (!exitOrigin.value) legsBeforeExit = copyLegs(legs.value) }
function exitAllPaper() {
  if (!paper.value || paperStale.value || exitBlocked.value) return
  const pending = pendingOrders.value
  let names = ''
  try { names = pending.length ? confirmRowsFor(pending, paper.value.book, contractName, {}).map((r) => r.text).filter(Boolean).join(', ') : '' } catch { names = '' }
  const waiting = pending.length ? { legs: copyLegs(legs.value), names: names || 'your edited legs' } : null
  markExit()
  setLegs([])
  reviewPending(true)
  exitAllWaiting.value = paperDialog.value ? waiting : null // only when the dialog really opened
}
function exitPaper(contractId, lots) {
  if (!paper.value || paperStale.value || exitBlocked.value) return
  const next = legsAfterExit(paper.value.net, legs.value, contractId, lots)
  const only = exitOnlyOrders(paper.value.net, contractId, lots) // ADR-330 (49): this leg's exit alone; other legs' staged changes stay staged
  if (!next || !only?.length) return
  markExit()
  setLegs(next)
  reviewPending(true, only, { net: copyLegs(paper.value.net), id: contractId, lots })
}
// N-04 / N-05: the ONE way the PAGE closes an Exit dialog without a Confirm (the trade changed elsewhere; a failed read no longer closes it:
// hotfix 27 Nov T2-08, ADR-016..019). It drops the staged exits too (the legs the user had before the Exit click come back, their other edits with
// them), so no "pending change" outlives a dialog the page closed. The user's own Cancel is userCancelPaperDialog: u513 (owner test note
// #85) keeps the exits the user chose as edits, counted and discardable. A dialog of "Review and add" keeps its edits. While a POST is in
// flight nothing closes it: its answer (or the unknown-outcome text) decides.
const userCancelPaperDialog = () => {
  if (paperBusy.value) return
  paperDialog.value = false
  if (exitAllWaiting.value) { // ADR-330 (59): Cancel gives the staged change back exactly as it was; the exits are not kept as edits
    const back = exitAllWaiting.value.legs
    exitAllWaiting.value = null
    exitOrigin.value = false
    legsBeforeExit = null
    setLegs(copyLegs(back))
    return
  }
  if (exitOrigin.value) { exitOrigin.value = false; legsBeforeExit = null } // the kept exits are ordinary edits now: the next Exit takes a fresh snapshot
}
function cancelPaperDialog() {
  if (paperBusy.value) return
  exitAllWaiting.value = null
  const wasExit = exitOrigin.value
  paperDialog.value = false
  if (wasExit && !paperStale.value) { // stored orders (stale net): nothing to drop, the re-read replaces the legs
    exitOrigin.value = false
    if (legsBeforeExit) setLegs(legsBeforeExit)
    else discardPending()
    legsBeforeExit = null
  }
}
// ADR-328 (4) / D-05, hotfix 27 Nov T2-08 (ADR-016..019): a paper dialog posts nothing while the read failed or the trade changed elsewhere
// (any dialog: its orders are built from the net on screen). Same rule as Positions, through the same door (exitEndText): a FAILED READ keeps
// the dialog open, Confirm blocked, with "<legs>: Prices are not live..." in it (it enables again after a good read); the trade really
// CHANGED elsewhere closes it (N-04: the legs as before the Exit click) and leaves the visible sentence in paperExitNote.
// ADR-330 (28): Review and add of entry orders in Drafts Mode is Add to Paper too: not-live prices show the line to tick (an Exit keeps its own gate)
const paperEntryNotLiveLine = computed(() => (paperDialog.value && !pricesLive.value && pricesNow.value.kind !== 'last_close' && !exitOrigin.value && paperRows.value.length && paperRows.value.every((r) => r.kind !== 'exit') ? notLiveEntryLine(pricesNow.value.at) : ''))
const paperLegNames = () => paperRows.value.map((r) => r.text).filter(Boolean)
// Lane U hotfix (27 Nov, ADR-016..019; PC T1-22): the builder's Exit door is single-ended: ONE record (lib/exitRecord.js) of the latest
// attempt holds its one final sentence; a page-side close (changed elsewhere) and the POST's own 201 both write through it, so a late
// 201 replaces the "changed elsewhere" line with "Exit placed on paper" and never adds a second line.
const EXIT_KEY = 'builder'
const exitRec = createExitRecords()
const paperExitNote = computed(() => exitRec.cur(EXIT_KEY)?.text ?? '') // the sentence of the record (hotfix 27 Nov T2-08)
// TD O-3: when the block is the exit rows' own legs having no live price (a good read), the sentence names them; a failed read, an unreadable state or a mixed block keeps the general sentence
const paperNoPriceNames = () => {
  const b = paper.value?.book
  const exits = paperRows.value.filter((r) => r.kind === 'exit')
  const ids = paperReadFailed.value || !b ? null : legsNoPrice(b.state, b.positions?.map((p) => ({ id: p.contract_id, live: p.price_state === 'live' })), exits.map((r) => r.contract_id))
  return ids ? exits.filter((r) => ids.includes(r.contract_id)).map((r) => r.text).filter(Boolean) : null
}
const paperNotLiveLine = computed(() => {
  if (!(paperDialog.value && exitBlocked.value && !paperContractsChanged.value)) return ''
  if (exitUnknown.value) return exitEndText('checking', paperLegNames())
  const named = paperNoPriceNames()
  return named?.length ? exitEndText('no_price', named) : exitEndText('not_live', paperLegNames())
})
function closeChanged() {
  exitRec.put(EXIT_KEY, 'changed', exitEndText('changed', paperLegNames()))
  cancelPaperDialog()
}
watch([exitBlocked, paperContractsChanged, paperBusy], ([blocked]) => { // also when a POST answers: a block that arrived meanwhile is acted on now
  if (blocked && paperContractsChanged.value && paperDialog.value && !paperBusy.value && !paperStale.value && paperState.value !== PAPER_STATE.UNKNOWN) closeChanged()
})
// Drafts Mode summary: the book's Profit left / Loss left first (or the words for its extremes_reason), its original Max Profit /
// Max Loss below; every figure the book reply's text as sent. Null outside Drafts Mode: the summary is unchanged.
// D-11: the tiles and the chart's marks are the WHOLE trade (booked in, the paper reply: the tiles after charges, the marks on
// the drawn curve's own basis, before charges, so they sit where the line crosses zero) with the switch ON, the open legs only (the
// outcome's own summary) with it OFF; the server computes both, this only picks which served figure to show
const wholeTrade = computed(() => !!paperLeft.value && includeBooked.value)
// UX-B25: while an exit's outcome is unknown for THIS book the tiles' book figures are the book before it: not shown (the screen legs' own outcome speaks)
const bookOutcomeUnknown = computed(() => !!exitUnknown.value && String(exitUnknown.value.id) === String(paper.value?.id))
const paperCharges = computed(() => (paper.value && includeBooked.value && !bookOutcomeUnknown.value ? paperChargesOf(paper.value.book) : null)) // D-13/D-14: the charges of the tiles beside it: switch ON = the paper tiles (paid + close); OFF = the open-legs tiles, the plan's round trip at entry prices (data.charges_breakdown)
// UX-B25: the book's figures are not known to belong to the legs on screen (the trade changed elsewhere, an add or exit was stored but not re-read, or an exit's outcome is unknown)
const tilesHeld = computed(() => !!paper.value && (bookOutcomeUnknown.value || paperStale.value || paperContractsChanged.value))
const paperLeft = computed(() => { // GC-ICFIX u124: after-charges forms, labelled (lib/paperDrafts paperLeftOf)
  const b = bookOutcomeUnknown.value ? null : paper.value?.book
  return b ? paperLeftOf(b, withAsOf(typeof b.pause_reason_text === 'string' && b.pause_reason_text.trim() !== '' ? b.pause_reason_text.trim() : null, b.as_of)) : null
})
// R-11: legs still carrying the entry and time the book loaded are paper fills ("Paper average", no time)
const paperFills = computed(() => (paper.value ? paper.value.net.map(paperFillKey) : []))
// #774, ADR-330 (48) (owner, 27 Nov): a move of a leg removes that leg's stop (the server cancels it in the order transaction and the review
// said so). After the move the app offers "Set a stop on <new leg>" through the existing leg-stop control (PaperStops, POST .../triggers).
// The offer rests on two server reads, never on a guess: the stops list before the Confirm and again after, and the book's net before and
// after. A stop the re-read shows gone AND a leg the book shows new: one offer per new leg. A refused move, an unknown answer (until the
// re-reads say otherwise), a leg without a stop, or a failed read: no offer, nothing claimed.
const stopOffer = ref(null) // { strategyId, legs: [{ index, label, contractId }] } | null
const stopOfferLeg = ref(null) // the offered leg whose control is open
let moveCheck = null // { id, stops, net }: what the page held before a Confirm whose answer is not yet known
// Lane FJ item 2 (review F3, page half; ADR-330 (48)): the stops a move cancelled, from the order reply alone. `cancelledStops` = the reply's list ([] = none, null = absent);
// `stopsReplyUnreadable` = the exit's 2xx reply was not an object. Both go to the dialog and, because a good exit closes it, are printed again in the stop-offer block.
const cancelledStops = ref(null)
const stopsReplyUnreadable = ref(false)
const cancelledStopTexts = computed(() => cancelledStopLines(cancelledStops.value))
const clearStopOffer = () => { stopOffer.value = null; stopOfferLeg.value = null; moveCheck = null; cancelledStops.value = null; stopsReplyUnreadable.value = false }
async function readStops(id) {
  try { return triggerListOf((await api.get(triggersPath(id))).data) } catch { return null } // a failed read is "unknown", never "empty"
}
// UX-A02: a leg's price as the book sent it, only while that leg's price is live (the Stops box says "not priced" for null; no field, no line)
const ltpTextOf = (contractId) => { const p = paper.value?.book?.positions?.find((x) => x.contract_id === contractId); return p?.price_state === 'live' && typeof p.ltp_text === 'string' && p.ltp_text.trim() !== '' ? p.ltp_text.trim() : null }
async function offerAfterMove(check) {
  if (!check?.stops?.length || !paper.value || paper.value.id !== check.id) return
  const now = await readStops(check.id)
  if (!now || !legStopsGone(check.stops, now).length) return
  const legs = paper.value.net.filter((l) => !check.net.includes(l.contract_id) && l.lots > 0)
    .map((l) => ({ index: l.contract_id, label: contractName(l), contractId: String(l.contract_id), ltpText: ltpTextOf(l.contract_id) }))
  if (legs.length) stopOffer.value = { strategyId: check.id, legs }
}
async function confirmPending(orders, _held = null, notLiveTicked = false, dialogKey = null) {
  if (paperBusy.value || !paper.value || !paperDialog.value) return // a Confirm for a dialog that is no longer open (the page closed it) posts nothing
  if (exitBlocked.value) { if (paperContractsChanged.value) closeChanged(); return } // post nothing (the watch may not have run yet); a failed read keeps the dialog and its sentence
  const { id } = paper.value
  if (exitLockFor(id)) return // F1 second path (Opus review F2): a lock of an earlier page instance for THIS strategy: post nothing until a read of its book decides it
  const names = paperLegNames()
  const wasExit = exitOrigin.value
  const waiting = exitAllWaiting.value // ADR-330 (59): an Exit all that discards a staged change posts the exits alone, like a per-leg Exit
  const own = legOnly // ADR-330 (49): a per-leg Exit carries no acted / basket / approach state; it stays for the staged change
  keepStaged = own ? { ...own, snapshot: copyLegs(legs.value) } : null
  const attempt = exitRec.begin(EXIT_KEY, names)
  paperBusy.value = true
  paperError.value = ''
  paperState.value = PAPER_STATE.READY
  let reply = null
  clearStopOffer()
  let stopsNow = []
  try { stopsNow = (await readStops(id)) ?? [] } catch { stopsNow = [] }
  if (!paper.value || !paperDialog.value || exitBlocked.value) { // Opus review F3: the book was left or the trade changed during that read: post nothing, free the dialog
    exitRec.clear(EXIT_KEY)
    paperBusy.value = false
    if (paper.value && exitBlocked.value && paperContractsChanged.value) closeChanged()
    return
  }
  const check = { id, stops: stopsNow.filter((x) => x.kind === 'leg_stop' && x.state === 'armed'), net: paper.value.net.map((l) => l.contract_id) }
  const sendsExit = orders.some((o) => o?.kind === 'exit')
  // F1 second path (Opus review F1): the lock is written BEFORE the post, so a page left or reloaded while the post is still out is covered; a definite answer removes it
  const key = orderKeyFor(id, JSON.stringify(orders), dialogKey) // Lane FJ item 1d: the dialog's key; the same orders still open after an unknown outcome send the key already held
  const book = bookOfNet(paper.value.net) // the WHOLE book the orders go against: the one key every page reads (lib/unknownLocks.js), the exited legs' units, the book they should leave
  const lockBase = { before: book?.key ?? null, units: sendsExit ? exitUnitsOf(orders, book) : null, expected: expectedKeyOf(orders, book), names, key, sig: JSON.stringify(orders), waiting: waiting ? { legs: waiting.legs, names: waiting.names } : null }
  if (sendsExit) saveExitLock(id, { at: Date.now(), out: true, ...lockBase }) // `out`: at = when the post went out; the give-up time replaces it below
  try {
    reply = own || waiting ? await postPaperOrders(api, id, orders, [], null, null, null, false, key) : await postPaperOrders(api, id, orders, actedSuggestionIds.value, preparedBasketLegs.value, null, preparedApproachId.value, notLiveTicked === true, key)
  } catch (e) {
    const outcome = paperPostOutcome(e)
    if (outcome === PAPER_STATE.REFUSED) dropOrderKey(id) // the server itself refused (580 / 581 / 583 too): nothing stored, the key is free
    if (sendsExit && outcome === PAPER_STATE.REFUSED) dropExitLock(id)
    if (outcome === PAPER_STATE.REFUSED) { // 4xx: the server stored nothing (one transaction or none)
      paperError.value = refusalText(e?.parts, NEUTRAL_PARTS.what_happened) // F6: every part of the reply
    }
    if (outcome === PAPER_STATE.UNKNOWN) {
      if (!orders.some((o) => o?.kind === 'exit')) addUnknown = { net: netKey(paper.value?.net) }
      exitRec.settle(EXIT_KEY, attempt, 'unknown')
      moveCheck = check // the re-reads decide, not this guess
      if (orders.some((o) => o?.kind === 'exit')) { // ADR-017: this exit may be stored; it is never sent again until a re-read decides it (any post that carries an exit row, wherever the click came from)
        const gaveUp = Date.now()
        saveExitLock(id, { ...lockBase, at: gaveUp, out: false }) // F1 second path: the lock outlives this page instance (see lib/unknownLocks.js); `at` is now when the client gave up
        exitUnknown.value = { id, attempt, names, waiting, at: gaveUp, lock: exitLockFor(id) }
        if (waiting) { exitAllWaiting.value = null; stagedNote.value = KEPT_UNTIL_KNOWN_TEXT(waiting.names) }
        void recheckUnknownExit()
      }
    }
    else if (outcome === PAPER_STATE.REFUSED) exitRec.settle(EXIT_KEY, attempt, 'refused')
    paperState.value = outcome // hotfix 27 Nov: a superseded POST is UNKNOWN (paperPostOutcome), never READY
    // REQ-163: a refused record is dropped, so the next request differs from the refused one; Confirm is ready again (text kept)
    if (outcome === PAPER_STATE.REFUSED) keepStaged = null // nothing stored: the screen legs stay as they are
    if (outcome === PAPER_STATE.REFUSED && !own && actedSuggestionIds.value.length && ACTED_REFUSED.has(e?.status)) {
      await dropActed() // the server's sentence above says why
      paperState.value = PAPER_STATE.READY
    }
    paperBusy.value = false
    return
  }
  // STORED (201). From here nothing may offer these orders again: a failure below is only a failed refresh.
  dropOrderKey(id) // stored: the action is over
  if (sendsExit) { // item 2: what the reply says about the stops of a move; a 2xx that is not an object says the stops are not known
    stopsReplyUnreadable.value = !(reply && typeof reply === 'object' && !Array.isArray(reply))
    cancelledStops.value = Array.isArray(reply?.cancelled_stops) ? reply.cancelled_stops : null
  }
  if (sendsExit) dropExitLock(id) // the server answered: the lock written before the post ends
  exitRec.settle(EXIT_KEY, attempt, 'placed', wasExit ? exitEndText('done', names, { orders: reply?.orders, sent: orders.length }) : '') // the server answered: placed replaces a page-side guess
  paperStale.value = true
  exitAllWaiting.value = null // cleared at once (Opus review): a later throw or a new Exit all during the re-read must not meet a stale value
  if (own) { exitOrigin.value = false; legsBeforeExit = null } // ADR-330 (49): what is left is no Exit edit; the other legs' edits are put back by restoreStaged
  try {
    if (!own) await dropActed({ withApproach: true }) // an Exit all that discards a staged change drops its acted / basket / approach too: they belong to the discarded change // one basket answers the records once (a per-leg Exit answered none)
  } catch { /* the ids may stay in the URL: the stored orders are never offered again (paperStale) */ }
  try {
    // the dialog stays, says it was placed, and has no Confirm, while the book is read again (issue 18: bounded retries, then Retry)
    if (waiting) stagedNote.value = DISCARDED_TEXT(waiting.names) // said at once: also when the re-read below fails
    if (await rereadAfterPlace(id, () => { paperState.value = PAPER_STATE.PLACED; paperBusy.value = false })) await offerAfterMove(check)
  } finally {
    paperBusy.value = false
  }
}
// GC-ICFIX issue 18 (finding panel-renders-nothing-when-its-read-fails): the book right after practice orders were stored may
// not be readable yet. Read it up to PAPER_REREAD_DELAYS_MS tries; the first failure calls `onFirstFail` (what the path says meanwhile),
// the last one shows the shared "could not load" state with Retry. What is on screen is never replaced by a failed read.
const rereadFailed = ref(false)
const rereadBusy = ref(false) // a read of the book is in flight (or waiting for its next try)
const barRef = ref(null)
let rereadId = null
let rereadFirstFail = null
let rereadRun = null // the one run whose answer still counts; another strategy opening ends it
let leaving = false
onBeforeUnmount(() => { leaving = true })
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
function cancelReread() {
  keepStaged = null
  rereadRun = null
  rereadId = null
  rereadFailed.value = false
  rereadBusy.value = false
}
async function rereadAfterPlace(id, onFirstFail) {
  const run = {}
  rereadRun = run
  rereadId = id
  rereadFirstFail = onFirstFail
  rereadFailed.value = false
  rereadBusy.value = true
  let failedOnce = false
  for (const wait of PAPER_REREAD_DELAYS_MS) {
    if (wait) await sleep(wait)
    if (leaving || rereadRun !== run) return false
    let read = null
    try { read = await readPaperBook(api, id) } catch { read = null } // only a failed READ is "not ready yet"
    if (leaving || rereadRun !== run) return false
    if (read?.kind === 'paper') {
      try {
        enterDrafts(id, read)
        restoreStaged(read.net)
        openError.value = null
        paperDialog.value = false
        paperState.value = PAPER_STATE.READY
        barRef.value?.showPaperTab()
        rereadBusy.value = false
        return true
      } catch {
        break // any other error is not a reason to read again: straight to the failure state
      }
    }
    if (!failedOnce) { failedOnce = true; onFirstFail?.() }
  }
  rereadBusy.value = false
  openError.value = null
  paperDialog.value = false
  rereadFailed.value = true
  return false
}
const retryReread = () => (rereadId === null ? null : rereadAfterPlace(rereadId, rereadFirstFail))
// Lane U2 (ADR-017, ADR-016..019): a good re-read of the book (the server's truth) decides an exit whose outcome was unknown: stored (the net moved to what
// the exit leaves, or to anything else) or not stored (the net equals the net before). Either way the lock ends; a not-stored exit is never kept as a staged edit.
let readSeq = 0 // reads of the book started by the unknown-exit door; an answer older than one already applied is ignored (Tier A round 1, finding 2)
let appliedSeq = 0
const REREAD_EVERY_MS = 5000 // how often the unknown exit's book is read again
// Lane Z review F1: an UNCHANGED trade is not proof of "not stored" until the server's longest possible commit window (UNKNOWN_EXIT_WINDOW_MS) has passed; the lock stays, with its plain line, meanwhile
function decideUnknownExit(newNet, readId, sentAt = Date.now()) {
  const u = exitUnknown.value
  if (!u) return true
  if (String(u.id) !== String(readId)) return false // Opus review F1: only a read of THIS strategy's book decides its unknown exit
  takeNewerGiveUp()
  const d = decideLock({ ...u.lock, at: u.at }, bookOfNet(newNet), sentAt) // the ONE decision (lib/unknownLocks.js): the whole book, the exited legs' units; a missing field keeps the lock
  if (d.verdict === 'keep') return false // Lane FJ: only a read SENT after the window decides unchanged; the order may still commit: stays locked, never "not stored" yet
  const unchanged = d.verdict === 'not_stored'
  exitUnknown.value = null
  dropExitLock(u.id) // decided by the server's answer: the remembered lock ends with it
  if (!unchanged) dropOrderKey(u.id) // stored or changed: the action is over; "not stored" keeps its key for the resend
  if (unchanged) { // not stored: say so, put the other legs' edits back without the exit
    restoreStaged(newNet, true)
    exitRec.put(EXIT_KEY, 'not_stored', exitEndText('not_stored', u.names))
  } else { // stored (or the trade changed): the book decides
    restoreStaged(newNet)
    if (d.verdict === 'stored') exitRec.settle(EXIT_KEY, u.attempt, 'placed', exitEndText('done', u.names, { orders: null, sent: 0 }))
    else exitRec.put(EXIT_KEY, 'changed', exitEndText('changed', u.names))
  }
  if (u.waiting) { // ADR-330 (59): the staged change comes back only if the exits were not stored; otherwise it is discarded and the screen says so
    if (unchanged) { setLegs(copyLegs(u.waiting.legs)); stagedNote.value = BACK_UNCHANGED_TEXT(u.waiting.names) }
    else stagedNote.value = DISCARDED_TEXT(u.waiting.names)
  }
  paperDialog.value = false
  paperState.value = PAPER_STATE.READY
  exitOrigin.value = false
  legsBeforeExit = null
  return true
}
async function recheckUnknownExit() { // the automatic re-read; a failed or too-early one leaves the lock (the Orderbook link and a reload read again)
  const u = exitUnknown.value
  if (!u || !paper.value) return
  const { id } = paper.value
  for (let first = true; ; first = false) { // reads every REREAD_EVERY_MS until one taken after the commit window has decided (or the lock ended)
    if (!first) await sleep(REREAD_EVERY_MS)
    if (leaving || exitUnknown.value !== u) return
    const seq = ++readSeq
    const sentAt = Date.now()
    let read = null
    try { read = await readPaperBook(api, id) } catch { read = null }
    if (leaving || exitUnknown.value !== u) return
    if (sentAt - u.at > UNKNOWN_EXIT_READ_AFTER_MS && !(seq < appliedSeq)) { // the last read of this loop: SENT past the window (Lane FJ: the time it left, not the time its answer came)
      if (read?.kind === 'paper') { const kept = keepStaged; enterDrafts(id, read); keepStaged = kept; appliedSeq = seq; decideUnknownExit(read.net, id, read.sentAt) }
      return
    }
    if (seq < appliedSeq) continue // a newer read (the Orderbook link's) was applied: this answer is dropped, the loop goes on (Opus review F4)
    if (read?.kind === 'paper') {
      const kept = keepStaged
      enterDrafts(id, read) // cancelReread ends keepStaged unless it is put back
      keepStaged = kept
      appliedSeq = seq
      if (decideUnknownExit(read.net, id, read.sentAt)) return
    }
  }
}
// the unknown-outcome link: re-read the book (the server's truth) and show its Orderbook; a failed read is said plainly
async function openPaperOrderbook() {
  if (!paper.value) return
  const { id } = paper.value
  paperDialog.value = false
  const seq = ++readSeq
  try {
    const read = await readPaperBook(api, id)
    if (read.kind !== 'paper') throw new Error('unreadable paper book')
    if (seq < appliedSeq) return // a newer read has already been applied: an older answer never reopens a leg
    appliedSeq = seq
    const kept = keepStaged // enterDrafts ends a re-read run that is not this strategy's (cancelReread) and would drop it
    enterDrafts(id, read)
    keepStaged = kept
    if (exitUnknown.value) decideUnknownExit(read.net, id, read.sentAt)
    else restoreStaged(read.net, true)
    showOrdersTick.value += 1
    const check = moveCheck
    moveCheck = null
    await offerAfterMove(check) // an unknown answer: the stop state and the book come from these re-reads
  } catch (e) {
    paperStale.value = true // the screen's net cannot be trusted until a book is read
    openError.value = unreadableParts(e)
  }
}
// N-13: while a strategy is being opened (its book read is out) the builder is not empty, it is loading: the empty-builder
// state and "No legs yet" are not shown until the read answers. One counter, so overlapping opens end it only when the last ends.
const opening = ref(false)
let openingCount = 0
async function whileOpening(fn) {
  openingCount += 1
  opening.value = true
  try { return await fn() } finally { openingCount -= 1; opening.value = openingCount > 0 }
}
// the Saved tab's Open goes through the same check: a strategy with paper orders opens as its net position, never its plan
const openFromBar = (next, id, revision, name) => whileOpening(() => openFromBarRead(next, id, revision, name))
async function openFromBarRead(next, id, revision, name) {
  if (Number.isInteger(id)) {
    try {
      const read = await readPaperBook(api, id)
      if (read.kind === 'paper') return enterDrafts(id, read)
    } catch (e) {
      openError.value = unreadableParts(e)
      return
    }
  }
  leaveDrafts()
  openSaved(next, id, revision, name)
}
// GC-TP step 3c: after Add to Paper confirms, the strategy is a paper strategy: re-read the book and enter Drafts Mode through the same
// enterDrafts as opening ?strategy=N. A failed read is said plainly (the bar keeps Add to Paper locked); the plan is not left live.
async function onPaperAdded(id) {
  await rereadAfterPlace(id, () => { openError.value = unreadableParts(null) })
}
function openFromUrl() {
  if (!STRATEGY_ID.test(String(route.query.strategy ?? ''))) return Promise.resolve()
  return whileOpening(readUrlStrategy)
}
async function readUrlStrategy() {
  const id = String(route.query.strategy ?? '')
  const before = legs.value
  let read
  try {
    read = await readPaperBook(api, id)
  } catch (e) {
    if (String(route.query.strategy ?? '') === id) openError.value = unreadableParts(e) // said plainly; the plan is not shown instead
    return
  }
  if (String(route.query.strategy ?? '') !== id || legs.value !== before) return
  // the book names its own strategy id (an integer); it must be the one in the URL
  if (read.kind === 'paper') return String(read.book.strategy_id) === id ? enterDrafts(read.book.strategy_id, read) : (openError.value = unreadableParts(null))
  realTradeId.value = null
  leaveDrafts()
  try {
    const saved = await fetchSavedDraft(api, id)
    if (String(route.query.strategy ?? '') !== id) return // F-4: the URL moved on while the read was out
    if (legs.value !== before) return // the user changed the legs while the read was out: never overwrite them
    openSaved(saved.legs, saved.id, saved.revision, saved.name)
    if (saved.statusWord === 'Running' && saved.id === savedId.value) realTradeId.value = saved.id // ADR-330 (58): orders exist (Running) and the paper book has none: a real trade
  } catch (e) {
    openError.value = e?.parts ?? NEUTRAL_PARTS // not found, unreadable, request failed: the screen stays as it is
    openNotFound.value = e?.error_code === STRATEGY_NOT_FOUND_CODE ? openError.value : null
  }
}
// F-4: the page stays mounted when only the query changes (App.vue's router-view is unkeyed), so a new ?strategy= / ?draft= is
// opened here through the same paths a fresh load uses. The ?strategy= the page itself writes after Save names the open strategy
// already, so it is not read again. Unsaved edits are replaced, exactly as the Saved tab's Open does (openSaved, no prompt).
watch(() => route.query.strategy, (v) => {
  if (!v || String(openStrategy.value?.id) === String(v)) return
  if (String(v) !== String(rereadId)) cancelReread()
  openError.value = null
  openFromUrl()
})
// ADR-328 (2): a replacing ?draft= link while the builder shows legs asks first (replacePrompt, the same words as the ready-made
// panel). Cancel keeps the legs, Drafts Mode and the open strategy and puts the previous link back in the URL (the one watch call
// that write causes is ignored). A newer link settles an open question as Cancel; an unreadable link takes today's refusal path.
const replaceAsk = ref(null) // null, or { count, resolve }
let replaceSeq = 0
let ignoreDraftWrites = 0
const settleReplace = (yes) => {
  const a = replaceAsk.value
  replaceAsk.value = null
  a?.resolve(yes)
}
const sameDraftContent = (canon) => canon.length === legs.value.length
  && canon.every((l, i) => l.instrument_id === legs.value[i].instrument_id && l.action === legs.value[i].action && l.lots === legs.value[i].lots)
watch(() => route.query.draft, async (v, old) => {
  if (ignoreDraftWrites > 0) { ignoreDraftWrites -= 1; return } // our own restore of the previous link
  if (!v) { // dropped from the URL by Save: an open replace question is Cancel, and its late answer must not apply the stale link
    replaceSeq += 1
    settleReplace(false)
    return
  }
  const mine = ++replaceSeq
  settleReplace(false) // a second question settles the first as Cancel
  const nextDraft = readDraft()
  const nextCanon = nextDraft ? canonicalLegs(nextDraft.legs) : []
  const refused = nextDraft !== null && nextCanon === null
  if (legs.value.length && nextDraft !== null && !refused) {
    if (sameDraftContent(nextCanon)) return // the same content as shown: nothing to ask, nothing to reseed
    cancelDuplicate() // one live question: an open leg-door question closes as Cancel
    const yes = await new Promise((resolve) => { replaceAsk.value = { count: legs.value.length, resolve } })
    if (mine !== replaceSeq) return // a newer link took over: it asks (or applies) on its own
    if (!yes) {
      ignoreDraftWrites += 1
      const { draft: _shown, ...rest } = route.query
      await router.replace({ path: route.path, query: old ? { ...rest, draft: old } : rest })
      return
    }
  }
  draftQuery = nextDraft
  canonicalQueryLegs = nextCanon
  leaveDrafts()
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
  restoreNote.value = null
  cancelDuplicate() // D-60: every legs replacement passes here; a question about the replaced legs closes (its edit settles as Cancel)
  dropUndo() // any new leg list supersedes an Undo still on offer: it can never restore over new legs
  savedId.value = null
  savedRevision.value = null
  linkRefused.value = false
  // fix1 (review): a target level / date picked for another underlying or first expiry means nothing for this one - reset it
  const [oldExpiry, newExpiry] = [firstExpiry(legs.value), firstExpiry(next)] // a draft's legs carry no expiry: compare only two known ones
  if (legs.value[0]?.underlying !== next[0]?.underlying || (oldExpiry && newExpiry && oldExpiry !== newExpiry)) targetPick.value = { level: '', dateIndex: 0 }
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
  if (legs.value.some((l) => l.capturing === true && l.planned_entry == null)) return // FB2 deferred: a leg still waiting for its entry is not read; the read goes out once, when the entry is in
  if (!linkRefused.value && legs.value.length >= 2) editLeg({ control: 'read' })
}

// REQ-135 AC-1: Clear all legs. The legs (and the saved strategy they belong to) are held for the served Clear-all window; the clear is
// an ordinary edit (the saved copy changes only on Save), exactly as removing the last leg is. One timer, not a recurring one.
const undoHeld = ref(null) // { legs, savedId, savedRevision, openStrategy } of the last clear, or null (expired, used, superseded, left)
let undoTimer = null
function dropUndo() {
  clearTimeout(undoTimer)
  undoHeld.value = null
}
async function clearAll() {
  if (!legs.value.length) return
  const held = { legs: legs.value, savedId: savedId.value, savedRevision: savedRevision.value, openStrategy: openStrategy.value } // taken BEFORE setLegs([]) nulls them
  setLegs([])
  openStrategy.value = null // a cleared screen is a new strategy: the next Save asks a name
  const ms = await useSettingsValues().waitMs(CLEAR_UNDO_SECONDS_KEY) // the served wait (REQ-167 AC-7)
  if (ms === null) return // not readable: no Undo is offered, never a typed time
  if (legs.value.length) return // legs came back while the wait was read: an Undo would restore over them
  undoHeld.value = held
  clearTimeout(undoTimer)
  undoTimer = setTimeout(dropUndo, ms)
}
// REQ-030 AC-15 (Q56): a row's trash is immediate and offers the SAME Undo as Clear all (one mechanism: undoHeld/undoClear). A paper
// trade's removal is a staged change with its own Discard, so it gets no second Undo.
async function removeLeg(i) {
  const held = { legs: legs.value, savedId: savedId.value, savedRevision: savedRevision.value, openStrategy: openStrategy.value, text: LEG_REMOVED }
  setLegs(legs.value.filter((_, k) => k !== i))
  if (paper.value) return
  const ms = await useSettingsValues().waitMs(CLEAR_UNDO_SECONDS_KEY)
  if (ms === null || legs.value.length !== held.legs.length - 1) return // unreadable, or the legs changed while the wait was read
  undoHeld.value = held
  clearTimeout(undoTimer)
  undoTimer = setTimeout(dropUndo, ms)
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
const DRAFTS_CHANGED_TEXT = 'The strategy changed while you were away. Your unsaved edits were not restored.'
const restoreNote = ref(null) // ADR-329: said when the book changed while the user was away and the held edits were not restored
// ADR-329 (1), Drafts Mode: the held legs belong to a paper strategy. Its book is read again (the net is the book's, never the held
// copy); the held edits reappear only when the net is the one they were made on, else the book stands and the page says so.
async function restoreDrafts(h) {
  const before = legs.value
  let read
  try {
    read = await readPaperBook(api, String(h.paperId))
  } catch (e) {
    openError.value = unreadableParts(e)
    return
  }
  if (legs.value !== before) return // the legs changed while the read was out: never overwrite them
  if (read.kind !== 'paper' || String(read.book.strategy_id) !== String(h.paperId)) { openError.value = unreadableParts(null); return }
  enterDrafts(read.book.strategy_id, read)
  if (h.netKey && JSON.stringify(netKeyOf(read.net)) === JSON.stringify(h.netKey)) {
    // N-37: a leg that was the book's own fill when held stays the book's fill: it takes the fill the book just answered (the average and its
    // quote time), so the page still knows it as a fill and never calls it a price the user typed. Other legs come back as held.
    const fills = new Set(h.fills ?? [])
    setLegs(h.legs.map((l) => {
      const fill = fills.has(paperFillKey(l)) ? read.net.find((n) => n.contract_id === l.contract_id) : undefined
      return fill ? { ...l, planned_entry: fill.planned_entry, captured_at: fill.captured_at } : { ...l }
    }))
  }
  else restoreNote.value = DRAFTS_CHANGED_TEXT
}
// ADR-329 (3): Add Selected arrives as a ?draft= link on the builder's held legs: the ticked contracts go through the one door
// (a same-action clash asks, an opposite side is a deliberate add), never through the draft-replace question. Returns true when
// it replaced the legs (setLegs already reloaded the numbers).
let chainError = null
// ADR-330 (20): once the ticked contracts are in the builder the ticks are cleared (they persist until they are added). The ONE
// place: called only after the legs were really set from the chain's own draft (the store's draft, byte for byte), so Cancel on
// a clash, the other-index refusal and an error leave the ticks, and a ?draft= from elsewhere never clears them.
const chainTicks = useChainSelection()
function clearAddedTicks() {
  const q = route.query.draft
  const u = draftQuery?.underlying
  if (typeof q !== 'string' || !u || !chainTicks.entries.length) return
  if (JSON.stringify(chainTicks.draftOf(u)) === q) chainTicks.clear()
}
let addedDraft = heldBack?.addedDraft ?? null
// N-36: the handled mark is the ?draft= text plus the history entry that carried it, so Back into the same entry asks nothing
// while a NEW Add Selected with the very same ticks (a new entry) still asks.
const entryMark = () => JSON.stringify([route.query.draft ?? null, router?.options?.history?.state?.addEntry ?? null])
async function addFromChain() {
  const fresh = legsFromQuery()
  // F1: a strategy has one underlying; ticked contracts of another underlying than the held legs are refused, nothing is added
  const heldUnderlying = legs.value[0]?.underlying
  const tickedUnderlying = fresh[0]?.underlying
  if (heldUnderlying && tickedUnderlying && heldUnderlying !== tickedUnderlying) {
    chainError = { ...INVALID_LINK_PARTS, what_happened: `These contracts are on ${tickedUnderlying}; the legs in the builder are on ${heldUnderlying}. Nothing was added.` }
    return false
  }
  const used = new Set(legs.value.map((l) => l.id))
  let n = 0
  const incoming = fresh.map((l) => {
    while (used.has(`chain-${n}`)) n += 1
    used.add(`chain-${n}`)
    return { ...l, id: `chain-${n}` }
  })
  const r = await door.admit(legs.value, incoming, { opposite: 'allow' })
  if (!r) { // Cancel: the held legs stay as they were, the ticks stay (ADR-330 (20)); Back into this same ?draft= entry asks nothing again (N-36)
    addedDraft = entryMark()
    return false
  }
  if (r.error) {
    chainError = { ...INVALID_LINK_PARTS, what_happened: r.error } // shown after the held legs' first reads, which clear editError
    return false
  }
  setLegs([...r.legs, ...r.kept])
  addedDraft = entryMark() // F3: Back into this same ?draft= entry must not add the same ticks again
  clearAddedTicks()
  return true
}
onMounted(async () => {
  index.start() // the page holds the index itself (its own socket), so an empty builder still has a spot
  if (heldBack?.paperId != null) await whileOpening(() => restoreDrafts(heldBack))
  const sameAdd = heldBack?.addedDraft != null && heldBack.addedDraft === entryMark() // F3: already added to this hold
  const added = heldBack && draftQuery && canonicalQueryLegs && !sameAdd ? await addFromChain() : false
  if (!added) {
    load()
    syncLive()
    readShape()
    if (!heldBack && legs.value.length && !linkRefused.value) clearAddedTicks() // the plain open from the chain's draft (nothing held)
  }
  if (chainError) editError.value = chainError
  if (!heldForUrl) openFromUrl() // the held strategy is already the page's: reading its book again would overwrite the restored edit
})
// REQ-076 AC-1/AC-4/AC-6/AC-8: ONE edit goes to the server; legs, name, marks and every number come from its reply.
// Only the tick leaves a saved draft saved (it is never part of the saved strategy, AC-7); any other edit makes it unsaved.
// The server's leg-edit takes the view but has no range field: a custom range is never sent there (it is asked for by load()).
const editView = () => {
  const { view } = choiceFields(choice.value)
  return view ? { view } : {}
}
// 2026-11-06 (REQ-076 AC-1, REQ-119): a strike step / Shift / Width / Hedge is RELATIVE to the legs shown. Under newest-wins
// alone each quick click cancelled the one before and was computed from the same old legs, so 5 clicks moved 1 strike. Now
// the clicks of one control (and leg) ADD UP while a request is in flight: every click sends ONE request from the last
// CONFIRMED legs carrying the total (`steps`), and newest-wins still drops every older reply. Any other edit waits until
// the move has landed (it would otherwise cancel it and send the old legs). `move` is null when no move is pending.
let move = null
const pendingSteps = ref({}) // the clicks not yet confirmed, per move key ({ 'step:2': 4 }): the row shows them at once
function endMove(m) {
  if (move !== m) return
  move = null
  pendingSteps.value = {}
  m.release()
}
async function moveLeg(edit) {
  const key = moveKey(edit)
  while (move && move.key !== key) await move.done
  if (!move) {
    let release
    const done = new Promise((resolve) => (release = resolve))
    move = { key, net: 0, legs: legs.value, shiftTotal: controls.value.shiftTotal, done, release }
  }
  const m = move
  m.net = Math.max(-MAX_STEPS, Math.min(MAX_STEPS, m.net + edit.direction))
  pendingSteps.value = { [key]: m.net }
  if (m.net === 0) { // the clicks cancel out: nothing to ask, the confirmed legs stand
    guard.cancel('leg-edit')
    cancelDuplicate() // a question left open by the move that just netted out closes as Cancel
    endMove(m)
    return
  }
  await sendEdit({ ...edit, direction: Math.sign(m.net), steps: Math.abs(m.net) }, m.legs, m.shiftTotal, m)
}
async function editLeg(edit) {
  if (RELATIVE_CONTROLS.includes(edit?.control) && (edit.direction === 1 || edit.direction === -1)) return moveLeg(edit)
  while (move) await move.done
  return sendEdit(edit, legs.value, controls.value.shiftTotal, null)
}
async function sendEdit(edit, baseLegs, shiftTotal, owner) {
  const body = buildEditRequest(baseLegs[0]?.underlying, baseLegs, edit, shiftTotal)
  if (!body) {
    if (owner) endMove(owner)
    return
  }
  const mine = guard.next('leg-edit') // aborts the edit still in flight (its reply would be stale)
  cancelDuplicate() // a question left open by the older move closes: the old edit settles as Cancel
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
    const shown = legs.value // the legs the reply is computed against; the answer must still find them on screen
    let landed = applyEditReply(shown, reply)
    let increased = false
    if (MOVE_CONTROLS.includes(edit.control)) { // D-48: the absolute expiry control lands on other contracts too (ADR-319 (1), ADR-328 (1))
      // D-60 (ADR-319, review finding 2): a move that lands a leg on a contract another leg holds with the same action asks
      // through the one shared door; Cancel keeps the legs as before the step, a refused Increase says why.
      const moved = await door.admitMoved(baseLegs, landed)
      if (!guard.isNewest('leg-edit', mine)) return // a newer edit took over while the question was open
      if (!sameLegs(legs.value, shown)) return // the move's base is no longer current: never overwrite the legs (Cancel)
      if (!moved) return
      if (moved.error) {
        editError.value = { ...NEUTRAL_PARTS, what_happened: moved.error }
        return
      }
      increased = moved.increased
      landed = moved.legs
    }
    legs.value = landed
    if (!keep) {
      savedId.value = null
      savedRevision.value = null
    }
    shapeName.value = reply.shape_name ?? null
    controls.value = controlsFrom(reply) // the server's controls and Shift total (null after a step, Width or Hedge)
    hasReply.value = true
    // The embedded outcome is the server's At Expiry on its default range, so it is drawn only when it matches the legs and
    // choice on screen and no outcome request is pending (that one is never cancelled here: its reply is checked the same way).
    if (increased) {
      load() // Increase quantity changed the legs the reply priced: the numbers for the legs now on screen
    } else if (reply.outcome && drawable(reply.outcome) && !guard.pending.outcome) {
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
    // the move ends with its NEWEST request (answered, refused or failed): a refused one leaves the confirmed legs shown
    if (owner && guard.isNewest('leg-edit', mine)) endMove(owner)
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
// "..." menu items: History opens the existing activity panel in the shared right Drawer (UI-108); Add to Paper opens the confirm list; it used to go to the
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
  replaceSeq += 1
  settleReplace(false) // F7: no dangling replace question
  cancelDuplicate() // the pending edit settles
  clearTimeout(slowTimer)
  clearTimeout(undoTimer)
})

// ADR-329 (2): the ONE count of unsaved legs (Drafts Mode: pending changes); the leave question and the line under the bar both read it.
const unsavedNow = computed(() => unsavedCount({ legCount: legs.value.length, savedId: savedId.value, inDrafts: paper.value !== null, pendingCount: pendingOrders.value?.length ?? 0 }))

const indexLevel = computed(() => headerLevel(data.value?.spot_level, index.shownValue(index.rowFor(headerUnderlying.value || pickUnderlying.value))))
// ADR-200 (2): the page's one market-closed banner. With an outcome reply it follows that reply; with none (no legs yet,
// the drawer priced from the last close) it follows the index answer the page already holds (its own socket / REST read)
let settledClosedBanner = null // UX-AF1: the last banner that was not drawn while an answer was out
const closedBanner = computed(() => {
  const fresh = pricesNow.value.kind === 'last_close'
    ? { at: pricesNow.value.at, text: state.value !== 'loading' && data.value?.market_closed ? data.value.closed_prices_text ?? null : null }
    : null
  const shown = closedBannerFor(state.value === 'loading', fresh, settledClosedBanner)
  if (fresh && state.value !== 'loading') settledClosedBanner = fresh
  if (!fresh) settledClosedBanner = null
  return shown
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
// D-18: each leg's own quote time from the reply (leg_quotes[].quote_at), by instrument id
const quoteAtById = computed(() => Object.fromEntries((data.value?.leg_quotes ?? []).filter((q) => typeof q.quote_at === 'string').map((q) => [q.instrument_id, q.quote_at])))
const ltpById = computed(() => Object.fromEntries((data.value?.legs ?? []).filter((l) => l.ltp != null).map((l) => [l.instrument_id, l.ltp])))
// GC-UI D-PX (REQ-152 AC-2): the server's two-decimal price texts by instrument id; the browser prints these, never the values
// fix/paper-dialog-safe item 2: the live price per leg as the table shows it (ltp_display, else the ltp string); an entry row in
// the paper confirm list starts at it instead of the planned entry captured when the leg was added
const livePriceById = computed(() => Object.fromEntries((data.value?.legs ?? []).map((l) => [l.instrument_id, l.ltp_display ?? l.ltp ?? null]).filter(([, v]) => typeof v === 'string' && v.trim() !== '')))
const priceTextById = computed(() => Object.fromEntries((data.value?.legs ?? []).map((l) => [l.instrument_id, { ltp_display: l.ltp_display ?? null, planned_entry_display: l.planned_entry_display ?? null }])))
// #744: the leg list's "Price has moved ... now" price: a paper trade reads the book (through the one join), any other plan keeps the reply's
const legListPrices = computed(() => (paper.value ? paperLegListPrices(data.value?.legs, paperLegsOf(paper.value.net, paper.value.book, paperBookFailed.value)) : { ltpById: ltpById.value, priceTextById: priceTextById.value }))
const legQuoteRows = computed(() => legQuotes(data.value))
// A leg's contract name: from its own fields, else looked up from the page's draft legs by instrument id (ADR-086).
// ADR-330 (61), I-30 (real case 27 Nov 08:30, app started 08:07: the builder went empty with "No legs yet" and said nothing about the list):
// the server's own line while an earlier day's list is in use (expiries reply `list_notice`). Never worded here. A failed read keeps what
// is shown (it says nothing new); the line is read again each minute only while it shows, and goes when a reply carries none.
const listNotice = ref('')
const LIST_NOTICE_REREAD_MS = 60000
let listSeq = 0
let listTimer = null
async function readListNotice() {
  clearTimeout(listTimer)
  const name = headerUnderlying.value || pickUnderlying.value
  if (!name) return
  const mine = ++listSeq
  try {
    const reply = (await api.get(`/catalogue/${name}/expiries`)).data
    if (mine !== listSeq) return
    listNotice.value = typeof reply?.list_notice === 'string' ? reply.list_notice.trim() : ''
  } catch {
    if (mine !== listSeq) return
  }
  if (listNotice.value) listTimer = setTimeout(readListNotice, LIST_NOTICE_REREAD_MS)
}
watch(() => headerUnderlying.value || pickUnderlying.value, readListNotice, { immediate: true })
onBeforeUnmount(() => { listSeq += 1; clearTimeout(listTimer) })
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
// ADR-329 (1), (2): leaving the builder for the Option Chain holds what it shows; leaving for any other page with unsaved legs asks.
// The guard registers only when the page is rendered by a <router-view> (the app); a page mounted directly has none.
// the snapshot's paperId comes from `paper` (Drafts Mode itself; a refresh reply's book may carry no id): the leave question's "pending" reads it
const leaveGuard = useLeaveBuilder({
  role: 'builder',
  unsaved: () => unsavedNow.value,
  snapshot: () => (legs.value.length
    ? { legs: legs.value, openStrategy: openStrategy.value, savedId: savedId.value, savedRevision: savedRevision.value, shapeName: shapeName.value,
      paperId: paper.value ? (paper.value.book?.strategy_id ?? paper.value.id) : null, netKey: paper.value ? netKeyOf(paper.value.net) : null, fills: paperFills.value, addedDraft }
    : null),
})
</script>

<template>
  <section data-testid="strategy-builder" :data-state="state" :data-live="live.status.value">
    <!-- W-193 (UI-005): the visible title block is gone (the top bar breadcrumb names the page); the heading stays for screen
         readers. The planning sentence moved into the Important info note under the summary card. -->
    <h1 class="sr-only" data-testid="page-title">Strategy Builder</h1>
    <!-- F6 (ADR-319, ADR-328 (1)): the ONE leg-door question (picker, forms, steps, chain add); outside every v-if chain, so no state hides it -->
    <DuplicateLegDialog :door="door" />
    <!-- ADR-328 (2): a replacing draft link while legs are shown -->
    <Modal :open="replaceAsk !== null" title="Replace the legs?" @close="settleReplace(false)">
      <div data-testid="draft-replace-dialog"><p data-testid="draft-replace-text">{{ replaceAsk ? replacePrompt(replaceAsk.count) : '' }}</p></div>
      <template #actions>
        <button type="button" class="rounded border border-line px-2 py-1" data-testid="draft-replace-yes" @click="settleReplace(true)">Replace</button>
        <button type="button" class="rounded border border-line px-2 py-1" data-testid="draft-replace-cancel" @click="settleReplace(false)">Cancel</button>
      </template>
    </Modal>
    <LeaveBuilderDialog :leave="leaveGuard" />
    <p v-if="restoreNote" class="mt-2 text-sm text-ink-muted" data-testid="drafts-restore-note">{{ restoreNote }}</p>

    <MarketClosedBanner v-if="closedBanner" class="mt-2" :prices-at="closedBanner.at" :server-text="closedBanner.text ?? null" />
    <p v-if="orderPathNotice" class="mt-2 text-sm text-ink-muted" data-testid="order-path-off-notice">{{ ORDER_PATH_OFF_SENTENCE }}</p>

    <AdjustCompare v-if="adjustId" :key="adjustId" :strategy-id="adjustId" :picked="pickedIds" :opportunities="opportunityIds" @prepare="prepareApproach" />
    <div v-else class="mt-3 grid grid-cols-1 gap-4 min-[1100px]:grid-cols-[minmax(480px,572px)_minmax(0,1fr)]" data-testid="builder-columns">
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
            ><Icon name="gear" :size="14" />View</button>
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

        <LoadFailed v-if="rereadFailed" :text="PAPER_REREAD_FAILED_TEXT" prefix="paper-reread" @retry="retryReread" />
        <ErrorMessage v-if="openError" :parts="openError" compact prefix="open-error" data-testid="open-error" />
        <RouterLink v-if="openError && openError === openNotFound" to="/strategies/my-strategies" class="mt-2 inline-block rounded border border-line px-2 py-1 text-sm" data-testid="open-error-my-strategies">Open My Strategies</RouterLink>
        <!-- Region B (UI-104..UI-108) -->
        <!-- GC-TP step 3b1 (Sensibull Drafts Mode 274-279): a paper strategy's legs are its net position, in a dashed frame -->
        <div :class="paper ? 'rounded-lg border-2 border-dashed border-warn p-2' : 'contents'" data-testid="legs-frame" :data-paper-mode="paper ? 'true' : 'false'">
        <p v-if="paper" class="mb-2 text-xs font-semibold text-warn" data-testid="paper-mode-label">{{ PAPER_MODE_LABEL }}</p>
        <!-- #774 (ADR-330 (48), owner 27 Nov): the stop went with the moved leg; offer a new one on each new leg (pending owner read) -->
        <div v-if="paper && (stopOffer || cancelledStopTexts.length || stopsReplyUnreadable)" class="mb-2 text-sm" data-testid="stop-offer">
          <ul v-if="cancelledStopTexts.length" class="mb-1 font-medium text-warn" role="status" data-testid="stop-offer-cancelled"><li v-for="line in cancelledStopTexts" :key="line">{{ line }}</li></ul>
          <p v-if="stopsReplyUnreadable" class="mb-1 font-medium text-warn" role="status" data-testid="stop-offer-reply-unreadable">{{ STOP_REPLY_UNREADABLE_TEXT }}</p>
          <div v-if="stopOffer" class="flex flex-wrap items-center gap-2">
            <button v-for="l in stopOffer.legs" :key="l.index" type="button" class="h-9 rounded-lg border border-line px-3 font-medium" :aria-expanded="stopOfferLeg === l.index" data-testid="stop-offer-open" @click="stopOfferLeg = stopOfferLeg === l.index ? null : l.index">{{ STOP_OFFER_LABEL(l.label) }}</button>
            <button type="button" class="h-9 rounded-lg px-3 text-ink-muted underline" data-testid="stop-offer-dismiss" @click="clearStopOffer">Not now</button>
          </div>
          <PaperStops v-for="l in (stopOffer?.legs ?? []).filter((x) => x.index === stopOfferLeg)" :key="l.index" leg-stop-only :strategy-id="stopOffer.strategyId" :legs="[l]" :leg-names="{ [l.index]: l.label }" />
        </div>
        <p v-if="listNotice" class="mb-2 text-sm text-ink-muted" data-testid="contract-list-notice">{{ listNotice }}</p>
        <LegList
          :opening="opening" :done="paperCompleted" :held-legs="paper && pendingOrders?.length ? paper.net : []" :failed="!!openError" :locked="exitBlocked" :lock-reason="exitGate.reason.value"
          :multiplier-max="served.integer(MULTIPLIER_MAX_KEY)" :legs="legs" :pending-steps="pendingSteps" :paper-fills="paperFills" :staged-exit-ids="paper ? stagedExitIds(paper.net, legs) : []" :quote-at-by-id="quoteAtById" :oldest-quote-at="data?.oldest_quote_at ?? null" :shape-name="shapeName" :has-reply="hasReply" :controls="controls" :updating="updating" :working="updating" :one-line="state === 'loading' && !showNumbers" :error-parts="editError" :error-index="editErrorIndex" :ltp-by-id="legListPrices.ltpById" :price-text-by-id="legListPrices.priceTextById"
          :undo-offered="undoHeld !== null" :undo-text="undoHeld?.text" :leg-unit="legUnit" :strategy-name="openStrategy?.name ?? null"
          @edit="editLeg" @edit-leg="openInPicker" @include-all="includeAll" @remove="removeLeg" @add-leg="focusPicker" @pick-chain="pickFromChain" @clear-all="clearAll" @undo-clear="undoClear"
        >
          <template #money>
            <div v-if="showNumbers" :class="updating ? 'opacity-60' : ''"><MoneySummary class="!mt-0 !px-0" :net-premium="data.summary.net_premium ?? null" :charges="data.charges_breakdown ?? null" :paper-charges="paperCharges" :basis-text="data.summary.price_basis_text ?? null" /></div>
          </template>
        </LegList>
        <!-- GC-ICFIX P3 u513: while the confirm dialog is open its list is a preview, not "N pending changes" the user made -->
        <p v-if="paper && stagedNote" class="mt-2 text-sm font-medium text-warn" role="status" data-testid="staged-not-kept">{{ stagedNote }}</p>
        <p v-if="paper && paperExitNote && !paperDialog" class="mt-2 text-sm font-medium text-warn" role="status" data-testid="paper-exit-note">{{ paperExitNote }}</p>
        <div v-if="paper && !paperDialog" class="mt-2 flex flex-wrap items-center gap-2 text-sm" data-testid="paper-pending">
          <span v-if="paperStale && rereadBusy" class="flex-1" data-testid="paper-pending-stale">{{ PAPER_PLACED_NOT_REFRESHED_TEXT }}</span>
          <span v-else class="flex-1" data-testid="paper-pending-count">{{ pendingOrders === null ? PAPER_PENDING_UNREADABLE : pendingText(pendingOrders.length) }}</span>
          <ExitButton v-if="!paperStale && pendingOrders?.length" :blocked="exitBlocked" :show-reason="false" class="h-9 rounded-lg bg-accent px-3 font-medium text-white disabled:opacity-50" data-testid="paper-review" @click="reviewPending">{{ REVIEW_AND_ADD_LABEL }}</ExitButton>
          <button v-if="pendingOrders === null || pendingOrders.length" type="button" class="h-9 rounded-lg border border-line px-3 font-medium" data-testid="paper-discard" @click="discardPending">{{ DISCARD_LABEL }}</button>
        </div>
        <PaperBookPanel v-if="paper" :book="paper.book" :net="paper.net" :changed-ids="stagedChangeIds(paper.net, legs)" :read-failed="paperBookFailed" :contracts-changed="paperContractsChanged" :exit-unresolved="!!exitUnknown" :show-orders="showOrdersTick" @exit="exitPaper" @exit-all="exitAllPaper" />
        </div>
        <PaperConfirmDialog :open="paperDialog" :orders="paperRows" :strategy-id="route.query.strategy" :busy="paperBusy" :blocked="exitBlocked" :note="exitAllWaiting ? DISCARD_WARNING(exitAllWaiting.names) : ''" :locked="!!exitUnknown" :locked-at-ms="exitUnknown ? exitUnknown.at : 0" :cancelled-stops="cancelledStops" :stops-reply-unreadable="stopsReplyUnreadable" :error="paperError || paperNotLiveLine" :state="paperState" :not-live-line="paperEntryNotLiveLine" @confirm="confirmPending" @cancel="userCancelPaperDialog" @orderbook="openPaperOrderbook" />
        <SaveDraftBar v-show="!(opening && !legs.length)" ref="barRef" :legs="legs" :rules-ref="String(route.query.rules_ref || '')" :current="openStrategy" :shown-name="shapeName ?? ''" :paper-mode="paper !== null" :live-price-by-id="livePriceById" :prices-live="pricesLive" :market-closed="pricesNow.kind === 'last_close'" :price-as-of="pricesNow.at ?? ''" class="max-[1099px]:contents" @open="openFromBar" @saved="onSaved" @paper-added="onPaperAdded" @renamed="onRenamed" @deleted="onDeleted">
          <template #add-edit>
            <button v-if="!paperCompleted" type="button" class="h-10 flex-1 basis-0 rounded-lg border border-line font-medium" aria-haspopup="dialog" :aria-expanded="pickerOpen ? 'true' : 'false'" data-testid="add-edit" :disabled="exitBlocked" :title="exitBlocked ? exitGate.reason.value : undefined" @click="pickerOpen = !pickerOpen">Add/Edit</button>
          </template>
          <template #menu="{ close, addToPaper, canAddToPaper }">
            <button v-if="openStrategy" type="button" role="menuitem" data-testid="menu-activity" @click="close(); showHistory()">History</button>
            <button v-if="!paper" type="button" role="menuitem" data-testid="menu-add-to-paper" :disabled="!canAddToPaper" @click="close(); addToPaper()">{{ ADD_TO_PAPER_LABEL }}</button>
          </template>
          <template #ready-made><ReadyMadePanel :legs="legs" :underlying="headerUnderlying || pickUnderlying" @update:legs="setLegs" /></template>
          <!-- GC-BP step 6: the Tracked tab is the shared paper list; it reads (and polls) only while that tab is shown -->
          <template #tracked="{ active }"><PaperStrategies v-if="active" compact /></template>
        </SaveDraftBar>
        <!-- ADR-330 (34): remove this line when REQ-154 (unsaved strategy kept across a reload) ships. Shown while unsavedNow > 0 (in Drafts Mode too:
             pending changes are lost on a reload as well); gone once saved or cleared. -->
        <p v-if="unsavedNow > 0" class="mt-1 text-xs text-ink-muted" data-testid="unsaved-reload-note">{{ UNSAVED_RELOAD_NOTE }}</p>
        <!-- W-195 (ADR-193 UI-200): the leg picker is a left slide-in drawer; it stays mounted while shut so Edit can open
             it on a leg and a half-made selection survives a close -->
        <!-- GC-UI 6c D-C20: no title bar (S-032: the picker's own header row is the top line); the width stays 520 px so the
             strike grid keeps the 470 px D-C27 fits in. D-C35: the "Show Editor" edge tab folds the drawer away to see the
             builder; the "Show Strikes" tab at the page edge brings it back with the picks kept (the picker stays mounted). -->
        <Drawer :open="pickerOpen" title="Add or edit legs" side="left" width="520px" persist bare @close="pickerOpen = false; pickerFolded = false">
          <div class="h-full" data-testid="leg-picker-panel"><LegPicker ref="picker" :max-lots="served.integer(MAX_LOTS_KEY)" :lot-choice-count="served.integer(LOT_CHOICES_KEY)" :legs="legs" :show-leg-list="false" :active="pickerOpen" :page-underlying="headerUnderlying || pickUnderlying" :last-close="closedBanner ? indexLevel : null" :closed-at="closedBanner?.at ?? null" @update:legs="setLegs" @done="pickerOpen = false; pickerFolded = false" /></div>
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
        <p v-else-if="state === 'loading' || (opening && state === 'no-draft')" class="mt-4" data-testid="state-loading">
          Working out the outcome...<span v-if="slow" data-testid="state-slow"> This is taking longer than usual.</span>
        </p>

        <p v-else-if="state === 'no-draft' && rightKind === 'closed'" class="mt-4 text-ink-muted" data-testid="state-closed">{{ CLOSED_TRADE_TEXT }}</p>
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

        <!-- GC-ICFIX 21 (X-7, ADR-259): a strategy with orders and no open leg (Completed) has no tracking panel; its history stays readable. Not strategyStatus.js: a practice strategy opens from GET /paper/strategies/{id}, which carries no status. -->
        <AdjustSteps v-if="paper && savedId && !showNumbers && state === 'no-draft' && !opening" :strategy-id="savedId" />

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

          <!-- D-11/D-16 (ADR-209): the tiles follow the Add Booked switch; this line says which basis they are on -->
          <p v-if="paperLeft" class="mt-4 text-xs text-ink-muted" data-testid="tiles-basis">{{ wholeTrade ? (paper.book.breakevens_basis_text ?? '') : (data.summary?.charges != null ? OPEN_LEGS_ONLY_TEXT : OPEN_LEGS_ONLY_BEFORE_CHARGES_TEXT) }}</p>
          <SummaryCards
            v-model:flipped="ratioFlipped"
            class="mt-4"
            :left="paperLeft"
            :holding="tilesHeld"
            :summary="data.summary"
            :max-profit="wholeTrade ? paper.book.max_profit_text ?? '-' : summaryFigure(data.summary, 'profit')"
            :max-loss="wholeTrade ? paper.book.max_loss_text ?? '-' : summaryFigure(data.summary, 'loss')"
            :max-profit-exact="wholeTrade ? paper.book.max_profit ?? null : data.summary.max_profit ?? null"
            :max-loss-exact="wholeTrade ? paper.book.max_loss ?? null : data.summary.max_loss ?? null"
            :breakevens="wholeTrade ? paper.book.breakevens_display ?? [] : data.summary.breakevens_display ?? []"
            :breakevens-exact="wholeTrade ? paper.book.breakevens ?? [] : data.summary.breakevens ?? []"
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
            :time-value-basis="data.summary.time_value_basis_text ?? null"
            :value-reason="data.summary.value_reason ?? null"
            :funds-share="paperLeft ? null : data.summary.funds_share ?? null"
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
            :max-profit="wholeTrade ? (paper.book.max_profit === 'unlimited' ? null : paper.book.max_profit ?? null) : data.summary.max_profit_unlimited ? null : data.summary.max_profit"
            :max-loss="wholeTrade ? (paper.book.max_loss === 'unlimited' ? null : paper.book.max_loss ?? null) : data.summary.max_loss_unlimited ? null : data.summary.max_loss"
            :curves="data.curves ?? null"
            :target-curve="targetShown?.curve ?? null"
            :include-booked="includeBooked"
            :target-booked-text="targetShown?.includes_booked_text ?? ''"
            :target-badge="targetShown?.badge ?? null" :target-stale="targetStale" :target-stale-text="targetShown?.stale_text ?? ''" :show-badge="!!targetShown"
            :breakevens="wholeTrade ? paper.book.breakevens_curve ?? [] : data.summary.breakevens ?? []"
            :curve-booked-text="data.curve_includes_booked_text ?? ''"
            :sd="data.standard_deviation ?? null"
            :oi="data.open_interest ?? null"
            :zoom="zoomGrid"
            :payoff-table="data.payoff_table ?? null"
            :saved-id="savedId"
            :paper-total="paperTotal"
            :paper-legs="paper ? paperLegsOf(paper.net, paper.book, paperBookFailed) : null"
            :closed="paper?.book?.closed ?? null"
            :charges="paper ? { paid: paper.book.charges_paid_text ?? paper.book.charges_text ?? null, close: paper.book.charges_to_close_text ?? null } : null"
            :saved-revision="savedRevision"
            @zoom="zoomTo"
            @update:include-booked="pickBooked"
            @payoff-step="stepTo"
          >
            <!-- GC-TP R-19a (Sensibull 020): the what-if Target block sits BELOW the payoff graph, inside the chart card -->
            <template #target>
              <TargetBlock
                :target="targetShown" :pick="targetPick" :stop-count="dateStopList.length" :stale="targetStale" :not-live-text="targetNotLiveText"
                @level="(v) => pickTarget({ level: v })"
                @date="(i) => pickTarget({ dateIndex: i })"
                @reset-level="pickTarget({ level: '' })"
                @reset-date="pickTarget({ dateIndex: 0 })"
              />
            </template>
            <template #controls>
              <ScenarioControls :choice="choice" :scenario-label="data?.scenario?.label ?? ''" :estimate-note="data?.output_label ?? ''" @update:choice="setChoice" />
            </template>
            <template #details>
              <AdvancedDetails v-if="legQuoteRows" :rows="legQuoteRows" :name-of="nameOf" />
            </template>
          </ChartCard>
          <LowerCard :table="data.table" :legs="data.legs ?? null" :sd="data.standard_deviation ?? null" />
          <StrategyActions :saved-id="savedId" :execute-refusal="refusal" />
          <TrackingPanel :saved-id="savedId" :legs="data.legs ?? null" :shared="paper?.book ?? null" :shared-failed="paperBookFailed" :trade-mode="tradeMode" />
        </div>
        <!-- ADR-330 (57): a fully closed trade has no monitoring badge (its plan line is in the book panel). P10 (ADR-330 (13)): the Plan watch under the live P&L column, whatever the numbers state is (it is its own server read); it re-reads on the page's own book read (paper.book is replaced by each good read) -->
        <MonitoringBadge v-if="planWatchId && !paperCompleted" :entry="monitoring.entryOf(planWatchId)" class="mt-4" />
        <!-- UX-A06: a settled trade keeps the box with the closed fact (nothing is read). UX-C3: while the page's own "Working out the outcome..." is the one loading line, the box keeps its rows but says nothing of loading (outcomeLoading) -->
        <PlanWatch v-if="planWatchId" :strategy-id="planWatchId" :read-tick="paper?.book ?? null" :stale="paperBookFailed" :closed="paperCompleted" :outcome-loading="state === 'loading' && !showNumbers" class="mt-4" />
      </div>
    </div>
  </section>
</template>

