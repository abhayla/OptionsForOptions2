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
      <!-- ADR-311: the open legs with no price, named by the server; the total above stays paused -->
      <p v-if="headline.unpriced" class="text-xs text-ink-muted" data-testid="tracking-unpriced">{{ headline.unpriced }}</p>
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
          <tr v-for="leg in rows" :key="leg.key" class="border-b border-line" data-testid="tracking-leg">
            <td class="py-1.5 text-left">
              <span class="inline-flex flex-wrap items-center gap-1.5">
                <Chip :kind="leg.action === 'BUY' ? 'buy' : 'sell'" :label="leg.action === 'BUY' ? 'B' : 'S'" />
                <span data-testid="instrument-text">{{ leg.text }}</span>
              </span>
            </td>
            <td class="py-1.5 pl-6 text-right tabular-nums">{{ leg.entry }}</td>
            <td class="py-1.5 pl-6 text-right tabular-nums">
              <span data-testid="tracking-leg-ltp">{{ leg.exited ? `Exited at ${leg.exitPrice ?? '—'}` : (leg.current ?? '-') }}</span>
              <!-- D-18: the leg's own quote time beside its price (the server's price_at); "time not available" when it sent none -->
              <span v-if="!leg.exited && leg.current !== null" class="ml-1 text-xs text-ink-muted" data-testid="tracking-leg-quote-at">{{ istClock(leg.quoteAt) ?? QUOTE_TIME_UNAVAILABLE_TEXT }}</span>
            </td>
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
        <!-- GC-ICFIX issue 12 (u241): any other fired rule shows the time its record opened, the server's stamp in India time -->
        <span v-else-if="firedClock(f)" data-testid="playbook-flag-time">{{ firedAtText(firedClock(f)) }}</span>
        <!-- ADR-309: a fired rule stays fired until its record clears; the value now is shown beside the one that fired it -->
        <span v-if="f.live_value != null && f.live_value !== f.value" data-testid="playbook-flag-live">{{ liveNowText(f.live_value, f.live_as_of_text) }}</span>
      </div>
      <!-- ADR-272 (3): the check's withheld state, in the server's words, instead of silence -->
      <!-- GC-ICFIX issue 12 (u241, ADR-272 (3), ADR-245): the rules line. A rule that is not checked says so with the server's reason;
           a rule that fired earlier and cleared keeps its line; a failed rule-check read says so; a quiet rule adds nothing. -->
      <p v-if="checkStatus === 'failed'" class="mt-1 text-xs text-red-700" data-testid="rules-load-failed">{{ RULES_LOAD_FAILED_TEXT }}</p>
      <p v-if="settledRecords.state === 'failed'" class="mt-1 text-xs text-red-700" data-testid="rules-earlier-failed">{{ RULES_LOAD_FAILED_TEXT }}</p>
      <ul v-if="notChecked.length || earlier.length" class="mt-1 space-y-0.5 text-xs text-ink-muted" data-testid="rules-line">
        <li v-for="n in notChecked" :key="n.rule_id" data-testid="rules-not-checked">{{ ruleNotCheckedText(n.reason) }}</li>
        <li v-for="e in earlier" :key="e.id" data-testid="rules-earlier">{{ ruleEarlierText(e.text, e.outcome_text, istStamp(e.shown_at), istStamp(e.closed_at)) }}</li>
        <li v-if="earlierMore" data-testid="rules-earlier-more">{{ earlierMoreText(earlierMore) }}</li>
      </ul>
      <p v-if="typed && withheldText" class="mt-1 text-xs text-ink-muted" data-testid="check-withheld">{{ withheldText }}</p>
      <!-- GC-ICFIX u141: the check's own read time; a background re-read that failed keeps the last lines and says so -->
      <p v-if="typed && check.as_of_text" class="mt-1 text-xs text-ink-muted" data-testid="check-as-of">{{ check.as_of_text }}</p>
      <p v-if="typed && checkStale" class="mt-1 text-xs text-red-700" data-testid="check-stale">{{ checkStaleLine(checkRefusal) }}</p>
      <p v-for="a in alreadyTrue" :key="a.rule_id" class="mt-1 text-xs text-ink-muted" data-testid="playbook-already-true">{{ a.wording?.what_happened }} {{ a.condition }}</p>
      <button v-if="view.detections.length || flags.length || liveHere" ref="reviewBtn" type="button" class="mt-2 rounded border border-line bg-surface px-2 py-1 text-xs font-medium" data-testid="review-adjustment" @click="openDrawer">{{ REVIEW_BUTTON_TEXT }}</button>
    </div>
    <!-- GC-ADJ2 step 6 (REQ-163): the entry, every adjustment and the whole-trade totals; read when opened -->
    <AdjustSteps :strategy-id="savedId" />
    <PlanEntry v-if="status === 'tracked'" :strategy-id="savedId" :check="check" :check-status="checkStatus" :check-stale="checkStale" :check-refusal="checkRefusal" :exits="exits" :exits-failed="exitsFailed" @retry-check="retryCheck" />
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
import { LEG_PNL_MISSING, NOT_CONNECTED_TEXT, PAPER_PNL_PREFIX, readTracking } from '@/lib/tracking'
import { closedLegRowsOf, openLegRowsOf, paperPnlBlock } from '@/lib/usePaperBookRead'
import { EARLIER_SHOWN_MAX, QUOTE_TIME_UNAVAILABLE_TEXT, RULES_LOAD_FAILED_TEXT, checkStaleLine, earlierMoreText, firedAtText, liveNowText, ruleEarlierText, ruleNotCheckedText } from '@/lib/sharedStateText'
import { istClock, istStamp } from '@/lib/displayFormat'
import { openRecords, settledRecords } from '@/lib/paperAlerts'
import { said } from '@/lib/playbookEditor'
import { usePaperRefresh } from '@/lib/usePaperRefresh'
import { armedIndexExits, triggerListOf, triggersPath } from '@/lib/paperTriggers'

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
// B6 round 2: a book read for ANOTHER strategy is not this strategy's book (the headline and the rows then come from the tracking reply)
const bookIsHere = computed(() => !!props.shared && (props.shared.strategy_id == null || String(props.shared.strategy_id) === String(props.savedId)))
const block = computed(() => (bookIsHere.value ? paperPnlBlock(props.shared, props.sharedFailed) : null)) // D-41: the page's one book read
const headline = computed(() => {
  const v = view.value
  const s = block.value && v ? block.value : null
  if (!s) return { ...v, line: null, unpriced: v?.unpriced ?? null }
  const text = s.text === null ? (s.line ?? NOT_CONNECTED_TEXT) : `${PAPER_PNL_PREFIX}${s.text} ${s.label}${v.kind === 'exited' ? ' - exited' : ''}`.replace(/ +$/, '')
  return { text, kind: s.kind, breakdown: s.breakdown, afterReason: s.reason, line: s.text === null ? null : s.line, unpriced: s.unpriced ?? null }
})
// D-41 (modular doors, Phase 3): with the page's book read, an OPEN leg's LTP, quote time and P&L are that book's own (its display price,
// ADR-212), the very LegPrice the Net Positions table shows; P&L is the leg's TOTAL, the table's figure (ADR-328 (3)). The leg is found by its
// CONTRACT ID (the reply's contract_id), never by `key` (the feed identity). An exited leg, a leg the book does not hold, and a reply without
// a contract id keep the tracking row: it fails to the old source, never to another contract's price. Up to 5 s after an exit the book and
// tracking reads can differ for one row (two polls); the next tick settles it.
// B6 round 2 (ADR-328 (3), D-10): with a book read for this strategy the rows are built from the book ONLY, as the legs table builds them:
// its open positions (net != 0), then its closed lifecycles, each its own row, so the rows add up to the book total whatever the tracking
// reply says (it may be one poll behind). The tracking reply only supplies the open row's label (with its lots), joined by contract id.
// No usable book read: the tracking reply's rows. A failed read prints the one dash in every row.
const rows = computed(() => {
  const tracked = view.value?.legs ?? []
  if (!block.value) return tracked // no usable book read: the tracking reply's rows
  const label = new Map((view.value?.legs ?? []).filter((l) => l.contractId != null && !l.exited).map((l) => [String(l.contractId), l.text]))
  const open = openLegRowsOf(props.shared, props.sharedFailed).map((r) => ({ ...r, text: label.get(String(r.contractId)) ?? r.text }))
  const all = [...open, ...closedLegRowsOf(props.shared, props.sharedFailed)]
  return all.length ? all : tracked // a book that holds no open contract and no closed lifecycle (empty, or all flat): nothing to build rows from
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
const notChecked = computed(() => (typed.value ? (check.value.results ?? []) : []).filter((r) => r.kind === 'not_checked' && r.reason))
// this trade's settled records only, newest first, at most EARLIER_SHOWN_MAX; the app's one read of the records (header), never a second fetch
const allEarlier = computed(() => [...(settledRecords.byStrategy[props.savedId] ?? [])].sort((a, b) => Date.parse(b.shown_at) - Date.parse(a.shown_at)))
const earlier = computed(() => allEarlier.value.slice(0, EARLIER_SHOWN_MAX))
// D-26: a live idea (an open record of this trade in the app's one read) keeps the Review button even when this panel's own
// rule check gave no flag (failed, not read yet): the button is the way to the approaches
const liveHere = computed(() => openRecords.list.some((o) => o.strategy_id === props.savedId))
const earlierMore = computed(() => allEarlier.value.length - earlier.value.length)
const firedClock = (f) => istStamp(f.fired_at)
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
// GC-ICLIVE D-24: the armed / fired index exits of this strategy, read on the same rhythm as the check (never a second timer)
let lastKind = null // the previous tick's tracking kind
const exits = ref([])
const exitsFailed = ref(false)
async function readExits(id) {
  try {
    const { data } = await api.get(triggersPath(id))
    if (id !== props.savedId) return
    const list = triggerListOf(data)
    exits.value = armedIndexExits(list ?? [])
    exitsFailed.value = list === null
  } catch {
    if (id === props.savedId) exitsFailed.value = true // the last good lines stay
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
    ...flags.value.flatMap((f) => {
      const name = String(f.condition ?? '').split(':')[0] || f.rule_id // the rule's own label, as its condition line names it
      return [f.wording, f.condition, firedClock(f) ? `${name}: ${firedAtText(firedClock(f))}` : null,
        f.live_value != null && f.live_value !== f.value ? `${name}: ${liveNowText(f.live_value, f.live_as_of_text)}` : null].filter(Boolean)
    }),
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
  exits.value = []
  exitsFailed.value = false
  lastKind = null
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
    await Promise.all([readCheck(id), readExits(id)])
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
    // the exits are read on every tick not exited AND on the tick the kind turns exited (a fired exit is what exited it); the check keeps its skip
    const wasExited = lastKind === 'exited'
    lastKind = view.value?.kind
    if (lastKind !== 'exited') readCheck(props.savedId, true)
    if (lastKind !== 'exited' || !wasExited) readExits(props.savedId)
  },
  onError: failed,
})

watch(() => props.savedId, load, { immediate: true })
</script>
