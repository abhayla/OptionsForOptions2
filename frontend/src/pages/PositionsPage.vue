<!-- Positions pages, part 1 (W-111; REQ-044 AC-3, ADR-109 (2), ADR-027, ADR-138 (2)). Reads GET /api/positions once on
     load and shows QUANTITIES and each contract's Zerodha P&L (Lane S: the server's figure, or a dash with its reason) grouped by strategy, with each strategy's link: no price, margin or Greek, no
     order button (every action routes back to the strategy). ADR-138 (2): "strategy groups, strategy P&L, the mismatch
     badge and "N outside lots - view on Kite"; no copy of Kite's full position list" - so only contracts linked to a
     strategy are rows; units no strategy owns are one count with a link to Kite. A refused read (no Zerodha session,
     failed read) shows the catalogue message, never an empty list. A PENDING contract (ADR-110: an open plan's orders are
     not final at Zerodha) shows the waiting line, Zerodha's quantity marked not yet confirmed, no own split, and the link
     to the strategy's Execute screen where Check is. Both Positions menu items show this same strategy-grouped page.
     New file, copy from: none. -->
<script setup>
import ListLoadFailed from '@/components/common/ListLoadFailed.vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import api, { NEUTRAL_PARTS, hasShape } from '@/services/api'
import PageHeader from '@/components/common/PageHeader.vue'
import PriceNotice from '@/components/states/PriceNotice.vue'
import { readAnswer } from '@/composables/useIndexLive'
import EmptyState from '@/components/states/EmptyState.vue'
import PositionsTotals from '@/components/positions/PositionsTotals.vue'
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'
import PlanDoor from '@/components/strategy/PlanDoor.vue'
import { istTime } from '@/lib/displayFormat'
import { priceNoticeUp } from '@/lib/priceState'
import { PAPER_NO_FIGURE as NO_FIGURE } from '@/lib/paperList'
import { KITE_POSITIONS_URL } from '@/lib/execute'
import { useOrderPath } from '@/lib/orderPath'
import { brokerIsConnected } from '@/lib/brokerConnected'
import { recordLineOf } from '@/lib/positionKind'

const route = useRoute()
// ADR-330 (10) replaces ADR-201 (2): ONE list for real and paper trades, filtered All / Real / Paper (default All). The old
// ?tab=paper opens Paper and ?tab=positions opens Real, so bookmarks and the builder's links still land where they did.
const FILTERS = [{ key: 'all', label: 'All' }, { key: 'real', label: 'Real' }, { key: 'paper', label: 'Paper' }]
const filterOf = (tab) => (tab === 'paper' ? 'paper' : tab === 'positions' ? 'real' : 'all')
// ?exit= (the Live card's Exit link) always opens on Paper, so the exit confirm never opens over the Real view; the filter stays Paper
// after PaperStrategies consumes the parameter (the tab did not change, so nothing resets it).
const hasExit = () => route.query.exit !== undefined
const filter = ref(hasExit() ? 'paper' : filterOf(route.query.tab))
watch(() => route.query.tab, (tab) => { filter.value = hasExit() ? 'paper' : filterOf(tab) })
watch(() => route.query.exit, (x) => { if (x !== undefined) filter.value = 'paper' })
const paperSummary = ref(null) // PaperStrategies' emitted figures: this page reads no paper list itself (one reader)
const notConnected = ref(false) // the read was refused AND the connection read says not connected
// W-121 (REQ-073 AC-6, ADR-165): a link to the strategy's Execute screen is absent (not disabled) unless the server said
// the order path is on; off, the strategy is named in plain text.
const orderPathOn = useOrderPath()
const view = route.meta.view === 'linked' ? 'linked' : 'current'
const loading = ref(true)
const result = ref(null)
const errorParts = ref(null)
// The page's own words, one home each (ADR-110 quotes the first two verbatim).
const WAITING = 'Order placed - waiting for Check with Zerodha'
const UNCONFIRMED = 'not yet confirmed'
const BLOCKED = 'blocked until its position matches Zerodha'
// A pending contract's other holders are blocked too (ADR-110 + Q224); the answer names them in blocked_strategy_ids.
const HOLDERS = 'Every other strategy holding units on this contract is blocked too (listed above).'
const NO_ROW = 'No confirmed position of this strategy to show yet.'
const REAL_TAG = 'REAL (Zerodha)'
const VIEW_ON_KITE = 'view on Kite'
const outsideText = (lots) => (lots === null ? 'Positions outside your strategies' : `${lots} outside ${lots === 1 ? 'lot' : 'lots'}`)

const realEmpty = computed(() => !!result.value && !result.value.strategies.length && !result.value.has_outside)
// the five answer states of the real section; the paper section below it never waits for, or hides behind, any of them
const realState = computed(() => {
  if (loading.value) return 'loading'
  if (errorParts.value) return notConnected.value ? 'not_connected' : 'read_failed'
  if (brokerOff.value) return 'not_connected'
  return realEmpty.value ? 'empty' : 'connected'
})
// fd2: no Zerodha session is a 200 with broker_connected:false (real_pnl.state "not_connected" and its reason); only exactly false counts, so an old reply is unchanged
const brokerOff = computed(() => result.value?.broker_connected === false)
const NOT_CONNECTED_LINE = 'No broker is connected, so no real positions are shown.' // new wording, pending owner read (28 Nov 2026): used only when the server sent no reason
const brokerOffLine = computed(() => { const r = result.value?.real_pnl?.reason; return typeof r === 'string' && r.trim() !== '' ? r : NOT_CONNECTED_LINE })
// ADR-330 (10), (24): the Real P&L total is the server's real_pnl, every string printed as sent (no arithmetic here). A refused read
// shows its own message as the reason; only a reply with no real_pnl key keeps the legacy "not shown yet" line.
const realTotals = computed(() => {
  if (figureOld.value && !errorParts.value) return { text: null, reason: OLD_FIGURE_TEXT, caption: null, note: null }
  if (errorParts.value) return { text: null, reason: errorParts.value.what_happened ?? null, caption: null, note: null }
  const r = result.value?.real_pnl
  if (result.value && !r) return { text: typeof result.value.pnl_text === 'string' ? result.value.pnl_text : null, legacy: true }
  if (!r) return null
  return { text: r.state === 'stated' ? r.pnl_text : null, reason: r.reason, caption: r.caption, note: r.excludes_note }
})
// ADR-330 (56): the page's one price notice reads the index answer (market closed: the banner with the close time; feed down: the not-live line)
const marketAnswer = ref(null)
const noticeUp = computed(() => priceNoticeUp(marketAnswer.value, paperSummary.value?.affected || null)) // UX-A09: the list stays quiet exactly when the page notice speaks
onMounted(async () => { marketAnswer.value = await readAnswer(false) })
// D-13 (R2 FC2): the Real part is re-read every REREAD_MS and at once when the browser loses or regains its connection. A figure
// older than STALE_AFTER_MS (the server's own STALE_AFTER_SECONDS = 90, routes/positions.py) is hidden, so a hung read or a gone
// session never leaves an old number on the page. Age is counted from the page's receipt of the read; no timer outlives the page.
const REREAD_MS = 30_000
const STALE_AFTER_MS = 90_000
const CHECK_MS = 10_000
const OLD_FIGURE_TEXT = 'The real P&L figure is more than 90 seconds old and is hidden until the next read.' // pending owner read
const figureOld = ref(false)
let lastGoodAt = 0
let seq = 0
async function loadReal() {
  const mine = ++seq
  try {
    const body = (await api.get('/positions')).data
    if (!hasShape(body, ['strategies']) || !Array.isArray(body.strategies)) throw { unreadable: true } // ADR-008: an answer with no strategies list is a failed read, never an empty one
    if (mine !== seq) return
    result.value = body
    errorParts.value = null
    notConnected.value = false
    lastGoodAt = Date.now()
    figureOld.value = false
  } catch (e) {
    if (mine !== seq) return
    errorParts.value = e?.parts ?? NEUTRAL_PARTS
    // fail closed: only a connection read that succeeded and says not connected is "not connected"; an unreadable one is a failed read
    let nc = false
    try { nc = !brokerIsConnected((await api.get('/broker/status')).data) } catch { nc = false }
    if (mine === seq) notConnected.value = nc
  } finally {
    if (mine === seq) loading.value = false
  }
}
let rereadTimer = null
let checkTimer = null
const onLinkChange = () => { loadReal() }
onMounted(() => {
  loadReal()
  rereadTimer = setInterval(loadReal, REREAD_MS)
  checkTimer = setInterval(() => { if (result.value && !errorParts.value && Date.now() - lastGoodAt > STALE_AFTER_MS) figureOld.value = true }, CHECK_MS)
  window.addEventListener('offline', onLinkChange)
  window.addEventListener('online', onLinkChange)
})
onBeforeUnmount(() => {
  clearInterval(rereadTimer)
  clearInterval(checkTimer)
  window.removeEventListener('offline', onLinkChange)
  window.removeEventListener('online', onLinkChange)
  seq++ // an answer that arrives after the page is left is dropped
})
</script>

<template>
  <!-- Owner 2026-10-30 (Sensibull 050 / 090): the shared header, a summary bar (read time left, outside lots right), then one
       card per strategy with its contracts in an aligned table (Contract | Your units | Zerodha | Status). -->
  <section data-testid="positions-page" :data-view="view">
    <PageHeader :parent="route.meta.parent ?? ''" :title="route.meta.title" />
    <!-- ADR-330 (10) replaces ADR-201 (2): ONE list. Two totals (never added), a filter All / Real / Paper, the real section (read
         from Zerodha first, ADR-016) and the one paper list, which loads by itself and is never held up by the Zerodha read. -->
    <div class="mt-4 grid gap-4">
    <PriceNotice :answer="marketAnswer" :affected="paperSummary?.affected || null" />
    <PositionsTotals :real="realTotals" :paper="paperSummary" />
    <div role="group" aria-label="Show real trades, paper trades or both" class="flex gap-2" data-testid="positions-filter">
      <button v-for="f in FILTERS" :key="f.key" type="button" class="rounded border border-line px-3 py-1 text-sm" :class="filter === f.key ? 'bg-accent-soft font-semibold text-accent' : ''" :aria-pressed="filter === f.key" :data-testid="`filter-${f.key}`" @click="filter = f.key">{{ f.label }}</button>
    </div>
    <div v-if="filter !== 'paper'" :data-state="realState" data-testid="real-state">
    <p v-if="loading" class="text-sm text-ink-muted" data-testid="positions-loading">Reading your positions from Zerodha.</p>
    <ListLoadFailed v-else-if="errorParts" :parts="errorParts" compact prefix="positions-error" @retry="loadReal" />
    <p v-else-if="brokerOff" class="text-sm text-ink-muted" data-testid="positions-not-connected">{{ brokerOffLine }}</p>
    <div v-else-if="result" class="grid gap-4 text-sm">
      <div class="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 rounded-lg border border-line bg-surface px-4 py-3">
        <p class="text-ink-muted">Read from Zerodha at <span class="num font-medium text-ink" data-testid="positions-read-at">{{ istTime(result.read_at) }}</span>.</p>
        <p v-if="result.has_outside" data-testid="positions-outside">
          <span data-testid="positions-outside-count">{{ outsideText(result.outside_lots) }}</span> -
          <a :href="KITE_POSITIONS_URL" target="_blank" rel="noopener noreferrer" class="link" data-testid="positions-outside-kite">{{ VIEW_ON_KITE }}</a>
        </p>
      </div>
      <div v-if="result.blocked" class="rounded-lg border border-line bg-surface px-4 py-3" data-testid="positions-blocked">
        <p class="font-medium text-warn">A strategy is {{ BLOCKED }}.</p>
        <ul class="mt-1">
          <li v-for="id in result.blocked_strategy_ids" :key="id" data-testid="positions-blocked-strategy" :data-strategy="id">
            <RouterLink v-if="orderPathOn" :to="`/strategy/${id}/execute`" class="link" data-testid="positions-blocked-link">Strategy {{ id }}</RouterLink><span v-else>Strategy {{ id }}</span> ({{ BLOCKED }})
          </li>
        </ul>
      </div>
      <!-- GC-UI D-C40 (Sensibull 050): the shared empty state; the title is new text (owner read), the line is ours as before. -->
      <div v-if="!result.strategies.length && !result.has_outside" data-testid="positions-empty">
        <EmptyState title="Real positions" message="No open Zerodha positions." />
      </div>
      <p v-else-if="!result.strategies.length" class="text-ink-muted" data-testid="positions-no-strategy">
        None of your strategies holds a position.
      </p>
      <section v-for="g in result.strategies" :key="g.strategy_id" class="overflow-hidden rounded-lg border border-line bg-surface" data-testid="position-group" :data-strategy="g.strategy_id">
        <h2 class="flex h-11 items-center gap-2 border-b border-line px-4 text-sm font-semibold">
          <span class="rounded bg-surface-muted px-1 text-xs font-semibold" data-testid="real-tag">{{ REAL_TAG }}</span>
          <RouterLink v-if="orderPathOn" :to="`/strategy/${g.strategy_id}/execute`" class="link" data-testid="position-strategy-link">Strategy {{ g.strategy_id }}</RouterLink><span v-else data-testid="position-strategy-name">Strategy {{ g.strategy_id }}</span>
          <span v-if="g.blocked" class="font-normal text-warn" data-testid="position-mismatch-badge">({{ BLOCKED }})</span>
          <!-- ADR-330 (54): the Plan button of a running real trade; the same plan sheet as the paper rows and the builder -->
          <PlanDoor v-if="g.contracts.length" :strategy-id="g.strategy_id" tag="real" class="ml-auto" />
        </h2>
        <!-- owner 28 Nov: an Exit or Stop stored for this real strategy is one line here; the P&L below stays Zerodha's figure and the units never change for it -->
        <p v-if="recordLineOf(g)" class="border-b border-line px-4 py-2 text-sm font-semibold" role="status" data-testid="position-record-line">{{ recordLineOf(g) }}</p>
        <p v-if="!g.contracts.length" class="px-4 py-3 text-ink-muted" data-testid="position-group-empty">{{ NO_ROW }}</p>
        <div v-else class="overflow-x-auto">
        <table class="ui-table">
          <thead>
            <tr><th>Contract</th><th class="ui-num">Your units</th><th class="ui-num">Zerodha units</th><th class="ui-num">P&amp;L</th><th>Status</th></tr>
          </thead>
          <tbody>
            <tr v-for="c in g.contracts" :key="c.tradingsymbol" data-testid="position-row" :data-symbol="c.tradingsymbol">
              <td class="font-medium">{{ c.tradingsymbol }}</td>
              <template v-if="c.pending">
                <td class="ui-num"><span data-testid="position-waiting">{{ WAITING }}</span> (plan <span data-testid="position-pending-plans">{{ c.pending_plans.join(', ') }}</span>)</td>
                <td class="ui-num"><span data-testid="position-zerodha">{{ c.zerodha_units }}</span></td>
                <td class="ui-num"><span data-testid="position-pnl">{{ c.pnl_state === 'stated' ? c.pnl_text : NO_FIGURE }}</span><span v-if="c.pnl_reason" class="block text-xs text-ink-muted" data-testid="position-pnl-reason">{{ c.pnl_reason }}</span></td>
                <td class="text-ink-muted"><span data-testid="position-unconfirmed">{{ UNCONFIRMED }}</span>. <span data-testid="position-pending-holders">{{ HOLDERS }}</span></td>
              </template>
              <template v-else>
                <td class="ui-num"><span data-testid="position-own-units">{{ c.units }}</span></td>
                <td class="ui-num"><span data-testid="position-zerodha">{{ c.zerodha_units }}</span></td>
                <td class="ui-num"><span data-testid="position-pnl">{{ c.pnl_state === 'stated' ? c.pnl_text : NO_FIGURE }}</span><span v-if="c.pnl_reason" class="block text-xs text-ink-muted" data-testid="position-pnl-reason">{{ c.pnl_reason }}</span></td>
                <td></td>
              </template>
            </tr>
          </tbody>
        </table>
        </div>
      </section>
    </div>
    </div>
    <PaperStrategies v-show="filter !== 'real'" headline-above :notice-up="noticeUp" data-testid="positions-paper" @summary="paperSummary = $event" />
    </div>
  </section>
</template>
