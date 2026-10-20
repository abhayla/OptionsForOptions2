<!-- W-118 (REQ-029 AC-1/AC-2/AC-6/AC-8) + W-120 (REQ-030): the Option Chain. Display (W-118), plus leg selection: a selector
  and explicit Buy / Sell per Call and Put cell, a persistent Selected Legs summary, and "Add Selected (N)" which opens the
  Strategy Builder with exactly those legs (never an order, ADR-002). The selection lives in the chainSelection store, so it
  persists across expiries (AC-10). The W-118 text follows; its "no selection" now holds only for REQ-029 itself.
  W-118: the Option Chain, display only. Calls | Strike | Puts for a chosen underlying and
  expiry, from the server's chain socket. Every value is shown as the server gave it (a string); the ATM row is the
  server's `atm_strike`; Change shows "-" (the feed carries no previous close, F-47). No order placement, selection or
  import here (REQ-029 AC-6; REQ-030 is a later item). Adapted for layout only from abhayla/algochanakya@bf9faf7
  frontend/src/views/OptionChainView.vue (legacy-reuse row 144: no local ATM fallback, strike logic in the backend). -->
<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ACTIONS, contractOf, useChainSelection } from '@/stores/chainSelection'
import { UNAVAILABLE_LABEL, isPermitted, reasonLine } from '@/lib/chainUnavailable'
import api from '@/services/api'
import { NOT_LIVE_LABEL, VALUE_UNAVAILABLE, chainRequest, daysLeft, useChainAnswer } from '@/composables/useChainLive'

const UNDERLYINGS = ['NIFTY', 'SENSEX']
const SIDE_FIELDS = [['ltp', 'LTP'], ['change', 'Change'], ['oi', 'OI'], ['volume', 'Volume']]
const ROWS_MISSING_LABELS = {
  SPOT_MISSING: 'The underlying price is missing, so no strikes can be chosen yet.',
  EXPIRY_UNKNOWN: 'This expiry is not in the catalogue.',
  CATALOGUE_EMPTY: 'The catalogue lists no options for this expiry.',
  CATALOGUE_UNREADABLE: 'The catalogue could not be read.',
}

const UNDO_MS = 8000 // how long the short Undo (REQ-030 AC-15) stays offered
const BUILDER_ROUTE = 'strategies-strategy-builder'
const ACTION_LABELS = { BUY: 'Buy', SELL: 'Sell' }

const props = defineProps({ initialUnderlying: { type: String, default: 'NIFTY' } })
const underlying = ref(props.initialUnderlying)
const expiries = ref([])
const expiry = ref('')
const catalogueFailed = ref(false)
let expirySeq = 0 // the newest expiry read wins

const { status, request, follow, clear, refresh, shown, notLive } = useChainAnswer()

async function loadExpiries() {
  const mine = ++expirySeq
  expiries.value = []
  expiry.value = ''
  catalogueFailed.value = false
  try {
    const res = await api.get(`/catalogue/${underlying.value}/expiries`)
    if (mine !== expirySeq) return
    expiries.value = [...res.data.expiries].sort()
    expiry.value = expiries.value[0] ?? ''
    if (!expiry.value) catalogueFailed.value = true
  } catch {
    if (mine === expirySeq) catalogueFailed.value = true
  }
}

onMounted(loadExpiries)
// A changed choice clears the old answer at once (sync flush), before the expiries load: no number from one choice is
// ever shown under another (REQ-049 AC-4).
watch(underlying, () => {
  clear()
  loadExpiries()
}, { flush: 'sync' })
watch(expiry, (value) => {
  if (value) follow(chainRequest(underlying.value, value))
  else clear()
}, { flush: 'sync' })

const router = useRouter()
const selection = useChainSelection()
const legs = computed(() => selection.legsOf(underlying.value))
const pending = computed(() => selection.pendingOf(underlying.value))
const picked = computed(() => selection.forUnderlying(underlying.value))
const expiriesPicked = computed(() => selection.expiriesOf(underlying.value))
const askExpiries = ref(false) // the multi-expiry notice is open (AC-6)
const summary = ref(null)
let undoTimer = null

const contractFor = (row, type) => contractOf(underlying.value, expiry.value, row.strike, type, type === 'CE' ? row.ce : row.pe)
const entriesOf = (cell) => (cell ? picked.value.filter((e) => e.instrument_id === cell.instrument_id) : [])
const isTicked = (cell) => entriesOf(cell).length > 0
const isChosen = (cell, action) => entriesOf(cell).some((e) => e.action === action)
const tick = (row, type) => selection.toggleContract(contractFor(row, type))
const choose = (row, type, action) => selection.chooseAction(contractFor(row, type), action)
const canAdd = computed(() => legs.value.length > 0 && pending.value.length === 0)
const contractName = (e) => `${e.underlying} ${e.expiry} ${e.strike} ${e.type}`

function openBuilder() {
  askExpiries.value = false
  router?.push({ name: BUILDER_ROUTE, query: { draft: JSON.stringify(selection.draftOf(underlying.value)) } })
}
function addSelected() {
  if (!canAdd.value) return
  if (expiriesPicked.value.length > 1) askExpiries.value = true
  else openBuilder()
}
function reviewSelection() {
  askExpiries.value = false
  summary.value?.scrollIntoView?.({ block: 'nearest' })
}
function removeLeg(id) {
  selection.remove(id)
  clearTimeout(undoTimer)
  undoTimer = setTimeout(() => selection.dismissUndo(), UNDO_MS)
}
watch(() => legs.value.map((e) => e.expiry).join(), () => (askExpiries.value = false))
onBeforeUnmount(() => clearTimeout(undoTimer))

const view = computed(() => shown())
// REQ-030 AC-16: every chain answer tells the selection which of its contracts Zerodha permits right now.
const cellsOf = (v) => (v ? v.rows.flatMap((r) => [r.ce, r.pe]).filter(Boolean) : [])
const anyUnavailable = computed(() => cellsOf(view.value).some((c) => !isPermitted(c)))
watch(view, (v) => selection.syncPermissions(cellsOf(v)), { immediate: true })
const rowsMissing = computed(() => (view.value?.rows_missing ? ROWS_MISSING_LABELS[view.value.rows_missing] : ''))
const days = computed(() => (expiry.value ? daysLeft(expiry.value) : null))
const spotTime = computed(() => {
  const at = (view.value ?? null)?.spot_at ?? null
  return at ? new Date(at).toLocaleTimeString() : ''
})

const text = (v) => (typeof v === 'string' || typeof v === 'number' ? String(v) : VALUE_UNAVAILABLE)
const healthWord = (cell) => (cell && cell.health && cell.health !== 'available' ? cell.health : '')
const isAtm = (row) => view.value?.atm_strike != null && row.strike === view.value.atm_strike
</script>

<template>
  <section data-testid="option-chain-page">
    <p class="text-xs text-ink-muted">Market</p>
    <h1 class="text-xl font-semibold" data-testid="page-title">Option Chain</h1>

    <div class="mt-3 flex flex-wrap items-end gap-3" data-testid="chain-header">
      <label class="text-sm">
        Underlying
        <select v-model="underlying" class="ml-1 rounded border border-line bg-surface px-2 py-1" data-testid="underlying-select">
          <option v-for="u in UNDERLYINGS" :key="u" :value="u">{{ u }}</option>
        </select>
      </label>
      <label class="text-sm">
        Expiry
        <select v-model="expiry" class="ml-1 rounded border border-line bg-surface px-2 py-1" data-testid="expiry-select">
          <option v-for="e in expiries" :key="e" :value="e">{{ e }}</option>
        </select>
      </label>
      <span v-if="days !== null" class="text-sm text-ink-muted" data-testid="days-left">{{ days }} days left</span>
      <p class="text-sm" data-testid="spot-line">
        <span class="text-ink-muted">{{ underlying }}</span>
        <span class="ml-1 font-semibold" data-testid="spot">{{ view ? text(view.spot) : VALUE_UNAVAILABLE }}</span>
        <span v-if="spotTime" class="ml-1 text-ink-muted" data-testid="spot-time">as of {{ spotTime }}</span>
        <span v-if="view && view.spot_health && view.spot_health !== 'available'" class="ml-1 text-ink-muted" data-testid="spot-health">{{ view.spot_health }}</span>
      </p>
      <span class="text-xs text-ink-muted" data-testid="socket-status">{{ status }}</span>
    </div>

    <p v-if="catalogueFailed" class="mt-3 text-sm" data-testid="catalogue-unreadable">The expiries could not be read, so no chain is shown.</p>
    <p v-else-if="notLive()" class="mt-3 text-sm" data-testid="not-live">{{ NOT_LIVE_LABEL }}</p>
    <p v-else-if="!view && request" class="mt-3 text-sm text-ink-muted" data-testid="chain-waiting">Waiting for live data.</p>
    <p v-if="rowsMissing" class="mt-3 text-sm" data-testid="rows-missing">{{ rowsMissing }}</p>

    <p v-if="anyUnavailable" class="mt-3 text-sm" data-testid="unavailable-notice">
      Some contracts are currently unavailable on Zerodha and cannot be added.
    </p>
    <p v-if="view && view.rows.length" class="mt-3 text-sm">
      <button type="button" class="rounded border border-line px-2 text-xs" data-testid="chain-refresh" @click="refresh">Refresh</button>
    </p>

    <div v-if="view && view.rows.length" class="mt-3 overflow-x-auto rounded border border-line bg-surface" data-testid="chain-card">
      <table class="min-w-full text-sm" data-testid="chain-table">
        <thead>
          <tr>
            <th class="px-1 py-1" data-testid="ce-select-head"></th>
            <th :colspan="SIDE_FIELDS.length" class="px-2 py-1 text-center" data-testid="calls-head">Calls</th>
            <th class="px-2 py-1 text-center" data-testid="strike-head">Strike</th>
            <th :colspan="SIDE_FIELDS.length" class="px-2 py-1 text-center" data-testid="puts-head">Puts</th>
            <th class="px-1 py-1" data-testid="pe-select-head"></th>
          </tr>
          <tr class="text-xs text-ink-muted" data-testid="chain-columns">
            <th class="px-1 py-1"></th>
            <th v-for="[key, label] in SIDE_FIELDS" :key="'c' + key" class="px-2 py-1 text-right">{{ label }}</th>
            <th class="px-2 py-1 text-center">Strike</th>
            <th v-for="[key, label] in SIDE_FIELDS" :key="'p' + key" class="px-2 py-1 text-right">{{ label }}</th>
            <th class="px-1 py-1"></th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in view.rows"
            :key="row.strike"
            :class="{ 'bg-accent-soft font-semibold': isAtm(row) }"
            :data-atm="isAtm(row) ? 'true' : 'false'"
            data-testid="chain-row"
          >
            <td class="whitespace-nowrap px-1 py-1" data-testid="sel-ce">
              <template v-if="row.ce">
                <input type="checkbox" :checked="isTicked(row.ce)" :disabled="!isPermitted(row.ce)" :aria-label="'Select CE ' + row.strike" data-testid="select-ce" @change="tick(row, 'CE')" />
                <button v-for="a in ACTIONS" :key="a" type="button" class="ml-1 rounded border border-line px-1 text-xs" :class="{ 'bg-accent-soft font-semibold': isChosen(row.ce, a) }" :aria-pressed="isChosen(row.ce, a)" :disabled="!isPermitted(row.ce)" :data-testid="a.toLowerCase() + '-ce'" @click="choose(row, 'CE', a)">{{ ACTION_LABELS[a] }}</button>
                <p v-if="!isPermitted(row.ce)" class="block max-w-[12rem] whitespace-normal text-xs" data-testid="unavailable-ce">
                  <span class="font-medium" data-testid="unavailable-label-ce">{{ UNAVAILABLE_LABEL }}</span>
                  <span data-testid="unavailable-reason-ce">{{ reasonLine(row.ce) }}</span>
                </p>
              </template>
            </td>
            <td v-for="[key] in SIDE_FIELDS" :key="'c' + key" class="px-2 py-1 text-right" :data-testid="'ce-' + key">
              {{ row.ce ? text(row.ce[key]) : VALUE_UNAVAILABLE }}<span v-if="key === 'ltp' && healthWord(row.ce)" class="ml-1 text-xs text-ink-muted" data-testid="ce-health">{{ healthWord(row.ce) }}</span>
            </td>
            <td class="px-2 py-1 text-center" data-testid="strike">{{ row.strike }}</td>
            <td v-for="[key] in SIDE_FIELDS" :key="'p' + key" class="px-2 py-1 text-right" :data-testid="'pe-' + key">
              {{ row.pe ? text(row.pe[key]) : VALUE_UNAVAILABLE }}<span v-if="key === 'ltp' && healthWord(row.pe)" class="ml-1 text-xs text-ink-muted" data-testid="pe-health">{{ healthWord(row.pe) }}</span>
            </td>
            <td class="whitespace-nowrap px-1 py-1" data-testid="sel-pe">
              <template v-if="row.pe">
                <input type="checkbox" :checked="isTicked(row.pe)" :disabled="!isPermitted(row.pe)" :aria-label="'Select PE ' + row.strike" data-testid="select-pe" @change="tick(row, 'PE')" />
                <button v-for="a in ACTIONS" :key="a" type="button" class="ml-1 rounded border border-line px-1 text-xs" :class="{ 'bg-accent-soft font-semibold': isChosen(row.pe, a) }" :aria-pressed="isChosen(row.pe, a)" :disabled="!isPermitted(row.pe)" :data-testid="a.toLowerCase() + '-pe'" @click="choose(row, 'PE', a)">{{ ACTION_LABELS[a] }}</button>
                <p v-if="!isPermitted(row.pe)" class="block max-w-[12rem] whitespace-normal text-xs" data-testid="unavailable-pe">
                  <span class="font-medium" data-testid="unavailable-label-pe">{{ UNAVAILABLE_LABEL }}</span>
                  <span data-testid="unavailable-reason-pe">{{ reasonLine(row.pe) }}</span>
                </p>
              </template>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="picked.length" ref="summary" class="sticky bottom-0 mt-3 rounded border border-line bg-surface p-3" data-testid="selected-legs">
      <h2 class="text-sm font-medium">Selected Legs</h2>
      <ul class="mt-1 text-sm">
        <li v-for="e in picked" :key="e.id" class="flex flex-wrap items-center gap-2" data-testid="selected-leg" :data-action="e.action ?? ''">
          <span data-testid="selected-leg-name">{{ contractName(e) }}</span>
          <span v-if="e.permitted !== true" class="text-xs" data-testid="selected-leg-unavailable">{{ UNAVAILABLE_LABEL }}. {{ reasonLine(e) }} It will not be added.</span>
          <button v-for="a in ACTIONS" :key="a" type="button" class="rounded border border-line px-1 text-xs" :class="{ 'bg-accent-soft font-semibold': e.action === a }" :aria-pressed="e.action === a" :data-testid="'leg-' + a.toLowerCase()" :disabled="e.permitted !== true" @click="selection.chooseAction(e, a)">{{ ACTION_LABELS[a] }}</button>
          <template v-if="e.action && e.permitted === true">
            <button type="button" class="rounded border border-line px-2 text-xs" aria-label="Fewer lots" data-testid="lots-minus" @click="selection.stepLots(e.id, -1)">-</button>
            <span data-testid="leg-lots">{{ e.lots }}</span>
            <button type="button" class="rounded border border-line px-2 text-xs" aria-label="More lots" data-testid="lots-plus" @click="selection.stepLots(e.id, 1)">+</button>
          </template>
          <button type="button" class="rounded border border-line px-1 text-xs" :aria-label="'Remove ' + contractName(e)" data-testid="leg-remove" @click="removeLeg(e.id)">Remove</button>
        </li>
      </ul>
      <p v-if="selection.removed" class="mt-1 text-sm" data-testid="undo-line">
        <button type="button" class="underline" data-testid="undo" @click="selection.undo()">Undo</button>
      </p>
      <div v-if="askExpiries" class="mt-2 rounded border border-line p-2 text-sm" data-testid="multi-expiry">
        <p>Multiple expiries detected — Continue / Review Selection</p>
        <button type="button" class="mr-2 rounded border border-line px-2" data-testid="multi-expiry-continue" @click="openBuilder">Continue</button>
        <button type="button" class="rounded border border-line px-2" data-testid="multi-expiry-review" @click="reviewSelection">Review Selection</button>
      </div>
      <button type="button" class="mt-2 rounded border border-line px-3 py-1 text-sm font-medium" :disabled="!canAdd" data-testid="add-selected" @click="addSelected">Add Selected ({{ legs.length }})</button>
    </div>
  </section>
</template>
