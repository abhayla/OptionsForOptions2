<!-- W-117 (REQ-009 AC-6; ADR-114, ADR-003): the Alerts pages - Active, History, Notification settings.
     GC-TP step 7b (REQ-109 AC-8, ADR-207 (5)): Active lists the server's paper stop alerts, newest first, text as sent; opening
     it marks them read (one POST). History and Notification settings stay honest empty states: no logic exists for them yet. -->
<script setup>
import PageHeader from '@/components/common/PageHeader.vue'
import EmptyState from '@/components/states/EmptyState.vue'
import { computed, onMounted } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import { istTime } from '@/lib/displayFormat'
import { plainName } from '@/lib/saveDraft'
import { compareUrl } from '@/lib/adjustDrawer'
import { EARLIER_HEADING, PAPER_ALERTS_EMPTY, attentionItems, dropAlerts, earlierAlerts, openRecords, markPaperAlertsRead, paperAlerts, readPaperAlerts, takeAlerts } from '@/lib/paperAlerts'

// U23: the title shows once; an older stored body still opens with it, so that repeat is dropped (display only)
const alertBody = (a) => (a.body.startsWith(`${a.title}: `) ? a.body.slice(a.title.length + 2) : a.body)

const attention = computed(() => attentionItems())
const earlier = computed(() => earlierAlerts())

const NO_CHANNELS = 'No notification channels are set up yet.'

const route = useRoute()
const isActive = computed(() => route.path.endsWith('/active'))
const line = computed(() => (route.path.endsWith('/notification-settings') ? NO_CHANNELS : PAPER_ALERTS_EMPTY))

onMounted(async () => {
  if (!isActive.value) return
  try {
    const ok = takeAlerts(await readPaperAlerts())
    if (ok && paperAlerts.unread > 0) await markPaperAlertsRead()
  } catch (e) {
    dropAlerts(e)
  }
})
</script>

<template>
  <section data-testid="alerts">
    <!-- Owner 2026-10-30 (Sensibull 171 / 172): shared header; alerts as one card with a row each; empty = shared empty state -->
    <PageHeader parent="Alerts" :title="route.meta.title" />
    <template v-if="isActive && paperAlerts.parts">
      <ErrorMessage :parts="paperAlerts.parts" compact prefix="alerts-error" />
    </template>
    <template v-else-if="isActive && (paperAlerts.alerts.length || openRecords.list.length)">
      <!-- ADR-260: the top list is exactly what the bell counts (open records, then unread stops); read stops sit under "Earlier" -->
      <ul v-if="attention.length" class="divide-y divide-line overflow-hidden rounded-lg border border-line bg-surface" data-testid="alerts-attention">
        <li v-for="i in attention" :key="`${i.kind}${i.id}`" class="px-4 py-3 hover:bg-surface-muted" :data-testid="i.kind === 'open' ? 'open-record-row' : 'alert-row'">
          <template v-if="i.kind === 'open'">
            <p class="font-medium" data-testid="open-record-strategy">{{ plainName(i.strategy_name) ?? `Strategy ${i.strategy_id}` }}</p>
            <p class="mt-1 text-sm" data-testid="open-record-text">{{ i.text }}</p>
            <RouterLink :to="compareUrl(i.strategy_id, [], [i.id])" class="text-sm text-accent underline" data-testid="open-record-compare">Compare approaches</RouterLink>
          </template>
          <template v-else>
            <p class="font-medium" data-testid="alert-title">{{ i.title }}</p>
            <p class="text-xs text-ink-muted"><span data-testid="alert-time">{{ istTime(i.created_at) }}</span> - <span data-testid="alert-strategy">{{ plainName(i.strategy_name) ?? `Strategy ${i.strategy_id}` }}</span></p>
            <p class="mt-1 text-sm" data-testid="alert-body">{{ alertBody(i) }}</p>
          </template>
        </li>
      </ul>
      <div v-if="earlier.length" data-testid="alerts-earlier">
        <h2 class="mb-2 mt-4 text-sm font-medium text-ink-muted" data-testid="alerts-earlier-heading">{{ EARLIER_HEADING }}</h2>
        <ul class="divide-y divide-line overflow-hidden rounded-lg border border-line bg-surface">
          <li v-for="a in earlier" :key="a.id" class="px-4 py-3 hover:bg-surface-muted" data-testid="alert-row">
            <p class="font-medium" data-testid="alert-title">{{ a.title }}</p>
            <p class="text-xs text-ink-muted"><span data-testid="alert-time">{{ istTime(a.created_at) }}</span> - <span data-testid="alert-strategy">{{ plainName(a.strategy_name) ?? `Strategy ${a.strategy_id}` }}</span></p>
            <p class="mt-1 text-sm" data-testid="alert-body">{{ alertBody(a) }}</p>
          </li>
        </ul>
      </div>
    </template>
    <EmptyState v-else :message="line" icon="bell" data-testid="alerts-empty" />
  </section>
</template>
