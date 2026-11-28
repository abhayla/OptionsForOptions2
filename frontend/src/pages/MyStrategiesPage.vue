<!-- My Strategies and Completed Strategies (W-109, W-157; REQ-009 AC-2, REQ-038 AC-5, REQ-134 AC-3/AC-4/AC-5, OQ-13). The
     user's saved strategies from GET /api/strategies: name (quoted user words, shown without the API quotes, as text), underlying,
     first leg + "and N more", status, last saved and the tracked state (copies Sensibull screen 117's list line); a search box
     filters by name as typed; Rename calls PATCH /api/strategies/{id}/name; each row links to the Strategy Builder
     (`?strategy=<id>`) and to Execute Strategy for that id. No money figure is computed or shown. The status word is lib/strategyStatus (ADR-299).
     The Completed page lists only completed strategies (stored 'closed' when the last open leg is
     exited, alembic 0049) and shows each one's final P&L, adjustments made and their cost exactly as the server worded them
     (a figure the server could not give shows the server's reason, never 0; no money arithmetic here). -->
<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api, { NEUTRAL_PARTS } from '@/services/api'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import EmptyState from '@/components/states/EmptyState.vue'
import LoadFailed from '@/components/common/LoadFailed.vue'
import DraftDeleteConfirm from '@/components/strategy/DraftDeleteConfirm.vue'
import DraftDelete from '@/components/strategy/DraftDelete.vue'
import DraftDeleteStatus from '@/components/strategy/DraftDeleteStatus.vue'
import { TIME_UNAVAILABLE, istTime, noteShownDate } from '@/lib/displayFormat'
import { afterFigure } from '@/lib/tracking'
// u125: the server's sentence for why charges / the net are absent (an older server sends none: the Completed reason, else a plain word)
// the net counts only when the helper calls it an after figure (a reply that also sends a reason is not trusted)
const net = (s) => { const a = afterFigure(s, null); return a.kind === 'after' ? a.text : null }
// u127 (ADR-263): one tap on the net opens the breakdown (before = the Final P&L text as sent)
const netBreakdown = (s) => afterFigure(s, typeof s.final_pnl_text === 'string' && s.final_pnl_text.trim() !== '' ? s.final_pnl_text.trim() : null).breakdown
import AfterChargesTap from '@/components/common/AfterChargesTap.vue'
const notAvailable = (s) => s.after_charges_reason_text ?? s.completed_reason_text ?? 'the server sent no figure'
import { STRATEGY_NAME_MAX, legsLine, nameLimitText, noMatchText, plainName, renameStrategy, searchStrategies, strategyListLabel } from '@/lib/saveDraft'
import { isCompleted, isRunning, strategyStatusWord } from '@/lib/strategyStatus'
import { CLOSED_HEADER, CLOSED_PREFIX, CLOSED_UNAVAILABLE_TEXT } from '@/lib/sharedStateText'
import { useOrderPath } from '@/lib/orderPath'
import PnlLine from '@/components/live/PnlLine.vue'
import { recordLineOf } from '@/lib/positionKind'
import { usePaperPnl } from '@/lib/paperPnl'
import { bulkConfirmText, canDelete, selectAllText, useDeleteFlow } from '@/lib/strategyActivity'
import { CLEAR_UNDO_SECONDS_KEY } from '@/lib/legEdit'
import { useSettingsValues } from '@/stores/settingsValues'

// Owner 2026-10-30 (Sensibull 117): one column grid shared by the header row and every strategy row, so columns line up
// User test 2026-10-30 round 2 widths: last saved 16rem holds "last saved 30 Oct 2026, 08:28:55 IST" on one line
const COLS = 'lg:grid lg:grid-cols-[minmax(9.5rem,1.4fr)_3.5rem_minmax(0,1fr)_5rem_13rem_12rem]'
const HEADS = computed(() => ['Name', 'Index', 'Legs', 'Status', completedOnly.value ? CLOSED_HEADER : 'Last saved', '']) // ADR-299: the Tracking column is gone (its words are retired)

// W-121 (REQ-073 AC-6, ADR-165): the Execute link is absent (not disabled) unless the server said the order path is on.
const orderPathOn = useOrderPath()
const pnl = usePaperPnl() // D-41: the Positions page's P&L (one read of the paper list); only a running row shows it

// D-66: the Completed page shows when the trade closed (the server's close time), never the last save; words: sharedStateText
const closedText = (s) => {
  const time = istTime(s.closed_at)
  return time === TIME_UNAVAILABLE ? CLOSED_UNAVAILABLE_TEXT : `${CLOSED_PREFIX}${time}`
}

const route = useRoute()
const router = useRouter()
const completedOnly = computed(() => route.meta.completedOnly === true)
const hasCompleted = computed(() => rows.value.some(isCompleted))
const rows = ref([])
const loaded = ref(false)
const busy = ref(false)
const query = ref('') // REQ-134 AC-4: the search text, matched in the browser against the names of the user's own list
const renaming = ref(null) // { id, text } while a row's name field is open
const renameError = ref(null) // { id, parts }
const errorParts = ref(null)

// User test 2026-10-30 (U2): newest save first, as Home's "Recent strategies" lists them (ISO times sort as text)
const newestFirst = (list) => [...list].sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at)))
const shown = computed(() => newestFirst(completedOnly.value ? rows.value.filter(isCompleted) : rows.value.filter((r) => !isCompleted(r)))) // ADR-259: a closed trade leaves this list
const visible = computed(() => searchStrategies(shown.value, query.value))

// S-05 (ADR-320): the list read shows a skeleton while it runs; a failure, or no answer within the page's limit, shows LoadFailed
// with Retry (which reads again). A late answer after the limit is ignored (the user already saw the failure and may retry).
const LIST_LIMIT_MS = 15000
const LIST_LOAD_FAILED_TEXT = 'Could not load your strategies. Nothing was changed.'
const loadFailed = ref(false)
let readNo = 0
// UX-05 (Lane L): true while a re-read of the list is in flight (after an Undo the row is on its way back): the list then says
// so instead of "No saved strategy matches ..." or "No strategy ..." (new sentence, pending owner read)
const refreshing = ref(false)
const LOADING_LIST_TEXT = 'Loading your strategies...'
// FJ2-9 (T2-17; ADR-259: a completed strategy leaves this list and is listed on Strategies > Completed Strategies): when the only trades are completed ones, this page says where they are (new sentence, pending owner read)
const COMPLETED_ELSEWHERE_TEXT = 'No open strategies. Your completed strategies are listed under Strategies > Completed Strategies.'
const emptyText = computed(() => (completedOnly.value ? 'No strategy is completed yet.' : rows.value.some(isCompleted) ? COMPLETED_ELSEWHERE_TEXT : 'You have no saved strategies yet. Save a draft from the Strategy Builder and it will appear here.'))
async function loadList() {
  const mine = ++readNo
  refreshing.value = true
  let timer = null
  const limit = new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('timed out')), LIST_LIMIT_MS) })
  try {
    const list = noteShownDate((await Promise.race([api.get('/strategies'), limit])).data)?.strategies
    if (mine !== readNo) return
    rows.value = Array.isArray(list) ? list : []
    loadFailed.value = false
    loaded.value = true
  } catch {
    if (mine !== readNo) return
    if (!loaded.value) loadFailed.value = true // a failed re-read after a good first read keeps the list on screen
  } finally {
    clearTimeout(timer)
    if (mine === readNo) refreshing.value = false
  }
}
function retryList() {
  loadFailed.value = false
  loaded.value = false
  return loadList()
}
onMounted(loadList)

// REQ-070 AC-6: Delete with Undo (one flow, shared with the Builder's saved list). Undo puts the row back from a fresh read.
const deleteFlow = useDeleteFlow(api, {
  undoMs: () => useSettingsValues().waitMs(CLEAR_UNDO_SECONDS_KEY),
  onRemoved: (id) => { rows.value = rows.value.filter((r) => r.id !== id) },
  revisionOf: (id) => rows.value.find((r) => r.id === id)?.revision, // N-30: the list row's revision, no GET per row
  onBack: loadList,
  reload: loadList,
})
onBeforeUnmount(() => deleteFlow.dispose())

// ADR-330 (8): tick boxes. Only rows the server lets be deleted (and not held at the broker) can be ticked; the selection is
// always a subset of the rows shown, so a hidden row is never deleted by a click on Delete selected.
const selectable = computed(() => visible.value.filter(canDelete))
const chosen = computed(() => selectable.value.filter((r) => deleteFlow.selected.includes(r.id)))
const allTicked = computed(() => selectable.value.length > 0 && chosen.value.length === selectable.value.length)
watch(query, () => deleteFlow.setSelection(chosen.value.map((r) => r.id)))
const toggleAll = (on) => deleteFlow.setSelection(on ? selectable.value.map((r) => r.id) : [])
function askBulk() {
  deleteFlow.setSelection(chosen.value.map((r) => r.id))
  deleteFlow.askBulk(chosen.value.filter(isRunning).length)
}
// ADR-330 (19): the list label: name, then (#id, expiry) from the list reply's first leg
const listLabel = (r) => strategyListLabel({ name: r.name, id: r.id, expiries: [r.first_leg?.expiry], fallback: `Strategy ${r.id}` })
const keptName = (id) => { const r = rows.value.find((x) => x.id === id); return r ? listLabel(r) : `Strategy ${id}` }

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

// REQ-134 AC-3: rename in the list. The list row carries no revision: renameStrategy reads the strategy once for the one it has
// now and sends the name to PATCH /strategies/{id}/name with it (a rename never changes legs, status, revision or last-saved time).
function startRename(row) {
  renaming.value = { id: row.id, text: plainName(row.name) ?? '' }
  renameError.value = null
  nextTick(() => document.querySelector('[data-testid="rename-input"]')?.focus()) // typing works at once, no click first
}
async function confirmRename(row) {
  if (busy.value || !renaming.value || renaming.value.id !== row.id) return
  const { id, text } = renaming.value
  busy.value = true
  renameError.value = null
  try {
    const done = await renameStrategy(api, id, null, text) // reads the revision itself; unreadable -> throws, nothing sent
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
    <LoadFailed v-else-if="loadFailed" :text="LIST_LOAD_FAILED_TEXT" prefix="list-load" @retry="retryList" />
    <div v-else-if="!loaded" class="space-y-2" role="status" aria-label="Loading your strategies" data-testid="list-skeleton">
      <div v-for="n in 4" :key="n" class="h-9 animate-pulse rounded bg-line"></div>
    </div>
    <p v-else-if="refreshing && !shown.length" class="text-sm text-ink-muted" role="status" data-testid="list-refreshing">{{ LOADING_LIST_TEXT }}</p>
    <EmptyState
      v-else-if="!shown.length" data-testid="list-empty"
      :message="emptyText"
    />
    <template v-else>
      <div v-if="visible.length" class="mb-2 flex flex-wrap items-center gap-3 text-[13px]" data-testid="bulk-bar">
        <label class="inline-flex items-center gap-2" data-testid="select-all-label">
          <input type="checkbox" :checked="allTicked" :disabled="!selectable.length || deleteFlow.busy" data-testid="select-all" @change="toggleAll($event.target.checked)" />
          <span>{{ selectAllText(selectable.length, visible.length) }}</span>
        </label>
        <button type="button" class="btn btn-sm" :disabled="!chosen.length || deleteFlow.busy" data-testid="delete-selected" @click="askBulk">Delete selected ({{ chosen.length }})</button>
        <span v-if="deleteFlow.bulkConfirming" class="flex flex-wrap items-center gap-2" role="alertdialog" data-testid="bulk-confirm-box">
          <span data-testid="bulk-confirm-text">{{ bulkConfirmText(deleteFlow.bulkConfirming.count, deleteFlow.bulkConfirming.running) }}</span>
          <button type="button" class="link" :disabled="deleteFlow.busy" data-testid="bulk-confirm" @click="deleteFlow.confirmBulk()">Delete</button>
          <button type="button" class="link" data-testid="bulk-cancel" @click="deleteFlow.cancelBulk()">Cancel</button>
        </span>
      </div>
      <p v-if="!visible.length && refreshing" class="text-sm text-ink-muted" role="status" data-testid="list-refreshing">{{ LOADING_LIST_TEXT }}</p>
      <p v-else-if="!visible.length" class="text-sm text-ink-muted" data-testid="search-no-match">{{ noMatchText(query) }}</p>
      <div v-else class="overflow-hidden rounded-lg border border-line bg-surface">
      <div class="hidden gap-x-2 border-b border-line bg-surface-muted px-4 py-1.5 text-[11px] leading-4 font-medium text-ink-muted" :class="COLS" aria-hidden="true">
        <span v-for="(h, i) in HEADS" :key="i" :class="{ 'text-right': i === HEADS.length - 1 }">{{ h }}</span>
      </div>
      <ul class="divide-y divide-line" data-testid="strategy-list">
        <li v-for="s in visible" :key="s.id" class="flex flex-wrap min-h-9 items-center gap-x-2 gap-y-1 px-4 py-1.5 text-[13px] hover:bg-surface-muted" :class="COLS" data-testid="strategy-row" :data-strategy-id="s.id">
          <span class="flex min-w-0 max-w-full items-center gap-2">
            <input v-if="canDelete(s)" type="checkbox" :checked="deleteFlow.selected.includes(s.id)" :disabled="deleteFlow.busy" :aria-label="`Select ${listLabel(s)}`" :data-testid="`select-${s.id}`" @change="deleteFlow.toggle(s.id, $event.target.checked)" />
            <span v-else class="inline-block w-[13px] shrink-0" aria-hidden="true"></span>
            <span class="min-w-0 max-w-full truncate font-medium" :title="listLabel(s)" data-testid="row-name">{{ listLabel(s) }}</span>
          </span>
          <span data-testid="row-underlying">{{ s.underlying }}</span>
          <span v-if="legsLine(s)" class="min-w-0 max-w-full truncate text-ink-muted" :title="legsLine(s)" data-testid="row-legs">{{ legsLine(s) }}</span>
          <span v-else class="hidden lg:block" aria-hidden="true"></span>
          <span v-if="typeof s.current_legs_text === 'string' && s.current_legs_text" class="col-span-full w-full text-xs text-ink-muted" data-testid="row-legs-note">{{ s.current_legs_text }}</span>
          <span data-testid="row-status">{{ strategyStatusWord(s) }}</span>
          <span class="num whitespace-nowrap text-ink-muted" data-testid="row-saved">{{ isCompleted(s) ? closedText(s) : `last saved ${istTime(s.updated_at)}` }}</span>
          <span class="flex flex-wrap items-center justify-end gap-x-3 gap-y-1" data-testid="row-actions">
          <button type="button" class="link" :disabled="busy" :data-testid="`open-builder-${s.id}`" @click="openInBuilder(s.id)">Open in Builder</button>
          <button v-if="'name' in s" type="button" class="link" :disabled="busy" :data-testid="`rename-${s.id}`" @click="startRename(s)">Rename</button>
          <DraftDelete :row="s" :flow="deleteFlow" confirm-below />
          <router-link v-if="orderPathOn" :to="`/strategy/${s.id}/execute`" class="link" :data-testid="`open-execute-${s.id}`">Execute Strategy</router-link>
          </span>
          <PnlLine v-if="isRunning(s)" class="col-span-full w-full" :cell="pnl.cellFor(s.id)" testid="row-pnl" />
          <!-- owner 28 Nov: a stored action on a REAL position is one line under the row; the P&L above is still Zerodha's figure and never moves for it -->
          <p v-if="isRunning(s) && s.position_kind === 'real' && recordLineOf(s)" class="col-span-full w-full text-sm font-semibold" role="status" data-testid="row-record-line">{{ recordLineOf(s) }}</p>
          <p v-if="isCompleted(s)" class="col-span-full w-full text-ink-muted" data-testid="row-completed">
            <span data-testid="row-final-pnl">Final P&amp;L {{ s.final_pnl_text ?? s.completed_reason_text }}</span>
            <!-- GC-ICFIX u125 (ADR-259, ADR-263): charges paid and the net after charges, the server's fields as sent; absent -> "not available: <its reason>", never 0 -->
            <span data-testid="row-charges"> · {{ s.charges_paid_text != null ? `Charges ${s.charges_paid_text}` : (s.charges_paid != null ? `Charges ${s.charges_paid}` : `Charges not available: ${notAvailable(s)}`) }}</span>
            <span data-testid="row-net-after"> · Net after charges <AfterChargesTap :breakdown="netBreakdown(s)">{{ net(s) ?? `not available: ${notAvailable(s)}` }}</AfterChargesTap></span>
            <span data-testid="row-adjustments"> · Adjustments made {{ s.adjustments_made ?? s.completed_reason_text }}</span>
            <span data-testid="row-adjustment-cost"> · Adjustment cost {{ s.adjustment_cost_text ?? s.completed_reason_text }}</span>
          </p>
          <form v-if="renaming && renaming.id === s.id" class="col-span-full flex w-full flex-wrap items-center gap-2" data-testid="rename-form" @submit.prevent="confirmRename(s)" @keydown.esc.stop="renaming = null">
            <input v-model="renaming.text" type="text" class="field" data-testid="rename-input" :maxlength="STRATEGY_NAME_MAX" aria-label="New strategy name" autocomplete="off" />
            <span class="text-xs" :class="renaming.text.length > STRATEGY_NAME_MAX ? 'text-warn' : 'text-ink-muted'" data-testid="rename-limit">{{ nameLimitText(renaming.text.length) }}</span>
            <button type="submit" class="btn btn-sm btn-primary" :disabled="busy" data-testid="rename-save">Save</button>
            <button type="button" class="btn btn-sm" data-testid="rename-cancel" @click="renaming = null">Cancel</button>
          </form>
          <DraftDeleteConfirm v-if="deleteFlow.confirming === s.id" :row="s" :flow="deleteFlow" class="col-span-full w-full" />
          <ErrorMessage v-if="renameError && renameError.id === s.id" class="col-span-full w-full" :parts="renameError.parts" compact prefix="rename-error" data-testid="rename-error" />
        </li>
      </ul>
      </div>
    </template>
    <div v-if="deleteFlow.bulkResult" class="mt-2 text-sm" data-testid="bulk-result">
      <p class="flex flex-wrap items-center gap-3">
        <span data-testid="bulk-summary">{{ deleteFlow.bulkResult.summary }}</span>
        <template v-if="deleteFlow.kept?.bulk">
          <button type="button" class="link" :disabled="deleteFlow.busy" data-testid="result-undo" @click="deleteFlow.undoDelete()">Undo</button>
          <button type="button" class="link" data-testid="result-dismiss" @click="deleteFlow.dismissUndo()">Dismiss</button>
        </template>
      </p>
      <ul v-if="deleteFlow.bulkResult.kept.length" class="list-disc pl-5">
        <li v-for="k in deleteFlow.bulkResult.kept" :key="k.id" data-testid="bulk-kept">{{ keptName(k.id) }}: {{ k.text }}</li>
      </ul>
    </div>
    <p v-if="deleteFlow.kept && !deleteFlow.kept.bulk" class="mt-2 flex flex-wrap items-center gap-3 text-sm" data-testid="delete-result">
      <span>Strategy deleted.</span>
      <button type="button" class="link" :disabled="deleteFlow.busy" data-testid="result-undo" @click="deleteFlow.undoDelete()">Undo</button>
      <button type="button" class="link" data-testid="result-dismiss" @click="deleteFlow.dismissUndo()">Dismiss</button>
    </p>
    <DraftDeleteStatus :flow="deleteFlow" />
    <!-- I-203 (F3, ADR-259): a closed trade leaves this list by design; say where it went (new sentence, pending owner read) -->
    <p v-if="loaded && !loadFailed && !errorParts && !completedOnly && hasCompleted" class="mt-3 text-xs text-ink-muted" data-testid="completed-pointer">
      Completed strategies are listed under Strategies &gt; Completed Strategies.
    </p>
  </section>
</template>
