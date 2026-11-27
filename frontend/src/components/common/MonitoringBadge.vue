<!-- Lane Y item 1: the "Monitoring paused" badge, its reason and since-when, and the grey "Health unknown" dot (REQ-049 line 38,
     REQ-115 AC-4/AC-6). Prints the server's sentences only. No strategy kind is named: a real trade's row uses the same component
     (ADR-330 (58)). `entry` null = no answer yet: nothing is shown. An active entry shows nothing (no "all well" claim). -->
<script setup>
defineProps({ entry: { type: Object, default: null } })
</script>

<template>
  <span v-if="entry && entry.watch_state !== 'active'" class="inline-flex flex-wrap items-center gap-x-2 text-sm" data-testid="monitoring-badge" :data-reason="entry.reason">
    <span data-testid="monitoring-paused">⏸ {{ entry.badge_text }}</span>
    <span class="inline-flex items-center gap-1 text-ink-muted" data-testid="monitoring-health-dot" data-health="unknown">
      <span class="inline-block h-2 w-2 rounded-full bg-gray-400" aria-hidden="true"></span>{{ entry.health_text }}
    </span>
    <span class="text-ink-muted" data-testid="monitoring-reason">{{ entry.reason_text }}</span>
    <span v-if="entry.since_text" class="text-ink-muted" data-testid="monitoring-since">{{ entry.since_text }}</span>
  </span>
</template>
