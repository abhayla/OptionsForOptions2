<!-- W-117 (REQ-009 AC-6; ADR-114, ADR-003): the Alerts pages - Active, History, Notification settings.
     ADR-330 (3), (4): Active lists exactly the server's unanswered actionable alerts (GET /alerts/active), the same read the header
     bell counts; opening it writes nothing. Each row: "Fired at HH:MM", "no longer true since HH:MM" when set, one button per server
     answer. The alert only informs and asks: it never exits by itself. History = the answered rows (GET /alerts/answered) plus D-22 /
     D-71 every fired stop and every expiry settlement (GET /paper/alerts/records). Notification settings stays an honest empty state. -->
<script setup>
import PageHeader from '@/components/common/PageHeader.vue'
import EmptyState from '@/components/states/EmptyState.vue'
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import { istHm, istTime } from '@/lib/displayFormat'
import { plainName } from '@/lib/saveDraft'
import { NEUTRAL_PARTS } from '@/services/api'
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

async function answer(a, code) {
  if (busy.value) return
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
  // WAVE 2: open usePaperExit confirmation. Until then Exit goes to the strategy's builder page; it never exits by itself.
  if (code === exitCode) await router.push({ path: '/strategy/builder', query: { strategy: String(a.strategy_id) } })
}

onMounted(async () => {
  if (isRecords.value) { await Promise.all([loadAlertHistory(), loadPaperRecords()]); return }
  if (!isActive.value) return
  try {
    takeActive(await readActive())
  } catch (e) {
    dropActive(e)
  }
})
</script>

<template>
  <section data-testid="alerts">
    <!-- Owner 2026-10-30 (Sensibull 171 / 172): shared header; alerts as one card with a row each; empty = shared empty state -->
    <PageHeader parent="Alerts" :title="route.meta.title" />
    <template v-if="isRecords">
      <ErrorMessage v-if="alertHistory.parts" :parts="alertHistory.parts" compact prefix="answered-error" />
      <ul v-else-if="alertHistory.items.length" class="mb-4 divide-y divide-line overflow-hidden rounded-lg border border-line bg-surface" data-testid="alerts-answered">
        <li v-for="h in alertHistory.items" :key="`h${h.id}`" class="px-4 py-3 hover:bg-surface-muted" data-testid="answered-row">
          <p class="font-medium" data-testid="answered-strategy">{{ plainName(h.strategy_name) ?? `Strategy ${h.strategy_id}` }}</p>
          <p class="mt-1 text-sm">{{ h.text }}</p>
          <p class="text-xs text-ink-muted">{{ h.fired_line }}<template v-if="h.answer_label"> - {{ h.answer_label }} at {{ istHm(h.answered_at) }}</template><template v-else-if="h.closed_reason"> - closed: {{ h.closed_reason }}</template></p>
          <p v-if="h.worse_line" class="text-xs text-ink-muted" data-testid="answered-worse">{{ h.worse_line }}</p>
        </li>
      </ul>
      <ErrorMessage v-if="paperRecords.parts" :parts="paperRecords.parts" compact prefix="records-error" />
      <ul v-else-if="paperRecords.records.length" class="divide-y divide-line overflow-hidden rounded-lg border border-line bg-surface" data-testid="alerts-records">
        <li v-for="(r, n) in paperRecords.records" :key="`${r.kind}${n}`" class="px-4 py-3 hover:bg-surface-muted" data-testid="record-row">
          <p class="font-medium" data-testid="record-title">{{ r.title }}</p>
          <p class="text-xs text-ink-muted"><span data-testid="record-time">{{ istTime(r.at) }}</span> - <span data-testid="record-strategy">{{ plainName(r.strategy_name) ?? `Strategy ${r.strategy_id}` }}</span></p>
          <p class="mt-1 text-sm" data-testid="record-body">{{ alertBody({ title: r.title, body: r.body }) }}</p>
        </li>
      </ul>
      <EmptyState v-if="!alertHistory.items.length && !alertHistory.parts && !paperRecords.records.length && !paperRecords.parts" :message="line" icon="bell" data-testid="alerts-empty" />
    </template>
    <template v-else-if="isActive && activeAlerts.parts">
      <ErrorMessage :parts="activeAlerts.parts" compact prefix="alerts-error" />
    </template>
    <ul v-else-if="isActive && activeAlerts.alerts.length" class="divide-y divide-line overflow-hidden rounded-lg border border-line bg-surface" data-testid="alerts-attention">
      <li v-for="a in activeAlerts.alerts" :key="a.id" class="px-4 py-3 hover:bg-surface-muted" data-testid="alert-row">
        <p class="font-medium" data-testid="alert-strategy">{{ plainName(a.strategy_name) ?? `Strategy ${a.strategy_id}` }}</p>
        <p class="mt-1 text-sm" data-testid="alert-text">{{ a.text }}</p>
        <p class="text-xs text-ink-muted"><span data-testid="alert-fired">{{ a.fired_line }}</span><span v-if="a.no_longer_true_line" data-testid="alert-no-longer"> - {{ a.no_longer_true_line }}</span></p>
        <p v-if="a.worse_line" class="text-xs text-ink-muted" data-testid="alert-worse">{{ a.worse_line }}</p>
        <div class="mt-2 flex flex-wrap gap-2">
          <button v-for="x in a.answers" :key="x.code" type="button" class="rounded border border-line px-2 py-1 text-sm" :disabled="busy" :data-testid="`alert-answer-${x.code}`" @click="answer(a, x.code)">{{ x.label }}</button>
        </div>
        <div v-if="answerError[a.id]" class="mt-2" data-testid="alert-answer-error"><ErrorMessage :parts="answerError[a.id]" compact prefix="alert-answer" /></div>
      </li>
    </ul>
    <EmptyState v-else :message="line" icon="bell" data-testid="alerts-empty" />
  </section>
</template>
