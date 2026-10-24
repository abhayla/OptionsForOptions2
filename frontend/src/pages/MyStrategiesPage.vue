<!-- My Strategies and Completed Strategies (W-109, W-157; REQ-009 AC-2, REQ-038 AC-5, REQ-134 AC-3/AC-4/AC-5, OQ-13). The
     user's saved strategies from GET /api/strategies: name (quoted user words, shown without the API quotes, as text), underlying,
     first leg + "and N more", status, last saved and the tracked state (copies Sensibull screen 117's list line); a search box
     filters by name as typed; Rename calls PATCH /api/strategies/{id}/name; each row links to the Strategy Builder
     (`?strategy=<id>`) and to Execute Strategy for that id. No money figure is computed or shown. A status the page does not know is shown
     as the API sent it. The Completed page lists only statuses in COMPLETED_STATUSES; the store holds only 'draft'
     today (alembic 0008 CHECK), so that list is empty and the page says so instead of offering a filter it cannot back. -->
<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api, { NEUTRAL_PARTS } from '@/services/api'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import { istTime } from '@/lib/displayFormat'
import { STRATEGY_NAME_MAX, legsLine, noMatchText, plainName, searchStrategies, strategyLabel, trackedText } from '@/lib/saveDraft'
import { useOrderPath } from '@/lib/orderPath'

const COMPLETED_STATUSES = []

// W-121 (REQ-073 AC-6, ADR-165): the Execute link is absent (not disabled) unless the server said the order path is on.
const orderPathOn = useOrderPath()

const route = useRoute()
const router = useRouter()
const completedOnly = computed(() => route.meta.completedOnly === true)
const rows = ref([])
const loaded = ref(false)
const busy = ref(false)
const query = ref('') // REQ-134 AC-4: the search text, matched in the browser against the names of the user's own list
const renaming = ref(null) // { id, text } while a row's name field is open
const renameError = ref(null) // { id, parts }
const errorParts = ref(null)

const shown = computed(() => (completedOnly.value ? rows.value.filter((r) => COMPLETED_STATUSES.includes(r.status)) : rows.value))
const visible = computed(() => searchStrategies(shown.value, query.value))

onMounted(async () => {
  try {
    const list = (await api.get('/strategies')).data?.strategies
    rows.value = Array.isArray(list) ? list : []
  } catch (e) {
    errorParts.value = e?.parts ?? NEUTRAL_PARTS
  } finally {
    loaded.value = true
  }
})

// REQ-134 AC-5: the Builder opens the saved strategy from its `strategy` link and reads the saved copy itself (legs, planned
// entries and revision as saved), so a reload opens it again and Save there updates this strategy.
async function openInBuilder(id) {
  if (busy.value) return
  busy.value = true
  errorParts.value = null
  try {
    await router.push({ path: '/strategy/builder', query: { strategy: String(id) } })
  } catch (e) {
    errorParts.value = e?.parts ?? NEUTRAL_PARTS
  } finally {
    busy.value = false
  }
}

// REQ-134 AC-3: rename in the list. The list row carries no revision, so the strategy is read once for the one it has now and
// the name goes to PATCH /strategies/{id}/name with it (a rename never changes legs, status, revision or last-saved time).
function startRename(row) {
  renaming.value = { id: row.id, text: plainName(row.name) ?? '' }
  renameError.value = null
}
async function confirmRename(row) {
  if (busy.value || !renaming.value || renaming.value.id !== row.id) return
  const { id, text } = renaming.value
  busy.value = true
  renameError.value = null
  try {
    const revision = (await api.get(`/strategies/${id}`)).data?.revision
    if (!Number.isInteger(revision)) throw new Error('unreadable answer') // fail closed: no rename is sent
    const done = (await api.patch(`/strategies/${id}/name`, { name: text, expected_revision: revision })).data
    if (typeof done?.name !== 'string') throw new Error('unreadable answer')
    rows.value = rows.value.map((r) => (r.id === id ? { ...r, name: done.name } : r)) // only the name changes in the row
    renaming.value = null
  } catch (e) {
    renameError.value = { id, parts: e?.parts ?? NEUTRAL_PARTS }
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section :data-testid="completedOnly ? 'completed-strategies' : 'my-strategies'">
    <p class="text-xs text-ink-muted" data-testid="page-parent">{{ route.meta.parent }}</p>
    <h1 class="text-xl font-semibold" data-testid="page-title">{{ route.meta.title }}</h1>
    <ErrorMessage v-if="errorParts" class="mt-3" :parts="errorParts" compact prefix="list-error" data-testid="list-error" />
    <p v-else-if="!loaded" class="mt-3 text-ink-muted" data-testid="list-loading">Loading...</p>
    <p v-else-if="!shown.length" class="mt-3 text-ink-muted" data-testid="list-empty">
      {{ completedOnly ? 'No strategy is completed yet.' : 'You have no saved strategies yet. Save a draft from the Strategy Builder and it will appear here.' }}
    </p>
    <template v-else>
      <input
v-model="query" type="search" class="mt-4 w-full rounded border border-line px-3 py-2 text-sm" data-testid="strategy-search"
             placeholder="Search name" aria-label="Search saved strategies by name" autocomplete="off" />
      <p v-if="!visible.length" class="mt-3 text-ink-muted" data-testid="search-no-match">{{ noMatchText(query) }}</p>
      <ul v-else class="mt-4 divide-y divide-line rounded border border-line bg-surface" data-testid="strategy-list">
        <li v-for="s in visible" :key="s.id" class="flex flex-wrap items-center gap-3 px-3 py-2 text-sm" data-testid="strategy-row" :data-strategy-id="s.id">
          <span class="font-medium" data-testid="row-name">{{ strategyLabel(s, `Strategy ${s.id}`) }}</span>
          <span data-testid="row-underlying">{{ s.underlying }}</span>
          <span v-if="legsLine(s)" class="text-ink-muted" data-testid="row-legs">{{ legsLine(s) }}</span>
          <span data-testid="row-status">{{ s.status }}</span>
          <span class="text-ink-muted" data-testid="row-saved">last saved {{ istTime(s.updated_at) }}</span>
          <span v-if="trackedText(s.tracked)" class="text-ink-muted" data-testid="row-tracked">{{ trackedText(s.tracked) }}</span>
          <button type="button" class="underline" :disabled="busy" :data-testid="`open-builder-${s.id}`" @click="openInBuilder(s.id)">Open in Builder</button>
          <button v-if="'name' in s" type="button" class="underline" :disabled="busy" :data-testid="`rename-${s.id}`" @click="startRename(s)">Rename</button>
          <router-link v-if="orderPathOn" :to="`/strategy/${s.id}/execute`" class="underline" :data-testid="`open-execute-${s.id}`">Execute Strategy</router-link>
          <form v-if="renaming && renaming.id === s.id" class="flex w-full flex-wrap items-center gap-2" data-testid="rename-form" @submit.prevent="confirmRename(s)">
            <input v-model="renaming.text" type="text" class="rounded border border-line px-2 py-1" data-testid="rename-input" :maxlength="STRATEGY_NAME_MAX" aria-label="New strategy name" autocomplete="off" />
            <button type="submit" class="underline" :disabled="busy" data-testid="rename-save">Save</button>
            <button type="button" class="underline" data-testid="rename-cancel" @click="renaming = null">Cancel</button>
          </form>
          <ErrorMessage v-if="renameError && renameError.id === s.id" class="w-full" :parts="renameError.parts" compact prefix="rename-error" data-testid="rename-error" />
        </li>
      </ul>
    </template>
  </section>
</template>
