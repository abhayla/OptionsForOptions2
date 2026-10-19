<!-- W-118 (REQ-029 AC-1/AC-2/AC-6/AC-8): the Option Chain, display only. Calls | Strike | Puts for a chosen underlying and
  expiry, from the server's chain socket. Every value is shown as the server gave it (a string); the ATM row is the
  server's `atm_strike`; Change shows "-" (the feed carries no previous close, F-47). No order placement, selection or
  import here (REQ-029 AC-6; REQ-030 is a later item). Adapted for layout only from abhayla/algochanakya@bf9faf7
  frontend/src/views/OptionChainView.vue (legacy-reuse row 144: no local ATM fallback, strike logic in the backend). -->
<script setup>
import { computed, onMounted, ref, watch } from 'vue'
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

const props = defineProps({ initialUnderlying: { type: String, default: 'NIFTY' } })
const underlying = ref(props.initialUnderlying)
const expiries = ref([])
const expiry = ref('')
const catalogueFailed = ref(false)
let expirySeq = 0 // the newest expiry read wins

const { status, request, follow, clear, shown, notLive } = useChainAnswer()

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

const view = computed(() => shown())
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

    <div v-if="view && view.rows.length" class="mt-3 overflow-x-auto rounded border border-line bg-surface" data-testid="chain-card">
      <table class="min-w-full text-sm" data-testid="chain-table">
        <thead>
          <tr>
            <th :colspan="SIDE_FIELDS.length" class="px-2 py-1 text-center" data-testid="calls-head">Calls</th>
            <th class="px-2 py-1 text-center" data-testid="strike-head">Strike</th>
            <th :colspan="SIDE_FIELDS.length" class="px-2 py-1 text-center" data-testid="puts-head">Puts</th>
          </tr>
          <tr class="text-xs text-ink-muted" data-testid="chain-columns">
            <th v-for="[key, label] in SIDE_FIELDS" :key="'c' + key" class="px-2 py-1 text-right">{{ label }}</th>
            <th class="px-2 py-1 text-center">Strike</th>
            <th v-for="[key, label] in SIDE_FIELDS" :key="'p' + key" class="px-2 py-1 text-right">{{ label }}</th>
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
            <td v-for="[key] in SIDE_FIELDS" :key="'c' + key" class="px-2 py-1 text-right" :data-testid="'ce-' + key">
              {{ row.ce ? text(row.ce[key]) : VALUE_UNAVAILABLE }}<span v-if="key === 'ltp' && healthWord(row.ce)" class="ml-1 text-xs text-ink-muted" data-testid="ce-health">{{ healthWord(row.ce) }}</span>
            </td>
            <td class="px-2 py-1 text-center" data-testid="strike">{{ row.strike }}</td>
            <td v-for="[key] in SIDE_FIELDS" :key="'p' + key" class="px-2 py-1 text-right" :data-testid="'pe-' + key">
              {{ row.pe ? text(row.pe[key]) : VALUE_UNAVAILABLE }}<span v-if="key === 'ltp' && healthWord(row.pe)" class="ml-1 text-xs text-ink-muted" data-testid="pe-health">{{ healthWord(row.pe) }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
