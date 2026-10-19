<!-- Live Strategies (W-113; REQ-049 AC-4..6, REQ-044 AC-2 part 1). Lists the saved strategies (GET /strategies) and gives
     each its own card, which follows it on the live outcome socket. The newest 20 by update time are shown. No number is
     read or computed here (ADR-008); there is no order or execute control (ADR-002). -->
<script setup>
import { computed, onMounted, ref } from 'vue'
import api, { NEUTRAL_PARTS } from '@/services/api'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import LiveStrategyCard from '@/components/live/LiveStrategyCard.vue'

const MAX_CARDS = 20
const state = ref('loading') // loading | ready | error
const all = ref([])
const errorParts = ref(NEUTRAL_PARTS)

const stamp = (s) => Date.parse(s.updated_at) || 0 // sort key only
const shown = computed(() => [...all.value].sort((a, b) => stamp(b) - stamp(a)).slice(0, MAX_CARDS))
const capped = computed(() => all.value.length > MAX_CARDS)

onMounted(async () => {
  try {
    all.value = (await api.get('/strategies')).data.strategies
    state.value = 'ready'
  } catch (e) {
    errorParts.value = e?.parts ?? NEUTRAL_PARTS
    state.value = 'error'
  }
})
</script>

<template>
  <section data-testid="live-strategies" :data-state="state">
    <h1 class="text-xl font-semibold" data-testid="page-title">Live Strategies</h1>
    <p class="mt-1 text-sm text-ink-muted">Your saved strategies followed on live market data. This is for monitoring, not a recommendation.</p>
    <p v-if="state === 'loading'" class="mt-4" data-testid="live-list-loading">Loading your strategies...</p>
    <ErrorMessage v-else-if="state === 'error'" class="mt-4" :parts="errorParts" data-testid="state-error" />
    <p v-else-if="!all.length" class="mt-4 text-ink-muted" data-testid="live-empty">
      No saved strategies yet. Build one in the <router-link to="/strategy/builder" class="underline">Strategy Builder</router-link>.
    </p>
    <template v-else>
      <p v-if="capped" class="mt-2 text-sm text-ink-muted" data-testid="live-capped">Showing the 20 most recent</p>
      <div class="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <LiveStrategyCard v-for="s in shown" :key="s.id" :strategy="s" />
      </div>
    </template>
  </section>
</template>
