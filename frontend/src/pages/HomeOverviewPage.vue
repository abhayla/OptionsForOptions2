<!-- W-115 (REQ-008 AC-2..AC-5; ADR-114, ADR-003): Home overview. The state comes only from GET /strategies: none saved ->
     `new` (Create Strategy, Explore Option Chain, Learn first); some saved -> `has-strategies` (My Strategies first, then
     Create Strategy, the three most recently updated). A failed read -> `error` with the server's message. The live index
     strip shows in every state. Zerodha is a quiet line only: no connect control anywhere on this page (AC-5). No money. -->
<script setup>
import { computed, onMounted, ref } from 'vue'
import api, { NEUTRAL_PARTS } from '@/services/api'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import IndexStrip from '@/components/layout/IndexStrip.vue'
import Card from '@/components/common/Card.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import { istTime } from '@/lib/displayFormat'
import { plainName } from '@/lib/saveDraft'
import { SECTIONS } from '@/router/nav'

const RECENT_COUNT = 3
const TAP = 'inline-flex min-h-11 items-center justify-center' // 44 px tap target, no fixed width
// Owner 2026-10-30 (Sensibull 001): one primary action in the accent, the rest as quiet bordered buttons
const PROMINENT = `${TAP} rounded-md border border-line bg-surface px-4 py-2 text-sm font-medium hover:bg-surface-muted`
const PRIMARY = `${TAP} rounded-md border border-accent bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover`
const SECONDARY = `${TAP} text-accent hover:underline`
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
    <PageHeader parent="Home" title="Overview" />
    <IndexStrip />

    <ErrorMessage v-if="state === 'error'" class="mt-4" :parts="errorParts" prefix="home-error" data-testid="home-error" />

    <Card v-else-if="state === 'new'" class="mt-4" data-testid="home-new">
      <!-- HOME-NEW leaves this slot empty: `Welcome, [Name]` and the Pro-trial line need the signed-in user (row #433, stage 5). -->
      <div data-testid="home-welcome-slot" />
      <p class="text-lg font-semibold" data-testid="home-line">Plan your trade. Follow your strategy. Then execute.</p>
      <div class="mt-4 flex flex-wrap gap-3" data-testid="home-actions">
        <router-link to="/strategies/create-strategy" :class="PRIMARY" data-testid="action-create">Create Strategy</router-link>
        <router-link to="/market/option-chain" :class="PROMINENT" data-testid="action-chain">Explore Option Chain</router-link>
        <router-link :to="LEARN_PATH" :class="PROMINENT" data-testid="action-learn">Learn</router-link>
      </div>
      <p class="mt-2 text-sm"><router-link to="/strategy/builder" :class="SECONDARY" data-testid="action-know">I already know my strategy</router-link></p>
    </Card>

    <div v-else-if="state === 'has-strategies'" class="mt-4 grid gap-4" data-testid="home-has-strategies">
      <div class="flex flex-wrap gap-3" data-testid="home-actions">
        <router-link to="/strategies/my-strategies" :class="PRIMARY" data-testid="action-my">My Strategies</router-link>
        <router-link to="/strategies/create-strategy" :class="PROMINENT" data-testid="action-create">Create Strategy</router-link>
      </div>
      <Card title="Recent strategies" flush>
        <ul class="divide-y divide-line text-sm" data-testid="recent-strategies">
          <li
            v-for="s in recent" :key="s.id"
            class="grid min-h-9 grid-cols-[minmax(0,1.2fr)_minmax(0,2fr)_auto] items-center gap-3 px-4 py-2 hover:bg-surface-muted"
            data-testid="recent-row"
          >
            <span v-if="plainName(s.name)" class="min-w-0 truncate font-medium" data-testid="recent-name">{{ plainName(s.name) }}</span>
            <span v-else class="text-ink-subtle" aria-hidden="true">—</span>
            <span class="min-w-0 truncate text-ink-muted">{{ s.underlying }}, {{ s.status }}, last saved {{ istTime(s.updated_at) }}</span>
            <router-link to="/strategy/builder" class="text-accent hover:underline" :data-testid="`recent-open-${s.id}`">Open in Strategy Builder</router-link>
          </li>
        </ul>
      </Card>
    </div>

    <p v-if="state !== 'loading'" class="mt-6 text-xs text-ink-muted" data-testid="zerodha-line">Already trade with Zerodha? Connect when ready</p>
  </section>
</template>
