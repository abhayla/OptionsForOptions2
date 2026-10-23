<!-- W-115 (REQ-008 AC-4; ADR-077, ADR-008): the small live market strip on Home. One line: NIFTY 50 and SENSEX, each with
     the server's value string, its time and its health word. Round 2: it holds NO answer state; useIndexAnswer (the one
     state machine, shared with the index page) owns first paint, pushes, the drop counter and clear-on-drop.
     No maths, no change figure, no order button. -->
<script setup>
import { onMounted } from 'vue'
import { istTime } from '@/lib/displayFormat'
import MarketClosedBanner from '@/components/states/MarketClosedBanner.vue'
import { INDEX_KEYS, INDEX_NAMES, NOT_LIVE_LABEL, useIndexAnswer } from '@/composables/useIndexLive'

defineProps({ showStatus: { type: Boolean, default: false } }) // W-117: Market context adds one status line
const { answer, start, reconnecting, reconnectingText, rowFor, shownValue, notLive, isLive } = useIndexAnswer()
onMounted(start)
const statusText = () => (isLive() ? 'Index values are live.' : answer.value || notLive() ? 'Index values are not live.' : '')
const timeText = (row) => (row?.at ? istTime(row.at) : '')
</script>

<template>
  <div class="flex flex-wrap items-center gap-x-6 gap-y-1 rounded border border-line bg-surface px-3 py-2 text-sm" data-testid="index-strip">
    <MarketClosedBanner v-if="answer?.market_closed" :prices-at="answer.last_price_at" />
    <span v-if="reconnecting" class="font-medium" data-testid="live-reconnecting">{{ reconnectingText }}</span>
    <span v-if="notLive()" class="font-medium" data-testid="strip-state">{{ NOT_LIVE_LABEL }}</span>
    <span v-for="u in INDEX_KEYS" :key="u" :data-testid="`strip-${u}`" class="flex items-baseline gap-2">
      <span class="font-medium">{{ INDEX_NAMES[u] }}</span>
      <span class="tabular-nums" data-testid="strip-value">{{ shownValue(rowFor(u)) }}</span>
      <span class="text-xs text-ink-muted" data-testid="strip-at">{{ timeText(rowFor(u)) }}</span>
      <span v-if="rowFor(u)?.health && rowFor(u).health !== 'available'" class="text-xs font-medium" data-testid="strip-health">{{ rowFor(u).health }}</span>
    </span>
    <span v-if="showStatus && statusText()" class="basis-full text-xs text-ink-muted" data-testid="market-status">{{ statusText() }}</span>
  </div>
</template>
