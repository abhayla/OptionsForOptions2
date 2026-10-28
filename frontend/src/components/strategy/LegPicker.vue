<!-- Leg picker (W-068; REQ-035 AC-8, ADR-068 items 1 and 4, ADR-020 Q185, ADR-008, ADR-012).
     Underlying -> expiry -> CE/PE/FUT -> strike (none for FUT) -> BUY/SELL -> lots -> Add. Every choice except the
     underlying list, the action and the lots comes from the catalogue API (GET /api/catalogue/...); the browser never
     talks to Zerodha. A planned entry is the string POST /api/strategies/planned-entry returns when the leg is added;
     without a live price the leg has none and is shown with the not-connected wording. No price or P&L is computed here.
     Adapted from the legacy StrategyBuilderView leg-row form shape only (client P&L, price fallbacks and the basket call
     are dropped). -->
<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import api, { NEUTRAL_PARTS } from '@/services/api'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import DepthPopup from '@/components/strategy/DepthPopup.vue'
import MarketClosedBanner from '@/components/states/MarketClosedBanner.vue'
import { capturedCaption, contractName, daysByExpiry, expiryText, expiryWithDays, istTime, strikeLabel } from '@/lib/displayFormat'
import { marketClosedText } from '@/lib/sharedStateText'
import { QUICK_PICK_DISTANCES } from '@/lib/readyMade'
import { healthSentence } from '@/lib/dataHealthText'
import { oiBarMax, oiBarWidth as barWidthOf } from '@/lib/oiBars'
import {
  DEFAULT_STRIKE_WIDTH,
  FORWARD_LABEL,
  LEG_NOT_LIVE_LABEL,
  NOT_CONNECTED_LABEL,
  PICKER_REFRESH_MS,
  REPRICE_PROMPT,
  STRIKE_WIDTHS,
  UNDERLYINGS,
  centreText,
  contractByInstrumentId,
  forwardReasonText,
  futureReasonText,
  futuresListReasonText,
  instrumentId,
  itmSides,
  listReasonText,
  lotChoices,
  lotsValid,
  offeredStrikes,
  offeredTypes,
  selectedContract,
  shown,
  oiCompact,
} from '@/lib/legPicker'

const props = defineProps({
  // the Strategy Builder draws the ONE leg list (LegList.vue), so it passes false
  showLegList: { type: Boolean, default: true },
  legs: { type: Array, default: () => [] },
  // W-195: the Builder keeps the picker mounted inside its closed drawer; the 5 s refresh reads nothing while it is shut
  active: { type: Boolean, default: true },
  // GC-BM F-14: the page's chosen underlying, used when the strategy has no legs; '' = no opinion (keep the current one)
  pageUnderlying: { type: String, default: '' },
  // GC-UI polish D-7b (ADR-197): after hours the page header shows the last close; the drawer header shows that same string (the page's own
  // source, nothing computed here) with the same "Market closed" label. null = the page has none: the header says so and shows no number.
  lastClose: { type: String, default: null },
  closedAt: { type: String, default: null },
})
// `done`: Done added the selection (the Builder closes the drawer, UI-206)
const emit = defineEmits(['update:legs', 'done'])

const underlying = ref(props.legs[0]?.underlying ?? 'NIFTY')
const expiries = ref([])
const expiry = ref('')
const expiryDays = ref({}) // REQ-135 AC-2: the server's day count by expiry (the same reply as the expiries)
const expiryLabel = (e) => expiryWithDays(e, expiryDays.value[e])
const contracts = ref([])
const type = ref('')
const strike = ref('')
const action = ref('SELL')
const lots = ref(1) // v-model.number: a whole number once valid, else the typed text
const editingId = ref(null)
const busy = ref(false)
const errorParts = ref(null)
let nextId = 1
let seq = 0 // the newest catalogue request wins; an older answer arriving late is dropped

const editing = computed(() => props.legs.find((l) => l.id === editingId.value) ?? null)
// Locked while any leg exists, also while editing the only one: a leg's contract belongs to its underlying.
const underlyingLocked = computed(() => props.legs.length > 0)
const serverDefault = ref('') // ADR-199 (4): the expiries reply's default_expiry; '' = the reply carried none (older server)
const types = computed(() => offeredTypes(contracts.value))
const strikes = computed(() => offeredStrikes(contracts.value, type.value))
const contract = computed(() => selectedContract(contracts.value, type.value, strike.value))
const lotsOk = computed(() => typeof lots.value === 'number' && lotsValid(String(lots.value)))
const canSave = computed(() => !busy.value && lotsOk.value && (contract.value !== null || (editing.value !== null && !type.value && underlying.value === editing.value.underlying)))

/** G-070 (REQ-150 AC-4, S-032): the drawer opens on the strategy's own expiry if its legs carry one the list offers, else
 *  the server's default (ADR-199: not today's expiry after the close), else the first listed one. An empty or unreadable list chooses nothing. */
function openingExpiry() {
  const own = props.legs.find((l) => l.expiry && expiries.value.includes(l.expiry))
  return own ? own.expiry : (expiries.value.includes(serverDefault.value) ? serverDefault.value : (expiries.value[0] ?? ''))
}

// `preselect` is false for startEdit, which chooses the edited leg's own expiry itself
async function loadExpiries(preselect = true) {
  const mine = ++seq
  expiries.value = []
  serverDefault.value = ''
  contracts.value = []
  expiry.value = ''
  type.value = ''
  strike.value = ''
  try {
    const res = await api.get(`/catalogue/${underlying.value}/expiries`)
    if (mine !== seq) return false
    expiries.value = res.data.expiries
    serverDefault.value = res.data.default_expiry ?? ''
    expiryDays.value = daysByExpiry(res.data.expiry_days)
    errorParts.value = null
    // F-13: a shut drawer reads no strikes or contracts; the opening watcher picks the expiry and reads them on open
    if (preselect && props.active) {
      expiry.value = openingExpiry()
      await loadContracts()
    }
    return true
  } catch (e) {
    if (mine === seq) errorParts.value = e?.parts ?? NEUTRAL_PARTS
    return false
  }
}

async function loadContracts() {
  const mine = ++seq
  contracts.value = []
  type.value = ''
  strike.value = ''
  if (!expiry.value) return false
  try {
    const res = await api.get(`/catalogue/${underlying.value}/contracts?expiry=${expiry.value}`)
    if (mine !== seq) return false
    contracts.value = res.data.contracts
    errorParts.value = null
    return true
  } catch (e) {
    if (mine === seq) errorParts.value = e?.parts ?? NEUTRAL_PARTS
    return false
  }
}

async function onUnderlying(value) {
  underlying.value = value
  await loadExpiries()
}
async function onExpiry(value) {
  expiry.value = value
  await loadContracts()
}
function onType(value) {
  type.value = value
  strike.value = ''
}

// ---- REQ-080: Strikes / Futures tabs, multi-select and Done (W-147). Every figure is what the server sent; a read that
// fails or is superseded leaves NO old list on screen. ----
const tab = ref('strikes')
const width = ref(DEFAULT_STRIKE_WIDTH)
const lotsMode = ref('lots') // 'lots' | 'quantity' (the per-user setting is REQ-138; here a local choice)
const strikesData = ref(null)
const strikesFailed = ref(false)
const futuresData = ref(null)
const futuresFailed = ref(false)
const picked = ref({}) // instrument_id -> 'BUY' | 'SELL'
const cellLots = ref({}) // instrument_id -> lots chosen in that cell
// GC-BP F-2: the contract is stored AT the pick, so Done never depends on the expiry list on screen (a pick made on another
// expiry or width is still a leg). instrument_id -> catalogue contract, or null when the list did not carry it at that moment.
const pickedContracts = ref({})
const doneError = ref('')
const depthFor = ref(null) // the leg whose depth popup is open
let stSeq = 0
let fuSeq = 0
let timer = null

// GC-UI 6c (D-C21, S-032): the select shows Sensibull's short "3 Nov" so it is never clipped; the server's day count
// (REQ-135 AC-2) sits beside it as its own text, and the option value stays the ISO date.
const expiryShort = (e) => expiryText(e) ?? e
const expiryDaysText = computed(() => {
  const d = expiryDays.value[expiry.value]
  return Number.isInteger(d) && d >= 0 ? `${d} ${d === 1 ? 'day' : 'days'}` : ''
})
// D-C23: the spot sits in the header (the read time as its tooltip); with no live spot the header says why, and no row is
// centred on a guess (D-C28 centres only the row the server marked ATM).
const spotLive = computed(() => (strikesData.value?.centre === 'LIVE_SPOT' && strikesData.value?.spot ? strikesData.value.spot : null))
const spotTitle = computed(() => (spotLive.value && strikesData.value?.answered_at ? `Index price, read ${istTime(strikesData.value.answered_at)}` : ''))
const centreStrike = computed(() => (strikesData.value?.centre === 'MIDDLE_STRIKE' ? null : (strikesData.value?.rows ?? []).find((r) => r.is_atm)?.strike ?? null))
const centreLine = computed(() => centreText(strikesData.value, istTime))
const strikesReason = computed(() => listReasonText(strikesData.value?.reason))
const futuresReason = computed(() => futuresListReasonText(futuresData.value?.reason))
const pickedCount = computed(() => Object.keys(picked.value).length)

async function loadStrikes() {
  if (!expiry.value) return
  const mine = ++stSeq
  try {
    const res = await api.get(`/leg-picker/strikes?underlying=${underlying.value}&expiry=${expiry.value}&width=${width.value}`)
    if (mine !== stSeq) return
    strikesData.value = res.data
    strikesFailed.value = false
  } catch {
    if (mine !== stSeq) return
    strikesData.value = null
    strikesFailed.value = true
  }
}

async function loadFutures() {
  const mine = ++fuSeq
  try {
    const res = await api.get(`/leg-picker/futures?underlying=${underlying.value}`)
    if (mine !== fuSeq) return
    futuresData.value = res.data
    futuresFailed.value = false
  } catch {
    if (mine !== fuSeq) return
    futuresData.value = null
    futuresFailed.value = true
  }
}

function refreshOpenTab() {
  return tab.value === 'futures' ? loadFutures() : loadStrikes()
}
function tick() {
  if (props.active) refreshOpenTab()
}

// W-195 (UI-202, UI-205): the view switch picks which of the server's columns each side shows (S-032/S-033); the Greeks
// view shows Delta and IV only, since Theta/Vega/Gamma are not in this reply (REQ-084). Settings holds the width and size.
const VIEW_COLUMNS = Object.freeze({ ltp: ['delta', 'ltp', 'oi', 'iv'], oi: ['ltp', 'oi'], greeks: ['delta', 'iv'] })
// D-C27 round 2: the LTP view's widths and the 3 px gap add up to 464 px, inside the 470 px the 1536 x 864 drawer panel allows
// (round 1 widened columns without adding the total up and the grid scrolled sideways). Delta takes a 7-character
// "-0.4920", the OI a compact "1.23Cr" (oiCompact), the B / S pair two 12 px buttons.
const COLUMN_WIDTH = Object.freeze({ delta: '44px', ltp: 'minmax(42px,1fr)', oi: '40px', iv: '36px' })
const ACT_WIDTH = '26px'
const STRIKE_WIDTH = '58px'
const view = ref('ltp')
const settingsOpen = ref(false)
const columns = computed(() => VIEW_COLUMNS[view.value])
const sideColumns = (side) => (side === 'ce' ? [...columns.value, 'act'] : ['act', ...[...columns.value].reverse()])
const gridStyle = computed(() => {
  const widths = columns.value.map((c) => COLUMN_WIDTH[c])
  return { gridTemplateColumns: [...widths, ACT_WIDTH, STRIKE_WIDTH, ACT_WIDTH, ...[...widths].reverse()].join(' ') }
})
// the qty sub-row sits under its own side, on the row's second line
const subRowStyle = (side) => ({ gridRow: '2', gridColumn: side === 'ce' ? `1 / span ${columns.value.length + 1}` : `span ${columns.value.length + 1} / -1` })
const itm = computed(() => itmSides(strikesData.value?.rows))
const COLUMN_LABEL = Object.freeze({ delta: 'Delta', ltp: 'LTP', oi: 'OI', iv: 'IV' })

// GC-UI 6c D-C26 (S-032): an OI bar under the server's OI label, sized in lib/oiBars.js (drawing only, ADR-008); a cell
// with no OI draws no bar and shows the dash (REQ-083 AC-6).
const maxOi = computed(() => oiBarMax(strikesData.value?.rows))
const oiBarWidth = (v) => barWidthOf(v, maxOi.value)

// ---- GC-UI 6c D-C22 / D-C24 / D-C25 (S-032, S-036..S-038): four tabs. Straddles, Strangles and Strikes are strategy TYPES
// that each build the one selection (`picked`); Futures adds a future directly. Changing type while picks exist asks first.
const TABS = Object.freeze([['straddles', 'Straddles'], ['strangles', 'Strangles'], ['strikes', 'Strikes'], ['futures', 'Futures']])
const TYPE_NAME = Object.freeze({ straddles: 'Straddles', strangles: 'Strangles', strikes: 'Strikes' })
const pickType = ref('strikes') // the type the current picks were made under (kept while the Futures tab is open)
const pendingTab = ref(null) // the type change waiting for Proceed / Cancel
const typeSide = ref('SELL') // Straddles / Strangles: Buy or Sell both legs (the existing quick-pick `side`)
const quickError = ref('')
function selectTab(next) {
  if (next === tab.value) return
  if (next in TYPE_NAME && next !== pickType.value && pickedCount.value > 0) {
    pendingTab.value = next
    return
  }
  if (next in TYPE_NAME) pickType.value = next
  tab.value = next
}
const confirmText = computed(() => (pendingTab.value ? `You are changing strategy type from ${TYPE_NAME[pickType.value]} to ${TYPE_NAME[pendingTab.value]}` : ''))
function proceedTab() {
  const next = pendingTab.value
  pendingTab.value = null
  clearAll()
  pickType.value = next
  tab.value = next
}
const cancelTab = () => { pendingTab.value = null }

/** Pick a set of cells as THE selection of a Straddles / Strangles tab (it replaces the earlier picks of that type). */
function pickSet(cells, side) {
  const next = {}
  const contractsNow = {}
  for (const cell of cells) {
    next[cell.instrument_id] = side
    contractsNow[cell.instrument_id] = contractByInstrumentId(contracts.value, cell.instrument_id) ?? null
  }
  picked.value = next
  pickedContracts.value = contractsNow
  cellLots.value = {}
  doneError.value = ''
}
// S-037: one radio per strike; the straddle is that strike's call and put, both on the chosen side
const straddleStrike = computed(() => {
  const ids = Object.keys(picked.value)
  const row = (strikesData.value?.rows ?? []).find((r) => r.ce && r.pe && ids.length === 2 && ids.includes(r.ce.instrument_id) && ids.includes(r.pe.instrument_id))
  return row ? row.strike : ''
})
function pickStraddle(row) {
  if (row.ce && row.pe && choicesFor(row.ce).length && choicesFor(row.pe).length) pickSet([row.ce, row.pe], typeSide.value)
}
// S-038: a box on each side; at most one call and one put
const strangleLeg = (side) => (strikesData.value?.rows ?? []).find((r) => r[side] && picked.value[r[side].instrument_id])?.strike ?? ''
function pickStrangleSide(row, side) {
  const other = side === 'ce' ? 'pe' : 'ce'
  const otherRow = (strikesData.value?.rows ?? []).find((r) => r[other] && picked.value[r[other].instrument_id])
  pickSet([row[side], ...(otherRow ? [otherRow[other]] : [])], typeSide.value)
}
function setTypeSide(side) {
  typeSide.value = side
  const ids = Object.keys(picked.value)
  if (ids.length) picked.value = Object.fromEntries(ids.map((id) => [id, side]))
}
const quickDistances = computed(() => QUICK_PICK_DISTANCES[underlying.value] ?? [])
/** D-C08 / D-C24: Quick Select asks the EXISTING quick-pick call (POST /strategies/quick-pick) which strikes make the
 *  strangle; its legs become the selection, so Done prices and adds them like any pick. A failed or empty answer picks nothing. */
async function quickSelect(distance) {
  quickError.value = ''
  if (busy.value || !expiry.value) return
  const und = underlying.value
  try {
    const res = await api.post('/strategies/quick-pick', { underlying: und, kind: 'strangle', distance, side: typeSide.value, expiry: expiry.value })
    const legs = Array.isArray(res?.data?.legs) ? res.data.legs : []
    if (und !== underlying.value) return
    if (!legs.length) { quickError.value = 'No strangle could be made at this distance, so nothing was picked.'; return }
    pickSet(legs.map((l) => ({ instrument_id: l.instrument_id })), typeSide.value)
  } catch {
    quickError.value = 'The quick select could not be read right now, so nothing was picked.'
  }
}

// D-C28: the list opens scrolled so the server's ATM row sits in the middle (on open and on a new list, never on the
// 5 s refresh, which would pull the user's scroll back). jsdom has no layout, so the call is guarded.
const strikesPanel = ref(null)
let centrePending = true
function centreAtm() {
  if (!centrePending || !centreStrike.value) return
  centrePending = false
  nextTick(() => {
    const el = strikesPanel.value?.querySelector?.('[data-centre="true"]')
    if (el && typeof el.scrollIntoView === 'function') el.scrollIntoView({ block: 'center' })
  })
}
watch(strikesData, centreAtm)

// A new underlying, expiry or width is a new list: the old one goes before the new read starts. GC-BP F-2: the picks stay
// across an expiry or width change (each carries its own contract, Done adds them all); only a new UNDERLYING clears them,
// since a strategy has one underlying.
watch([underlying, expiry, width], () => {
  stSeq++
  strikesData.value = null
  strikesFailed.value = false
  centrePending = true
  if (tab.value !== 'futures' && props.active) loadStrikes()
})
watch(underlying, () => {
  picked.value = {}
  cellLots.value = {}
  pickedContracts.value = {}
})
watch(underlying, () => {
  fuSeq++
  futuresData.value = null
  futuresFailed.value = false
  if (tab.value === 'futures' && props.active) loadFutures()
})
watch(tab, refreshOpenTab)
// W-195 review 4: the drawer opening is the moment the user looks, so the open tab's prices are read again then (the
// 5 s tick reads nothing while it is shut, so they may be minutes old)
// (C) a catalogue read that failed earlier is tried again on open, so the error at the top of the drawer is current
watch(() => props.active, (on) => {
  if (!on) return
  centrePending = true // D-C28: every open shows the ATM row in the middle again
  // F-14: the underlying is the strategy's, decided when the drawer opens (the picker was mounted before the legs or the
  // header choice existed). A different one reloads its expiries; that load picks the opening expiry and reads the strikes.
  if (editingId.value === null) {
    const target = props.legs[0]?.underlying || props.pageUnderlying || underlying.value
    if (target !== underlying.value) {
      underlying.value = target
      loadExpiries()
      if (tab.value === 'futures') loadFutures()
      return
    }
  }
  if (!expiries.value.length && editingId.value === null) loadExpiries()
  // F-12: the opening expiry is chosen when the drawer opens, from the legs as they are NOW (they may have changed since
  // mount). A different expiry is shown and its strikes are read by the expiry watcher: that one read is this open's read.
  else if (editingId.value === null && expiries.value.length) {
    const target = openingExpiry()
    if (target && target !== expiry.value) {
      onExpiry(target) // on the Strikes tab the expiry watcher reads the strikes: that is this open's read
      if (tab.value === 'futures') loadFutures() // the watcher reads nothing on the Futures tab, so this open reads its prices
      return
    }
  }
  refreshOpenTab()
})
// a leg removed by the page (the one list lives outside this component) while it is being edited leaves no stale form
watch(() => props.legs, (now) => { if (editingId.value !== null && !now.some((l) => l.id === editingId.value)) resetForm() })

onMounted(() => {
  loadExpiries()
  timer = setInterval(tick, PICKER_REFRESH_MS)
})
onBeforeUnmount(() => clearInterval(timer))

/** Buy or Sell on a cell selects that contract with that side; the same button again unselects it. */
function choose(id, side) {
  const next = { ...picked.value }
  if (next[id] === side) delete next[id]
  else next[id] = side
  picked.value = next
  if (!(id in next)) { const { [id]: _c, ...rest } = pickedContracts.value; pickedContracts.value = rest }
  else if (!pickedContracts.value[id]) pickedContracts.value = { ...pickedContracts.value, [id]: contractByInstrumentId(contracts.value, id) ?? null }
}
/** The contract stored at the pick; a pick made before the list carried it falls back to the list on screen (else null). */
const contractOfPick = (id) => pickedContracts.value[id] ?? contractByInstrumentId(contracts.value, id)
const lotsOf = (id) => cellLots.value[id] ?? 1
/** Drop one selection (from the selection list): Done then no longer adds it. */
function unpick(id) {
  const { [id]: _side, ...rest } = picked.value
  const { [id]: _lots, ...restLots } = cellLots.value
  const { [id]: _pc, ...restContracts } = pickedContracts.value
  picked.value = rest
  cellLots.value = restLots
  pickedContracts.value = restContracts
}
/** Clear All (REQ-080 AC-3): the whole selection and its lots go; nothing is added or sent. */
function clearAll() {
  picked.value = {}
  cellLots.value = {}
  pickedContracts.value = {}
  doneError.value = ''
}
/** Every leg Done will add, as the user reads it: contract, side, lots. */
const selection = computed(() => Object.keys(picked.value).map((id) => {
  const c = contractOfPick(id)
  const name = c ? contractName({ underlying: underlying.value, expiry: c.expiry, instrument_type: c.instrument_type, strike: c.strike }) : id
  return { id, name, action: picked.value[id], lots: lotsOf(id) }
}))
const choicesFor = (cell) => lotChoices(lotsMode.value, cell?.lot_size)
/** The select's text maps back to one of the offered choices (never parsed): an unknown text changes nothing. */
function setLots(cell, text) {
  const choice = choicesFor(cell).find((o) => String(o.value) === text)
  if (choice) cellLots.value = { ...cellLots.value, [cell.instrument_id]: choice.value }
}

function resetForm() {
  editingId.value = null
  type.value = ''
  strike.value = ''
  action.value = 'SELL'
  lots.value = 1
}

async function startEdit(leg) {
  editingId.value = leg.id
  action.value = leg.action
  lots.value = leg.lots
  underlying.value = leg.underlying
  if (!(await loadExpiries(false)) || editingId.value !== leg.id) return // cancelled or switched meanwhile
  if (leg.expiry && expiries.value.includes(leg.expiry)) {
    expiry.value = leg.expiry
    if ((await loadContracts()) && editingId.value === leg.id) {
      type.value = leg.instrument_type
      strike.value = leg.strike ?? ''
    }
  }
}

/** The planned entry for a newly chosen contract: the API's strings, or nothing. Never a default, zero or last price. */
async function capture(id, und) {
  try {
    const res = await api.post('/strategies/planned-entry', { underlying: und, instrument_ids: [id] })
    const found = res.data.entries.find((e) => instrumentId(e.exchange_segment, e.exchange_token) === id)
    if (found && found.planned_entry != null && found.captured_at != null) {
      return { planned_entry: found.planned_entry, captured_at: found.captured_at, source: found.source, reason_code: null,
               close_at: found.close_at ?? null, checked_at: res.data.answered_at ?? null } // ADR-197: close_at = the close's own time
    }
    return { planned_entry: null, captured_at: null, source: null, reason_code: found?.reason_code ?? 'no_live_price',
             checked_at: res.data.answered_at ?? null }
  } catch {
    return { planned_entry: null, captured_at: null, source: null, reason_code: 'capture_failed', checked_at: null }
  }
}

async function save() {
  if (!canSave.value) return
  busy.value = true
  // Snapshot every input, then reset the form BEFORE the await: picks made while the entry is captured belong to the
  // next leg and must not be read into this one or wiped by it.
  const old = editing.value
  const c = contract.value
  const und = underlying.value
  const act = action.value
  const lotCount = lots.value
  const id = c ? instrumentId(c.exchange_segment, c.exchange_token) : old.instrument_id
  resetForm()
  try {
    // A priced leg keeps its captured entry while its contract is unchanged (only buy/sell or lots changed).
    const pricing = old && old.instrument_id === id && old.planned_entry != null
      ? { planned_entry: old.planned_entry, captured_at: old.captured_at, source: old.source, reason_code: null, close_at: old.close_at ?? null }
      : await capture(id, und)
    const leg = {
      id: old ? old.id : nextId++,
      underlying: und,
      instrument_id: id,
      contract_id: c ? c.contract_id : old.contract_id, // W-071: what Save Draft sends (ADR-057)
      symbol: c ? c.symbol : old.symbol,
      expiry: c ? c.expiry : old.expiry,
      instrument_type: c ? c.instrument_type : old.instrument_type,
      strike: c ? c.strike : old.strike,
      lot_size: c ? c.lot_size : old.lot_size,
      action: act,
      lots: lotCount,
      ...pricing,
    }
    emit('update:legs', old ? props.legs.map((l) => (l.id === old.id ? leg : l)) : [...props.legs, leg])
    emit('done') // a leg added or saved by contract also hands the page back (the Builder closes the drawer)
  } finally {
    busy.value = false
  }
}

function remove(leg) {
  if (editingId.value === leg.id) resetForm()
  emit('update:legs', props.legs.filter((l) => l.id !== leg.id))
}

/** Done (REQ-080 AC-3): every selected contract becomes a leg, each through the same planned-entry capture as a single
 *  add. A leg whose capture finds no price is still added and carries the reprice prompt (ADR-085). Never an order. */
async function done() {
  const ids = Object.keys(picked.value)
  if (busy.value || !ids.length) return
  const chosen = ids.map((id) => ({ id, c: contractOfPick(id), action: picked.value[id], lots: lotsOf(id) }))
  if (chosen.some((x) => !x.c || !lotsValid(String(x.lots)))) {
    doneError.value = 'Contract details are not available for every selected contract, so nothing was added.'
    return
  }
  doneError.value = ''
  busy.value = true
  picked.value = {} // picks made while the entries are captured belong to the next batch
  cellLots.value = {}
  pickedContracts.value = {}
  await addChosen(chosen, underlying.value)
  emit('done')
}

/** The one path that turns chosen contracts into legs (Done and a future's Buy/Sell): each is captured like a single add;
 *  a leg with no price is still added and carries the reprice prompt. Caller has set busy. */
async function addChosen(chosen, und) {
  try {
    const pricing = await Promise.all(chosen.map((x) => capture(x.id, und)))
    const added = chosen.map((x, i) => ({
      id: nextId++,
      underlying: und,
      instrument_id: x.id,
      contract_id: x.c.contract_id,
      symbol: x.c.symbol,
      expiry: x.c.expiry,
      instrument_type: x.c.instrument_type,
      strike: x.c.strike,
      lot_size: x.c.lot_size,
      action: x.action,
      lots: x.lots,
      ...pricing[i],
      reason_code: pricing[i].planned_entry == null ? 'needs_reprice' : null,
    }))
    emit('update:legs', [...props.legs, ...added])
  } finally {
    busy.value = false
  }
}

/** Buy or Sell on a REAL future (REQ-080 AC-9): its contract details come from the catalogue for that future's own expiry
 *  (the Futures tab lists every expiry, the form holds one), then the leg is added through addChosen. No contract found
 *  or a failed read adds nothing. The forward row is a calculated price and has no such button. */
async function addFuture(f, side) {
  if (busy.value) return
  doneError.value = ''
  busy.value = true
  const und = underlying.value
  let c = null
  try {
    const res = await api.get(`/catalogue/${und}/contracts?expiry=${f.expiry}`)
    c = contractByInstrumentId(res.data.contracts, f.instrument_id)
  } catch {
    c = null
  }
  if (!c || c.instrument_type !== 'FUT') {
    busy.value = false
    doneError.value = 'Contract details are not available for this future, so nothing was added.'
    return
  }
  await addChosen([{ id: f.instrument_id, c, action: side, lots: 1 }], und)
}

const legName = (l) => contractName(l)
// the Builder's one leg list (LegList.vue) opens the same edit form through this, as the picker's own Edit did
/** W-195 review 7: "Pick from Option Chain" opens the picker on the Strikes tab (Add leg keeps the tab the user left). */
function showStrikes() {
  if (editingId.value !== null) resetForm()
  selectTab('strikes') // picks made under another type still ask before they are dropped (D-C25)
}
defineExpose({ startEdit, showStrikes })
</script>

<template>
  <!-- W-195 (ADR-193 UI-200..UI-207, Sensibull S-032..S-038): the body of the Builder's left slide-in drawer. Header
       (underlying, expiry, Settings), Strikes | Futures tabs with the LTP / OI / Greeks view switch, the dense strike table,
       the leg-by-contract form (also the Edit / Reprice form), and a footer kept in view with the count, Clear All, Done. -->
  <section class="flex h-full min-h-0 flex-col gap-3 text-sm" data-testid="leg-picker">
    <!-- Compact and with its own test id: the page's ErrorMessage keeps error-what/impact/blocked/next to itself. -->
    <ErrorMessage v-if="errorParts" :parts="errorParts" compact prefix="picker-error" data-testid="picker-error" />
    <div class="flex flex-wrap items-center gap-2 pr-10" data-testid="picker-header">
      <select class="h-8 rounded border border-line px-1 font-semibold" aria-label="Underlying" data-testid="pick-underlying" :value="underlying" :disabled="underlyingLocked" @change="onUnderlying($event.target.value)">
        <option v-for="u in UNDERLYINGS" :key="u" :value="u">{{ u }}</option>
      </select>
      <!-- D-C23 (S-032): the index price in the header; its read time is the tooltip. No live price: the header says so. -->
      <span v-if="spotLive" class="num font-semibold" :title="spotTitle" data-testid="picker-spot">{{ spotLive }}</span>
      <template v-else-if="strikesData && lastClose">
        <span class="num font-semibold" :title="marketClosedText(istTime(closedAt))" data-testid="picker-spot">{{ lastClose }}</span>
        <span class="text-xs text-ink-muted" data-testid="picker-spot-closed">Market closed</span>
      </template>
      <span v-else-if="strikesData" class="text-xs text-ink-muted" data-testid="picker-spot">No live index price</span>
    </div>

    <div class="flex min-h-0 flex-1 flex-col" data-testid="picker-tabs">
      <!-- D-C22 row 1: the four tabs, Settings at the right -->
      <div class="flex shrink-0 items-center gap-3 border-b border-line" data-testid="picker-row1">
        <span class="flex items-center gap-3" role="tablist">
          <button
            v-for="tb in TABS" :key="tb[0]" type="button" role="tab" class="-mb-px border-b-2 py-2"
            :class="tab === tb[0] ? 'border-accent font-semibold text-ink' : 'border-transparent text-ink-muted'"
            :data-testid="`tab-${tb[0]}`" :aria-selected="tab === tb[0]" @click="selectTab(tb[0])"
          >{{ tb[1] }}</button>
        </span>
      <span class="relative ml-auto" @keydown.esc.stop="settingsOpen = false">
        <button type="button" class="h-8 rounded border border-line px-2" aria-haspopup="dialog" :aria-expanded="settingsOpen ? 'true' : 'false'" data-testid="picker-settings" @click="settingsOpen = !settingsOpen">Settings</button>
        <span v-show="settingsOpen" role="dialog" aria-label="Picker settings" class="absolute right-0 top-full z-10 mt-1 flex w-[240px] flex-col gap-2 rounded-lg border border-line bg-surface p-3 shadow-menu" data-testid="picker-settings-popover">
          <label class="flex items-center justify-between gap-2">Strikes each side
            <select v-model.number="width" class="rounded border border-line px-1" data-testid="pick-width">
              <option v-for="w in STRIKE_WIDTHS" :key="w" :value="w">{{ w }}</option>
            </select>
          </label>
          <label class="flex items-center justify-between gap-2">Size in
            <select v-model="lotsMode" class="rounded border border-line px-1" data-testid="pick-lots-mode">
              <option value="lots">Lots</option>
              <option value="quantity">Quantity</option>
            </select>
          </label>
        </span>
      </span>
      </div>

      <!-- D-C25 (S-036): a change of strategy type with picks made asks first; Cancel keeps the picks -->
      <div v-if="pendingTab" role="alertdialog" aria-label="Change strategy type" class="mt-2 flex flex-wrap items-center gap-2 rounded border border-line p-2" data-testid="type-confirm">
        <span class="w-full" data-testid="type-confirm-text">{{ confirmText }}</span>
        <button type="button" class="rounded border border-line px-3 py-1" data-testid="type-confirm-cancel" @click="cancelTab">Cancel</button>
        <button type="button" class="rounded bg-accent px-3 py-1 font-semibold text-white" data-testid="type-confirm-proceed" @click="proceedTab">Proceed</button>
      </div>

      <!-- D-C22 row 2: the expiry (D-C21: Sensibull's short "3 Nov", the day count beside it) and the LTP / OI / Greeks switch -->
      <div v-show="tab !== 'futures'" class="flex shrink-0 items-center gap-2 py-2" data-testid="picker-row2">
        <select class="h-8 rounded border border-line px-1" aria-label="Expiry" data-testid="pick-expiry" :value="expiry" @change="onExpiry($event.target.value)">
          <option value="">Expiry</option>
          <option v-for="e in expiries" :key="e" :value="e">{{ expiryShort(e) }}</option>
        </select>
        <span v-if="expiryDaysText" class="text-xs text-ink-muted" data-testid="pick-expiry-days">{{ expiryDaysText }}</span>
        <span v-if="tab === 'strikes'" class="ml-auto flex overflow-hidden rounded border border-line text-xs" role="radiogroup" aria-label="Columns" data-testid="picker-view">
          <button
            v-for="vw in [['ltp', 'LTP'], ['oi', 'OI'], ['greeks', 'Greeks']]" :key="vw[0]" type="button" role="radio" class="px-2 py-1"
            :class="view === vw[0] ? 'bg-accent-soft font-semibold text-accent' : 'text-ink-muted'" :aria-checked="view === vw[0] ? 'true' : 'false'"
            :data-testid="`picker-view-${vw[0]}`" @click="view = vw[0]"
          >{{ vw[1] }}</button>
        </span>
      </div>

      <div v-if="tab === 'strikes'" ref="strikesPanel" class="min-h-0 flex-1 overflow-y-auto" data-testid="strikes-panel">
        <p v-if="!expiry" data-testid="strikes-choose-expiry">Choose an expiry to see its strikes.</p>
        <p v-else-if="strikesFailed" data-testid="strikes-error">The strikes could not be read right now.</p>
        <p v-else-if="!strikesData" data-testid="strikes-loading">Reading strikes...</p>
        <template v-else>
          <!-- ADR-200 (2): after hours every cell is the last close, under the one market-closed banner -->
          <MarketClosedBanner v-if="strikesData.market_closed === true" class="mb-2" :prices-at="strikesData.last_price_at" />
          <p v-if="strikesReason" data-testid="strikes-reason">{{ strikesReason }}</p>
          <p v-if="centreLine" data-testid="strikes-centre">{{ centreLine }}</p>
          <!-- UI-202 column heads: Call side | Strike | Put side, the same columns as every row below -->
          <div class="mt-2 grid items-end gap-x-[3px] border-b border-line pb-1 text-[10px] leading-tight text-ink-muted" :style="gridStyle" data-testid="strike-head">
            <span v-for="col in sideColumns('ce')" :key="`ce-${col}`" class="text-right">{{ col === 'act' ? '' : `Call ${COLUMN_LABEL[col]}` }}</span>
            <span class="text-center">Strike</span>
            <span v-for="col in sideColumns('pe')" :key="`pe-${col}`">{{ col === 'act' ? '' : `Put ${COLUMN_LABEL[col]}` }}</span>
          </div>
          <div
            v-for="(row, ri) in strikesData.rows" :key="row.strike" class="group grid items-center gap-x-[3px] border-b border-line text-[11px] tabular-nums num"
            :class="row.is_atm ? 'bg-accent-soft font-semibold' : ''" :style="gridStyle" data-testid="strike-row" :data-strike="row.strike" :data-atm="row.is_atm ? 'true' : 'false'"
            :data-centre="row.strike === centreStrike ? 'true' : 'false'"
          >
            <template v-for="side in ['ce', 'pe']" :key="side">
              <!-- the strike sits between the two sides; each side is `contents` so its columns join the row's grid -->
              <div
                v-if="side === 'pe'" class="flex h-7 items-center justify-center bg-surface-muted font-semibold" :class="row.is_atm ? '!bg-accent-soft text-accent' : ''"
                data-testid="row-strike"
              >{{ strikeLabel(row.strike) }}<span v-if="row.is_atm" class="ml-1 text-[10px]" data-testid="atm-mark">ATM</span></div>
              <div class="contents" :data-testid="`cell-${side}`">
                <template v-if="row[side]">
                  <div
                    v-for="col in sideColumns(side)" :key="col" class="flex h-7 items-center"
                    :class="[side === 'ce' ? 'justify-end' : 'justify-start', itm[ri]?.[side] && col !== 'act' ? 'bg-warn-soft' : '']"
                  >
                    <span v-if="col === 'delta'" data-testid="cell-delta">{{ shown(row[side].delta) }}</span>
                    <span v-else-if="col === 'ltp'" class="font-medium text-ink" data-testid="cell-ltp">{{ shown(row[side].ltp) }}</span>
                    <span v-else-if="col === 'iv'" class="text-ink-muted" data-testid="cell-iv">{{ shown(row[side].iv_percent) }}</span>
                    <!-- UI-202 / D-C26: the OI count in Indian units (oiCompact) over a bar drawn from the server's OI (drawing
                         only, never a printed figure, ADR-008); no OI = no bar and the dash -->
                    <span v-else-if="col === 'oi'" class="relative flex h-5 w-full items-center" :class="side === 'ce' ? 'justify-end' : 'justify-start'">
                      <span
                        v-if="oiBarWidth(row[side].oi)" aria-hidden="true" class="absolute bottom-0 h-1 rounded-sm" :class="[side === 'ce' ? 'right-0 bg-sell-soft' : 'left-0 bg-buy-soft']"
                        :style="{ width: oiBarWidth(row[side].oi) }" data-testid="cell-oi-bar"
                      />
                      <span class="relative text-ink-muted" data-testid="cell-oi">{{ oiCompact(row[side].oi) }}</span>
                    </span>
                    <!-- UI-203: B and S show on row hover or keyboard focus, and stay shown once chosen -->
                    <span v-else-if="col === 'act' && choicesFor(row[side]).length" class="flex gap-0.5">
                      <button
                        v-for="sd in [['BUY', 'B', 'Buy'], ['SELL', 'S', 'Sell']]" :key="sd[0]" type="button"
                        class="h-4 w-3 rounded text-[10px] font-semibold focus:opacity-100"
                        :class="picked[row[side].instrument_id] === sd[0]
                          ? (sd[0] === 'BUY' ? 'bg-buy text-white' : 'bg-sell text-white')
                          : (sd[0] === 'BUY' ? 'bg-buy-soft text-buy' : 'bg-sell-soft text-sell') + (picked[row[side].instrument_id] ? '' : ' opacity-0 group-hover:opacity-100 group-focus-within:opacity-100')"
                        :data-testid="sd[0] === 'BUY' ? 'cell-buy' : 'cell-sell'" :aria-pressed="picked[row[side].instrument_id] === sd[0]"
                        :aria-label="`${sd[2]} ${strikeLabel(row.strike)} ${side.toUpperCase()}`" :title="`${sd[2]} ${strikeLabel(row.strike)} ${side.toUpperCase()}`"
                        @click="choose(row[side].instrument_id, sd[0])"
                      >{{ sd[1] }}</button>
                    </span>
                  </div>
                  <!-- UI-203 qty sub-row under the chosen side (lots or quantity per Settings); kept in the page so a size can be
                       chosen first, shown once the side is picked -->
                  <label
                    v-if="choicesFor(row[side]).length" v-show="picked[row[side].instrument_id]" class="flex h-8 items-center gap-1 px-1"
                    :class="side === 'ce' ? 'justify-end' : 'justify-start'" :style="subRowStyle(side)"
                  >{{ lotsMode === 'quantity' ? 'Qty' : 'Lots' }}
                    <select class="rounded border border-line px-1" data-testid="cell-lots" :value="lotsOf(row[side].instrument_id)" @change="setLots(row[side], $event.target.value)">
                      <option v-for="o in choicesFor(row[side])" :key="o.value" :value="o.value">{{ o.label }}</option>
                    </select>
                  </label>
                </template>
                <span v-else class="flex h-7 items-center justify-center text-ink-subtle" :style="{ gridColumn: `span ${columns.length + 1}` }" data-testid="cell-none">-</span>
              </div>
            </template>
          </div>
        </template>
        <!-- The selection is its own list, whatever the strike list shows (the refresh re-centres the rows): Done adds
             exactly these. -->
        <ul v-if="pickedCount" class="mt-2 flex flex-col gap-1" data-testid="selection-list">
          <li v-for="item in selection" :key="item.id" class="flex items-center gap-2" data-testid="selection-row" :data-instrument-id="item.id" :data-action="item.action" :data-lots="item.lots">
            <span class="rounded px-1 text-xs font-semibold" :class="item.action === 'BUY' ? 'bg-buy-soft text-buy' : 'bg-sell-soft text-sell'" data-testid="selection-side">{{ item.action }}</span>
            <span data-testid="selection-name">{{ item.name }}</span>
            <span class="text-ink-muted" data-testid="selection-lots">{{ item.lots }} lot</span>
            <button type="button" class="ml-auto text-ink-muted underline" data-testid="selection-remove" :aria-label="`Remove ${item.name}`" @click="unpick(item.id)">Remove</button>
          </li>
        </ul>
      </div>

      <!-- D-C24 (S-037 Straddles: one radio per strike; S-038 Strangles: a box each side + Quick Select). Both build the
           same selection the footer's Done adds; the rows are the strikes reply, nothing is computed here. -->
      <div v-else-if="tab === 'straddles' || tab === 'strangles'" class="min-h-0 flex-1 overflow-y-auto" :data-testid="`${tab}-panel`">
        <div class="flex flex-wrap items-center gap-2 py-1">
          <span class="flex overflow-hidden rounded border border-line text-xs" role="radiogroup" aria-label="Buy or sell" data-testid="type-side">
            <button
              v-for="sd in [['BUY', 'Buy'], ['SELL', 'Sell']]" :key="sd[0]" type="button" role="radio" class="px-2 py-1"
              :class="typeSide === sd[0] ? 'bg-accent-soft font-semibold text-accent' : 'text-ink-muted'" :aria-checked="typeSide === sd[0] ? 'true' : 'false'"
              :data-testid="`type-side-${sd[0].toLowerCase()}`" @click="setTypeSide(sd[0])"
            >{{ sd[1] }}</button>
          </span>
          <span v-if="tab === 'strangles' && quickDistances.length" class="flex flex-wrap items-center gap-1 text-xs" data-testid="quick-select">Quick Select
            <button
              v-for="d in quickDistances" :key="d" type="button" class="rounded border border-line px-2 py-0.5" :disabled="busy || !expiry"
              :data-testid="`quick-select-${d}`" @click="quickSelect(d)"
            >{{ d }} pt</button>
          </span>
        </div>
        <p v-if="quickError" class="text-error" data-testid="quick-select-error">{{ quickError }}</p>
        <p v-if="!expiry" data-testid="strikes-choose-expiry">Choose an expiry to see its strikes.</p>
        <p v-else-if="strikesFailed" data-testid="strikes-error">The strikes could not be read right now.</p>
        <p v-else-if="!strikesData" data-testid="strikes-loading">Reading strikes...</p>
        <p v-else-if="!strikesData.rows?.length" data-testid="strikes-reason">{{ strikesReason || 'No strikes are listed for this expiry.' }}</p>
        <template v-else>
          <p v-if="centreLine" data-testid="strikes-centre">{{ centreLine }}</p>
          <div class="grid grid-cols-[1fr_70px_1fr] border-b border-line pb-1 text-[10px] text-ink-muted" data-testid="type-head">
            <span class="text-right">Call LTP</span><span class="text-center">Strike</span><span>Put LTP</span>
          </div>
          <div
            v-for="row in strikesData.rows" :key="row.strike" class="grid h-7 grid-cols-[1fr_70px_1fr] items-center border-b border-line text-[11px] tabular-nums num"
            :class="row.is_atm ? 'bg-accent-soft font-semibold' : ''" data-testid="type-row" :data-strike="row.strike"
          >
            <label class="flex items-center justify-end gap-1 pr-1">
              <span data-testid="type-ce-ltp">{{ row.ce ? shown(row.ce.ltp) : '-' }}</span>
              <input
                v-if="tab === 'strangles' && row.ce && choicesFor(row.ce).length" type="radio" name="strangle-ce" :checked="strangleLeg('ce') === row.strike"
                :aria-label="`Call ${strikeLabel(row.strike)}`" data-testid="strangle-ce" @change="pickStrangleSide(row, 'ce')"
              />
            </label>
            <label class="flex items-center justify-center gap-1">
              <input
                v-if="tab === 'straddles'" type="radio" name="straddle" :checked="straddleStrike === row.strike" :disabled="!(row.ce && row.pe)"
                :aria-label="`Straddle ${strikeLabel(row.strike)}`" data-testid="straddle-radio" @change="pickStraddle(row)"
              />{{ strikeLabel(row.strike) }}
            </label>
            <label class="flex items-center justify-start gap-1 pl-1">
              <input
                v-if="tab === 'strangles' && row.pe && choicesFor(row.pe).length" type="radio" name="strangle-pe" :checked="strangleLeg('pe') === row.strike"
                :aria-label="`Put ${strikeLabel(row.strike)}`" data-testid="strangle-pe" @change="pickStrangleSide(row, 'pe')"
              />
              <span data-testid="type-pe-ltp">{{ row.pe ? shown(row.pe.ltp) : '-' }}</span>
            </label>
          </div>
        </template>
      </div>

      <div v-else data-testid="futures-panel">
        <p v-if="futuresFailed" data-testid="futures-error">The futures could not be read right now.</p>
        <p v-else-if="!futuresData" data-testid="futures-loading">Reading futures...</p>
        <template v-else>
          <p v-if="futuresReason" data-testid="futures-reason">{{ futuresReason }}</p>
          <!-- UI-204 / D-C32 (S-034): an "Expiry / Price" head, then one row per future - expiry, B / S, price right-aligned -->
          <div class="mt-2 flex border-b border-line pb-1 text-[10px] text-ink-muted" data-testid="futures-head"><span>Expiry</span><span class="ml-auto">Price</span></div>
          <p v-if="!futuresData.futures?.length" class="py-1 text-ink-muted" data-testid="futures-none">No future is listed for this index.</p>
          <ul data-testid="futures-list">
            <li v-for="f in futuresData.futures" :key="f.instrument_id" class="flex h-8 items-center gap-2 border-b border-line" data-testid="future-row" :data-expiry="f.expiry">
              <span>{{ expiryLabel(f.expiry) }}</span>
              <button type="button" class="h-5 w-5 rounded bg-buy-soft text-[11px] font-semibold text-buy" aria-label="Buy" title="Buy" data-testid="future-buy" :disabled="busy" @click="addFuture(f, 'BUY')">B</button>
              <button type="button" class="h-5 w-5 rounded bg-sell-soft text-[11px] font-semibold text-sell" aria-label="Sell" title="Sell" data-testid="future-sell" :disabled="busy" @click="addFuture(f, 'SELL')">S</button>
              <span class="ml-auto num" data-testid="future-ltp">{{ shown(f.ltp) }}</span>
              <span v-if="f.ltp_reason" class="text-ink-muted" data-testid="future-reason">({{ futureReasonText(f.ltp_reason) }})</span>
            </li>
          </ul>
          <p v-if="doneError" data-testid="future-add-error">{{ doneError }}</p>
          <!-- D-C32 (S-034): the section is "Synthetic Futures" with an (i); each row is the forward used for pricing that
               expiry (ADR-061 source labels kept). B / S on a synthetic future is Later: none here. -->
          <h3 class="mt-3 flex items-center gap-1 text-xs font-semibold text-ink-muted" data-testid="synthetic-title">Synthetic Futures
            <span
              class="cursor-help rounded-full border border-line px-1 text-[10px]" tabindex="0" role="img" aria-label="About synthetic futures"
              :title="`${FORWARD_LABEL}: the price a future would have for an expiry, from put-call parity or, when a chain has too few prices, estimated from spot.`"
              data-testid="synthetic-info"
            >i</span>
          </h3>
          <ul class="mt-1" data-testid="forwards-list">
            <li v-for="f in futuresData.forwards" :key="f.expiry" class="flex flex-wrap items-center gap-1 border-b border-line py-1" data-testid="forward-row" :data-expiry="f.expiry" :data-source="f.source ?? ''">
              {{ expiryLabel(f.expiry) }} <span class="ml-auto num" data-testid="forward-value">{{ shown(f.forward) }}</span>
              <span v-if="f.source === 'parity'" data-testid="forward-source">(from put-call parity)</span>
              <span v-else-if="f.source === 'spot_fallback'" data-testid="forward-source">({{ f.label ?? 'estimated from spot' }})</span>
              <span v-if="f.forward != null && f.spot_health !== 'available'" data-testid="forward-health">({{ healthSentence(f.spot_health) }})</span>
              <span v-if="f.reason" data-testid="forward-reason">({{ forwardReasonText(f.reason) }})</span>
            </li>
          </ul>
        </template>
      </div>
    </div>

    <!-- A leg by its contract: the Edit / Reprice form for a leg already in the strategy (the page's Edit opens it), and a
         second way to add one. The order and wording of its choices are the catalogue's. -->
    <div v-if="editing" class="order-first rounded border border-accent border-line p-3" data-testid="picker-by-contract">
      <h2 class="text-sm font-medium">Edit leg</h2>
      <form class="mt-2 flex flex-wrap items-end gap-2" @submit.prevent>
        <label class="flex flex-col">Type
          <select class="rounded border border-line px-1" data-testid="pick-type" :value="type" @change="onType($event.target.value)">
            <option value="">Choose</option>
            <option v-for="t in types" :key="t" :value="t">{{ t }}</option>
          </select>
        </label>
        <label v-if="type !== 'FUT'" class="flex flex-col">Strike
          <select v-model="strike" class="rounded border border-line px-1" data-testid="pick-strike" :disabled="!strikes.length">
            <option value="">Choose</option>
            <option v-for="s in strikes" :key="s" :value="s">{{ strikeLabel(s) }}</option>
          </select>
        </label>
        <label class="flex flex-col">Buy or sell
          <select v-model="action" class="rounded border border-line px-1" data-testid="pick-action">
            <option value="BUY">BUY</option>
            <option value="SELL">SELL</option>
          </select>
        </label>
        <label class="flex flex-col">Lots
          <input v-model.number="lots" class="w-16 rounded border border-line px-1" data-testid="pick-lots" inputmode="numeric" />
        </label>
        <button type="submit" data-testid="add-leg" :disabled="!canSave" class="rounded border border-line px-3 py-1" @click.prevent="save">Save leg</button>
        <button v-if="editing" type="button" data-testid="cancel-edit" class="rounded border border-line px-3 py-1" @click="resetForm">Cancel</button>
      </form>
      <p v-if="!lotsOk" class="mt-1" data-testid="lots-error">Lots must be a whole number from 1 to 10000.</p>
      <p v-if="contract" class="mt-1 text-ink-muted" data-testid="lot-size">{{ contractName({ underlying, expiry: contract.expiry, instrument_type: contract.instrument_type, strike: contract.strike }) }}, lot size {{ contract.lot_size }}</p>
    </div>

    <ul v-if="showLegList && legs.length" class="mt-3 text-sm" data-testid="leg-list">
      <li
v-for="l in legs" :key="l.id" class="flex flex-wrap items-center gap-2" data-testid="leg-row"
          :data-instrument-id="l.instrument_id" :data-action="l.action" :data-lots="l.lots" :data-entry="l.planned_entry ?? ''"
          :data-captured="l.captured_at ?? ''" :data-strike="l.strike ?? ''" :data-type="l.instrument_type" :data-expiry="l.expiry">
        <span>{{ l.action }} {{ l.lots }} lot, <span data-testid="leg-name">{{ legName(l) }}</span></span>
        <span v-if="l.planned_entry != null" data-testid="leg-entry">planned entry {{ l.planned_entry }}</span>
        <span v-if="l.planned_entry != null && l.captured_at != null" class="text-ink-muted" data-testid="leg-captured">{{ l.close_at ? capturedCaption(l.captured_at, undefined, l.close_at) : `captured ${istTime(l.captured_at)}` }}</span>
        <span v-if="l.not_live" data-testid="leg-not-live" :data-reason="l.reason_code">{{ LEG_NOT_LIVE_LABEL }}</span>
        <span v-else-if="l.planned_entry == null" data-testid="leg-unpriced">{{ NOT_CONNECTED_LABEL }}</span>
        <template v-if="l.planned_entry == null && l.reason_code === 'needs_reprice'">
          <span data-testid="leg-reprice-prompt">{{ REPRICE_PROMPT }}</span>
          <button type="button" data-testid="reprice-leg" class="underline" @click="startEdit(l)">Reprice</button>
        </template>
        <button v-if="!l.not_live" type="button" data-testid="depth-icon" :aria-label="`Market depth for ${legName(l)}`" title="Market depth" class="underline" @click="depthFor = depthFor === l.id ? null : l.id">Depth</button>
        <button type="button" data-testid="edit-leg" class="underline" @click="startEdit(l)">Edit</button>
        <button type="button" data-testid="remove-leg" class="underline" @click="remove(l)">Remove</button>
        <DepthPopup v-if="depthFor === l.id" class="w-full" :instrument-id="l.instrument_id" :title="legName(l)" @close="depthFor = null" />
      </li>
    </ul>

    <!-- UI-206 footer, kept in view at the drawer's bottom edge: the count left; Pick from Option Chain, Clear All and Done
         right. Done adds every selected contract through the same planned-entry capture; it never places an order. -->
    <div
      v-if="tab !== 'futures' && expiry" class="-mx-4 -mb-4 flex min-h-16 shrink-0 flex-wrap items-center gap-2 border-t border-line bg-surface px-4 py-2"
      data-testid="picker-footer"
    >
      <span class="font-medium" data-testid="picker-count">{{ pickedCount }} {{ pickedCount === 1 ? 'leg' : 'legs' }} selected</span>
      <button type="button" class="ml-auto text-accent underline" data-testid="picker-pick-chain" @click="view = 'ltp'">Pick from Option Chain</button>
      <button type="button" data-testid="picker-clear-all" class="rounded border border-line px-3 py-1" :disabled="!pickedCount" @click="clearAll">Clear All</button>
      <button type="button" data-testid="picker-done" class="rounded bg-accent px-3 py-1 font-semibold text-white hover:bg-accent-hover disabled:opacity-50" :disabled="busy || !pickedCount" @click="done">Done</button>
      <span v-if="doneError" class="w-full text-error" data-testid="done-error">{{ doneError }}</span>
    </div>
  </section>
</template>
