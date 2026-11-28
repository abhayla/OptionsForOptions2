<!-- W-117 (REQ-009 AC-6; ADR-114, ADR-003): the Alerts pages - Active, History, Notification settings.
     ADR-330 (3), (4): Active lists exactly the server's unanswered actionable alerts (GET /alerts/active), the same read the header
     bell counts; opening it writes nothing. Each row: "Fired at HH:MM", "no longer true since HH:MM" when set, one button per server
     answer. The alert only informs and asks: it never exits by itself. History = the answered rows (GET /alerts/answered) plus D-22 /
     D-71 every fired stop and every expiry settlement (GET /paper/alerts/records). Notification settings stays an honest empty state. -->
<script setup>
import ListLoadFailed from '@/components/common/ListLoadFailed.vue'
import { KIND_UNREAD_LINE, isPaperKind } from '@/lib/positionKind'
import PageHeader from '@/components/common/PageHeader.vue'
import EmptyState from '@/components/states/EmptyState.vue'
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'
import { istHm, istTime } from '@/lib/displayFormat'
import { plainName } from '@/lib/saveDraft'
import { NEUTRAL_PARTS } from '@/services/api'
import { builderLinkOf } from '@/lib/strategyLinks'
import { RECORDS_EMPTY, PAPER_ALERTS_EMPTY, activeAlerts, alertHistory, answerAlert, dropActive, loadAlertHistory, loadPaperRecords, paperRecords, readActive, takeActive } from '@/lib/paperAlerts'

// U23: the title shows once; an older stored body still opens with it, so that repeat is dropped (display only)
const alertBody = (a) => (a.body.startsWith(`${a.title}: `) ? a.body.slice(a.title.length + 2) : a.body)

const NO_CHANNELS = 'No notification channels are set up yet.'

const route = useRoute()
const router = useRouter()
const isActive = computed(() => route.path.endsWith('/active'))
// the third tab is the one that is neither Active nor Notification settings (no path literal: ADR-066's scan)
const isRecords = computed(() => !isActive.value && !route.path.endsWith('/notification-settings'))
const line = computed(() => (route.path.endsWith('/notification-settings') ? NO_CHANNELS : isRecords.value ? RECORDS_EMPTY : PAPER_ALERTS_EMPTY))

// the server's reason for a refused answer, per alert id; the row stays
const answerError = ref({})
const busy = ref(false)
const exitCode = 'exit'
// W2-B (ADR-330 (3), (12)): after the answer is stored, Exit opens the ONE shared paper exit confirmation (the Paper list's door:
// usePaperExit gate + PaperConfirmDialog + the one addToPaper post) for that strategy, here on this page. Nothing exits before the
// user confirms in it; a flat strategy gets the door's own note; closing it (confirm or cancel) leaves the alert answered.
const exitFor = ref(null)

// P7 (ADR-330 (2)(b), (33)): a side_closed row. "Add the legs again" stores add_legs then opens that strategy's builder (the builder
// cannot be told a side: it shows the strategy and the server's notice). "Confirm the new shape" first shows the server's sentence
// naming the shape that remains (the row's own text); only its Confirm stores confirm_new_shape; Cancel stores nothing and the row stays asking.
const confirming = ref(null) // the alert id whose confirmation sentence is showing
const isSideClosed = (a) => a.kind === 'side_closed'
// ADR-330 (64): "Exit the position" only for a PAPER position (the server already leaves it out; this re-checks, fail closed)
const answersOf = (a) => (a.answers ?? []).filter((x) => x.code !== exitCode || isPaperKind(a))
const kindLineOf = (a) => (isPaperKind(a) || a.position_kind === 'none' ? null : a.position_kind_text || KIND_UNREAD_LINE)

async function answer(a, code) {
  if (busy.value) return
  if (isSideClosed(a) && code === 'confirm_new_shape' && confirming.value !== a.id) {
    if (typeof a.text !== 'string' || a.text === '') { // no sentence from the server: store nothing (fail closed)
      answerError.value = { ...answerError.value, [a.id]: NEUTRAL_PARTS }
      return
    }
    answerError.value = { ...answerError.value, [a.id]: null }
    confirming.value = a.id
    return
  }
  confirming.value = null
  busy.value = true
  answerError.value = { ...answerError.value, [a.id]: null }
  try {
    await answerAlert(a.id, code)
  } catch (e) {
    answerError.value = { ...answerError.value, [a.id]: e?.parts ?? NEUTRAL_PARTS }
    busy.value = false
    // ADR-330 (3): a refusal 404 / 409 means the server's list moved on (answered elsewhere, gone): re-read Active at once so the row and bell follow it
    if (e?.status === 404 || e?.status === 409) {
      try {
        takeActive(await readActive())
      } catch (err) {
        dropActive(err)
      }
    }
    return
  }
  busy.value = false
  if (isSideClosed(a) && code === 'add_legs') {
    const to = builderLinkOf(a.strategy_id)
    if (to) router.push(to)
    return
  }
  if (code === exitCode && isPaperKind(a)) { exitFor.value = null; await nextTick(); exitFor.value = String(a.strategy_id) }
}

async function loadTab() {
  if (isRecords.value) { await Promise.all([loadAlertHistory(), loadPaperRecords()]); return }
  if (!isActive.value) return
  try {
    takeActive(await readActive())
  } catch (e) {
    dropActive(e)
  }
}
onMounted(loadTab)
</script>

<template>
  <section data-testid="alerts">
    <!-- Owner 2026-10-30 (Sensibull 171 / 172): shared header; alerts as one card with a row each; empty = shared empty state -->
    <PageHeader parent="Alerts" :title="route.meta.title" />
    <template v-if="isRecords">
      <h2 class="mb-2 text-sm font-semibold text-ink-muted" data-testid="alerts-answered-heading">Answered alerts</h2>
      <ListLoadFailed v-if="alertHistory.parts" :parts="alertHistory.parts" compact prefix="answered-error" @retry="loadTab" />
      <p v-else-if="alertHistory.loaded && !alertHistory.items.length && paperRecords.records.length" class="mb-4 text-sm text-ink-muted" data-testid="answered-none">No answered alerts yet.</p>
      <ul v-else-if="alertHistory.items.length" class="mb-4 divide-y divide-line overflow-hidden rounded-lg border border-line bg-surface" data-testid="alerts-answered">
        <li v-for="h in alertHistory.items" :key="`h${h.id}`" class="px-4 py-3 hover:bg-surface-muted" data-testid="answered-row">
          <p class="font-medium" data-testid="answered-strategy">{{ plainName(h.strategy_name) ?? `Strategy ${h.strategy_id}` }}</p>
          <p class="mt-1 text-sm">{{ h.text }}</p>
          <p class="text-xs text-ink-muted">{{ h.fired_line }}<template v-if="h.closed_reason"> - {{ h.closed_reason }}</template><template v-else-if="h.answer_label"> - {{ h.answer_label }} at {{ istHm(h.answered_at) }}</template></p>
          <p v-if="h.worse_line" class="text-xs text-ink-muted" data-testid="answered-worse">{{ h.worse_line }}</p>
        </li>
      </ul>
      <h2 class="mb-2 text-sm font-semibold text-ink-muted" data-testid="alerts-records-heading">Stops and expiry settlements</h2>
      <ListLoadFailed v-if="paperRecords.parts" :parts="paperRecords.parts" compact prefix="records-error" @retry="loadTab" />
      <ul v-else-if="paperRecords.records.length" class="divide-y divide-line overflow-hidden rounded-lg border border-line bg-surface" data-testid="alerts-records">
        <li v-for="(r, n) in paperRecords.records" :key="`${r.kind}${n}`" class="px-4 py-3 hover:bg-surface-muted" data-testid="record-row">
          <p class="font-medium" data-testid="record-title">{{ r.title }}</p>
          <p class="text-xs text-ink-muted"><span data-testid="record-time">{{ istTime(r.at) }}</span> - <span data-testid="record-strategy">{{ plainName(r.strategy_name) ?? `Strategy ${r.strategy_id}` }}</span></p>
          <p class="mt-1 text-sm" data-testid="record-body">{{ alertBody({ title: r.title, body: r.body }) }}</p>
        </li>
      </ul>
      <p v-if="!alertHistory.loaded || !paperRecords.loaded" class="text-sm text-ink-muted" data-testid="alerts-loading">Loading...</p>
      <EmptyState v-else-if="!alertHistory.items.length && !alertHistory.parts && !paperRecords.records.length && !paperRecords.parts" :message="line" icon="bell" data-testid="alerts-empty" />
    </template>
    <template v-else-if="isActive && activeAlerts.parts">
      <ListLoadFailed :parts="activeAlerts.parts" compact prefix="alerts-error" @retry="loadTab" />
    </template>
    <ul v-else-if="isActive && activeAlerts.alerts.length" class="divide-y divide-line overflow-hidden rounded-lg border border-line bg-surface" data-testid="alerts-attention">
      <li v-for="a in activeAlerts.alerts" :key="a.id" class="px-4 py-3 hover:bg-surface-muted" data-testid="alert-row">
        <p class="font-medium" data-testid="alert-strategy">{{ plainName(a.strategy_name) ?? `Strategy ${a.strategy_id}` }}</p>
        <p class="mt-1 text-sm" data-testid="alert-text">{{ a.text }}</p>
        <p class="text-xs text-ink-muted"><span data-testid="alert-fired">{{ a.fired_line }}</span><span v-if="a.no_longer_true_line" data-testid="alert-no-longer"> - {{ a.no_longer_true_line }}</span></p>
        <p v-if="a.worse_line" class="text-xs text-ink-muted" data-testid="alert-worse">{{ a.worse_line }}</p>
        <p v-if="kindLineOf(a)" class="mt-1 text-xs text-ink-muted" data-testid="alert-position-kind-line">{{ kindLineOf(a) }}</p>
        <div class="mt-2 flex flex-wrap gap-2">
          <button v-for="x in answersOf(a)" :key="x.code" type="button" class="rounded border border-line px-2 py-1 text-sm" :disabled="busy" :data-testid="`alert-answer-${x.code}`" @click="answer(a, x.code)">{{ x.label }}</button>
        </div>
        <div v-if="confirming === a.id" class="mt-2 rounded border border-line p-2" data-testid="side-closed-confirm">
          <p class="text-sm">{{ a.text }}</p>
          <div class="mt-2 flex gap-2">
            <button type="button" class="rounded border border-line px-2 py-1 text-sm" :disabled="busy" data-testid="side-closed-confirm-yes" @click="answer(a, 'confirm_new_shape')">{{ a.answers.find((x) => x.code === 'confirm_new_shape')?.label }}</button>
            <button type="button" class="rounded border border-line px-2 py-1 text-sm" :disabled="busy" data-testid="side-closed-confirm-no" @click="confirming = null">Cancel</button>
          </div>
        </div>
        <div v-if="answerError[a.id]" class="mt-2" data-testid="alert-answer-error"><ErrorMessage :parts="answerError[a.id]" compact prefix="alert-answer" /></div>
      </li>
    </ul>
    <p v-else-if="isActive && !activeAlerts.loaded" class="text-sm text-ink-muted" data-testid="alerts-loading">Loading...</p>
    <EmptyState v-else :message="line" icon="bell" data-testid="alerts-empty" />
    <PaperStrategies v-if="exitFor !== null" :key="exitFor" :exit-only-for="exitFor" class="mt-3" data-testid="alerts-exit-door" @exit-closed="exitFor = null" />
  </section>
</template>
