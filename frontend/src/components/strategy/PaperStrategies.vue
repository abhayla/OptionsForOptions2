<!-- GC-BP step 6 (ADR-201 (2); REQ-109 AC-2, AC-3, AC-4), rebuilt by GC-TP step 4b (ADR-207; RD-121; Sensibull Positions 050-053
     and Draft Portfolios 090-092): the user's paper strategies from GET /paper/strategies (newest first) - a totals strip
     (Total P&L, Booked, Unbooked, Total Decay), a "Show closed positions" toggle (off), and per strategy a card with
     "N of M positions", Total / Booked / Unbooked and one row per contract (Qty, Avg, LTP, Booked, Unbooked, P&L) with
     Open in Builder, Add orders, Exit (n) and Stops. Shown in the Positions page's Paper tab and the builder's Tracked tab.
     The browser computes no money (ADR-008): every figure is the server's text. A failed or unreadable read shows no figure.
     Nothing here reaches Execute (REQ-109 AC-3): an exit is a paper order and sends nothing to Zerodha. -->
<template>
  <section class="rounded-lg border-2 border-dashed border-accent text-sm" :class="compact ? 'p-2' : 'p-3'" data-testid="paper-strategies">
    <p class="mb-2 rounded bg-accent-soft px-2 py-1 text-xs font-semibold text-accent" data-testid="paper-mode-header">Paper mode</p>
    <p class="rounded bg-amber-50 px-2 py-1 font-medium" data-testid="paper-banner">{{ BANNER }}</p>
    <p v-if="loading" class="mt-2" data-testid="paper-loading">Reading your paper strategies.</p>
    <ErrorMessage v-else-if="errorParts" class="mt-2" :parts="errorParts" compact prefix="paper-error" />
    <p v-else-if="!items.length" class="mt-2" data-testid="paper-empty">{{ EMPTY }}</p>
    <template v-else>
      <!-- Sensibull 050-053: the totals sit above the rows. A figure the reply omits is a dash with the server's reason. -->
      <dl v-if="totals && !compact" class="mt-2 flex flex-wrap gap-6 rounded bg-surface-muted px-3 py-2" data-testid="paper-totals">
        <div v-for="f in totalFigures" :key="f.id" class="text-right">
          <dt class="text-xs text-ink-muted">{{ f.label }}</dt>
          <dd class="text-lg font-semibold" :class="toneOf(totals[f.field])" :data-testid="`totals-${f.id}`">{{ pnlText(totals[f.field]) }}</dd>
          <p v-if="totals[f.field] === null && totals[f.reason]" class="text-xs text-ink-muted" :data-testid="f.reasonId">{{ totals[f.reason] }}</p>
        </div>
      </dl>
      <label v-if="!compact" class="mt-2 flex items-center gap-2"><input v-model="showClosed" type="checkbox" data-testid="show-closed" /> {{ SHOW_CLOSED_LABEL }}</label>
      <p v-if="!shown.length" class="mt-2" data-testid="paper-all-closed">{{ ALL_CLOSED_TEXT }}</p>
      <!-- GC-UI 6b D-C14 (ADR-201 (2); S-118): the builder's Paper tab is a compact list - name, positions count, the server's paper total
           (a dash and the reason when there is none), a link to Positions > Paper for that strategy. The full cards stay on Positions. -->
      <ul v-if="compact" class="mt-2" data-testid="paper-compact">
        <li v-for="g in shown" :key="g.id" class="border-b border-line py-2" data-testid="paper-compact-row" :data-strategy="g.id">
          <p v-if="!g.readable" data-testid="paper-unreadable">{{ g.text }}</p>
          <RouterLink v-else :to="{ path: '/positions/current-positions', query: { tab: 'paper', strategy: String(g.id) } }" class="flex items-center gap-2" :data-testid="`paper-compact-link-${g.id}`">
            <span class="min-w-0 flex-1">
              <span class="block truncate font-medium" data-testid="paper-group-name">{{ g.name ?? `Strategy ${g.id}` }}</span>
              <span class="block text-xs text-ink-muted" data-testid="paper-compact-legs">{{ g.positionCount }} {{ g.positionCount === 1 ? 'leg' : 'legs' }}</span>
            </span>
            <span class="shrink-0 text-right">
              <span class="block font-semibold" :class="toneOf(g.total)" data-testid="paper-total">{{ g.total ?? '-' }}</span>
              <span v-if="g.total === null" class="block text-xs text-ink-muted" data-testid="paper-compact-reason">{{ g.stateText || NO_TOTAL }}</span>
            </span>
          </RouterLink>
        </li>
      </ul>
      <template v-else>
        <div v-for="g in shown" :key="g.id" class="mt-3 rounded-lg border border-line p-3" data-testid="paper-group" :data-strategy="g.id">
          <p v-if="!g.readable" data-testid="paper-unreadable">{{ g.text }}</p>
          <template v-else>
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 class="font-semibold" data-testid="paper-group-name">{{ g.name ?? `Strategy ${g.id}` }}</h2>
                <span class="text-ink-muted" data-testid="paper-group-underlying">{{ g.underlying }}</span>
                <p class="text-xs text-ink-muted" data-testid="paper-count">{{ g.openCount }} of {{ g.positionCount }} positions</p>
              </div>
              <dl class="flex flex-wrap gap-6" data-testid="paper-figures">
                <div v-for="f in figures" :key="f.field" class="text-right">
                  <dt class="text-xs text-ink-muted" data-testid="paper-figure-label">{{ f.label }}</dt>
                  <dd class="text-lg font-semibold" :class="toneOf(g[f.field])" :data-testid="f.testid">{{ pnlText(g[f.field]) }}</dd>
                </div>
              </dl>
            </div>
            <p v-if="g.stateText" class="mt-1" data-testid="paper-state">{{ g.stateText }}</p>
            <div class="mt-2 flex gap-3">
              <table v-if="g.positions.length" class="w-full min-w-0 flex-1 text-left">
                <thead>
                  <tr><th class="w-6"><span class="sr-only">Select</span></th><th>Instrument</th><th>Qty</th><th>Avg</th><th>LTP</th><th>Booked</th><th>Unbooked</th><th>P&amp;L</th></tr>
                </thead>
                <tbody>
                  <tr v-for="p in g.positions" :key="p.key" data-testid="paper-leg" :data-leg="p.contractId">
                    <td>
                      <input v-if="canExit(p)" type="checkbox" :checked="isTicked(g.id, p.contractId)" :data-testid="`select-leg-${g.id}-${p.contractId}`" :aria-label="`Select ${p.name}`" @change="tick(g.id, p.contractId, $event.target.checked)" />
                    </td>
                    <td data-testid="paper-instrument"><span v-if="p.side" class="mr-1 rounded bg-surface-muted px-1 font-semibold">{{ p.side }}</span> <span>{{ p.name }}</span></td>
                    <td data-testid="paper-qty">{{ p.qtyText }}</td>
                    <td data-testid="paper-avg">{{ pnlText(p.averageText) }}</td>
                    <td data-testid="paper-ltp">{{ pnlText(p.ltpText) }}</td>
                    <td data-testid="paper-leg-booked">{{ pnlText(p.booked) }}</td>
                    <td data-testid="paper-leg-unbooked" :class="toneOf(p.unbooked)">{{ pnlText(p.unbooked) }}</td>
                    <td data-testid="paper-leg-pnl" :class="toneOf(p.total)">{{ pnlText(p.total) }}</td>
                  </tr>
                </tbody>
              </table>
              <!-- D-C50 / Sensibull 090-092: the action column. No Convert To Real Trades (ADR-165). Add orders opens the builder on
                   the strategy, where its paper position is Drafts Mode (GC-TP step 3c). -->
              <div class="flex w-36 shrink-0 flex-col gap-2" data-testid="paper-actions">
                <RouterLink :to="builderLink(g)" class="rounded border border-line px-2 py-1 text-center text-accent" data-testid="paper-open-builder">Open in Builder</RouterLink>
                <RouterLink :to="builderLink(g)" class="rounded border border-line px-2 py-1 text-center text-accent" data-testid="paper-add-orders">Add orders</RouterLink>
                <button v-if="g.openCount" type="button" class="rounded border border-line px-2 py-1" :aria-expanded="!!stopsOpen[g.id]" :data-testid="`stops-open-${g.id}`" @click="stopsOpen = { ...stopsOpen, [g.id]: !stopsOpen[g.id] }">Stops</button>
                <button v-if="g.openCount" type="button" class="rounded border border-line px-2 py-1" :data-testid="`exit-selected-${g.id}`" :disabled="busy || !tickedOpen(g).length" @click="ask(g, tickedOpen(g))">Exit ({{ tickedOpen(g).length }})</button>
              </div>
            </div>
            <div v-if="confirm && confirm.id === g.id" class="mt-2 rounded bg-amber-50 p-2" role="group" aria-label="Confirm paper exit">
              <p data-testid="exit-confirm-text">Paper exit - no order is sent. Exit {{ confirm.names }} at the current paper price?</p>
              <button type="button" class="mr-2 rounded border border-line px-3 py-1" data-testid="exit-confirm" :disabled="busy" @click="doExit">Confirm paper exit</button>
              <button type="button" class="rounded border border-line px-3 py-1" data-testid="exit-cancel" :disabled="busy" @click="cancelExit(g.id)">Cancel</button>
            </div>
            <p v-if="exitErrors[g.id]" class="mt-2 text-red-700" role="alert" data-testid="paper-exit-error">{{ exitErrors[g.id] }}</p>
            <PaperStops v-if="stopsOpen[g.id]" :strategy-id="g.id" :underlying="g.underlying" :legs="stopLegs(g)" />
          </template>
        </div>
      </template>
    </template>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import api, { NEUTRAL_ERROR, NEUTRAL_PARTS } from '@/services/api'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import PaperStops from '@/components/strategy/PaperStops.vue'
import { ALL_CLOSED_TEXT, PAPER_NO_FIGURE, SHOW_CLOSED_LABEL, exitOrdersFor, readPaperList, visibleGroups } from '@/lib/paperList'
import { usePaperRefresh } from '@/lib/usePaperRefresh'
import { signOf } from '@/lib/chartCard'

defineProps({ compact: { type: Boolean, default: false } })
const NO_TOTAL = 'No paper total yet: prices are not live'
const BANNER = 'Paper trades - not real money'
const EMPTY = 'No paper strategies yet. Build a strategy, then press Add to Paper.'
const figures = [
  { field: 'total', label: 'Total P&L', testid: 'paper-total' },
  { field: 'unbooked', label: 'Unbooked P&L', testid: 'paper-unbooked' },
  { field: 'booked', label: 'Booked P&L', testid: 'paper-booked' },
]
const totalFigures = [
  { id: 'total', field: 'total', reason: 'totalReason', reasonId: 'totals-reason', label: 'Total P&L' },
  { id: 'booked', field: 'booked', reason: 'totalReason', reasonId: 'totals-booked-reason', label: 'Booked P&L' },
  { id: 'unbooked', field: 'unbooked', reason: 'totalReason', reasonId: 'totals-unbooked-reason', label: 'Unbooked P&L' },
  { id: 'decay', field: 'decay', reason: 'decayReason', reasonId: 'totals-decay-reason', label: 'Total Decay' },
]
// the server's text, printed as sent (a missing figure is a dash); the colour follows the server's sign, read from its text
const pnlText = (v) => (v === null || v === undefined ? PAPER_NO_FIGURE : v)
const toneOf = (v) => ({ profit: 'text-profit', loss: 'text-loss' })[signOf(String(v ?? '').replace(/,/g, '').replace('−', '-'))] ?? ''
const builderLink = (g) => ({ path: '/strategy/builder', query: { strategy: String(g.id) } })

const items = ref(null)
const totals = ref(null)
const showClosed = ref(false)
const shown = computed(() => visibleGroups(items.value ?? [], showClosed.value))
const errorParts = ref(null)
const loading = ref(true)
const stopsOpen = ref({})
// R-10: a Stop row for each OPEN contract, keyed by the contract id the reply carries (a digit string sent as is)
const stopLegs = (g) => g.positions.filter((p) => p.open).map((p) => ({ index: p.contractId, label: p.name, contractId: String(p.contractId) }))

const ticks = ref({})
const isTicked = (id, c) => !!ticks.value[id]?.includes(c)
function tick(id, c, on) {
  const rest = (ticks.value[id] ?? []).filter((x) => x !== c)
  ticks.value = { ...ticks.value, [id]: on ? [...rest, c] : rest }
}
const canExit = (p) => p.open && p.exitPrice !== null // no live price, no price to exit at
const tickedOpen = (g) => g.positions.filter((p) => canExit(p) && isTicked(g.id, p.contractId))

const confirm = ref(null)
const busy = ref(false)
const exitErrors = ref({})

function show(data) {
  const read = readPaperList(data)
  if (read === null) {
    items.value = null
    totals.value = null
    errorParts.value = NEUTRAL_PARTS
  } else {
    const before = items.value
    items.value = read.groups
    totals.value = read.totals
    errorParts.value = null
    settle(before, items.value)
  }
  loading.value = false
}
// a failed read shows no figure: the old list is dropped, never left on screen as if current
function fail(e) {
  items.value = null
  totals.value = null
  confirm.value = null
  exitErrors.value = {}
  errorParts.value = e?.parts ?? NEUTRAL_PARTS
  loading.value = false
}

const { refresh, refreshNow } = usePaperRefresh({
  key: () => 'list',
  read: async () => (await api.get('/paper/strategies')).data,
  onData: show,
  onError: fail,
})
onMounted(refresh)

// what a group's contracts look like to an exit (contract and net units); a read that changes it ends the exit's open question
const sig = (g) => (g && g.readable ? g.positions.map((p) => `${p.contractId}:${p.units}`).join(',') : null)
function settle(before, now) {
  const c = confirm.value
  if (c) {
    const g = now.find((x) => x.id === c.id)
    const stillOpen = g && g.readable && c.units.every((u) => g.positions.some((p) => p.contractId === u.id && p.units === u.units))
    if (!stillOpen) confirm.value = null
  }
  const kept = {}
  for (const [id, text] of Object.entries(exitErrors.value)) {
    const was = (before ?? []).find((x) => String(x.id) === id)
    const is = now.find((x) => String(x.id) === id)
    if (text && was && is && sig(was) === sig(is)) kept[id] = text // the group did not move: the refusal still stands
  }
  exitErrors.value = kept
}
function cancelExit(id) {
  confirm.value = null
  exitErrors.value = { ...exitErrors.value, [id]: '' }
}

function ask(g, rows) {
  if (busy.value || !rows.length) return
  confirm.value = { id: g.id, rows, units: rows.map((p) => ({ id: p.contractId, units: p.units })), names: rows.map((p) => p.name).join(', ') }
}

async function doExit() {
  const c = confirm.value
  if (!c || busy.value) return
  const orders = exitOrdersFor(c.rows)
  if (orders === null) return
  busy.value = true
  exitErrors.value = { ...exitErrors.value, [c.id]: '' }
  try {
    await api.post(`/paper/strategies/${c.id}/orders`, { orders })
    confirm.value = null
    ticks.value = { ...ticks.value, [c.id]: [] }
    refreshNow()
  } catch (e) {
    confirm.value = null
    exitErrors.value = { ...exitErrors.value, [c.id]: e?.parts?.what_happened || NEUTRAL_ERROR }
  } finally {
    busy.value = false
  }
}
</script>
