<!-- W-117 + GC-6 LEARN (REQ-011 AC-1, REQ-009 AC-7; ADR-114, ADR-003, ADR-008): three tabs, a title search, a card list and a detail
     view. Strategy education lists the server's templates exactly as GET /api/strategy-templates sends them (name,
     description, level, market views; nothing retyped) and adds the six template parts from lib/learnContent.js when that
     home has text for the template id; a template with no text shows only the server's description. Options concepts and
     Platform guidance read the same content home. Nothing is computed here: payoff shapes are fixed points labelled Sample.
     A failed read shows the server's message. No money, no order link. -->
<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import api, { NEUTRAL_PARTS } from '@/services/api'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import { useHeldFeature } from '@/lib/heldFeatures'
import {
  CONCEPTS, NUMBERS_NOTE, PLATFORM, SAMPLE_LABEL, SAMPLE_NOTE, SHAPES, STRATEGY_PARTS, STRATEGY_TEXT, TABS,
} from '@/lib/learnContent'

const NOTHING_PUBLISHED = 'Nothing published here yet.'
const NO_MATCH = 'No lesson matches that search.'
const LEVELS = ['Beginner', 'Intermediate', 'Advanced'] // display order only; each template's level comes from the server
const VIEW_W = 100 // drawing box only; the points themselves are stated in the content home

const route = useRoute()
const platformStrikes = useHeldFeature('platform_strikes') // W-125: "Open in Builder" shows only when this is on
const tab = computed(() => TABS.find((t) => route.path.endsWith(`/${t.slug}`))?.slug ?? TABS[0].slug)
const isEducation = computed(() => tab.value === 'strategy-education')
const templates = ref(null) // null until read
const errorParts = ref(null)
const query = ref('')
const openId = ref(null)

async function loadTemplates() {
  if (templates.value !== null || errorParts.value) return
  try {
    const list = (await api.get('/strategy-templates')).data?.templates
    if (!Array.isArray(list)) throw new Error('unreadable answer') // fail closed: nothing is guessed
    templates.value = list
  } catch (e) {
    errorParts.value = e?.parts ?? NEUTRAL_PARTS
  }
}

watch(tab, () => { query.value = ''; openId.value = null }) // a tab change closes the detail and clears the search
watch(isEducation, (on) => { if (on) loadTemplates() }, { immediate: true })

const needle = computed(() => query.value.trim().toLowerCase())
const matches = (title) => !needle.value || title.toLowerCase().includes(needle.value)

const lessons = computed(() => (tab.value === 'options-concepts' ? CONCEPTS : tab.value === 'platform-guidance' ? PLATFORM : []))
const filteredLessons = computed(() => lessons.value.filter((l) => matches(l.title)))
const groups = computed(() =>
  LEVELS.map((level) => ({
    level, items: (templates.value ?? []).filter((t) => t.level === level && matches(t.name)),
  })).filter((g) => g.items.length))

const state = computed(() => {
  if (isEducation.value) {
    if (errorParts.value) return 'error'
    if (templates.value === null) return 'loading'
    return templates.value.length ? 'list' : 'empty'
  }
  return lessons.value.length ? 'list' : 'empty'
})
const noMatch = computed(() => state.value === 'list' && (isEducation.value ? !groups.value.length : !filteredLessons.value.length))

const openTemplate = computed(() => (isEducation.value ? (templates.value ?? []).find((t) => t.id === openId.value) : null))
const openLesson = computed(() => lessons.value.find((l) => l.id === openId.value) ?? null)
const text = computed(() => (openTemplate.value ? STRATEGY_TEXT[openTemplate.value.id] ?? null : null))
const shapePoints = computed(() => {
  const pts = SHAPES[text.value?.shape]
  return pts ? pts.map(([x, y]) => `${x},${VIEW_W - y}`).join(' ') : ''
})
</script>

<template>
  <section data-testid="learn" :data-state="state" :data-tab="tab">
    <p class="text-xs text-ink-muted" data-testid="page-parent">Learn</p>
    <h1 class="text-xl font-semibold" data-testid="page-title">{{ route.meta.title }}</h1>

    <nav class="mt-3 grid grid-cols-3 gap-1 rounded border border-line p-1 text-center text-sm" data-testid="learn-tabs" aria-label="Learn sections">
      <router-link
        v-for="t in TABS" :key="t.slug" :to="`/learn/${t.slug}`" :data-testid="`tab-${t.slug}`"
        :aria-current="tab === t.slug ? 'page' : undefined"
        class="rounded px-1 py-2 break-words" :class="tab === t.slug ? 'bg-surface font-semibold' : 'text-ink-muted'">{{ t.label }}</router-link>
    </nav>

    <ErrorMessage v-if="state === 'error'" class="mt-4" :parts="errorParts" prefix="learn-error" data-testid="learn-error" />
    <p v-else-if="state === 'empty'" class="mt-4 text-ink-muted" data-testid="learn-empty">{{ NOTHING_PUBLISHED }}</p>

    <template v-else-if="state === 'list' && (openTemplate || openLesson)">
      <button type="button" class="mt-4 text-sm underline" data-testid="detail-back" @click="openId = null">Back to the list</button>

      <article v-if="openLesson" class="mt-3" data-testid="lesson-detail">
        <h2 class="text-lg font-semibold" data-testid="detail-title">{{ openLesson.title }}</h2>
        <p v-for="(line, i) in openLesson.body" :key="i" class="mt-2" data-testid="lesson-line">{{ line }}</p>
      </article>

      <article v-else class="mt-3" data-testid="strategy-detail">
        <h2 class="text-lg font-semibold" data-testid="detail-title">{{ openTemplate.name }}</h2>
        <p class="mt-1 text-xs text-ink-muted" data-testid="detail-meta">{{ openTemplate.level }} - Market view: {{ openTemplate.views.join(', ') }}</p>
        <p class="mt-2" data-testid="detail-description">{{ openTemplate.description }}</p>
        <router-link
          v-if="platformStrikes" :to="{ path: '/strategy/builder', query: { template: openTemplate.id } }"
          class="mt-2 inline-block text-sm underline" data-testid="open-in-builder">Open in Builder</router-link>
        <template v-if="text">
          <section v-for="[key, heading] in STRATEGY_PARTS" :key="key" class="mt-4" :data-testid="`part-${key}`">
            <h3 class="font-medium">
              {{ heading }}<span v-if="key === 'shape'" class="ml-2 rounded border border-line px-1 text-xs" data-testid="sample-label">{{ SAMPLE_LABEL }}</span>
            </h3>
            <template v-if="key === 'shape'">
              <svg
                :viewBox="`0 0 ${VIEW_W} ${VIEW_W}`" class="mt-2 h-40 w-full max-w-full rounded border border-line" role="img"
                :aria-label="`${SAMPLE_LABEL} payoff shape of ${openTemplate.name}`" data-testid="shape-svg">
                <polyline :points="shapePoints" fill="none" stroke="currentColor" stroke-width="2" vector-effect="non-scaling-stroke" />
              </svg>
              <p class="mt-1 text-xs text-ink-muted" data-testid="sample-note">{{ SAMPLE_NOTE }}</p>
            </template>
            <p v-else class="mt-1" :data-testid="`part-text-${key}`">{{ text[key] }}</p>
          </section>
          <p class="mt-4 text-xs text-ink-muted" data-testid="numbers-note">{{ NUMBERS_NOTE }}</p>
        </template>
      </article>
    </template>

    <template v-else-if="state === 'list'">
      <label class="mt-4 block text-sm">
        <span class="sr-only">Search by title</span>
        <input v-model="query" type="search" placeholder="Search by title" class="w-full rounded border border-line bg-surface p-2" data-testid="learn-search" />
      </label>
      <p v-if="noMatch" class="mt-4 text-ink-muted" data-testid="learn-no-match">{{ NO_MATCH }}</p>

      <template v-if="isEducation">
        <div v-for="g in groups" :key="g.level" class="mt-5" :data-testid="`level-${g.level}`">
          <h2 class="text-lg font-semibold" data-testid="level-title">{{ g.level }}</h2>
          <ul class="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2">
            <li v-for="t in g.items" :key="t.id" class="rounded border border-line bg-surface p-3" data-testid="template-card">
              <h3 class="font-medium" data-testid="template-name">{{ t.name }}</h3>
              <p class="mt-1 text-sm" data-testid="template-description">{{ t.description }}</p>
              <p class="mt-1 text-xs text-ink-muted" data-testid="template-views">Market view: {{ t.views.join(', ') }}</p>
              <button type="button" class="mt-2 text-sm underline" data-testid="card-open" @click="openId = t.id">Read more</button>
            </li>
          </ul>
        </div>
      </template>
      <ul v-else class="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <li v-for="l in filteredLessons" :key="l.id" class="rounded border border-line bg-surface p-3" data-testid="lesson-card">
          <h3 class="font-medium" data-testid="lesson-title">{{ l.title }}</h3>
          <p class="mt-1 text-sm" data-testid="lesson-summary">{{ l.summary }}</p>
          <button type="button" class="mt-2 text-sm underline" data-testid="card-open" @click="openId = l.id">Read more</button>
        </li>
      </ul>
    </template>
  </section>
</template>
