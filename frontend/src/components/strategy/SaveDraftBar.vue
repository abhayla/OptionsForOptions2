<!-- Save, Save As and the saved list (W-071, W-157; REQ-038 AC-5, REQ-134 AC-1/AC-2, ADR-057, ADR-075, ADR-068 item 1).
     The first Save of a strategy that has never been saved asks for a name, prefilled (copies Sensibull screen 116: "Save New
     Strategy", a Strategy Name field with a character count, Cancel and Save). Save on an open saved strategy sends PUT
     /api/strategies/{id} with the revision THIS PAGE loaded and asks nothing (REQ-134 AC-2); Save As asks for a name
     prefilled "<name> copy", POSTs a new strategy and opens the copy; the original is never sent. The list (GET /api/strategies)
     reopens a draft (GET /api/strategies/{id}) with the legs exactly as stored: a planned entry and its capture time are never
     re-captured here. Every refusal shows the API's catalogue message (an empty name: "Give the strategy a name", from the API,
     not retyped); the draft on screen is never cleared by a failure. A name is shown as text, never as HTML. No number is computed. -->
<script setup>
import { computed, onMounted, ref } from 'vue'
import api, { NEUTRAL_PARTS } from '@/services/api'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import { istTime } from '@/lib/displayFormat'
import {
  SAVE_AS_SUFFIX, STRATEGY_NAME_DEFAULT, STRATEGY_NAME_MAX, buildSaveBody, buildUpdateBody, canSaveLegs, fetchSavedDraft, plainName, strategyLabel,
} from '@/lib/saveDraft'

const props = defineProps({
  legs: { type: Array, default: () => [] },
  rulesRef: { type: String, default: '' },
  // the saved strategy this screen is editing ({ id, revision, name } as the page loaded or saved it), or null for a never-saved one
  current: { type: Object, default: null },
})
const emit = defineEmits(['open', 'saved'])

const drafts = ref([])
const busy = ref(false)
const savedId = ref(null)
const savedName = ref(null)
const errorParts = ref(null)
const asking = ref(null) // null | 'save' | 'save-as': the name field is open for that action
const nameText = ref('')

const canSave = computed(() => !busy.value && canSaveLegs(props.legs))

async function refresh() {
  try {
    drafts.value = (await api.get('/strategies')).data.strategies
  } catch (e) {
    errorParts.value = e?.parts ?? NEUTRAL_PARTS
  }
}

function done(data) {
  if (!Number.isInteger(data?.id)) throw new Error('unreadable answer') // fail closed: not a saved draft
  savedId.value = data.id
  savedName.value = typeof data.name === 'string' ? data.name : null
  return Number.isInteger(data.revision) ? data.revision : null
}

// Save: an open saved strategy is updated with the revision the page loaded (read BEFORE the await); a never-saved one asks a name first.
async function save() {
  if (!canSave.value) return
  if (!props.current) {
    asking.value = 'save'
    nameText.value = STRATEGY_NAME_DEFAULT
    return
  }
  const { id, revision } = props.current
  busy.value = true
  savedId.value = null
  errorParts.value = null
  try {
    const res = await api.put(`/strategies/${id}`, buildUpdateBody(props.legs, props.rulesRef, revision))
    const next = done(res.data)
    emit('saved', res.data.id, next, savedName.value)
    await refresh()
  } catch (e) {
    errorParts.value = e?.parts ?? NEUTRAL_PARTS
  } finally {
    busy.value = false
  }
}

function saveAs() {
  if (!canSave.value || !props.current) return
  asking.value = 'save-as'
  nameText.value = `${plainName(props.current.name) ?? STRATEGY_NAME_DEFAULT}${SAVE_AS_SUFFIX}`
}

function cancelName() {
  asking.value = null
  errorParts.value = null
}

// The name field's Save: POST a NEW strategy with the typed name (the server refuses an empty or over-long one). Save As then
// opens the copy; the original strategy is never sent.
async function confirmName() {
  if (busy.value || !asking.value || !canSaveLegs(props.legs)) return
  const mode = asking.value
  const legs = props.legs
  busy.value = true
  savedId.value = null
  errorParts.value = null
  try {
    const res = await api.post('/strategies', buildSaveBody(legs, props.rulesRef, nameText.value))
    const revision = done(res.data)
    asking.value = null
    if (mode === 'save-as') emit('open', legs, res.data.id, revision, savedName.value)
    else emit('saved', res.data.id, revision, savedName.value)
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
    const { legs, revision, name } = await fetchSavedDraft(api, id) // throws when unreadable: the draft on screen stays
    asking.value = null
    emit('open', legs, id, revision, name)
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
              :disabled="!canSave" @click="save">Save Draft</button>
      <button
v-if="current" type="button" data-testid="save-as" class="rounded border border-line px-3 py-1"
              :disabled="!canSave" @click="saveAs">Save As</button>
      <span v-if="savedId" data-testid="save-status" :data-saved-id="savedId">{{ strategyLabel({ name: savedName }, `Draft ${savedId}`) }} saved.</span>
      <span v-else data-testid="save-status" data-saved-id=""></span>
    </div>
    <form v-if="asking" class="mt-2 text-sm" data-testid="name-form" :data-mode="asking" @submit.prevent="confirmName">
      <label class="block font-medium" for="strategy-name">{{ asking === 'save-as' ? 'Save As' : 'Save New Strategy' }}: Strategy Name</label>
      <input
id="strategy-name" v-model="nameText" data-testid="name-input" type="text" class="mt-1 rounded border border-line px-2 py-1"
             :maxlength="STRATEGY_NAME_MAX" autocomplete="off" />
      <p class="text-xs text-ink-muted" data-testid="name-count">{{ nameText.length }}/{{ STRATEGY_NAME_MAX }} characters</p>
      <div class="mt-1 flex gap-2">
        <button type="button" data-testid="name-cancel" class="rounded border border-line px-3 py-1" @click="cancelName">Cancel</button>
        <button type="submit" data-testid="name-confirm" class="rounded border border-line px-3 py-1" :disabled="busy">Save</button>
      </div>
    </form>
    <ErrorMessage v-if="errorParts" class="mt-2" :parts="errorParts" compact prefix="save-error" data-testid="save-error" />
    <h2 class="mt-3 text-sm font-medium">Saved drafts</h2>
    <ul v-if="drafts.length" class="mt-1 text-sm" data-testid="saved-drafts">
      <li v-for="d in drafts" :key="d.id" class="flex flex-wrap items-center gap-2" data-testid="saved-draft-row">
        <span data-testid="saved-draft-name">{{ strategyLabel(d, `Draft ${d.id}`) }}</span>
        <span>{{ d.underlying }}, updated {{ istTime(d.updated_at) }}</span>
        <button type="button" :data-testid="`open-draft-${d.id}`" class="underline" :disabled="busy" @click="open(d.id)">Open</button>
      </li>
    </ul>
  </section>
</template>
