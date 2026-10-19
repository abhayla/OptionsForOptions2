<!-- W-115 (REQ-008 AC-4; ADR-077, ADR-008): the small live market strip on Home. One line: NIFTY 50 and SENSEX, each with
     the server's value string, its time and its health word. Round 2: it holds NO answer state; useIndexAnswer (the one
     state machine, shared with the index page) owns first paint, pushes, the drop counter and clear-on-drop.
     No maths, no change figure, no order button. -->
<script setup>
import { onMounted } from 'vue'
import { istTime } from '@/lib/displayFormat'
import { INDEX_KEYS, INDEX_NAMES, NOT_LIVE_LABEL, useIndexAnswer } from '@/composables/useIndexLive'

const { start, rowFor, shownValue, notLive } = useIndexAnswer()
onMounted(start)
const timeText = (row) => (row?.at ? istTime(row.at) : '')
</script>

<template>
  <div class="flex flex-wrap items-center gap-x-6 gap-y-1 rounded border border-line bg-surface px-3 py-2 text-sm" data-testid="index-strip">
    <span v-if="notLive()" class="font-medium" data-testid="strip-state">{{ NOT_LIVE_LABEL }}</span>
    <span v-for="u in INDEX_KEYS" :key="u" :data-testid="`strip-${u}`" class="flex items-baseline gap-2">
      <span class="font-medium">{{ INDEX_NAMES[u] }}</span>
      <span class="tabular-nums" data-testid="strip-value">{{ shownValue(rowFor(u)) }}</span>
      <span class="text-xs text-ink-muted" data-testid="strip-at">{{ timeText(rowFor(u)) }}</span>
      <span v-if="rowFor(u)?.health && rowFor(u).health !== 'available'" class="text-xs font-medium" data-testid="strip-health">{{ rowFor(u).health }}</span>
    </span>
  </div>
</template>
