<!-- W-114 (REQ-072 AC-2; REQ-049 AC-2/AC-4; ADR-077, ADR-008, ADR-002): the Underlying/index view. Two panels, NIFTY 50
     and SENSEX: the value exactly as the server sent it, its time, and its health word whenever it is not "available".
     First paint from GET /api/market/indices, then the read-only socket's pushes; when the socket drops, the page asks
     the REST read with fallback=true and shows the server's not-live answer. No maths, no change figure, no order button. -->
<script setup>
import { onMounted, ref } from 'vue'
import api from '@/services/api'
import { istTime } from '@/lib/displayFormat'
import { INDEX_REST_PATH, isIndicesAnswer, useIndexLive } from '@/composables/useIndexLive'

const PANEL_NAMES = { NIFTY: 'NIFTY 50', SENSEX: 'SENSEX' }
const NOT_CONNECTED_LABEL = 'Index values unavailable.'
const VALUE_UNAVAILABLE = 'Not available'

const answer = ref(null) // the server's last answer, untouched
const failed = ref(false)
let pushed = false // a socket push arrived: a slower first-paint REST answer must not replace it
let drops = 0 // counts socket drops: an answer whose request was sent before the latest drop is ignored

function notLiveAfterDrop() {
  // REQ-072 AC-2 / REQ-049 AC-4: an old LIVE number is never kept; only each index's last time stays for the not-live line
  const rows = (answer.value?.indices ?? []).map((r) => ({ underlying: r.underlying, instrument_id: r.instrument_id, value: null, at: r.at ?? null, health: null }))
  answer.value = { state: 'NOT_CONNECTED', indices: rows }
}

async function read(fallback) {
  try {
    const { data } = await api.get(INDEX_REST_PATH, { params: fallback ? { fallback: true } : {} })
    return isIndicesAnswer(data) ? data : null
  } catch {
    return null
  }
}

const { status, start } = useIndexLive({
  onPush: (msg) => {
    pushed = true
    failed.value = false
    answer.value = msg
  },
  onDown: async () => {
    drops += 1
    const mine = drops
    pushed = false
    notLiveAfterDrop()
    const data = await read(true)
    if (mine !== drops || status.value === 'live' || pushed) return // a newer drop or a socket push is newer than this answer
    if (data) answer.value = data
    else failed.value = true
  },
})

onMounted(async () => {
  start()
  const sentAt = drops
  const data = await read(false)
  if (pushed || sentAt !== drops) return
  if (data) answer.value = data
  else failed.value = true
})

function rowFor(underlying) {
  return answer.value?.indices?.find((r) => r.underlying === underlying) ?? null
}

function timeText(row) {
  if (!row?.at) return ''
  return row.value === null || answer.value?.state !== 'LIVE' ? `Last updated ${istTime(row.at)}` : `as of ${istTime(row.at)}`
}

function shownValue(row) {
  // a null value is never rendered as a number; a value is shown only in a LIVE answer
  return answer.value?.state === 'LIVE' && typeof row?.value === 'string' ? row.value : VALUE_UNAVAILABLE
}
</script>

<template>
  <section data-testid="index-view-page">
    <p class="text-xs text-ink-muted" data-testid="page-parent">Market</p>
    <h1 class="text-xl font-semibold" data-testid="page-title">Underlying/index view</h1>
    <p v-if="answer?.state === 'NOT_CONNECTED' || failed" class="mt-2 font-medium" data-testid="index-state">
      {{ NOT_CONNECTED_LABEL }}
    </p>
    <div class="mt-4 grid gap-4 md:grid-cols-2">
      <div
        v-for="u in ['NIFTY', 'SENSEX']"
        :key="u"
        class="rounded border border-line bg-surface p-4"
        :data-testid="`index-panel-${u}`"
      >
        <div class="flex items-center justify-between gap-2">
          <h2 class="font-semibold">{{ PANEL_NAMES[u] }}</h2>
          <span
            v-if="rowFor(u)?.health && rowFor(u).health !== 'available'"
            class="text-sm font-medium"
            data-testid="index-health"
          >{{ rowFor(u).health }}</span>
        </div>
        <p class="mt-2 text-2xl font-semibold tabular-nums" data-testid="index-value">{{ shownValue(rowFor(u)) }}</p>
        <p class="mt-1 text-sm text-ink-muted" data-testid="index-at">{{ timeText(rowFor(u)) }}</p>
        <div class="mt-3 flex flex-wrap gap-3 text-sm">
          <router-link to="/market/option-chain" class="underline" data-testid="index-link-chain">Open Option Chain</router-link>
          <router-link to="/strategies/live-strategies" class="underline" data-testid="index-link-live">Live Strategies</router-link>
        </div>
      </div>
    </div>
  </section>
</template>
