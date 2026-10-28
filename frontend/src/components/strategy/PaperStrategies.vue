<!-- GC-BP step 6 (ADR-201 (2); REQ-109 AC-2, AC-3, AC-4): every paper-tracked strategy of the user as a group with its legs
     (entry, LTP, exit), the server's total / booked / unbooked, an Open in Builder link and a confirmed Paper exit. Shown in
     the Positions page's Paper tab and the builder's Tracked tab. Layout after Sensibull S-090..092 (Draft Portfolio).
     The browser computes no money (ADR-008): every figure is the server's string re-grouped; no sum across legs or
     strategies. A failed or unreadable read shows no figure. Nothing here reaches Execute (REQ-109 AC-3): the exit is a
     paper exit and sends no order. -->
<template>
  <section class="text-sm" data-testid="paper-strategies">
    <p class="rounded bg-amber-50 px-2 py-1 font-medium" data-testid="paper-banner">{{ BANNER }}</p>
    <p v-if="loading" class="mt-2" data-testid="paper-loading">Reading your paper strategies.</p>
    <ErrorMessage v-else-if="errorParts" class="mt-2" :parts="errorParts" compact prefix="paper-error" />
    <p v-else-if="!items.length" class="mt-2" data-testid="paper-empty">{{ EMPTY }}</p>
    <template v-else>
      <div v-for="g in items" :key="g.id" class="mt-3 rounded-lg border border-line p-3" data-testid="paper-group" :data-strategy="g.id">
        <p v-if="!g.readable" data-testid="paper-unreadable">{{ g.text }}</p>
        <template v-else>
          <div class="flex flex-wrap items-center gap-3">
            <h2 class="font-semibold" data-testid="paper-group-name">{{ g.name ?? `Strategy ${g.id}` }}</h2>
            <span class="text-ink-muted" data-testid="paper-group-underlying">{{ g.underlying }}</span>
            <RouterLink :to="{ path: '/strategy/builder', query: { strategy: String(g.id) } }" class="text-accent underline" data-testid="paper-open-builder">Open in Builder</RouterLink>
          </div>
          <p v-if="g.stateText" class="mt-1" data-testid="paper-state">{{ g.stateText }}</p>
          <p v-if="g.pauseReason" class="text-ink-muted" data-testid="paper-pause-reason">{{ g.pauseReason }}</p>
          <dl class="mt-2 flex flex-wrap gap-4 border-2 border-dashed rounded-lg p-2" data-testid="paper-figures">
            <div><dt class="inline">Paper total: </dt><dd class="inline font-semibold" data-testid="paper-total">{{ g.total ?? '-' }}</dd></div>
            <div><dt class="inline">Booked: </dt><dd class="inline" data-testid="paper-booked">{{ g.booked ?? '-' }}</dd></div>
            <div><dt class="inline">Unbooked: </dt><dd class="inline" data-testid="paper-unbooked">{{ g.unbooked ?? '-' }}</dd></div>
          </dl>
          <table v-if="g.legs.length" class="mt-2 w-full text-left">
            <thead>
              <tr><th>Leg</th><th>Expiry</th><th>Strike</th><th>Qty</th><th>Entry</th><th>LTP / exit</th><th /></tr>
            </thead>
            <tbody>
              <tr v-for="l in g.legs" :key="l.key" data-testid="paper-leg" :data-leg="l.index">
                <td>{{ l.action }} {{ l.instrument }}</td>
                <td>{{ expiryText(l.expiry) }}</td>
                <td>{{ strikeLabel(l.strike) }}</td>
                <td>{{ l.quantity }}</td>
                <td>{{ l.entry }}</td>
                <td>{{ l.exited ? `Exited at ${l.exitPrice}` : (l.current ?? '-') }}</td>
                <td>
                  <button v-if="!l.exited" type="button" class="rounded border border-line px-2 py-1" :data-testid="`exit-leg-${g.id}-${l.index}`" :disabled="busy" @click="ask(g, [l.index])">Exit</button>
                </td>
              </tr>
            </tbody>
          </table>
          <button v-if="openLegs(g).length" type="button" class="mt-2 rounded border border-line px-3 py-1" :data-testid="`exit-all-${g.id}`" :disabled="busy" @click="ask(g, openLegs(g))">Exit all</button>
          <div v-if="confirm && confirm.id === g.id" class="mt-2 rounded bg-amber-50 p-2" role="group" aria-label="Confirm paper exit">
            <p data-testid="exit-confirm-text">Paper exit - no order is sent. Exit {{ confirm.names }} at the current paper price?</p>
            <button type="button" class="mr-2 rounded border border-line px-3 py-1" data-testid="exit-confirm" :disabled="busy" @click="doExit">Confirm paper exit</button>
            <button type="button" class="rounded border border-line px-3 py-1" data-testid="exit-cancel" :disabled="busy" @click="confirm = null">Cancel</button>
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
import { expiryWithDays, strikeLabel } from '@/lib/displayFormat'

const BANNER = 'Paper trades - not real money'
const EMPTY = 'No paper strategies yet. Save a strategy in the builder, then press Start tracking.'
const expiryText = (e) => expiryWithDays(e, null)

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
    items.value = list.map((x, i) => readTrackingItem(x, i))
    errorParts.value = null
  }
  loading.value = false
}
// a failed read shows no figure: the old list is dropped, never left on screen as if current
function fail(e) {
  items.value = null
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
