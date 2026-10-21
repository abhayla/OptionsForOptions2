<!-- W-117 (REQ-009 AC-6; ADR-114, ADR-003): the Alerts pages - Active, History, Notification settings - as honest empty
     states. No alert logic exists yet (GC-4), so there are no rows, no buttons and no fake data. -->
<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const NO_ALERTS = 'No alerts yet. Alerts start when strategy monitoring rules are added.'
const NO_CHANNELS = 'No notification channels are set up yet.'

const route = useRoute()
const line = computed(() => (route.path.endsWith('/notification-settings') ? NO_CHANNELS : NO_ALERTS))
</script>

<template>
  <section data-testid="alerts">
    <p class="text-xs text-ink-muted" data-testid="page-parent">Alerts</p>
    <h1 class="text-xl font-semibold" data-testid="page-title">{{ route.meta.title }}</h1>
    <p class="mt-4 text-ink-muted" data-testid="alerts-empty">{{ line }}</p>
  </section>
</template>
