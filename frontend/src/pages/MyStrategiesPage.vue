<!-- My Strategies and Completed Strategies (W-109; REQ-009 AC-2, REQ-038 AC-5, OQ-13). Display only: the user's saved
     strategies from GET /api/strategies (underlying, status, last saved), each with a link to the Strategy Builder and
     to Execute Strategy for that id. No money figure is computed or shown. A status the page does not know is shown
     as the API sent it. The Completed page lists only statuses in COMPLETED_STATUSES; the store holds only 'draft'
     today (alembic 0008 CHECK), so that list is empty and the page says so instead of offering a filter it cannot back. -->
<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api, { NEUTRAL_PARTS } from '@/services/api'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import { istTime } from '@/lib/displayFormat'
import { fetchSavedLegs } from '@/lib/saveDraft'
import { buildDraft } from '@/lib/legPicker'

const COMPLETED_STATUSES = []

const route = useRoute()
const router = useRouter()
const completedOnly = computed(() => route.meta.completedOnly === true)
const rows = ref([])
const loaded = ref(false)
const busy = ref(false)
const notOpenable = ref(null)
const errorParts = ref(null)

const shown = computed(() => (completedOnly.value ? rows.value.filter((r) => COMPLETED_STATUSES.includes(r.status)) : rows.value))

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

// The Builder opens a draft from its `draft` link; the legs are rebuilt from the stored strategy, nothing is re-captured.
async function openInBuilder(id) {
  if (busy.value) return
  busy.value = true
  errorParts.value = null
  notOpenable.value = null
  try {
    const legs = await fetchSavedLegs(api, id)
    const draft = buildDraft(legs)
    // buildDraft drops a leg with no planned entry; a link that silently loses legs is refused, not opened.
    if (!draft || draft.legs.length !== legs.length) {
      notOpenable.value = id
      return
    }
    await router.push({ path: '/strategy/builder', query: { draft: JSON.stringify(draft) } })
  } catch (e) {
    errorParts.value = e?.parts ?? NEUTRAL_PARTS
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
    <ul v-else class="mt-4 divide-y divide-line rounded border border-line bg-surface" data-testid="strategy-list">
      <li v-for="s in shown" :key="s.id" class="flex flex-wrap items-center gap-3 px-3 py-2 text-sm" data-testid="strategy-row" :data-strategy-id="s.id">
        <span>Strategy {{ s.id }}</span>
        <span data-testid="row-underlying">{{ s.underlying }}</span>
        <span data-testid="row-status">{{ s.status }}</span>
        <span class="text-ink-muted">last saved {{ istTime(s.updated_at) }}</span>
        <button type="button" class="underline" :disabled="busy" :data-testid="`open-builder-${s.id}`" @click="openInBuilder(s.id)">Open in Builder</button>
        <router-link :to="`/strategy/${s.id}/execute`" class="underline" :data-testid="`open-execute-${s.id}`">Execute Strategy</router-link>
        <span v-if="notOpenable === s.id" class="text-ink-muted" data-testid="not-openable">This strategy has legs without a planned entry, so it cannot be opened in the Builder from here.</span>
      </li>
    </ul>
  </section>
</template>
