<!-- Leg picker (W-068; REQ-035 AC-8, ADR-068 items 1 and 4, ADR-020 Q185, ADR-008, ADR-012).
     Underlying -> expiry -> CE/PE/FUT -> strike (none for FUT) -> BUY/SELL -> lots -> Add. Every choice except the
     underlying list, the action and the lots comes from the catalogue API (GET /api/catalogue/...); the browser never
     talks to Zerodha. A planned entry is the string POST /api/strategies/planned-entry returns when the leg is added;
     without a live price the leg has none and is shown with the not-connected wording. No price or P&L is computed here.
     Adapted from the legacy StrategyBuilderView leg-row form shape only (client P&L, price fallbacks and the basket call
     are dropped). -->
<script setup>
import { computed, onMounted, ref } from 'vue'
import api, { NEUTRAL_PARTS } from '@/services/api'
import {
  NOT_CONNECTED_LABEL,
  UNDERLYINGS,
  instrumentId,
  lotsValid,
  offeredStrikes,
  offeredTypes,
  selectedContract,
} from '@/lib/legPicker'

const props = defineProps({ legs: { type: Array, default: () => [] } })
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

onMounted(loadExpiries)

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
      return { planned_entry: found.planned_entry, captured_at: found.captured_at, source: found.source, reason_code: null }
    }
    return { planned_entry: null, captured_at: null, source: null, reason_code: found?.reason_code ?? 'no_live_price' }
  } catch {
    return { planned_entry: null, captured_at: null, source: null, reason_code: 'capture_failed' }
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

const legName = (l) => l.symbol ?? l.instrument_id
</script>

<template>
  <section class="mt-4 rounded border border-line bg-surface p-4" data-testid="leg-picker">
    <h2 class="text-sm font-medium">{{ editing ? 'Edit leg' : 'Add a leg' }}</h2>
    <!-- Compact and with its own test id: the page's ErrorMessage keeps error-what/impact/blocked/next to itself. -->
    <p v-if="errorParts" class="mt-2 text-sm" role="alert" data-testid="picker-error">
      {{ errorParts.what_happened }} {{ errorParts.what_is_blocked }} {{ errorParts.next_action }}
    </p>
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
    <p v-if="contract" class="mt-1 text-sm text-ink-muted" data-testid="lot-size">{{ contract.symbol }}, lot size {{ contract.lot_size }}</p>

    <ul v-if="legs.length" class="mt-3 text-sm" data-testid="leg-list">
      <li v-for="l in legs" :key="l.id" class="flex flex-wrap items-center gap-2" data-testid="leg-row">
        <span>{{ l.action }} {{ l.lots }} lot, {{ legName(l) }}</span>
        <span v-if="l.planned_entry != null" data-testid="leg-entry">planned entry {{ l.planned_entry }}</span>
        <span v-else data-testid="leg-unpriced">{{ NOT_CONNECTED_LABEL }}</span>
        <button type="button" data-testid="edit-leg" class="underline" @click="startEdit(l)">Edit</button>
        <button type="button" data-testid="remove-leg" class="underline" @click="remove(l)">Remove</button>
      </li>
    </ul>
  </section>
</template>
