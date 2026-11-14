<!-- W-122 (REQ-109 AC-1, AC-2, AC-5; REQ-045 AC-1; REQ-046 AC-1; ADR-166): paper tracking of a saved strategy.
     Layout after the studied Draft Portfolios screens (per-leg entry and LTP, the total inside a dashed frame). The
     server stores the entry prices; the browser shows the server's strings (orders are placed from Add to Paper). A failed
     or unreadable answer shows no figure. Nothing here reaches Execute (REQ-109 AC-3). -->
<template>
  <section v-if="savedId" class="mt-4 rounded-lg border border-line bg-surface p-4" data-testid="tracking-panel">
    <p v-if="error" class="text-sm text-red-700" data-testid="tracking-error">{{ error }}</p>
    <div v-if="view" class="border-2 border-dashed rounded-lg p-3" data-testid="tracking-view">
      <AfterChargesTap :breakdown="headline.breakdown ?? null"><p class="font-semibold" data-testid="paper-pnl" :data-kind="headline.kind">{{ headline.text }}</p></AfterChargesTap>
      <p v-if="headline.afterReason" class="text-xs text-ink-muted" data-testid="tracking-after-reason">{{ headline.afterReason }}</p>
      <p v-if="headline.line" class="text-xs text-ink-muted" data-testid="paper-shared-line">{{ headline.line }}</p>
      <table v-if="view.legs.length" class="mt-2 w-full text-sm">
        <thead>
          <tr class="border-b border-line text-ink-muted">
            <th scope="col" class="py-1.5 text-left font-medium">Leg</th>
            <th scope="col" class="py-1.5 pl-6 text-right font-medium">Paper entry</th>
            <th scope="col" class="py-1.5 pl-6 text-right font-medium">LTP</th>
            <th scope="col" class="py-1.5 pl-6 text-right font-medium" data-testid="tracking-leg-pnl-head">P&amp;L (before charges)</th>
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
        <!-- GC-ICFIX u142: a fired stop's loss now / stop line in rupees and percent and the time it fired, the server's sentence -->
        <span v-if="f.stop_text" data-testid="playbook-flag-stop">{{ f.stop_text }}</span>
      </div>
      <!-- ADR-272 (3): the check's withheld state, in the server's words, instead of silence -->
      <p v-if="typed && withheldText" class="mt-1 text-xs text-ink-muted" data-testid="check-withheld">{{ withheldText }}</p>
      <!-- GC-ICFIX u141: the check's own read time; a background re-read that failed keeps the last lines and says so -->
      <p v-if="typed && check.as_of_text" class="mt-1 text-xs text-ink-muted" data-testid="check-as-of">{{ check.as_of_text }}</p>
      <p v-if="typed && checkStale" class="mt-1 text-xs text-red-700" data-testid="check-stale">{{ checkStaleLine(checkRefusal) }}</p>
      <p v-for="a in alreadyTrue" :key="a.rule_id" class="mt-1 text-xs text-ink-muted" data-testid="playbook-already-true">{{ a.wording?.what_happened }} {{ a.condition }}</p>
      <button v-if="view.detections.length || flags.length" ref="reviewBtn" type="button" class="mt-2 rounded border border-line bg-surface px-2 py-1 text-xs font-medium" data-testid="review-adjustment" @click="openDrawer">{{ REVIEW_BUTTON_TEXT }}</button>
    </div>
    <!-- GC-ADJ2 step 6 (REQ-163): the entry, every adjustment and the whole-trade totals; read when opened -->
    <AdjustSteps :strategy-id="savedId" />
    <PlanEntry v-if="status === 'tracked'" :strategy-id="savedId" :check="check" :check-status="checkStatus" :check-stale="checkStale" :check-refusal="checkRefusal" @retry-check="retryCheck" />
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
import AfterChargesTap from '@/components/common/AfterChargesTap.vue'
import AdjustSteps from '@/components/strategy/AdjustSteps.vue'
import PlanEntry from '@/components/strategy/PlanEntry.vue'
import { REVIEW_BUTTON_TEXT, cardRows } from '@/lib/adjustDrawer'
import Chip from '@/components/common/Chip.vue'
import FigureHint from '@/components/common/FigureHint.vue'
import api, { NEUTRAL_PARTS } from '@/services/api'
import { NOT_CONNECTED_TEXT, PAPER_PNL_PREFIX, readTracking, sharedTotal } from '@/lib/tracking'
import { checkStaleLine } from '@/lib/sharedStateText'
import { said } from '@/lib/playbookEditor'
import { usePaperRefresh } from '@/lib/usePaperRefresh'

const props = defineProps({
  savedId: { type: Number, default: null },
  shared: { type: Object, default: null }, // GC-ICFIX round 2 (F4): the page's ONE read of /paper/strategies/{id}: the profit figure and its As of come from it
  sharedFailed: { type: Boolean, default: false }, // the last shared read failed: the last figure stays, with the paused sentence
  legs: { type: Array, default: null }, // the builder reply's legs: their whole-lot count names each paper leg in lots (D-B39)
})

const status = ref('loading')
const view = ref(null)
const error = ref('')
const raw = ref(null) // the last tracking reply, for the drawer's layer 2 (display only)
const router = inject(routerKey, null) // absent in a panel mounted without a router: Compare then goes nowhere
const reviewBtn = ref(null)
// The headline total: from the page's shared paper read when there is one (so it equals the paper panel and the P&L table TOTAL
// row); what still comes from the tracking read: legs, per-leg P&L, detections, the rule check, and the headline when no shared read.
// Prices not live = the paused sentence, no number (REQ-109 AC-5).
const headline = computed(() => {
  const v = view.value
  const s = props.shared && v ? sharedTotal(props.shared, props.sharedFailed) : null
  if (!s) return { ...v, line: null }
  const text = s.text === null ? (s.line ?? NOT_CONNECTED_TEXT) : `${PAPER_PNL_PREFIX}${s.text} ${s.label}${v.kind === 'exited' ? ' - exited' : ''}`.replace(/ +$/, '')
  return { text, kind: s.kind, breakdown: s.breakdown, afterReason: s.reason, line: s.text === null ? null : s.line }
})
const drawerOpen = ref(false)
const drawerLines = ref([]) // layer 1: the detection's own text; kept when the detection lapses while the drawer is open
// GC-ADJ2 step 5: the playbook check answer. A typed strategy (strategy_type set) shows its flags; an untyped one keeps
// the platform detection of the tracking answer. A failed read shows no flag (nothing is invented here).
const check = ref(null)
const dismissed = ref([]) // record ids dismissed from the drawer: their flags leave the card at once
const withheldText = computed(() => said(check.value?.withheld)) // the server sends the withheld note as its error parts: only the sentence is shown
const typed = computed(() => !!check.value?.strategy_type)
const flags = computed(() => (typed.value ? (check.value.results ?? []) : [])
  .filter((r) => r.kind === 'flag' && !dismissed.value.includes(r.suggestion_id)))
const alreadyTrue = computed(() => (typed.value ? (check.value.results ?? []) : []).filter((r) => r.kind === 'already_true'))
const flagIds = computed(() => flags.value.map((f) => f.suggestion_id).filter((x) => x !== null && x !== undefined))
const checkStatus = ref('loading') // the plan card's limit lines read this one check: 'loading' | 'ok' | 'failed' (ADR-304 (3))
const checkStale = ref(false) // GC-ICFIX u141: a background re-read failed after a good read: the last lines stay, marked
const checkRefusal = ref('') // the server's sentence when the last check read was refused (a catalogue body); '' = no usable body
let checkReading = false // one check read at a time (a tick while one is out does nothing)
// `background` = the re-read inside the page's refresh: it never flips the status to loading and never blanks a good reply.
async function readCheck(id, background = false) {
  if (background && checkReading) return
  checkReading = true
  if (!background) checkStatus.value = 'loading'
  try {
    const { data } = await api.get(`/strategies/${id}/adjustment-check`)
    if (id === props.savedId) { check.value = data; checkStatus.value = 'ok'; checkStale.value = false; checkRefusal.value = '' }
  } catch (e) {
    if (id !== props.savedId) return
    checkRefusal.value = e?.parts?.what_happened ?? ''
    if (background && check.value) checkStale.value = true
    else if (!background) { check.value = null; checkStatus.value = 'failed' }
  } finally {
    checkReading = false
  }
}
const retryCheck = () => readCheck(props.savedId)
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
  error.value = (e?.parts ?? NEUTRAL_PARTS).what_happened
}

async function load(id) {
  status.value = 'loading'
  view.value = null
  raw.value = null
  check.value = null
  checkStatus.value = 'loading'
  checkStale.value = false
  checkRefusal.value = ''
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
    // GC-ICFIX u141: the rule check rides the same rhythm (no second timer); a closed trade's check is not re-read (as before)
    if (view.value?.kind !== 'exited') readCheck(props.savedId, true)
  },
  onError: failed,
})

watch(() => props.savedId, load, { immediate: true })
</script>
