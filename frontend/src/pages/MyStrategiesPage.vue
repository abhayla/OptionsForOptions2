<!-- My Strategies and Completed Strategies (W-109, W-157; REQ-009 AC-2, REQ-038 AC-5, REQ-134 AC-3/AC-4/AC-5, OQ-13). The
     user's saved strategies from GET /api/strategies: name (quoted user words, shown without the API quotes, as text), underlying,
     first leg + "and N more", status, last saved and the tracked state (copies Sensibull screen 117's list line); a search box
     filters by name as typed; Rename calls PATCH /api/strategies/{id}/name; each row links to the Strategy Builder
     (`?strategy=<id>`) and to Execute Strategy for that id. No money figure is computed or shown. A status the page does not know is shown
     as the API sent it. The Completed page lists only statuses in COMPLETED_STATUSES; the store holds only 'draft'
     today (alembic 0008 CHECK), so that list is empty and the page says so instead of offering a filter it cannot back. -->
<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api, { NEUTRAL_PARTS } from '@/services/api'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import EmptyState from '@/components/states/EmptyState.vue'
import DraftDelete from '@/components/strategy/DraftDelete.vue'
import DraftDeleteStatus from '@/components/strategy/DraftDeleteStatus.vue'
import { istTime } from '@/lib/displayFormat'
import { STRATEGY_NAME_MAX, legsLine, noMatchText, plainName, renameStrategy, searchStrategies, strategyLabel, trackedText } from '@/lib/saveDraft'
import { useOrderPath } from '@/lib/orderPath'
import { useDeleteFlow } from '@/lib/strategyActivity'

const COMPLETED_STATUSES = []
// Owner 2026-10-30 (Sensibull 117): one column grid shared by the header row and every strategy row, so columns line up
const COLS = 'grid-cols-[minmax(0,1fr)_4rem_minmax(0,2.4fr)_3.5rem_11rem_5.5rem_17rem]'
const HEADS = ['Name', 'Index', 'Legs', 'Status', 'Last saved', 'Tracking', '']

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

// User test 2026-10-30 (U2): newest save first, as Home's "Recent strategies" lists them (ISO times sort as text)
const newestFirst = (list) => [...list].sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at)))
const shown = computed(() => newestFirst(completedOnly.value ? rows.value.filter((r) => COMPLETED_STATUSES.includes(r.status)) : rows.value))
const visible = computed(() => searchStrategies(shown.value, query.value))

async function loadList() {
  try {
    const list = (await api.get('/strategies')).data?.strategies
    rows.value = Array.isArray(list) ? list : []
  } catch (e) {
    errorParts.value = e?.parts ?? NEUTRAL_PARTS
  } finally {
    loaded.value = true
  }
}
onMounted(loadList)

// REQ-070 AC-6: Delete with Undo (one flow, shared with the Builder's saved list). Undo puts the row back from a fresh read.
const deleteFlow = useDeleteFlow(api, {
  onRemoved: (id) => { rows.value = rows.value.filter((r) => r.id !== id) },
  onBack: loadList,
  reload: loadList,
})
onBeforeUnmount(() => deleteFlow.dispose())

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
    const done = await renameStrategy(api, id, revision, text)
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
    <PageHeader :parent="route.meta.parent ?? ''" :title="route.meta.title">
      <template v-if="loaded && shown.length" #actions>
        <input
          v-model="query" type="search" class="field w-64" data-testid="strategy-search"
          placeholder="Search name" aria-label="Search saved strategies by name" autocomplete="off" />
      </template>
    </PageHeader>
    <ErrorMessage v-if="errorParts" :parts="errorParts" compact prefix="list-error" data-testid="list-error" />
    <p v-else-if="!loaded" class="text-sm text-ink-muted" data-testid="list-loading">Loading...</p>
    <EmptyState
      v-else-if="!shown.length" data-testid="list-empty"
      :message="completedOnly ? 'No strategy is completed yet.' : 'You have no saved strategies yet. Save a draft from the Strategy Builder and it will appear here.'"
    />
    <template v-else>
      <p v-if="!visible.length" class="text-sm text-ink-muted" data-testid="search-no-match">{{ noMatchText(query) }}</p>
      <div v-else class="overflow-hidden rounded-lg border border-line bg-surface">
      <div class="grid gap-x-3 border-b border-line bg-surface-muted px-4 py-1.5 text-[11px] leading-4 font-medium text-ink-muted" :class="COLS" aria-hidden="true">
        <span v-for="(h, i) in HEADS" :key="i" :class="{ 'text-right': i === HEADS.length - 1 }">{{ h }}</span>
      </div>
      <ul class="divide-y divide-line" data-testid="strategy-list">
        <li v-for="s in visible" :key="s.id" class="grid min-h-9 items-center gap-x-3 gap-y-1 px-4 py-1.5 text-[13px] hover:bg-surface-muted" :class="COLS" data-testid="strategy-row" :data-strategy-id="s.id">
          <span class="min-w-0 truncate font-medium" :title="strategyLabel(s, `Strategy ${s.id}`)" data-testid="row-name">{{ strategyLabel(s, `Strategy ${s.id}`) }}</span>
          <span data-testid="row-underlying">{{ s.underlying }}</span>
          <span v-if="legsLine(s)" class="min-w-0 truncate text-ink-muted" :title="legsLine(s)" data-testid="row-legs">{{ legsLine(s) }}</span>
          <span v-else aria-hidden="true"></span>
          <span data-testid="row-status">{{ s.status }}</span>
          <span class="num whitespace-nowrap text-ink-muted" data-testid="row-saved">last saved {{ istTime(s.updated_at) }}</span>
          <span v-if="trackedText(s.tracked)" class="truncate text-ink-muted" data-testid="row-tracked">{{ trackedText(s.tracked) }}</span>
          <span v-else aria-hidden="true"></span>
          <span class="flex flex-wrap items-center justify-end gap-x-3 gap-y-1" data-testid="row-actions">
          <button type="button" class="link" :disabled="busy" :data-testid="`open-builder-${s.id}`" @click="openInBuilder(s.id)">Open in Builder</button>
          <button v-if="'name' in s" type="button" class="link" :disabled="busy" :data-testid="`rename-${s.id}`" @click="startRename(s)">Rename</button>
          <DraftDelete :row="s" :flow="deleteFlow" />
          <router-link v-if="orderPathOn" :to="`/strategy/${s.id}/execute`" class="link" :data-testid="`open-execute-${s.id}`">Execute Strategy</router-link>
          </span>
          <form v-if="renaming && renaming.id === s.id" class="col-span-full flex w-full flex-wrap items-center gap-2" data-testid="rename-form" @submit.prevent="confirmRename(s)">
            <input v-model="renaming.text" type="text" class="field" data-testid="rename-input" :maxlength="STRATEGY_NAME_MAX" aria-label="New strategy name" autocomplete="off" />
            <span class="text-xs" :class="renaming.text.length > STRATEGY_NAME_MAX ? 'text-warn' : 'text-ink-muted'" data-testid="rename-count">{{ renaming.text.length }}/{{ STRATEGY_NAME_MAX }}</span>
            <button type="submit" class="btn btn-sm btn-primary" :disabled="busy" data-testid="rename-save">Save</button>
            <button type="button" class="btn btn-sm" data-testid="rename-cancel" @click="renaming = null">Cancel</button>
          </form>
          <ErrorMessage v-if="renameError && renameError.id === s.id" class="col-span-full w-full" :parts="renameError.parts" compact prefix="rename-error" data-testid="rename-error" />
        </li>
      </ul>
      </div>
    </template>
    <DraftDeleteStatus :flow="deleteFlow" />
  </section>
</template>
