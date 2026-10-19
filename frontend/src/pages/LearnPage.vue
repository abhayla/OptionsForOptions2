<!-- W-117 (REQ-011 AC-1; ADR-114, ADR-003): Learn. Strategy education lists the reviewed strategy templates exactly as
     GET /api/strategy-templates sends them (name, description, market views), grouped by level, Beginner first; nothing
     is retyped here. Options concepts and Platform guidance have no reviewed text yet and say so in one line. A failed
     read shows the server's message. No money, no order link. -->
<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import api, { NEUTRAL_PARTS } from '@/services/api'
import ErrorMessage from '@/components/common/ErrorMessage.vue'

const NOTHING_PUBLISHED = 'Nothing published here yet.'
const LEVELS = ['Beginner', 'Intermediate', 'Advanced'] // display order only; each template's level comes from the server

const route = useRoute()
const isEducation = computed(() => route.path.endsWith('/strategy-education'))
const templates = ref(null) // null until read
const errorParts = ref(null)

const groups = computed(() =>
  LEVELS.map((level) => ({ level, items: (templates.value ?? []).filter((t) => t.level === level) })).filter((g) => g.items.length))

const state = computed(() => {
  if (!isEducation.value) return 'empty'
  if (errorParts.value) return 'error'
  if (templates.value === null) return 'loading'
  return templates.value.length ? 'list' : 'empty'
})

onMounted(async () => {
  if (!isEducation.value) return
  try {
    const list = (await api.get('/strategy-templates')).data?.templates
    if (!Array.isArray(list)) throw new Error('unreadable answer') // fail closed: nothing is guessed
    templates.value = list
  } catch (e) {
    errorParts.value = e?.parts ?? NEUTRAL_PARTS
  }
})
</script>

<template>
  <section data-testid="learn" :data-state="state">
    <p class="text-xs text-ink-muted" data-testid="page-parent">Learn</p>
    <h1 class="text-xl font-semibold" data-testid="page-title">{{ route.meta.title }}</h1>

    <ErrorMessage v-if="state === 'error'" class="mt-4" :parts="errorParts" prefix="learn-error" data-testid="learn-error" />
    <p v-else-if="state === 'empty'" class="mt-4 text-ink-muted" data-testid="learn-empty">{{ NOTHING_PUBLISHED }}</p>
    <template v-else-if="state === 'list'">
      <div v-for="g in groups" :key="g.level" class="mt-5" :data-testid="`level-${g.level}`">
        <h2 class="text-lg font-semibold" data-testid="level-title">{{ g.level }}</h2>
        <ul class="mt-2 grid gap-3 sm:grid-cols-2">
          <li v-for="t in g.items" :key="t.id" class="rounded border border-line bg-surface p-3" data-testid="template-card">
            <h3 class="font-medium" data-testid="template-name">{{ t.name }}</h3>
            <p class="mt-1 text-sm" data-testid="template-description">{{ t.description }}</p>
            <p class="mt-1 text-xs text-ink-muted" data-testid="template-views">Market view: {{ t.views.join(', ') }}</p>
          </li>
        </ul>
      </div>
    </template>
  </section>
</template>
