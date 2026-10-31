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
      <!-- GC-ADJ2 step 5 (REQ-045 AC-1, F-71): a typed strategy's playbook flags from GET .../adjustment-check, the label
           and the condition as the server worded them; a rule already true at entry is a quiet line, never a flag. -->
      <div v-for="f in flags" :key="f.rule_id" class="mt-2 flex flex-wrap items-center gap-2 rounded bg-warn-soft px-2 py-1.5 text-sm" data-testid="playbook-flag">
        <Chip kind="state" :label="f.wording" data-testid="playbook-flag-label" />
        <span data-testid="playbook-flag-condition">{{ f.condition }}</span>
      </div>
      <p v-for="a in alreadyTrue" :key="a.rule_id" class="mt-1 text-xs text-ink-muted" data-testid="playbook-already-true">{{ a.wording?.what_happened }} {{ a.condition }}</p>
      <button v-if="view.detections.length || flags.length" ref="reviewBtn" type="button" class="mt-2 rounded border border-line bg-surface px-2 py-1 text-xs font-medium" data-testid="review-adjustment" @click="openDrawer">{{ REVIEW_BUTTON_TEXT }}</button>
    </div>
    <!-- GC-ADJ2 step 6 (REQ-163): the entry, every adjustment and the whole-trade totals; read when opened -->
    <AdjustSteps :strategy-id="savedId" />
    <PlanEntry v-if="status === 'tracked'" :strategy-id="savedId" />
    <AdjustDrawer
      :open="drawerOpen" :strategy-id="savedId" :lines="drawerLines" :detected="!!view?.detections?.length || flags.length > 0" :card-rows="cardRows(raw)"
      :suggestion-ids="flagIds"
      @close="closeDrawer" @compare="goCompare" @dismissed="onDismissed"
    />
  </section>
</template>

<script setup>
import { computed, inject, nextTick, ref, watch } from 'vue'
import { routerKey } from 'vue-router'
import AdjustDrawer from '@/components/strategy/AdjustDrawer.vue'
import AdjustSteps from '@/components/strategy/AdjustSteps.vue'
import PlanEntry from '@/components/strategy/PlanEntry.vue'
import { REVIEW_BUTTON_TEXT, cardRows } from '@/lib/adjustDrawer'
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
const router = inject(routerKey, null) // absent in a panel mounted without a router: Compare then goes nowhere
const reviewBtn = ref(null)
const drawerOpen = ref(false)
const drawerLines = ref([]) // layer 1: the detection's own text; kept when the detection lapses while the drawer is open
// GC-ADJ2 step 5: the playbook check answer. A typed strategy (strategy_type set) shows its flags; an untyped one keeps
// the platform detection of the tracking answer. A failed read shows no flag (nothing is invented here).
const check = ref(null)
const dismissed = ref([]) // record ids dismissed from the drawer: their flags leave the card at once
const typed = computed(() => !!check.value?.strategy_type)
const flags = computed(() => (typed.value ? (check.value.results ?? []) : [])
  .filter((r) => r.kind === 'flag' && !dismissed.value.includes(r.suggestion_id)))
const alreadyTrue = computed(() => (typed.value ? (check.value.results ?? []) : []).filter((r) => r.kind === 'already_true'))
const flagIds = computed(() => flags.value.map((f) => f.suggestion_id).filter((x) => x !== null && x !== undefined))
async function readCheck(id) {
  try {
    const { data } = await api.get(`/strategies/${id}/adjustment-check`)
    if (id === props.savedId) check.value = data
  } catch {
    if (id === props.savedId) check.value = null
  }
}
function onDismissed({ ids }) {
  dismissed.value = [...dismissed.value, ...ids]
  closeDrawer()
}
function openDrawer() {
  drawerLines.value = [
    ...(view.value?.detections ?? []).flatMap((d) => [d.line, ...d.details]),
    ...flags.value.flatMap((f) => [f.wording, f.condition].filter(Boolean)),
  ]
  drawerOpen.value = true
}
async function closeDrawer() {
  drawerOpen.value = false
  await nextTick()
  reviewBtn.value?.focus?.() // the button may be gone if the detection lapsed
}
function goCompare({ url }) {
  drawerOpen.value = false
  router?.push(url)
}

function failed(e) {
  view.value = null
  error.value = e?.parts?.what_happened || NEUTRAL_ERROR
}

async function load(id) {
  status.value = 'loading'
  view.value = null
  raw.value = null
  check.value = null
  dismissed.value = []
  drawerOpen.value = false
  error.value = ''
  if (!id) return
  try {
    const { data } = await api.get(`/strategies/${id}/tracking`)
    if (id !== props.savedId) return // R1-2: the user opened another strategy while this read was out
    status.value = 'tracked'
    view.value = readTracking(data, props.legs)
    raw.value = data
    await readCheck(id)
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
