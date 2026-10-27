<!-- Save, Save As and the saved list (W-071, W-157; REQ-038 AC-5, REQ-134 AC-1/AC-2, ADR-057, ADR-075, ADR-068 item 1).
     The first Save of a strategy that has never been saved asks for a name, prefilled (copies Sensibull screen 116: "Save New
     Strategy", a Strategy Name field with a character count, Cancel and Save). Save on an open saved strategy sends PUT
     /api/strategies/{id} with the revision THIS PAGE loaded and asks nothing (REQ-134 AC-2); Save As asks for a name
     prefilled "<name> copy", POSTs a new strategy and opens the copy; the original is never sent. The list (GET /api/strategies)
     reopens a draft (GET /api/strategies/{id}) with the legs exactly as stored: a planned entry and its capture time are never
     re-captured here. Every refusal shows the API's catalogue message (an empty name: "Give the strategy a name", from the API,
     not retyped); the draft on screen is never cleared by a failure. A name is shown as text, never as HTML. No number is computed. -->
<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useOutsideClose } from '@/composables/useOutsideClose'
import api, { NEUTRAL_PARTS } from '@/services/api'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import Icon from '@/components/common/Icon.vue'
import EmptyState from '@/components/states/EmptyState.vue'
import Tabs from '@/components/common/Tabs.vue'
import DraftDelete from '@/components/strategy/DraftDelete.vue'
import DraftDeleteStatus from '@/components/strategy/DraftDeleteStatus.vue'
import { istTime } from '@/lib/displayFormat'
import { CLEAR_UNDO_MS } from '@/lib/legEdit'
import { newestEntry, newestSeq, restoreEntry, useDeleteFlow } from '@/lib/strategyActivity'
import {
  STRATEGY_NAME_DEFAULT, STRATEGY_NAME_MAX, buildSaveBody, buildUpdateBody, canSaveLegs, fetchSavedDraft, plainName, renameStrategy, saveAsName, strategyLabel,
} from '@/lib/saveDraft'

const props = defineProps({
  legs: { type: Array, default: () => [] },
  rulesRef: { type: String, default: '' },
  // the saved strategy this screen is editing ({ id, revision, name } as the page loaded or saved it), or null for a never-saved one
  current: { type: Object, default: null },
})
const emit = defineEmits(['open', 'saved', 'renamed', 'deleted'])

const drafts = ref([])
const busy = ref(false)
const savedId = ref(null)
const savedName = ref(null)
const errorParts = ref(null)
const asking = ref(null) // null | 'save' | 'save-as': the name field is open for that action
const nameText = ref('')
// W-192 (ADR-193 UI-108, UI-111..UI-114): the action row's "..." menu and the bottom tabs card. The Saved tab lists the 10
// most recent rows (UI-112) of the GET /api/strategies list, narrowed by a plain text match on name or underlying. The server lists
// by id ASCENDING, so the tab sorts by updated_at, newest first (ties: higher id first) before cutting at 10; taking the first 10
// in server order showed the 10 OLDEST and hid a just-saved draft (CI #581, strategy-save-draft.spec.ts).
const menuOpen = ref(false)
const menuRoot = ref(null)
const menuButton = ref(null)
async function closeMenu() {
  if (!menuOpen.value) return
  menuOpen.value = false
  await nextTick()
  menuButton.value?.focus?.()
}
useOutsideClose(() => menuOpen.value, () => menuRoot.value, closeMenu)
const BUILDER_TABS = [{ key: 'ready-made', label: 'Ready-made' }, { key: 'positions', label: 'Positions' }, { key: 'saved', label: 'Saved' }, { key: 'tracked', label: 'Tracked' }]
const SAVED_TAB_ROWS = 10
const tab = ref('ready-made')
const search = ref('')
const recentDrafts = computed(() => {
  const q = search.value.trim().toLowerCase()
  const hit = (d) => !q || `${strategyLabel(d, `Draft ${d.id}`)} ${d.underlying ?? ''}`.toLowerCase().includes(q)
  const at = (d) => {
    const ms = Date.parse(d.updated_at)
    return Number.isFinite(ms) ? ms : -Infinity // an unreadable time sorts last, never first
  }
  const newestFirst = (a, b) => (at(b) - at(a)) || (b.id - a.id)
  return drafts.value.filter(hit).slice().sort(newestFirst).slice(0, SAVED_TAB_ROWS)
})
const menuDo = (fn) => {
  closeMenu()
  fn()
}

// REQ-070 AC-6: Delete with Undo, one flow shared with My Strategies. When the deleted strategy is the one open, the Builder is told.
let deletedOpenId = null // the id of the OPEN strategy this bar deleted: its Undo re-opens it in the Builder (same id)
const deleteFlow = useDeleteFlow(api, {
  onRemoved: (id) => { drafts.value = drafts.value.filter((d) => d.id !== id) },
  onDeleted: (id) => { if (props.current?.id === id) { deletedOpenId = id; emit('deleted', id) } },
  onBack: async (id, body) => {
    if (deletedOpenId === id && Number.isInteger(body?.revision)) {
      deletedOpenId = null
      emit('saved', id, body.revision, typeof body.name === 'string' ? body.name : null) // the Builder holds it again: the next Save updates it
    }
    await refresh()
  },
  reload: () => refresh(),
})

// REQ-070 AC-4: Undo after a meaningful save. The save of a saved strategy wrote one history entry holding the configuration it
// replaced; that entry is offered back for CLEAR_UNDO_MS (the Clear-all window). A save that wrote no entry offers nothing.
const saveUndo = ref(null) // { id, seq, revision } or null
let saveUndoTimer = null
function dropSaveUndo() {
  clearTimeout(saveUndoTimer)
  saveUndo.value = null
}
// Any new leg list (an edit, a restore, an open) supersedes the Undo: it can never restore over newer legs. "New" means different legs
// as a save would send them; the Builder's own read of the shape name replaces the array with the same legs and must not drop it.
const sentLegs = (legs) => JSON.stringify(legs.map((l) => [l.contract_id, l.action, l.lots, l.lot_size, l.planned_entry ?? null, l.captured_at ?? null, l.typed === true]))
watch(() => sentLegs(props.legs), dropSaveUndo)
onBeforeUnmount(() => {
  dropSaveUndo()
  deleteFlow.dispose()
})

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
  dropSaveUndo()
  try {
    const before = await newestSeq(api, id) // null = unreadable: no Undo is offered
    const res = await api.put(`/strategies/${id}`, buildUpdateBody(props.legs, props.rulesRef, revision))
    const next = done(res.data)
    emit('saved', res.data.id, next, savedName.value)
    await offerUndo(id, before, next)
    await refresh()
  } catch (e) {
    errorParts.value = e?.parts ?? NEUTRAL_PARTS
  } finally {
    busy.value = false
  }
}

async function offerUndo(id, before, revision) {
  if (before === null || !Number.isInteger(revision)) return
  const after = await newestEntry(api, id)
  if (after === null || after.seq <= before) return // the save wrote no entry (nothing changed): nothing to undo
  if (after.restorable !== true) return // the server says this entry is not a restore target: no Undo (fail closed)
  dropSaveUndo()
  saveUndo.value = { id, seq: after.seq, revision }
  saveUndoTimer = setTimeout(dropSaveUndo, CLEAR_UNDO_MS)
}

async function undoSave() {
  const held = saveUndo.value
  if (!held || busy.value) return
  busy.value = true
  errorParts.value = null
  dropSaveUndo()
  try {
    const { legs, revision, name } = await restoreEntry(api, held.id, held.seq, held.revision)
    emit('open', legs, held.id, revision, name)
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
  nameText.value = saveAsName(props.current.name)
}

function renameOpen() {
  if (busy.value || !props.current) return
  asking.value = 'rename'
  nameText.value = plainName(props.current.name) ?? ''
}

function cancelName() {
  asking.value = null
  errorParts.value = null
}

// The name field's Save: POST a NEW strategy with the typed name (the server refuses an empty or over-long one). Save As then
// opens the copy; the original strategy is never sent.
// REQ-134 AC-3: Rename of the open saved strategy: PATCH with the revision THIS PAGE loaded (read BEFORE the await); the shown
// name comes from the reply. Legs, revision and status are untouched.
async function confirmRename() {
  const { id, revision } = props.current
  busy.value = true
  errorParts.value = null
  try {
    const res = await renameStrategy(api, id, revision, nameText.value)
    asking.value = null
    emit('renamed', id, res.name)
    await refresh()
  } catch (e) {
    errorParts.value = e?.parts ?? NEUTRAL_PARTS
  } finally {
    busy.value = false
  }
}

async function confirmName() {
  if (asking.value === 'rename' && props.current && !busy.value) return confirmRename()
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
  <section data-testid="save-draft-bar">
    <div class="-mt-4 flex h-12 items-center gap-2 rounded-b-lg border border-line bg-surface px-3 text-sm" data-testid="action-row">
      <slot name="add-edit" />
      <button
type="button" data-testid="save-draft" class="rounded bg-accent px-3 py-1 font-medium text-white disabled:opacity-50"
              :disabled="!canSave" @click="save">Save</button>
      <span ref="menuRoot" class="relative" @keydown.esc="closeMenu">
        <button
ref="menuButton" type="button" class="rounded border border-line px-2 py-1" aria-haspopup="menu" :aria-expanded="menuOpen ? 'true' : 'false'"
                aria-label="More actions" data-testid="more-menu" @click="menuOpen ? closeMenu() : (menuOpen = true)"><Icon name="more" :size="16" /></button>
        <span v-show="menuOpen" role="menu" class="absolute left-0 top-full z-20 mt-1 flex w-44 flex-col items-start gap-1 rounded border border-line bg-surface p-2 shadow" data-testid="more-menu-panel">
          <button
v-if="current" type="button" role="menuitem" data-testid="save-as"
                  :disabled="!canSave" @click="menuDo(saveAs)">Save As</button>
          <button
v-if="current" type="button" role="menuitem" data-testid="rename-open"
                  :disabled="busy" @click="menuDo(renameOpen)">Rename</button>
          <slot name="menu" :close="closeMenu" />
        </span>
      </span>
      <span v-if="current" class="ml-auto truncate text-ink-muted" data-testid="current-name">{{ strategyLabel(current, `Draft ${current.id}`) }}</span>
      <span v-if="savedId" class="truncate" data-testid="save-status" :data-saved-id="savedId">{{ strategyLabel({ name: savedName }, `Draft ${savedId}`) }} saved.</span>
      <span v-else data-testid="save-status" data-saved-id=""></span>
    </div>
    <slot name="after-actions" />
    <form v-if="asking" class="mt-2 text-sm" data-testid="name-form" :data-mode="asking" @submit.prevent="confirmName">
      <label class="block font-medium" for="strategy-name">{{ asking === 'save-as' ? 'Save As' : asking === 'rename' ? 'Rename' : 'Save New Strategy' }}: Strategy Name</label>
      <input
id="strategy-name" v-model="nameText" data-testid="name-input" type="text" class="mt-1 rounded border border-line px-2 py-1"
             :maxlength="STRATEGY_NAME_MAX" autocomplete="off" />
      <p class="text-xs" :class="nameText.length > STRATEGY_NAME_MAX ? 'text-warn' : 'text-ink-muted'" data-testid="name-count">{{ nameText.length }}/{{ STRATEGY_NAME_MAX }} characters</p>
      <div class="mt-1 flex gap-2">
        <button type="button" data-testid="name-cancel" class="rounded border border-line px-3 py-1" @click="cancelName">Cancel</button>
        <button type="submit" data-testid="name-confirm" class="rounded border border-line px-3 py-1" :disabled="busy">Save</button>
      </div>
    </form>
    <p v-if="saveUndo" class="mt-2 flex items-center gap-2 text-sm" data-testid="save-undo-toast">
      <span>Saved.</span>
      <button type="button" class="underline" :disabled="busy" data-testid="save-undo" @click="undoSave">Undo</button>
    </p>
    <ErrorMessage v-if="errorParts" class="mt-2" :parts="errorParts" compact prefix="save-error" data-testid="save-error" />

    <div class="mt-4 rounded-lg border border-line bg-surface p-3 text-sm" data-testid="builder-tabs" :data-tab="tab">
      <Tabs v-model="tab" :tabs="BUILDER_TABS" label="Strategy sources" />
      <div v-show="tab === 'ready-made'" class="mt-3" data-testid="tab-panel-ready-made"><slot name="ready-made" /></div>
      <!-- UI-113 / UI-114: the shared EmptyState (PR-1); no broker is named -->
      <div v-show="tab === 'positions'" class="mt-3" data-testid="tab-panel-positions"><EmptyState icon="briefcase" title="Coming soon: Positions" message="Open positions you hold will appear here, to analyse in the Builder." /></div>
      <div v-show="tab === 'saved'" class="mt-3" data-testid="tab-panel-saved">
        <input v-model="search" type="search" class="h-10 w-full rounded border border-line px-2" placeholder="Search name or underlying" aria-label="Search name or underlying" data-testid="saved-search" />
        <h2 class="sr-only">Saved drafts</h2>
        <ul v-if="recentDrafts.length" class="mt-2" data-testid="saved-drafts">
          <li v-for="d in recentDrafts" :key="d.id" class="flex min-h-10 items-center gap-2 border-b border-line py-1" data-testid="saved-draft-row" :data-current="current?.id === d.id ? 'true' : 'false'">
            <Icon v-if="current?.id === d.id" name="check" :size="14" />
            <span class="min-w-0 flex-1 truncate" data-testid="saved-draft-name">{{ strategyLabel(d, `Draft ${d.id}`) }}, {{ d.underlying }}, updated {{ istTime(d.updated_at) }}</span>
            <button type="button" :data-testid="`open-draft-${d.id}`" class="text-accent" :disabled="busy" @click="open(d.id)">Open</button>
            <DraftDelete :row="d" :flow="deleteFlow" />
          </li>
        </ul>
        <p v-else class="mt-2 text-ink-muted" data-testid="saved-empty">{{ search.trim() ? 'No saved strategy matches.' : 'No saved strategies yet.' }}</p>
        <router-link to="/strategies/my-strategies" class="mt-2 inline-block text-accent" data-testid="saved-show-all">Show all in My Strategies</router-link>
      </div>
      <div v-show="tab === 'tracked'" class="mt-3" data-testid="tab-panel-tracked"><slot name="tracked"><EmptyState icon="pulse" title="No tracked strategies here" message="Strategies you track appear in My Strategies." /></slot></div>
    </div>
    <DraftDeleteStatus :flow="deleteFlow" />
  </section>
</template>
