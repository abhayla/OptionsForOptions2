<!-- W-115 (REQ-008 AC-4; ADR-077, ADR-008): the small live market strip on Home. One line: NIFTY 50 and SENSEX, each with
     the server's value string, its time and its health word. It REUSES W-114's index socket (useIndexLive) and answer
     check; first paint from GET /api/market/indices, then pushes; when the socket drops it asks the REST read with
     fallback=true and shows the server's not-live answer. No maths, no change figure, no order button. -->
<script setup>
import { onMounted, ref } from 'vue'
import api from '@/services/api'
import { istTime } from '@/lib/displayFormat'
import { INDEX_REST_PATH, isIndicesAnswer, useIndexLive } from '@/composables/useIndexLive'

const NAMES = { NIFTY: 'NIFTY 50', SENSEX: 'SENSEX' }
const NOT_LIVE_LABEL = 'Index values unavailable.'
const VALUE_UNAVAILABLE = 'Not available'

const answer = ref(null)
const failed = ref(false)
let pushed = false

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
    const data = await read(true)
    if (status.value === 'live') return
    if (data) answer.value = data
    else failed.value = true
  },
})

onMounted(async () => {
  start()
  const data = await read(false)
  if (pushed) return
  if (data) answer.value = data
  else failed.value = true
})

const rowFor = (u) => answer.value?.indices?.find((r) => r.underlying === u) ?? null
const shownValue = (row) => (answer.value?.state === 'LIVE' && typeof row?.value === 'string' ? row.value : VALUE_UNAVAILABLE)
const timeText = (row) => (row?.at ? istTime(row.at) : '')
</script>

<template>
  <div class="flex flex-wrap items-center gap-x-6 gap-y-1 rounded border border-line bg-surface px-3 py-2 text-sm" data-testid="index-strip">
    <span v-if="answer?.state === 'NOT_CONNECTED' || failed" class="font-medium" data-testid="strip-state">{{ NOT_LIVE_LABEL }}</span>
    <span v-for="u in ['NIFTY', 'SENSEX']" :key="u" :data-testid="`strip-${u}`" class="flex items-baseline gap-2">
      <span class="font-medium">{{ NAMES[u] }}</span>
      <span class="tabular-nums" data-testid="strip-value">{{ shownValue(rowFor(u)) }}</span>
      <span class="text-xs text-ink-muted" data-testid="strip-at">{{ timeText(rowFor(u)) }}</span>
      <span v-if="rowFor(u)?.health && rowFor(u).health !== 'available'" class="text-xs font-medium" data-testid="strip-health">{{ rowFor(u).health }}</span>
    </span>
  </div>
</template>
