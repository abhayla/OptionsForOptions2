<!-- Lane Y item 1: the "Monitoring paused" badge, its reason and since-when, and the grey "Health unknown" dot (REQ-049 line 38,
     REQ-115 AC-4/AC-6). Prints the server's sentences only. No strategy kind is named: a real trade's row uses the same component
     (ADR-330 (58)). `entry` null = no answer yet: nothing is shown. An active entry shows nothing (no "all well" claim). -->
<script setup>
import { computed } from 'vue'
import { istTime } from '@/lib/displayFormat'
const props = defineProps({ entry: { type: Object, default: null } })
// Issue 880: "Since 10:12" can mean any day. When since_at is readable and not today (India date), the date follows the time.
const sinceText = computed(() => {
  const e = props.entry
  if (!e?.since_text) return null
  const at = typeof e.since_at === 'string' ? istTime(e.since_at) : null
  if (!at || at.indexOf(',') < 0) return e.since_text
  const day = (x) => x.slice(0, x.indexOf(','))
  const today = istTime(new Date().toISOString())
  return day(at) === day(today) ? e.since_text : `${e.since_text}, ${day(at)}`
})
</script>

<template>
  <span v-if="entry && entry.watch_state !== 'active'" class="inline-flex flex-wrap items-center gap-x-2 text-sm" data-testid="monitoring-badge" :data-reason="entry.reason">
    <span data-testid="monitoring-paused">⏸ {{ entry.badge_text }}</span>
    <span class="inline-flex items-center gap-1 text-ink-muted" data-testid="monitoring-health-dot" data-health="unknown">
      <span class="inline-block h-2 w-2 rounded-full bg-gray-400" aria-hidden="true"></span>{{ entry.health_text }}
    </span>
    <span class="text-ink-muted" data-testid="monitoring-reason">{{ entry.reason_text }}</span>
    <span v-if="sinceText" class="text-ink-muted" data-testid="monitoring-since">{{ sinceText }}</span>
  </span>
</template>
