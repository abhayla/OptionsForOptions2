<!-- ADR-330 (56) (owner 27 Nov 2026): the ONE price notice of a screen, mounted once at the top. Either the market-closed banner
     (the close time; ADR-177 / ADR-212) or, while the market is open and prices are not live, "Prices are not live. Figures are
     as of <time> IST." with the time of the last CAPTURED price (the answer's last_price_at / the reply's), never a page-load
     time and never the time a feed stopped being read. Tiles and rows below stay greyed, with no sentence of their own. Prints
     what the server sent; no price maths here (ADR-008). -->
<script setup>
import { computed } from 'vue'
import MarketClosedBanner from '@/components/states/MarketClosedBanner.vue'
import { notLiveNotice, priceNow } from '@/lib/priceState'

const props = defineProps({
  answer: { type: Object, default: null }, // the page's index answer (GET /market/indices or its socket)
  reply: { type: Object, default: null }, // the page's outcome reply, when it has one
  pageState: { type: String, default: 'computed' },
  reconnecting: { type: Boolean, default: false },
})
const now = computed(() => priceNow({ reply: props.reply, answer: props.answer, pageState: props.reply ? props.pageState : 'loading', reconnecting: props.reconnecting }))
const notLive = computed(() => {
  if (now.value.kind === 'last_close') return null
  const down = now.value.kind === 'stale' || (!!props.answer && props.answer.state !== 'LIVE')
  if (!down) return null
  return { text: notLiveNotice(now.value.at ?? props.answer?.last_price_at ?? null) }
})
</script>

<template>
  <MarketClosedBanner v-if="now.kind === 'last_close'" :prices-at="now.at" :server-text="now.text" />
  <div v-else-if="notLive" role="status" class="rounded border border-line bg-surface p-3 text-sm" data-testid="price-notice">
    <span class="font-medium" data-testid="price-notice-text">{{ notLive.text }}</span>
  </div>
</template>
