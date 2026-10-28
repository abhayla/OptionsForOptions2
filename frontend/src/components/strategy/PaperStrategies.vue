<!-- GC-BP step 6 (ADR-201 (2); REQ-109 AC-2, AC-3, AC-4): every paper-tracked strategy of the user as a group with its legs
     (entry, LTP, exit), the server's total / booked / unbooked, an Open in Builder link and a confirmed Paper exit. Shown in
     the Positions page's Paper tab and the builder's Tracked tab. Layout after Sensibull S-090..092 (Draft Portfolio).
     The browser computes no money (ADR-008): every figure is the server's string re-grouped; no sum across legs or
     strategies. A failed or unreadable read shows no figure. Nothing here reaches Execute (REQ-109 AC-3): the exit is a
     paper exit and sends no order. -->
<template>
  <section :class="['text-sm', compact ? '' : 'rounded-lg border-2 border-dashed border-accent p-3']" data-testid="paper-strategies">
    <p class="rounded bg-amber-50 px-2 py-1 font-medium" data-testid="paper-banner">{{ BANNER }}</p>
    <p v-if="loading" class="mt-2" data-testid="paper-loading">Reading your paper strategies.</p>
    <ErrorMessage v-else-if="errorParts" class="mt-2" :parts="errorParts" compact prefix="paper-error" />
    <p v-else-if="!items.length" class="mt-2" data-testid="paper-empty">{{ EMPTY }}</p>
    <!-- GC-UI 6b D-C14 (ADR-201 (2); S-118): the builder's Paper tab is a compact list - name, legs count, the server's paper total
         (a dash and the reason when there is none), a link to Positions > Paper for that strategy. The full cards stay on Positions. -->
    <ul v-else-if="compact" class="mt-2" data-testid="paper-compact">
      <li v-for="g in items" :key="g.id" class="border-b border-line py-2" data-testid="paper-compact-row" :data-strategy="g.id">
        <p v-if="!g.readable" data-testid="paper-unreadable">{{ g.text }}</p>
        <RouterLink v-else :to="{ path: '/positions/current-positions', query: { tab: 'paper', strategy: String(g.id) } }" class="flex items-center gap-2" :data-testid="`paper-compact-link-${g.id}`">
          <span class="min-w-0 flex-1">
            <span class="block truncate font-medium" data-testid="paper-group-name">{{ g.name ?? `Strategy ${g.id}` }}</span>
            <span class="block text-xs text-ink-muted" data-testid="paper-compact-legs">{{ g.legs.length }} {{ g.legs.length === 1 ? 'leg' : 'legs' }}</span>
          </span>
          <span class="shrink-0 text-right">
            <span class="block font-semibold" data-testid="paper-total">{{ g.total ?? '-' }}</span>
            <span v-if="g.total === null" class="block text-xs text-ink-muted" data-testid="paper-compact-reason">{{ g.stateText || NO_TOTAL }}</span>
          </span>
        </RouterLink>
      </li>
    </ul>
    <template v-else>
      <div v-for="g in items" :key="g.id" class="mt-3 rounded-lg border border-line p-3" data-testid="paper-group" :data-strategy="g.id">
        <p v-if="!g.readable" data-testid="paper-unreadable">{{ g.text }}</p>
        <template v-else>
          <!-- GC-UI 6d D-C44 (S-090): name, "N of N positions" (open of all), then Total / Unbooked / Booked P&L as labelled columns -->
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 class="font-semibold" data-testid="paper-group-name">{{ g.name ?? `Strategy ${g.id}` }}</h2>
              <span class="text-ink-muted" data-testid="paper-group-underlying">{{ g.underlying }}</span>
              <p class="text-xs text-ink-muted" data-testid="paper-count">{{ openLegs(g).length }} of {{ g.legs.length }} positions</p>
            </div>
            <dl class="flex flex-wrap gap-6" data-testid="paper-figures">
              <div v-for="f in figures" :key="f.field" class="text-right">
                <dt class="text-xs text-ink-muted" data-testid="paper-figure-label">{{ f.label }}</dt>
                <dd class="text-lg font-semibold" :class="toneOf(g[f.field])" :data-testid="f.testid">{{ pnlText(g[f.field]) }}</dd>
              </div>
            </dl>
          </div>
          <p v-if="g.stateText" class="mt-1" data-testid="paper-state">{{ g.stateText }}</p>
          <p v-if="g.pauseReason" class="text-ink-muted" data-testid="paper-pause-reason">{{ g.pauseReason }}</p>
          <div class="mt-2 flex gap-3">
            <table v-if="g.legs.length" class="w-full min-w-0 flex-1 text-left">
              <thead>
                <tr><th class="w-6"><span class="sr-only">Select</span></th><th>Instrument</th><th>Qty</th><th>Paper entry</th><th>LTP / exit</th></tr>
              </thead>
              <tbody>
                <tr v-for="l in g.legs" :key="l.key" data-testid="paper-leg" :data-leg="l.index">
                  <td>
                    <input v-if="!l.exited" type="checkbox" :checked="isTicked(g.id, l.index)" :data-testid="`select-leg-${g.id}-${l.index}`" :aria-label="`Select ${legName(l)}`" @change="tick(g.id, l.index, $event.target.checked)" />
                  </td>
                  <td data-testid="paper-instrument"><span class="mr-1 rounded bg-surface-muted px-1 font-semibold">{{ l.action === 'Buy' ? 'B' : l.action === 'Sell' ? 'S' : l.action }}</span> <span>{{ instrumentCell(l) }}</span></td>
                  <td data-testid="paper-qty">{{ qtyText(l) }}</td>
                  <td>{{ l.entry }}</td>
                  <td>{{ l.exited ? `Exited at ${l.exitPrice}` : (l.current ?? '-') }}</td>
                </tr>
              </tbody>
            </table>
            <!-- D-C50: the action column. No Add Orders and no Convert To Real Trades (ADR-165). -->
            <div class="flex w-36 shrink-0 flex-col gap-2" data-testid="paper-actions">
              <RouterLink :to="{ path: '/strategy/builder', query: { strategy: String(g.id) } }" class="rounded border border-line px-2 py-1 text-center text-accent" data-testid="paper-open-builder">Open in Builder</RouterLink>
              <button v-if="openLegs(g).length" type="button" class="rounded border border-line px-2 py-1" :data-testid="`exit-selected-${g.id}`" :disabled="busy || !tickedOpen(g).length" @click="ask(g, tickedOpen(g))">Exit ({{ tickedOpen(g).length }})</button>
            </div>
          </div>
          <div v-if="confirm && confirm.id === g.id" class="mt-2 rounded bg-amber-50 p-2" role="group" aria-label="Confirm paper exit">
            <p data-testid="exit-confirm-text">Paper exit - no order is sent. Exit {{ confirm.names }} at the current paper price?</p>
            <button type="button" class="mr-2 rounded border border-line px-3 py-1" data-testid="exit-confirm" :disabled="busy" @click="doExit">Confirm paper exit</button>
            <button type="button" class="rounded border border-line px-3 py-1" data-testid="exit-cancel" :disabled="busy" @click="cancelExit(g.id)">Cancel</button>
          </div>
          <p v-if="exitErrors[g.id]" class="mt-2 text-red-700" role="alert" data-testid="paper-exit-error">{{ exitErrors[g.id] }}</p>
        </template>
      </div>
    </template>
  </section>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import api, { NEUTRAL_ERROR, NEUTRAL_PARTS } from '@/services/api'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import { readTrackingItem } from '@/lib/tracking'
import { usePaperRefresh } from '@/lib/usePaperRefresh'
import { expiryWithDays, instrumentText, strikeLabel } from '@/lib/displayFormat'
import { signOf } from '@/lib/chartCard'

defineProps({ compact: { type: Boolean, default: false } })
const NO_TOTAL = 'No paper total yet: prices are not live'
const BANNER ='Paper trades - not real money'
const EMPTY = 'No paper strategies yet. Save a strategy in the builder, then press Start tracking.'
const expiryText = (e) => expiryWithDays(e, null)
const NO_FIGURE = '—'
const figures = [
  { field: 'total', label: 'Total P&L', testid: 'paper-total' },
  { field: 'unbooked', label: 'Unbooked P&L', testid: 'paper-unbooked' },
  { field: 'booked', label: 'Booked P&L', testid: 'paper-booked' },
]
// D-C53 (REQ-109 AC-2, REQ-152 AC-4): the server's text to the paisa; a true zero has no sign, a missing figure is a dash
// (the reason is the state line under the header). D-C54: the colour follows the server's sign, read from its text.
const pnlText = (v) => (v === null || v === undefined ? NO_FIGURE : /^[+-]0\.00$/.test(v) ? '0.00' : v)
const toneOf = (v) => ({ profit: 'text-profit', loss: 'text-loss' })[signOf(String(v ?? '').replace(/,/g, ''))] ?? ''
// D-C48: "3 Nov 23000 CE" (a FUT leg "3 Nov FUT"); the Qty is signed from the server's side, nothing is computed
const instrumentCell = (l) => instrumentText({ expiry: l.expiry, strike: l.strike, instrument: l.instrument }, null)
const qtyText = (l) => (l.action === 'Sell' ? `-${l.quantity}` : `${l.quantity}`)
const legName = (l) => `${l.action} ${strikeLabel(l.strike)} ${l.instrument} ${expiryText(l.expiry)}`
const ticks = ref({})
const isTicked = (id, i) => !!ticks.value[id]?.includes(i)
function tick(id, i, on) {
  const rest = (ticks.value[id] ?? []).filter((x) => x !== i)
  ticks.value = { ...ticks.value, [id]: on ? [...rest, i] : rest }
}
const tickedOpen = (g) => g.legs.filter((l) => !l.exited && isTicked(g.id, l.index)).map((l) => l.index)

const items = ref(null)
const errorParts = ref(null)
const loading = ref(true)
const confirm = ref(null)
const busy = ref(false)
const exitErrors = ref({})

function show(data) {
  const list = data && Array.isArray(data.strategies) ? data.strategies : null
  if (list === null) {
    items.value = null
    errorParts.value = NEUTRAL_PARTS
  } else {
    const before = items.value
    items.value = list.map((x, i) => readTrackingItem(x, i))
    errorParts.value = null
    settle(before, items.value)
  }
  loading.value = false
}
// a failed read shows no figure: the old list is dropped, never left on screen as if current
function fail(e) {
  items.value = null
  confirm.value = null // R1-4: nothing is shown to confirm against, and no old exit error comes back with the next read
  exitErrors.value = {}
  errorParts.value = e?.parts ?? NEUTRAL_PARTS
  loading.value = false
}

const { refresh, refreshNow } = usePaperRefresh({
  key: () => 'list',
  read: async () => (await api.get('/tracking')).data,
  onData: show,
  onError: fail,
})
onMounted(refresh)

// R1-4: what a group's legs look like to an exit (index and exited state); a read that changes it ends the exit's open question
const legSig = (g) => (g && g.readable ? g.legs.map((l) => `${l.index}:${l.exited ? 'x' : 'o'}`).join(',') : null)
const namesOf = (g, indexes) => g.legs.filter((l) => indexes.includes(l.index)).map((l) => `${l.action} ${strikeLabel(l.strike)} ${l.instrument}`).join(', ')
function settle(before, now) {
  const c = confirm.value
  if (c) {
    const g = now.find((x) => x.id === c.id)
    const stillOpen = g && g.readable && c.legs.every((i) => g.legs.some((l) => l.index === i && !l.exited)) && namesOf(g, c.legs) === c.names
    if (!stillOpen) confirm.value = null
  }
  const kept = {}
  for (const [id, text] of Object.entries(exitErrors.value)) {
    const was = (before ?? []).find((x) => String(x.id) === id)
    const is = now.find((x) => String(x.id) === id)
    if (text && was && is && legSig(was) === legSig(is)) kept[id] = text // the group did not move: the refusal still stands
  }
  exitErrors.value = kept
}
function cancelExit(id) {
  confirm.value = null
  exitErrors.value = { ...exitErrors.value, [id]: '' }
}

const openLegs = (g) => g.legs.filter((l) => !l.exited).map((l) => l.index)

function ask(g, indexes) {
  if (busy.value) return
  const names = g.legs
    .filter((l) => indexes.includes(l.index))
    .map((l) => `${l.action} ${strikeLabel(l.strike)} ${l.instrument}`)
    .join(', ')
  confirm.value = { id: g.id, legs: indexes, names }
}

async function doExit() {
  const c = confirm.value
  if (!c || busy.value) return
  busy.value = true
  exitErrors.value = { ...exitErrors.value, [c.id]: '' }
  try {
    await api.post(`/strategies/${c.id}/tracking/exit`, { legs: c.legs })
    confirm.value = null
    refreshNow()
  } catch (e) {
    confirm.value = null
    exitErrors.value = { ...exitErrors.value, [c.id]: e?.parts?.what_happened || NEUTRAL_ERROR }
  } finally {
    busy.value = false
  }
}
</script>
