<!-- GC-6 ST-SESSION (REQ-015 AC-5). Blocking card. Reconnect remembers the CURRENT route in sessionStorage (RETURN_ROUTE_KEY)
     and emits `reconnect` with it; the page starts the Zerodha login (API route /broker/zerodha/login) and, once connected,
     sends the user back to the stored route. Last sync time is the server's ISO instant via istTime. -->
<script setup>
import { useRoute } from 'vue-router'
import { istTime } from '@/lib/displayFormat'
import { SESSION_ENDED_TEXT, RECONNECT_LABEL, LAST_SYNC_PREFIX, RETURN_ROUTE_KEY } from '@/lib/sharedStateText'

defineProps({ lastSyncAt: { type: String, default: null } })
const emit = defineEmits(['reconnect'])
const route = useRoute()

function reconnect() {
  const returnTo = route?.fullPath ?? '/'
  try { sessionStorage.setItem(RETURN_ROUTE_KEY, returnTo) } catch { /* storage unavailable: the emit still carries it */ }
  emit('reconnect', { returnTo })
}
</script>

<template>
  <div role="alertdialog" aria-modal="true" class="rounded border border-line bg-surface p-4" data-testid="session-ended-card">
    <p class="font-medium" data-testid="session-ended-text">{{ SESSION_ENDED_TEXT }}</p>
    <p v-if="lastSyncAt" class="mt-1 text-sm text-ink-muted" data-testid="session-last-sync">{{ LAST_SYNC_PREFIX }}{{ istTime(lastSyncAt) }}</p>
    <button type="button" class="mt-3 min-h-[44px] rounded border border-line px-3" data-testid="session-reconnect" @click="reconnect">{{ RECONNECT_LABEL }}</button>
  </div>
</template>
