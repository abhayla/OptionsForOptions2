<!-- Market-depth popup for one leg (REQ-080 AC-7, AC-8; ADR-012, ADR-015). Reads GET /api/leg-picker/depth and shows what the
     server sent: 5 bid and ask levels with quantities, the day's open / high / low / previous close, the last trade time and
     the time the depth was read. It refreshes at most once a second while mounted (the page mounts it only while open) and
     the timer is cleared on unmount. When the server says not available, or a read fails, it says 'Depth not available' with
     the reason and renders NO table: an old table is never kept. No price is computed here and the popup has no order button. -->
<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import api from '@/services/api'
import { istTime } from '@/lib/displayFormat'
import { DEPTH_NOT_AVAILABLE, DEPTH_REFRESH_MS, dayStatsReasonText, depthReasonText, shown } from '@/lib/legPicker'

const props = defineProps({
  instrumentId: { type: String, required: true },
  title: { type: String, default: '' },
})
const emit = defineEmits(['close'])

const answer = ref(null) // the newest answer, or null when the newest read failed (never an older table)
const failed = ref(false)
const loaded = ref(false)
let timer = null
let inFlight = false
let closed = false

async function read() {
  if (inFlight || closed) return // at most one request at a time, so never faster than the timer's one a second
  inFlight = true
  try {
    const res = await api.get(`/leg-picker/depth?instrument_id=${encodeURIComponent(props.instrumentId)}`)
    if (closed) return
    answer.value = res.data
    failed.value = false
  } catch {
    if (closed) return
    answer.value = null
    failed.value = true
  } finally {
    inFlight = false
    loaded.value = true
  }
}

onMounted(() => {
  read()
  timer = setInterval(read, DEPTH_REFRESH_MS)
})
onBeforeUnmount(() => {
  closed = true
  clearInterval(timer)
})

// Fail closed: the table shows only for state AVAILABLE with levels on both sides.
const available = computed(() => {
  const a = answer.value
  return !!a && a.state === 'AVAILABLE' && Array.isArray(a.bids) && Array.isArray(a.asks) && a.bids.length > 0 && a.asks.length > 0
})
const unavailableReason = computed(() => {
  if (failed.value) return 'The depth could not be read right now.'
  const a = answer.value
  if (a && a.state === 'AVAILABLE' && !available.value) return depthReasonText('DEPTH_EMPTY')
  return depthReasonText(a?.reason)
})
const levels = computed(() => {
  const a = answer.value
  return available.value ? Array.from({ length: a.bids.length > a.asks.length ? a.bids.length : a.asks.length }, (_, i) => ({ bid: a.bids[i] ?? null, ask: a.asks[i] ?? null })) : []
})
</script>

<template>
  <!-- UI-115 (I-11): a 360 px popover; every value is its own padded table cell, never run together. -->
  <div class="w-[360px] rounded-lg border border-line bg-surface p-3 text-sm shadow" role="dialog" :aria-label="`Market depth${title ? `: ${title}` : ''}`" data-testid="depth-popup" :data-instrument-id="instrumentId" @keydown.esc="emit('close')">
    <div class="flex items-center justify-between">
      <h3 class="truncate font-medium">Market depth{{ title ? `: ${title}` : '' }}</h3>
      <button type="button" data-testid="depth-close" class="text-accent" @click="emit('close')">Close</button>
    </div>
    <p v-if="!loaded" data-testid="depth-loading">Reading depth...</p>
    <template v-else-if="available">
      <dl class="mt-2 grid grid-cols-4 gap-2" data-testid="depth-day">
        <div><dt class="text-xs text-ink-muted">Open</dt><dd data-testid="depth-open">{{ shown(answer.day_open) }}</dd></div>
        <div><dt class="text-xs text-ink-muted">High</dt><dd data-testid="depth-high">{{ shown(answer.day_high) }}</dd></div>
        <div><dt class="text-xs text-ink-muted">Low</dt><dd data-testid="depth-low">{{ shown(answer.day_low) }}</dd></div>
        <div v-if="answer.prev_close != null"><dt class="text-xs text-ink-muted">Prev close</dt><dd data-testid="depth-prev-close">{{ answer.prev_close }}</dd></div>
      </dl>
      <table class="mt-2 w-full border-collapse text-right tabular-nums" data-testid="depth-table">
        <thead class="text-xs text-ink-muted"><tr><th class="px-3 py-1">Bids</th><th class="px-3 py-1">Qty</th><th class="px-3 py-1">Offers</th><th class="px-3 py-1">Qty</th></tr></thead>
        <tbody>
          <tr v-for="(l, i) in levels" :key="i" class="h-7 border-t border-line" data-testid="depth-level">
            <td class="px-3" data-testid="depth-bid">{{ shown(l.bid?.price) }}</td><td class="px-3 text-buy" data-testid="depth-bid-qty">{{ shown(l.bid?.quantity) }}</td>
            <td class="px-3" data-testid="depth-ask">{{ shown(l.ask?.price) }}</td><td class="px-3 text-sell" data-testid="depth-ask-qty">{{ shown(l.ask?.quantity) }}</td>
          </tr>
        </tbody>
      </table>
      <p class="mt-2 text-xs text-ink-muted">
        Last trade <span data-testid="depth-last-trade">{{ answer.last_trade_at ? istTime(answer.last_trade_at) : '-' }}</span> ·
        read <span data-testid="depth-read-at">{{ istTime(answer.read_at) }}</span>
      </p>
      <p v-if="answer.day_stats_reason" class="mt-1 text-ink-muted" data-testid="depth-day-reason">Day figures not shown: {{ dayStatsReasonText(answer.day_stats_reason) }}</p>
    </template>
    <div v-else data-testid="depth-unavailable">
      <p class="mt-2 font-medium">{{ DEPTH_NOT_AVAILABLE }}</p>
      <p data-testid="depth-reason">{{ unavailableReason }}</p>
    </div>
  </div>
</template>
