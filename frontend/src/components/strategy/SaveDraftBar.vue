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
import Modal from '@/components/common/Modal.vue'
import api, { NEUTRAL_PARTS } from '@/services/api'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import Icon from '@/components/common/Icon.vue'
import EmptyState from '@/components/states/EmptyState.vue'
import Tabs from '@/components/common/Tabs.vue'
import { useHeldFeature } from '@/lib/heldFeatures'
import DraftDelete from '@/components/strategy/DraftDelete.vue'
import DraftDeleteStatus from '@/components/strategy/DraftDeleteStatus.vue'
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'
import { contractName, istTime } from '@/lib/displayFormat'
import { ADD_TO_PAPER_LABEL, PAPER_ADDED_TEXT, addToPaper } from '@/lib/tracking'
import { CLEAR_UNDO_MS } from '@/lib/legEdit'
import { newestEntry, newestSeq, restoreEntry, useDeleteFlow } from '@/lib/strategyActivity'
import {
  STRATEGY_NAME_DEFAULT, STRATEGY_NAME_MAX, buildSaveBody, buildUpdateBody, canSaveLegs, fetchSavedDraft, legsLine, plainName, renameStrategy, saveAsName, strategyLabel, trackedText,
} from '@/lib/saveDraft'

const props = defineProps({
  legs: { type: Array, default: () => [] },
  rulesRef: { type: String, default: '' },
  // the saved strategy this screen is editing ({ id, revision, name } as the page loaded or saved it), or null for a never-saved one
  current: { type: Object, default: null },
  // the name the builder shows for an unsaved strategy (its shape name); an unsaved strategy is saved under it before Add to Paper
  shownName: { type: String, default: '' },
  // GC-TP step 3b1 (ADR-207 (2), F-65): the builder shows a paper strategy's NET position (Drafts Mode). Save, Save As and Add to
  // Paper are not offered and refuse to run: an edit reaches the server only as the reviewed paper orders, never as a plan.
  paperMode: { type: Boolean, default: false },
})
const emit = defineEmits(['open', 'saved', 'renamed', 'deleted', 'paper-added'])

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
const ALL_BUILDER_TABS = [{ key: 'ready-made', label: 'Ready-made' }, { key: 'positions', label: 'Positions' }, { key: 'saved', label: 'Saved Strategies' }, { key: 'tracked', label: 'Paper' }]
// the Ready-made tab is the held feature `platform_strikes`: with the switch off its header is absent (not greyed), and the first tab left opens
const readyMadeOn = useHeldFeature('platform_strikes')
const BUILDER_TABS = computed(() => ALL_BUILDER_TABS.filter((t) => t.key !== 'ready-made' || readyMadeOn.value))
const SAVED_TAB_ROWS = 10
const picked = ref(null)
const tab = computed({
  get: () => (picked.value && BUILDER_TABS.value.some((t) => t.key === picked.value) ? picked.value : BUILDER_TABS.value[0].key),
  set: (key) => { picked.value = key },
})
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

const hasLegs = computed(() => !props.paperMode && canSaveLegs(props.legs)) // Save / Save As need legs that can be saved
// The "..." button is disabled only when the menu would be empty (nothing to save, no saved strategy); each item shows by its own condition.
const hasMenu = computed(() => hasLegs.value || !!props.current)
const canSave = computed(() => !props.paperMode && !busy.value && canSaveLegs(props.legs))

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
  if (!canSave.value) return
  asking.value = 'save-as'
  nameText.value = saveAsName(props.current?.name) // an unsaved strategy has no name: the default plus the suffix (ADR-192)
}

function renameOpen() {
  if (busy.value || !props.current) return
  asking.value = 'rename'
  nameText.value = plainName(props.current.name) ?? ''
}

// GC-UI 6b D-C16: the name form is a centred modal; focus goes to the field once the modal has taken it (Esc / X / Cancel all close)
const nameInput = ref(null)
watch(asking, async (mode) => {
  if (!mode) return
  await nextTick()
  await nextTick()
  nameInput.value?.focus?.()
})
const NAME_TITLES = { save: 'Save New Strategy', 'save-as': 'Save As', rename: 'Update Strategy Name' }

// GC-UI 6b D-C12: the row's pencil opens the EXISTING rename (REQ-134 AC-3) on that strategy. Rename needs the revision the page
// loaded, so a row that is not the open one is opened first and the dialog follows once the page holds it.
let pendingRename = null
async function renameRow(d) {
  if (busy.value) return
  if (props.current?.id === d.id) return renameOpen()
  pendingRename = d.id
  await open(d.id)
  await nextTick()
  pendingRename = null
}
watch(() => props.current?.id, (id) => {
  if (pendingRename !== null && id === pendingRename) {
    pendingRename = null
    renameOpen()
  }
})

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
  if (props.paperMode || busy.value || !asking.value || !canSaveLegs(props.legs)) return
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

// GC-TP step 2 (ADR-207 (1), REQ-109 AC-1; Sensibull Add to Drafts 166-173): "Add to Paper" lists the TICKED legs (B/S, contract,
// lots, price = the leg's entry price) in the confirm dialog; Confirm sends ONE POST of `open` orders. An unsaved strategy is saved
// first under its shown name through the same POST /strategies as Save. A refusal keeps the dialog and shows the server's text.
const PAPER_TOAST_MS = 8000
const paperOrders = ref([])
const paperOpen = ref(false)
const paperBusy = ref(false)
const paperError = ref('')
const paperTarget = ref(null)
const paperToast = ref(null) // the strategy id the toast's "Open in Builder" reopens, or null
let paperToastTimer = null
const tickedLegs = computed(() => props.legs.filter((l) => l.included !== false))
// GC-TP step 3c: once the orders are recorded this plan must not record them again; the page enters Drafts Mode (paperMode) after
// re-reading the book. If that re-read fails the lock stays until another strategy is opened or the page is reloaded.
const paperRecorded = ref(false)
watch(() => props.current?.id, () => { paperRecorded.value = false })
const canAddToPaper = computed(() => !props.paperMode && !paperRecorded.value && !busy.value && !paperBusy.value && canSaveLegs(props.legs) && tickedLegs.value.length > 0)

async function startPaper() {
  if (!canAddToPaper.value) return
  paperError.value = ''
  errorParts.value = null
  let id = props.current?.id ?? null
  if (id === null) {
    busy.value = true
    try {
      const name = props.shownName.length >= 1 && props.shownName.length <= STRATEGY_NAME_MAX ? props.shownName : STRATEGY_NAME_DEFAULT
      const res = await api.post('/strategies', buildSaveBody(props.legs, props.rulesRef, name))
      const revision = done(res.data)
      id = res.data.id
      emit('saved', id, revision, savedName.value)
      await refresh()
    } catch (e) {
      errorParts.value = e?.parts ?? NEUTRAL_PARTS
      return
    } finally {
      busy.value = false
    }
  }
  paperTarget.value = id
  paperOrders.value = tickedLegs.value.map((l, i) => ({
    key: l.id ?? `leg-${i}`, contract_id: l.contract_id, side: l.action, text: contractName(l), lots: l.lots, lot_size: l.lot_size,
    price: l.planned_entry ?? '', kind: 'open',
  }))
  paperOpen.value = true
}

async function confirmPaper(orders) {
  if (paperBusy.value) return
  paperBusy.value = true
  paperError.value = ''
  try {
    await addToPaper(api, paperTarget.value, orders)
    paperRecorded.value = true
    paperOpen.value = false
    paperToast.value = paperTarget.value
    clearTimeout(paperToastTimer)
    paperToastTimer = setTimeout(() => { paperToast.value = null }, PAPER_TOAST_MS)
    emit('paper-added', paperTarget.value)
  } catch (e) {
    paperError.value = (e?.parts ?? NEUTRAL_PARTS).what_happened || NEUTRAL_PARTS.what_happened // nothing is recorded locally on any refusal
  } finally {
    paperBusy.value = false
  }
}
function openInBuilder() {
  const id = paperToast.value
  paperToast.value = null
  if (id !== null) open(id)
}
onBeforeUnmount(() => clearTimeout(paperToastTimer))

onMounted(refresh)
</script>

<template>
  <section data-testid="save-draft-bar">
    <!-- GC-UI 3a D-A22 (ADR-165): equal full-height buttons across the card - Add/Edit, Save (filled, in the slot Trade All
         leaves), a square "..."; the strategy's name is the card title, so it is not repeated here -->
    <div class="-mt-4 flex min-h-14 items-center gap-2 rounded-b-lg border border-line bg-surface px-3 py-2 text-sm" data-testid="action-row">
      <slot name="add-edit" />
      <button
v-if="!paperMode" type="button" data-testid="save-draft" class="h-10 flex-1 basis-0 rounded-lg bg-accent px-3 font-medium text-white disabled:opacity-50"
              :disabled="!canSave" @click="save">Save</button>
      <button
v-if="!paperMode" type="button" data-testid="add-to-paper" class="h-10 flex-1 basis-0 rounded-lg border border-line px-3 font-medium disabled:opacity-50"
              :disabled="!canAddToPaper" @click="startPaper">{{ ADD_TO_PAPER_LABEL }}</button>
      <span ref="menuRoot" class="relative" @keydown.esc="closeMenu">
        <button
ref="menuButton" type="button" class="flex h-10 w-12 shrink-0 items-center justify-center rounded-lg border border-line" aria-haspopup="menu" :aria-expanded="menuOpen ? 'true' : 'false'"
                aria-label="More actions" data-testid="more-menu" :disabled="!hasMenu" @click="menuOpen ? closeMenu() : (menuOpen = true)"><Icon name="more" :size="16" /></button>
        <span v-show="menuOpen" role="menu" class="absolute left-0 top-full z-20 mt-1 flex w-44 flex-col items-start gap-1 rounded border border-line bg-surface p-2 shadow" data-testid="more-menu-panel">
          <button
v-if="hasLegs" type="button" role="menuitem" data-testid="menu-save"
                  :disabled="!canSave" @click="menuDo(save)">Save</button>
          <button
v-if="hasLegs" type="button" role="menuitem" data-testid="save-as"
                  :disabled="!canSave" @click="menuDo(saveAs)">Save As</button>
          <button
v-if="current" type="button" role="menuitem" data-testid="rename-open"
                  :disabled="busy" @click="menuDo(renameOpen)">Rename</button>
          <slot name="menu" :close="closeMenu" :add-to-paper="startPaper" :can-add-to-paper="canAddToPaper" />
        </span>
      </span>
    </div>
    <!-- the confirmation has its own line under the buttons, so it never squeezes the row (Add to Paper stayed on one line) -->
    <p class="mt-1 min-h-[1.25rem] truncate px-1 text-sm" aria-live="polite">
      <span v-if="savedId" data-testid="save-status" :data-saved-id="savedId">{{ strategyLabel({ name: savedName }, `Draft ${savedId}`) }} saved.</span>
      <span v-else data-testid="save-status" data-saved-id=""></span>
    </p>
    <slot name="after-actions" />
    <!-- GC-UI 6b D-C16 (S-116): the centred modal; Cancel + a primary Save; the 20-character limit and the counter are unchanged -->
    <Modal :open="!!asking" :title="NAME_TITLES[asking] ?? 'Save New Strategy'" fallback-focus="[data-testid='save-draft']" data-testid="name-modal" @close="cancelName">
      <form id="strategy-name-form" class="text-sm" data-testid="name-form" :data-mode="asking" @submit.prevent="confirmName">
        <label class="block font-medium" for="strategy-name">Strategy Name</label>
        <input
id="strategy-name" ref="nameInput" v-model="nameText" data-testid="name-input" type="text" class="mt-1 h-10 w-full rounded border border-line px-2"
               :maxlength="STRATEGY_NAME_MAX" autocomplete="off" />
        <p class="mt-1 text-xs" :class="nameText.length > STRATEGY_NAME_MAX ? 'text-warn' : 'text-ink-muted'" data-testid="name-count">{{ nameText.length }}/{{ STRATEGY_NAME_MAX }} characters</p>
      </form>
      <template #actions>
        <button type="button" data-testid="name-cancel" class="h-10 rounded-lg border border-line px-3 font-medium" @click="cancelName">Cancel</button>
        <button type="submit" form="strategy-name-form" data-testid="name-confirm" class="h-10 rounded-lg bg-accent px-3 font-medium text-white disabled:opacity-50" :disabled="busy">Save</button>
      </template>
    </Modal>
    <PaperConfirmDialog :open="paperOpen" :orders="paperOrders" :busy="paperBusy" :error="paperError" @confirm="confirmPaper" @cancel="paperOpen = false" />
    <!-- GC-TP step 3b2 (R-6): the toast is FIXED to the viewport (bottom centre), not inline under the action row. Inline it sat inside
         the left column's own scroll (sticky, overflow-y-auto at 1100 px and up; `contents` below), so after the save-first path
         it could be in the page but outside the visible area; its state lives here and survives the ?strategy=N route change
         (tests/paper-toast-save-first.test.js). -->
    <p v-if="paperToast !== null" role="status" class="fixed bottom-6 left-1/2 z-40 flex max-w-[calc(100vw-2rem)] -translate-x-1/2 flex-wrap items-center gap-3 rounded-lg bg-ink-overlay px-4 py-2.5 text-sm text-surface shadow" data-testid="paper-toast" data-placement="viewport">
      <span data-testid="paper-toast-message">{{ PAPER_ADDED_TEXT }}</span>
      <button type="button" class="font-semibold text-accent-soft underline" data-testid="paper-open-builder" @click="openInBuilder">Open in Builder</button>
      <router-link to="/positions/current-positions?tab=paper" class="font-semibold text-accent-soft underline" data-testid="paper-open-positions">Open Paper positions</router-link>
    </p>
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
        <p class="mt-2 text-ink-muted" data-testid="saved-hint">Please click on a saved strategy to load it:</p>
        <ul v-if="recentDrafts.length" class="mt-1" data-testid="saved-drafts">
          <!-- GC-UI 6b D-C11/D-C12 (S-117, S-218, S-219): the WHOLE row opens the strategy (click, or Enter on the row); line 1 the name,
               line 2 "<first leg> and N more" from the list reply's own first_leg + leg_count (no second line when it cannot be written);
               the pencil and the bin show on hover or keyboard focus -->
          <li
v-for="d in recentDrafts" :key="d.id" class="group flex min-h-14 cursor-pointer items-center gap-2 border-b border-line py-1 hover:bg-surface-muted" tabindex="-1"
              data-testid="saved-draft-row" :data-current="current?.id === d.id ? 'true' : 'false'" @click="open(d.id)" @keydown.enter.self="open(d.id)">
            <Icon v-if="current?.id === d.id" name="check" :size="14" />
            <button type="button" :data-testid="`open-draft-${d.id}`" class="min-w-0 flex-1 text-left" :disabled="busy" :title="`${d.underlying}, updated ${istTime(d.updated_at)}`">
              <span class="block truncate" :class="current?.id === d.id ? 'font-medium text-accent' : ''" data-testid="saved-draft-name">{{ strategyLabel(d, `Draft ${d.id}`) }}</span>
              <span v-if="legsLine(d)" class="block truncate text-xs text-ink-muted" data-testid="saved-draft-legs">{{ legsLine(d) }}</span>
            </button>
            <span v-if="trackedText(d.tracked)" class="shrink-0 text-xs text-ink-muted" data-testid="saved-draft-tracked">{{ trackedText(d.tracked) }}</span>
            <span
class="flex shrink-0 items-center gap-1 opacity-100 md:opacity-0 md:focus-within:opacity-100 md:group-hover:opacity-100" :class="deleteFlow.confirming === d.id ? '!opacity-100' : ''"
                  :data-testid="`actions-${d.id}`" @click.stop @keydown.enter.stop>
              <button type="button" class="flex h-8 w-8 items-center justify-center rounded text-ink-muted hover:text-ink" :aria-label="`Rename ${strategyLabel(d, `Draft ${d.id}`)}`" title="Rename" :disabled="busy" :data-testid="`rename-draft-${d.id}`" @click="renameRow(d)"><Icon name="pencil" :size="16" /></button>
              <DraftDelete :row="d" :flow="deleteFlow" icon />
            </span>
          </li>
        </ul>
        <p v-else class="mt-2 text-ink-muted" data-testid="saved-empty">{{ search.trim() ? 'No saved strategy matches.' : 'No saved strategies yet.' }}</p>
        <router-link to="/strategies/my-strategies" class="mt-2 inline-block text-accent" data-testid="saved-show-all">Show all in My Strategies</router-link>
      </div>
      <div v-show="tab === 'tracked'" class="mt-3" data-testid="tab-panel-tracked"><slot name="tracked" :active="tab === 'tracked'"><EmptyState icon="pulse" title="No tracked strategies here" message="Strategies you track appear in My Strategies." /></slot></div>
    </div>
    <DraftDeleteStatus :flow="deleteFlow" />
  </section>
</template>
