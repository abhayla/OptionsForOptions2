<!-- W-122 (REQ-109 AC-1, AC-2, AC-5; REQ-045 AC-1; REQ-046 AC-1; ADR-166): paper tracking of a saved strategy.
     Layout after the studied Draft Portfolios screens (per-leg entry and LTP, the total inside a dashed frame). The
     server stores the entry prices; the browser shows the server's strings (orders are placed from Add to Paper). A failed
     or unreadable answer shows no figure. Nothing here reaches Execute (REQ-109 AC-3). -->
<template>
  <section v-if="savedId" class="mt-4 rounded-lg border border-line bg-surface p-4" data-testid="tracking-panel">
    <p v-if="error" class="text-sm text-red-700" data-testid="tracking-error">{{ error }}</p>
    <div v-if="view" class="border-2 border-dashed rounded-lg p-3" data-testid="tracking-view">
      <p class="font-semibold" data-testid="paper-pnl" :data-kind="view.kind">{{ view.text }}</p>
      <table v-if="view.legs.length" class="mt-2 w-full text-sm">
        <thead>
          <tr class="border-b border-line text-ink-muted">
            <th scope="col" class="py-1.5 text-left font-medium">Leg</th>
            <th scope="col" class="py-1.5 pl-6 text-right font-medium">Paper entry</th>
            <th scope="col" class="py-1.5 pl-6 text-right font-medium">LTP</th>
            <th scope="col" class="py-1.5 pl-6 text-right font-medium">P&amp;L</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="leg in view.legs" :key="leg.key" class="border-b border-line" data-testid="tracking-leg">
            <td class="py-1.5 text-left">
              <span class="inline-flex flex-wrap items-center gap-1.5">
                <Chip :kind="leg.action === 'BUY' ? 'buy' : 'sell'" :label="leg.action === 'BUY' ? 'B' : 'S'" />
                <span data-testid="instrument-text">{{ leg.text }}</span>
              </span>
            </td>
            <td class="py-1.5 pl-6 text-right tabular-nums">{{ leg.entry }}</td>
            <td class="py-1.5 pl-6 text-right tabular-nums">{{ leg.exited ? `Exited at ${leg.exitPrice ?? '—'}` : (leg.current ?? '-') }}</td>
            <!-- GC-UI b2 D-B48: the server's per-leg paper P&L text (booked legs say so), "—" when it sent none -->
            <td class="py-1.5 pl-6 text-right tabular-nums" data-testid="tracking-leg-pnl">{{ leg.pnl }}</td>
          </tr>
        </tbody>
      </table>
      <!-- GC-UI D-B50 (ADR-202 (1), ADR-204): one visible line per detection; index, distance, threshold and time are
           behind its "?" (REQ-046 AC-1 Layer 1, every word reachable). -->
      <div v-for="d in view.detections" :key="d.key" class="mt-2 flex items-center rounded bg-warn-soft px-2 py-1.5 text-sm" data-testid="detection">
        <p class="font-semibold" data-testid="detection-line">{{ d.line }}</p>
        <FigureHint id="adjustment_detection" label="Why detected" :lines="d.details" />
      </div>
      <!-- GC-ADJ1 step 3 (REQ-046 AC-1..AC-3): the drawer with layers 1-3; shown only while a detection is shown -->
      <button ref="reviewBtn" type="button" v-if="view.detections.length" class="mt-2 rounded border border-line bg-surface px-2 py-1 text-xs font-medium" data-testid="review-adjustment" @click="openDrawer">{{ REVIEW_BUTTON_TEXT }}</button>
    </div>
    <AdjustDrawer
      :open="drawerOpen" :strategy-id="savedId" :lines="drawerLines" :detected="!!view?.detections?.length" :rows="stateRows(raw)" :legs="raw?.legs ?? []"
      @close="closeDrawer" @compare="goCompare"
    />
  </section>
</template>

<script setup>
import { nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import AdjustDrawer from '@/components/strategy/AdjustDrawer.vue'
import { REVIEW_BUTTON_TEXT, stateRows } from '@/lib/adjustDrawer'
import Chip from '@/components/common/Chip.vue'
import FigureHint from '@/components/common/FigureHint.vue'
import api, { NEUTRAL_ERROR } from '@/services/api'
import { readTracking } from '@/lib/tracking'
import { usePaperRefresh } from '@/lib/usePaperRefresh'

const props = defineProps({
  savedId: { type: Number, default: null },
  legs: { type: Array, default: null }, // the builder reply's legs: their whole-lot count names each paper leg in lots (D-B39)
})

const status = ref('loading')
const view = ref(null)
const error = ref('')
const raw = ref(null) // the last tracking reply, for the drawer's layer 2 (display only)
const router = useRouter()
const reviewBtn = ref(null)
const drawerOpen = ref(false)
const drawerLines = ref([]) // layer 1: the detection's own text; kept when the detection lapses while the drawer is open
function openDrawer() {
  drawerLines.value = (view.value?.detections ?? []).flatMap((d) => [d.line, ...d.details])
  drawerOpen.value = true
}
async function closeDrawer() {
  drawerOpen.value = false
  await nextTick()
  reviewBtn.value?.focus?.() // the button may be gone if the detection lapsed
}
function goCompare({ url }) {
  drawerOpen.value = false
  router.push(url)
}

function failed(e) {
  view.value = null
  error.value = e?.parts?.what_happened || NEUTRAL_ERROR
}

async function load(id) {
  status.value = 'loading'
  view.value = null
  raw.value = null
  drawerOpen.value = false
  error.value = ''
  if (!id) return
  try {
    const { data } = await api.get(`/strategies/${id}/tracking`)
    if (id !== props.savedId) return // R1-2: the user opened another strategy while this read was out
    status.value = 'tracked'
    view.value = readTracking(data, props.legs)
    raw.value = data
  } catch (e) {
    if (id !== props.savedId) return
    if (e?.status === 404) status.value = 'untracked'
    else failed(e)
  }
}

// GC-BP F-1 (the one shared loop, usePaperRefresh): while tracked, re-read every TRACKING_REFRESH_MS.
usePaperRefresh({
  key: () => props.savedId,
  enabled: () => status.value === 'tracked',
  read: async (id) => (await api.get(`/strategies/${id}/tracking`)).data,
  onData: (data) => {
    error.value = ''
    view.value = readTracking(data, props.legs)
    raw.value = data
  },
  onError: failed,
})

watch(() => props.savedId, load, { immediate: true })
</script>
