<!-- W-115 (REQ-008 AC-2..AC-5; ADR-114, ADR-003): Home overview. The state comes only from GET /strategies: none saved ->
     `new` (Create Strategy, Explore Option Chain, Learn first); some saved -> `has-strategies` (My Strategies first, then
     Create Strategy, the three most recently updated). A failed read -> `error` with the server's message. The live index
     strip shows in every state. Zerodha is a quiet line only: no connect control anywhere on this page (AC-5). No money. -->
<script setup>
import { computed, onMounted, ref } from 'vue'
import api, { NEUTRAL_PARTS } from '@/services/api'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import IndexStrip from '@/components/layout/IndexStrip.vue'
import { istTime } from '@/lib/displayFormat'
import { SECTIONS } from '@/router/nav'

const RECENT_COUNT = 3
const learnItems = SECTIONS.find((s) => s.key === 'learn').items
const LEARN_PATH = `/learn/${learnItems[0][0]}`

const strategies = ref(null) // null until read
const errorParts = ref(null)

const state = computed(() => {
  if (errorParts.value) return 'error'
  if (strategies.value === null) return 'loading'
  return strategies.value.length ? 'has-strategies' : 'new'
})

const recent = computed(() =>
  [...(strategies.value ?? [])]
    .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at))
    .slice(0, RECENT_COUNT))

onMounted(async () => {
  try {
    const list = (await api.get('/strategies')).data?.strategies
    if (!Array.isArray(list)) throw new Error('unreadable answer') // fail closed: no state is guessed
    strategies.value = list
  } catch (e) {
    errorParts.value = e?.parts ?? NEUTRAL_PARTS
  }
})
</script>

<template>
  <section data-testid="home" :data-state="state">
    <p class="text-xs text-ink-muted" data-testid="page-parent">Home</p>
    <h1 class="text-xl font-semibold" data-testid="page-title">Overview</h1>
    <IndexStrip class="mt-3" />

    <ErrorMessage v-if="state === 'error'" class="mt-4" :parts="errorParts" prefix="home-error" data-testid="home-error" />

    <div v-else-if="state === 'new'" class="mt-4" data-testid="home-new">
      <h2 class="text-lg font-semibold">Welcome</h2>
      <p class="mt-1 text-ink-muted">Plan your trade. Follow your strategy. Then execute.</p>
      <div class="mt-4 flex flex-wrap gap-3" data-testid="home-actions">
        <router-link to="/strategies/create-strategy" class="rounded border border-line bg-surface px-4 py-2 font-medium" data-testid="action-create">Create Strategy</router-link>
        <router-link to="/market/option-chain" class="rounded border border-line bg-surface px-4 py-2 font-medium" data-testid="action-chain">Explore Option Chain</router-link>
        <router-link :to="LEARN_PATH" class="rounded border border-line bg-surface px-4 py-2 font-medium" data-testid="action-learn">Learn</router-link>
      </div>
      <p class="mt-3 text-sm"><router-link to="/strategy/builder" class="underline" data-testid="action-know">I already know my strategy</router-link></p>
    </div>

    <div v-else-if="state === 'has-strategies'" class="mt-4" data-testid="home-has-strategies">
      <div class="flex flex-wrap gap-3" data-testid="home-actions">
        <router-link to="/strategies/my-strategies" class="rounded border border-line bg-surface px-4 py-2 font-medium" data-testid="action-my">My Strategies</router-link>
        <router-link to="/strategies/create-strategy" class="rounded border border-line bg-surface px-4 py-2 font-medium" data-testid="action-create">Create Strategy</router-link>
      </div>
      <h2 class="mt-5 text-sm font-medium">Recent strategies</h2>
      <ul class="mt-1 text-sm" data-testid="recent-strategies">
        <li v-for="s in recent" :key="s.id" class="flex flex-wrap items-center gap-2" data-testid="recent-row">
          <span>{{ s.underlying }}, {{ s.status }}, last saved {{ istTime(s.updated_at) }}</span>
          <router-link to="/strategy/builder" class="underline" :data-testid="`recent-open-${s.id}`">Open in Strategy Builder</router-link>
        </li>
      </ul>
    </div>

    <p v-if="state !== 'loading'" class="mt-8 text-xs text-ink-muted" data-testid="zerodha-line">Already trade with Zerodha? Connect when ready</p>
  </section>
</template>
