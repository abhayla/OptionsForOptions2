<!-- W-117 (REQ-009 AC-6; ADR-114, ADR-003): the Alerts pages - Active, History, Notification settings.
     GC-TP step 7b (REQ-109 AC-8, ADR-207 (5)): Active lists the server's paper stop alerts, newest first, text as sent; opening
     it marks them read (one POST). History and Notification settings stay honest empty states: no logic exists for them yet. -->
<script setup>
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import { istTime } from '@/lib/displayFormat'
import { plainName } from '@/lib/saveDraft'
import { PAPER_ALERTS_EMPTY, dropAlerts, markPaperAlertsRead, paperAlerts, readPaperAlerts, takeAlerts } from '@/lib/paperAlerts'

// U23: the title shows once; an older stored body still opens with it, so that repeat is dropped (display only)
const alertBody = (a) => (a.body.startsWith(`${a.title}: `) ? a.body.slice(a.title.length + 2) : a.body)

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
    <p class="text-xs text-ink-muted" data-testid="page-parent">Alerts</p>
    <h1 class="text-xl font-semibold" data-testid="page-title">{{ route.meta.title }}</h1>
    <template v-if="isActive && paperAlerts.parts">
      <ErrorMessage class="mt-4" :parts="paperAlerts.parts" compact prefix="alerts-error" />
    </template>
    <ul v-else-if="isActive && paperAlerts.alerts.length" class="mt-4 grid gap-3" data-testid="alerts-list">
      <li v-for="a in paperAlerts.alerts" :key="a.id" class="rounded border border-line bg-surface p-3" data-testid="alert-row">
        <p class="font-medium" data-testid="alert-title">{{ a.title }}</p>
        <p class="text-xs text-ink-muted"><span data-testid="alert-time">{{ istTime(a.created_at) }}</span> - <span data-testid="alert-strategy">{{ plainName(a.strategy_name) ?? `Strategy ${a.strategy_id}` }}</span></p>
        <p class="mt-1 text-sm" data-testid="alert-body">{{ alertBody(a) }}</p>
      </li>
    </ul>
    <p v-else class="mt-4 text-ink-muted" data-testid="alerts-empty">{{ line }}</p>
  </section>
</template>
