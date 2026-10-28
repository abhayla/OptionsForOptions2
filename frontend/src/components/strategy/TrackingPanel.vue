<!-- W-122 (REQ-109 AC-1, AC-2, AC-5; REQ-045 AC-1; REQ-046 AC-1; ADR-166): paper tracking of a saved strategy.
     Layout after the studied Draft Portfolios screens (per-leg entry and LTP, the total inside a dashed frame). The
     server stores the entry prices; the browser sends only the saved revision and shows the server's strings. A failed
     or unreadable answer shows no figure. Nothing here reaches Execute (REQ-109 AC-3). -->
<template>
  <section v-if="savedId" class="p-4 border-t" data-testid="tracking-panel">
    <div v-if="status === 'untracked'" class="flex items-center gap-3">
      <button
        type="button"
        data-testid="start-tracking"
        :disabled="busy || savedRevision === null"
        class="px-4 py-2 text-sm font-medium rounded-lg border border-line"
        @click="start"
      >
        {{ START_TRACKING_LABEL }}
      </button>
    </div>
    <p v-if="error" class="text-sm text-red-700" data-testid="tracking-error">{{ error }}</p>
    <div v-if="view" class="border-2 border-dashed rounded-lg p-3" data-testid="tracking-view">
      <p class="font-semibold" data-testid="paper-pnl" :data-kind="view.kind">{{ view.text }}</p>
      <table v-if="view.legs.length" class="mt-2 text-sm">
        <thead>
          <tr><th>Leg</th><th>Paper entry</th><th>LTP</th></tr>
        </thead>
        <tbody>
          <tr v-for="leg in view.legs" :key="leg.key" data-testid="tracking-leg">
            <td>{{ leg.action }} {{ leg.strike ?? '' }} {{ leg.instrument }}</td>
            <td>{{ leg.entry }}</td>
            <td>{{ leg.current ?? '-' }}</td>
          </tr>
        </tbody>
      </table>
      <div v-for="d in view.detections" :key="d.key" class="mt-3 p-2 bg-amber-50 rounded" data-testid="detection">
        <p class="font-semibold">{{ d.label }}</p>
        <ul class="text-sm">
          <li>{{ d.condition }}: {{ d.level }}</li>
          <li>Index: {{ d.index }}</li>
          <li>Distance: {{ d.distance }}</li>
          <li>Threshold: {{ d.threshold }}</li>
          <li>As of {{ d.at }}</li>
        </ul>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, watch } from 'vue'
import api, { NEUTRAL_ERROR } from '@/services/api'
import { START_TRACKING_LABEL, readTracking } from '@/lib/tracking'
import { usePaperRefresh } from '@/lib/usePaperRefresh'

const props = defineProps({
  savedId: { type: Number, default: null },
  savedRevision: { type: Number, default: null },
})

const status = ref('loading')
const view = ref(null)
const error = ref('')
const busy = ref(false)

function failed(e) {
  view.value = null
  error.value = e?.parts?.what_happened || NEUTRAL_ERROR
}

async function load(id) {
  status.value = 'loading'
  view.value = null
  error.value = ''
  if (!id) return
  try {
    const { data } = await api.get(`/strategies/${id}/tracking`)
    if (id !== props.savedId) return // R1-2: the user opened another strategy while this read was out
    status.value = 'tracked'
    view.value = readTracking(data)
  } catch (e) {
    if (id !== props.savedId) return
    if (e?.status === 404) status.value = 'untracked'
    else failed(e)
  }
}

async function start() {
  busy.value = true
  error.value = ''
  try {
    // the revision the page loaded: a strategy changed since then is refused by the server (409), never re-read here
    const { data } = await api.post(`/strategies/${props.savedId}/tracking`, { revision: props.savedRevision })
    status.value = 'tracked'
    view.value = readTracking(data)
  } catch (e) {
    failed(e)
  } finally {
    busy.value = false
  }
}

// GC-BP F-1 (the one shared loop, usePaperRefresh): while tracked, re-read every TRACKING_REFRESH_MS.
usePaperRefresh({
  key: () => props.savedId,
  enabled: () => status.value === 'tracked',
  read: async (id) => (await api.get(`/strategies/${id}/tracking`)).data,
  onData: (data) => {
    error.value = ''
    view.value = readTracking(data)
  },
  onError: failed,
})

watch(() => props.savedId, load, { immediate: true })
</script>
