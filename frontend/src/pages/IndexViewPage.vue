<!-- W-114 (REQ-072 AC-2; REQ-049 AC-2/AC-4; ADR-077, ADR-008, ADR-002): the Underlying/index view. Two panels, NIFTY 50
     and SENSEX: the value exactly as the server sent it, its time, and its health word whenever it is not "available".
     W-115 round 2: the answer state (first paint, pushes, drop counter, clear-on-drop, fallback read) lives in ONE place,
     useIndexAnswer in useIndexLive.js, shared with the Home strip; this page only renders its rows.
     No maths, no change figure, no order button. -->
<script setup>
import { onMounted } from 'vue'
import { istTime } from '@/lib/displayFormat'
import { healthSentence } from '@/lib/dataHealthText'
import MarketClosedBanner from '@/components/states/MarketClosedBanner.vue'
import { INDEX_KEYS, INDEX_NAMES, NOT_LIVE_LABEL, useIndexAnswer } from '@/composables/useIndexLive'

const { answer, start, reconnecting, reconnectingText, rowFor, shownValue, isLive, notLive, marketClosed, healthOf } = useIndexAnswer()
onMounted(start)

function timeText(row) {
  if (!row?.at) return ''
  return row.value === null || !isLive() ? `Last updated ${istTime(row.at)}` : `as of ${istTime(row.at)}`
}
</script>

<template>
  <section data-testid="index-view-page">
    <p class="text-xs text-ink-muted" data-testid="page-parent">Market</p>
    <h1 class="text-xl font-semibold" data-testid="page-title">Underlying/index view</h1>
    <!-- REQ-114 AC-7 / ADR-177: the one market-closed banner; the times then read "Last updated", never live "as of" -->
    <MarketClosedBanner v-if="marketClosed()" class="mt-2" :prices-at="answer.last_price_at" />
    <p v-if="reconnecting" class="mt-2 text-sm font-medium" data-testid="live-reconnecting">{{ reconnectingText }}</p>
    <p v-if="notLive() && !marketClosed()" class="mt-2 font-medium" data-testid="index-state">
      {{ NOT_LIVE_LABEL }}
    </p>
    <div class="mt-4 grid gap-4 md:grid-cols-2">
      <div
        v-for="u in INDEX_KEYS"
        :key="u"
        class="rounded border border-line bg-surface p-4"
        :data-testid="`index-panel-${u}`"
      >
        <div class="flex items-center justify-between gap-2">
          <h2 class="font-semibold">{{ INDEX_NAMES[u] }}</h2>
          <span
            v-if="healthOf(rowFor(u))"
            class="text-sm font-medium"
            data-testid="index-health"
          >{{ healthOf(rowFor(u)) }}</span>
        </div>
        <p v-if="healthOf(rowFor(u))" class="mt-1 text-xs text-ink-muted" data-testid="index-health-reason">{{ healthSentence(rowFor(u).health) }}</p>
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
