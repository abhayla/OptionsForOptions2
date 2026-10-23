<!-- Leg picker (W-068; REQ-035 AC-8, ADR-068 items 1 and 4, ADR-020 Q185, ADR-008, ADR-012).
     Underlying -> expiry -> CE/PE/FUT -> strike (none for FUT) -> BUY/SELL -> lots -> Add. Every choice except the
     underlying list, the action and the lots comes from the catalogue API (GET /api/catalogue/...); the browser never
     talks to Zerodha. A planned entry is the string POST /api/strategies/planned-entry returns when the leg is added;
     without a live price the leg has none and is shown with the not-connected wording. No price or P&L is computed here.
     Adapted from the legacy StrategyBuilderView leg-row form shape only (client P&L, price fallbacks and the basket call
     are dropped). -->
<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import api, { NEUTRAL_PARTS } from '@/services/api'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import DepthPopup from '@/components/strategy/DepthPopup.vue'
import { contractName, istTime } from '@/lib/displayFormat'
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
  listReasonText,
  lotChoices,
  lotsValid,
  offeredStrikes,
  offeredTypes,
  selectedContract,
  shown,
} from '@/lib/legPicker'

const props = defineProps({
  // the Strategy Builder draws the ONE leg list (LegList.vue), so it passes false
  showLegList: { type: Boolean, default: true },
  legs: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:legs'])

const underlying = ref(props.legs[0]?.underlying ?? 'NIFTY')
const expiries = ref([])
const expiry = ref('')
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
const types = computed(() => offeredTypes(contracts.value))
const strikes = computed(() => offeredStrikes(contracts.value, type.value))
const contract = computed(() => selectedContract(contracts.value, type.value, strike.value))
const lotsOk = computed(() => typeof lots.value === 'number' && lotsValid(String(lots.value)))
const canSave = computed(() => !busy.value && lotsOk.value && (contract.value !== null || (editing.value !== null && !type.value && underlying.value === editing.value.underlying)))

async function loadExpiries() {
  const mine = ++seq
  expiries.value = []
  contracts.value = []
  expiry.value = ''
  type.value = ''
  strike.value = ''
  try {
    const res = await api.get(`/catalogue/${underlying.value}/expiries`)
    if (mine !== seq) return false
    expiries.value = res.data.expiries
    errorParts.value = null
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
const doneError = ref('')
const depthFor = ref(null) // the leg whose depth popup is open
let stSeq = 0
let fuSeq = 0
let timer = null

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

// A new underlying, expiry or width is a new list: the old one and its selections go before the new read starts.
watch([underlying, expiry, width], () => {
  stSeq++
  strikesData.value = null
  strikesFailed.value = false
  picked.value = {}
  cellLots.value = {}
  if (tab.value === 'strikes') loadStrikes()
})
watch(underlying, () => {
  fuSeq++
  futuresData.value = null
  futuresFailed.value = false
  if (tab.value === 'futures') loadFutures()
})
watch(tab, refreshOpenTab)

onMounted(() => {
  loadExpiries()
  timer = setInterval(refreshOpenTab, PICKER_REFRESH_MS)
})
onBeforeUnmount(() => clearInterval(timer))

/** Buy or Sell on a cell selects that contract with that side; the same button again unselects it. */
function choose(id, side) {
  const next = { ...picked.value }
  if (next[id] === side) delete next[id]
  else next[id] = side
  picked.value = next
}
const lotsOf = (id) => cellLots.value[id] ?? 1
/** Drop one selection (from the selection list): Done then no longer adds it. */
function unpick(id) {
  const { [id]: _side, ...rest } = picked.value
  const { [id]: _lots, ...restLots } = cellLots.value
  picked.value = rest
  cellLots.value = restLots
}
/** Every leg Done will add, as the user reads it: contract, side, lots. */
const selection = computed(() => Object.keys(picked.value).map((id) => {
  const c = contractByInstrumentId(contracts.value, id)
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
  if (!(await loadExpiries()) || editingId.value !== leg.id) return // cancelled or switched meanwhile
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
               checked_at: res.data.answered_at ?? null }
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
      ? { planned_entry: old.planned_entry, captured_at: old.captured_at, source: old.source, reason_code: null }
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
  const chosen = ids.map((id) => ({ id, c: contractByInstrumentId(contracts.value, id), action: picked.value[id], lots: lotsOf(id) }))
  if (chosen.some((x) => !x.c || !lotsValid(String(x.lots)))) {
    doneError.value = 'Contract details are not available for every selected contract, so nothing was added.'
    return
  }
  doneError.value = ''
  busy.value = true
  const und = underlying.value
  picked.value = {} // picks made while the entries are captured belong to the next batch
  cellLots.value = {}
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

const legName = (l) => contractName(l)
// the Builder's one leg list (LegList.vue) opens the same edit form through this, as the picker's own Edit did
defineExpose({ startEdit })
</script>

<template>
  <section class="mt-4 rounded border border-line bg-surface p-4" data-testid="leg-picker">
    <h2 class="text-sm font-medium">{{ editing ? 'Edit leg' : 'Add a leg' }}</h2>
    <!-- Compact and with its own test id: the page's ErrorMessage keeps error-what/impact/blocked/next to itself. -->
    <ErrorMessage v-if="errorParts" class="mt-2" :parts="errorParts" compact prefix="picker-error" data-testid="picker-error" />
    <form class="mt-2 flex flex-wrap items-end gap-3 text-sm" @submit.prevent>
      <label class="flex flex-col">Underlying
        <select data-testid="pick-underlying" :value="underlying" :disabled="underlyingLocked" @change="onUnderlying($event.target.value)">
          <option v-for="u in UNDERLYINGS" :key="u" :value="u">{{ u }}</option>
        </select>
      </label>
      <label class="flex flex-col">Expiry
        <select data-testid="pick-expiry" :value="expiry" @change="onExpiry($event.target.value)">
          <option value="">Choose</option>
          <option v-for="e in expiries" :key="e" :value="e">{{ e }}</option>
        </select>
      </label>
      <label class="flex flex-col">Type
        <select data-testid="pick-type" :value="type" @change="onType($event.target.value)">
          <option value="">Choose</option>
          <option v-for="t in types" :key="t" :value="t">{{ t }}</option>
        </select>
      </label>
      <label v-if="type !== 'FUT'" class="flex flex-col">Strike
        <select v-model="strike" data-testid="pick-strike" :disabled="!strikes.length">
          <option value="">Choose</option>
          <option v-for="s in strikes" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
      <label class="flex flex-col">Buy or sell
        <select v-model="action" data-testid="pick-action">
          <option value="BUY">BUY</option>
          <option value="SELL">SELL</option>
        </select>
      </label>
      <label class="flex flex-col">Lots
        <input v-model.number="lots" data-testid="pick-lots" inputmode="numeric" class="w-24" />
      </label>
      <button type="submit" data-testid="add-leg" :disabled="!canSave" class="rounded border border-line px-3 py-1" @click.prevent="save">{{ editing ? 'Save leg' : 'Add' }}</button>
      <button v-if="editing" type="button" data-testid="cancel-edit" class="rounded border border-line px-3 py-1" @click="resetForm">Cancel</button>
    </form>
    <p v-if="!lotsOk" class="mt-1 text-sm" data-testid="lots-error">Lots must be a whole number from 1 to 10000.</p>
    <p v-if="contract" class="mt-1 text-sm text-ink-muted" data-testid="lot-size">{{ contractName({ underlying, expiry: contract.expiry, instrument_type: contract.instrument_type, strike: contract.strike }) }}, lot size {{ contract.lot_size }}</p>

    <div class="mt-3 text-sm" data-testid="picker-tabs">
      <div class="flex flex-wrap items-center gap-2" role="tablist">
        <button type="button" role="tab" data-testid="tab-strikes" :aria-selected="tab === 'strikes'" :class="tab === 'strikes' ? 'font-semibold underline' : ''" @click="tab = 'strikes'">Strikes</button>
        <button type="button" role="tab" data-testid="tab-futures" :aria-selected="tab === 'futures'" :class="tab === 'futures' ? 'font-semibold underline' : ''" @click="tab = 'futures'">Futures</button>
        <label v-if="tab === 'strikes'" class="ml-4">Strikes each side
          <select v-model.number="width" data-testid="pick-width">
            <option v-for="w in STRIKE_WIDTHS" :key="w" :value="w">{{ w }}</option>
          </select>
        </label>
        <label v-if="tab === 'strikes'">Size in
          <select v-model="lotsMode" data-testid="pick-lots-mode">
            <option value="lots">Lots</option>
            <option value="quantity">Quantity</option>
          </select>
        </label>
      </div>

      <div v-if="tab === 'strikes'" data-testid="strikes-panel">
        <p v-if="!expiry" data-testid="strikes-choose-expiry">Choose an expiry to see its strikes.</p>
        <p v-else-if="strikesFailed" data-testid="strikes-error">The strikes could not be read right now.</p>
        <p v-else-if="!strikesData" data-testid="strikes-loading">Reading strikes...</p>
        <template v-else>
          <p v-if="strikesReason" data-testid="strikes-reason">{{ strikesReason }}</p>
          <p v-if="centreLine" data-testid="strikes-centre">{{ centreLine }}</p>
          <p v-if="strikesData.spot && strikesData.centre === 'LIVE_SPOT'" class="text-ink-muted" data-testid="strikes-spot">Index {{ strikesData.spot }}, read {{ istTime(strikesData.answered_at) }}</p>
          <div
            v-for="row in strikesData.rows" :key="row.strike" class="grid grid-cols-3 gap-2 border-b border-line py-1"
            :class="row.is_atm ? 'bg-amber-100 font-semibold' : ''" data-testid="strike-row" :data-strike="row.strike" :data-atm="row.is_atm ? 'true' : 'false'">
            <div class="order-2 text-center" data-testid="row-strike">{{ row.strike }}<span v-if="row.is_atm" class="ml-1" data-testid="atm-mark">ATM</span></div>
            <div v-for="side in ['ce', 'pe']" :key="side" :class="side === 'ce' ? 'order-1' : 'order-3'" :data-testid="`cell-${side}`">
              <template v-if="row[side]">
                <span class="mr-2">{{ side.toUpperCase() }} LTP <span data-testid="cell-ltp">{{ shown(row[side].ltp) }}</span></span>
                <span class="mr-2">OI <span data-testid="cell-oi">{{ shown(row[side].oi) }}</span></span>
                <span class="mr-2">IV <span data-testid="cell-iv">{{ shown(row[side].iv_percent) }}</span></span>
                <span class="mr-2">Delta <span data-testid="cell-delta">{{ shown(row[side].delta) }}</span></span>
                <template v-if="choicesFor(row[side]).length">
                  <button type="button" data-testid="cell-buy" :aria-pressed="picked[row[side].instrument_id] === 'BUY'" :class="picked[row[side].instrument_id] === 'BUY' ? 'font-bold underline' : ''" @click="choose(row[side].instrument_id, 'BUY')">Buy</button>
                  <button type="button" class="ml-1" data-testid="cell-sell" :aria-pressed="picked[row[side].instrument_id] === 'SELL'" :class="picked[row[side].instrument_id] === 'SELL' ? 'font-bold underline' : ''" @click="choose(row[side].instrument_id, 'SELL')">Sell</button>
                  <select class="ml-1" data-testid="cell-lots" :value="lotsOf(row[side].instrument_id)" @change="setLots(row[side], $event.target.value)">
                    <option v-for="o in choicesFor(row[side])" :key="o.value" :value="o.value">{{ o.label }}</option>
                  </select>
                </template>
              </template>
              <span v-else data-testid="cell-none">-</span>
            </div>
          </div>
        </template>
        <!-- The selection is its own list, whatever the strike list shows (the refresh re-centres the rows): Done adds
             exactly these. -->
        <ul v-if="pickedCount" class="mt-2" data-testid="selection-list">
          <li v-for="item in selection" :key="item.id" class="flex items-center gap-2" data-testid="selection-row" :data-instrument-id="item.id" :data-action="item.action" :data-lots="item.lots">
            <span data-testid="selection-name">{{ item.name }}</span>
            <span data-testid="selection-side">{{ item.action }}</span>
            <span data-testid="selection-lots">{{ item.lots }} lot</span>
            <button type="button" class="underline" data-testid="selection-remove" :aria-label="`Remove ${item.name}`" @click="unpick(item.id)">Remove</button>
          </li>
        </ul>
        <div v-if="expiry" class="mt-2 flex items-center gap-3">
          <button type="button" data-testid="picker-done" class="rounded border border-line px-3 py-1" :disabled="busy || !pickedCount" @click="done">Done{{ pickedCount ? ` (${pickedCount})` : '' }}</button>
          <span v-if="doneError" data-testid="done-error">{{ doneError }}</span>
        </div>
      </div>

      <div v-else data-testid="futures-panel">
        <p v-if="futuresFailed" data-testid="futures-error">The futures could not be read right now.</p>
        <p v-else-if="!futuresData" data-testid="futures-loading">Reading futures...</p>
        <template v-else>
          <p v-if="futuresReason" data-testid="futures-reason">{{ futuresReason }}</p>
          <ul data-testid="futures-list">
            <li v-for="f in futuresData.futures" :key="f.instrument_id" data-testid="future-row" :data-expiry="f.expiry">
              {{ f.expiry }} future: LTP <span data-testid="future-ltp">{{ shown(f.ltp) }}</span>
              <span v-if="f.ltp_reason" data-testid="future-reason">({{ futureReasonText(f.ltp_reason) }})</span>
            </li>
          </ul>
          <ul class="mt-2" data-testid="forwards-list">
            <li v-for="f in futuresData.forwards" :key="f.expiry" data-testid="forward-row" :data-expiry="f.expiry" :data-source="f.source ?? ''">
              {{ f.expiry }} {{ FORWARD_LABEL }}: <span data-testid="forward-value">{{ shown(f.forward) }}</span>
              <span v-if="f.source === 'parity'" data-testid="forward-source">(from put-call parity)</span>
              <span v-else-if="f.source === 'spot_fallback'" data-testid="forward-source">({{ f.label ?? 'estimated from spot' }})</span>
              <span v-if="f.reason" data-testid="forward-reason">({{ forwardReasonText(f.reason) }})</span>
            </li>
          </ul>
        </template>
      </div>
    </div>

    <ul v-if="showLegList && legs.length" class="mt-3 text-sm" data-testid="leg-list">
      <li
v-for="l in legs" :key="l.id" class="flex flex-wrap items-center gap-2" data-testid="leg-row"
          :data-instrument-id="l.instrument_id" :data-action="l.action" :data-lots="l.lots" :data-entry="l.planned_entry ?? ''"
          :data-captured="l.captured_at ?? ''" :data-strike="l.strike ?? ''" :data-type="l.instrument_type" :data-expiry="l.expiry">
        <span>{{ l.action }} {{ l.lots }} lot, <span data-testid="leg-name">{{ legName(l) }}</span></span>
        <span v-if="l.planned_entry != null" data-testid="leg-entry">planned entry {{ l.planned_entry }}</span>
        <span v-if="l.planned_entry != null && l.captured_at != null" class="text-ink-muted" data-testid="leg-captured">captured {{ istTime(l.captured_at) }}</span>
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
  </section>
</template>
