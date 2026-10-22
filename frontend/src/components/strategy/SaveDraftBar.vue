<!-- Save Draft and the saved list (W-071; REQ-038 AC-5, ADR-057, ADR-075, ADR-068 item 1, W-024).
     Save Draft POSTs the picked legs (contract id, side, quantity, planned entry + capture time) to /api/strategies; the
     list (GET /api/strategies) reopens a draft (GET /api/strategies/{id}) with the legs exactly as stored: a planned entry
     and its capture time are never re-captured here. Every refusal shows the API's catalogue message (or the neutral one
     when the answer is not a catalogue message); the draft on screen is never cleared by a failure. No number is computed. -->
<script setup>
import { onMounted, ref } from 'vue'
import api, { NEUTRAL_PARTS } from '@/services/api'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import { istTime } from '@/lib/displayFormat'
import { buildSaveBody, canSaveLegs, fetchSavedDraft } from '@/lib/saveDraft'

const props = defineProps({ legs: { type: Array, default: () => [] }, rulesRef: { type: String, default: '' } })
const emit = defineEmits(['open', 'saved'])

const drafts = ref([])
const busy = ref(false)
const savedId = ref(null)
const errorParts = ref(null)

async function refresh() {
  try {
    drafts.value = (await api.get('/strategies')).data.strategies
  } catch (e) {
    errorParts.value = e?.parts ?? NEUTRAL_PARTS
  }
}

async function save() {
  if (busy.value || !canSaveLegs(props.legs)) return
  busy.value = true
  savedId.value = null
  errorParts.value = null
  try {
    const res = await api.post('/strategies', buildSaveBody(props.legs, props.rulesRef))
    if (!Number.isInteger(res.data?.id)) throw new Error('unreadable answer') // fail closed: not a saved draft
    savedId.value = res.data.id
    emit('saved', res.data.id, Number.isInteger(res.data.revision) ? res.data.revision : null)
    await refresh()
  } catch (e) {
    errorParts.value = e?.parts ?? NEUTRAL_PARTS
  } finally {
    busy.value = false
  }
}

async function open(id) {
  if (busy.value) return
  busy.value = true
  errorParts.value = null
  try {
    const { legs, revision } = await fetchSavedDraft(api, id) // throws when unreadable: the draft on screen stays
    emit('open', legs, id, revision)
  } catch (e) {
    errorParts.value = e?.parts ?? NEUTRAL_PARTS
  } finally {
    busy.value = false
  }
}

onMounted(refresh)
</script>

<template>
  <section class="mt-4 rounded border border-line bg-surface p-4" data-testid="save-draft-bar">
    <div class="flex flex-wrap items-center gap-3 text-sm">
      <button
type="button" data-testid="save-draft" class="rounded border border-line px-3 py-1"
              :disabled="busy || !canSaveLegs(legs)" @click="save">Save Draft</button>
      <span v-if="savedId" data-testid="save-status" :data-saved-id="savedId">Draft {{ savedId }} saved.</span>
      <span v-else data-testid="save-status" data-saved-id=""></span>
    </div>
    <ErrorMessage v-if="errorParts" class="mt-2" :parts="errorParts" compact prefix="save-error" data-testid="save-error" />
    <h2 class="mt-3 text-sm font-medium">Saved drafts</h2>
    <ul v-if="drafts.length" class="mt-1 text-sm" data-testid="saved-drafts">
      <li v-for="d in drafts" :key="d.id" class="flex flex-wrap items-center gap-2" data-testid="saved-draft-row">
        <span>Draft {{ d.id }}, {{ d.underlying }}, updated {{ istTime(d.updated_at) }}</span>
        <button type="button" :data-testid="`open-draft-${d.id}`" class="underline" :disabled="busy" @click="open(d.id)">Open</button>
      </li>
    </ul>
  </section>
</template>
