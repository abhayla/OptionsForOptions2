<!-- GC-BP step 6 (ADR-201 (2); REQ-109 AC-2, AC-3, AC-4), rebuilt by GC-TP step 4b (ADR-207; RD-121; Sensibull Positions 050-053
     and Draft Portfolios 090-092): the user's paper strategies from GET /paper/strategies (newest first) - a totals strip
     (Total P&L, Booked, Unbooked, Total Decay), a "Show closed positions" toggle (off), and per strategy a card with
     "N of M positions", Total / Booked / Unbooked and one row per contract (Lots, Avg, LTP, Booked, Unbooked, P&L) with
     Open in Builder, Add orders, Exit (n) and Stops. Shown in the Positions page's Paper tab and the builder's Tracked tab.
     The browser computes no money (ADR-008): every figure is the server's text. After a failed or unreadable refresh the list keeps its structure
     and open panels but every price-derived figure is paused (a dash) and no exit can be opened from the old prices (REQ-109 AC-5).
     Nothing here reaches Execute (REQ-109 AC-3): an exit is a paper order and sends nothing to Zerodha. -->
<template>
  <section class="rounded-lg border-2 border-dashed border-accent text-sm" :class="compact ? 'p-2' : 'p-3'" data-testid="paper-strategies">
    <p class="mb-2 rounded bg-accent-soft px-2 py-1 text-xs font-semibold text-accent" data-testid="paper-mode-header">Paper mode</p>
    <p class="rounded bg-amber-50 px-2 py-1 font-medium" data-testid="paper-banner">{{ BANNER }}</p>
    <p v-if="exitNote" class="mt-2 text-xs text-ink-muted" data-testid="paper-exit-link-note">{{ exitNote }}</p>
    <p v-if="loading" class="mt-2" data-testid="paper-loading">Reading your paper strategies.</p>
    <!-- D-05 r3: a failed refresh is a banner above the last loaded list, whose figures are paused (full-page error only when nothing ever loaded), so an open Stops panel and what was typed in it stay -->
    <ErrorMessage v-if="!loading && errorParts" class="mt-2" :parts="errorParts" compact prefix="paper-error" />
    <p v-if="!exitOnlyFor && !loading && items && !items.length" class="mt-2" data-testid="paper-empty">{{ EMPTY }}</p>
    <template v-else-if="!exitOnlyFor && !loading && items">
      <!-- Sensibull 050-053: the totals sit above the rows. A figure the reply omits is a dash with the server's reason. -->
      <dl v-if="totals && !compact" class="mt-2 flex flex-wrap gap-6 rounded bg-surface-muted px-3 py-2" data-testid="paper-totals">
        <div v-for="f in totalFigures.filter((x) => !(headlineAbove && x.id === 'total'))" :key="f.id" class="text-right">
          <dt class="text-xs text-ink-muted" :data-testid="`totals-${f.id}-label`">{{ shownFig(totals, f).label }}</dt>
          <dd class="text-lg font-semibold" :class="f.id === 'charges' ? '' : toneOf(shownFig(totals, f).text)" :data-testid="`totals-${f.id}`"><AfterChargesTap :breakdown="shownFig(totals, f).breakdown ?? null">{{ pnlText(shownFig(totals, f).text) }}</AfterChargesTap></dd>
          <p v-if="shownFig(totals, f).reason" class="text-xs text-ink-muted" :data-testid="f.reasonId">{{ shownFig(totals, f).reason }}</p>
        </div>
      </dl>
      <!-- D-68 (ADR-320 point 6): the Today total (trades opened or closed today, no scenario strategies): the server's figure, paused like the others -->
      <div v-if="today && !compact" class="mt-1 rounded bg-surface-muted px-3 py-2 text-right" data-testid="paper-today">
        <template v-if="today.count > 0 || stale">
          <p class="text-xs text-ink-muted" data-testid="totals-today-label">{{ shownFig(today, TODAY_FIGURE).label }}</p>
          <p class="text-lg font-semibold" :class="toneOf(shownFig(today, TODAY_FIGURE).text)" data-testid="totals-today"><AfterChargesTap :breakdown="shownFig(today, TODAY_FIGURE).breakdown ?? null">{{ pnlText(shownFig(today, TODAY_FIGURE).text) }}</AfterChargesTap></p>
          <p v-if="shownFig(today, TODAY_FIGURE).reason" class="text-xs text-ink-muted" data-testid="totals-today-reason">{{ shownFig(today, TODAY_FIGURE).reason }}</p>
        </template>
        <template v-else>
          <p class="text-xs text-ink-muted" data-testid="totals-today-label">{{ TODAY_FIGURE.label }}</p>
          <p class="text-sm" data-testid="totals-today-empty">{{ today.emptyText }}</p>
        </template>
      </div>
      <!-- ADR-330 (15): the server's line under the Paper total ("Includes N closed strategies"), printed as sent, only when served -->
      <p v-if="totals && !compact && !headlineAbove && totals.closedNote" class="mt-1 text-xs text-ink-muted" data-testid="totals-closed-note">{{ totals.closedNote }}</p>
      <p v-if="totals && !compact && totals.leftOut" class="mt-1 text-xs text-ink-muted" data-testid="totals-left-out">{{ totals.leftOut }}</p>
      <label class="mt-2 flex items-center gap-2"><input v-model="showClosed" type="checkbox" data-testid="show-closed" /> {{ SHOW_CLOSED_LABEL }}</label>
      <p v-if="!shown.length" class="mt-2" data-testid="paper-all-closed">{{ ALL_CLOSED_TEXT }}</p>
      <!-- GC-UI 6b D-C14 (ADR-201 (2); S-118): the builder's Paper tab is a compact list - name, positions count, the server's paper total
           (a dash and the reason when there is none), a link to Positions > Paper for that strategy. The full cards stay on Positions. -->
      <ul v-if="compact" class="mt-2" data-testid="paper-compact">
        <li v-for="g in shown" :key="g.id" class="border-b border-line py-2" data-testid="paper-compact-row" :data-strategy="g.id">
          <p v-if="!g.readable" data-testid="paper-unreadable">{{ g.text }}</p>
          <RouterLink v-else :to="{ path: '/positions/current-positions', query: { tab: 'paper', strategy: String(g.id) } }" class="flex items-center gap-2" :data-testid="`paper-compact-link-${g.id}`">
            <span class="flex-1" :class="NAME_FLOOR_CLASS">
              <span class="block truncate font-medium" :title="groupLabel(g)" data-testid="paper-group-name">{{ groupLabel(g) }}</span>
              <span class="block text-xs text-ink-muted" data-testid="paper-compact-legs">{{ legsText(g) }}</span>
            </span>
            <span class="shrink-0 text-right">
              <span class="block font-semibold" :class="toneOf(g.totalAfter.text)" data-testid="paper-total">{{ stale ? '-' : g.totalAfter.text ?? '-' }}</span>
              <span v-if="!stale && g.totalAfter.label" class="block text-xs text-ink-muted" data-testid="paper-total-label">{{ g.totalAfter.label }}</span>
              <span v-if="!stale && g.totalAfter.reason" class="block text-xs text-ink-muted" data-testid="paper-total-reason">{{ g.totalAfter.reason }}</span>
              <span v-if="stale || g.totalAfter.text === null" class="block text-xs text-ink-muted" data-testid="paper-compact-reason">{{ stale ? PAPER_PAUSED : g.stateText || NO_TOTAL }}</span>
            </span>
          </RouterLink>
        </li>
      </ul>
      <template v-else>
        <div v-for="g in shown" :key="g.id" :ref="(el) => (cards[g.id] = el)" class="mt-3 rounded-lg border border-line p-3" data-testid="paper-group" :data-strategy="g.id">
          <p v-if="!g.readable" data-testid="paper-unreadable">{{ g.text }}</p>
          <template v-else>
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div>
                <!-- ADR-330 (10): every paper group in the one Positions list is tagged PAPER -->
                <span class="mr-1 rounded bg-accent-soft px-1 text-xs font-semibold text-accent" data-testid="paper-tag">PAPER</span>
                <h2 class="font-semibold" data-testid="paper-group-name">{{ groupLabel(g) }}</h2>
                <span class="text-ink-muted" data-testid="paper-group-underlying">{{ g.underlying }}</span>
                <span v-if="g.statusWord" class="text-xs text-ink-muted" data-testid="paper-status-word">{{ g.statusWord }}</span>
                <p class="text-xs text-ink-muted" data-testid="paper-count">{{ g.openCount }} of {{ g.positionCount }} positions</p>
                <HeldNote :held="g.held" />
              </div>
              <dl class="flex flex-wrap gap-6" data-testid="paper-figures">
                <div v-for="f in figures" :key="f.field" class="text-right">
                  <dt class="text-xs text-ink-muted" :data-testid="f.field === 'total' ? 'paper-total-label' : 'paper-figure-label'">{{ shownFig(g, f).label }}</dt>
                  <dd class="text-lg font-semibold" :class="f.field === 'charges' ? '' : toneOf(shownFig(g, f).text)" :data-testid="f.testid"><AfterChargesTap :breakdown="shownFig(g, f).breakdown ?? null">{{ pnlText(shownFig(g, f).text) }}</AfterChargesTap></dd>
                  <p v-if="shownFig(g, f).reason" class="text-xs text-ink-muted" :data-testid="f.reasonId">{{ shownFig(g, f).reason }}</p>
                </div>
              </dl>
            </div>
            <!-- GC-TP R-19b (Sensibull 090): Breakeven, Max Profit and Max Loss on the card, and a Greeks toggle (off) with per-leg and
                 net Greeks. All server texts; a figure the reply lacks is a dash with its reason, never 0. -->
            <dl class="mt-2 flex flex-wrap items-start gap-6" data-testid="paper-summary">
              <div v-for="f in summaryFigures.filter((x) => !x.only || x.only(g))" :key="f.id" class="min-w-0">
                <dt class="text-xs text-ink-muted">{{ typeof f.label === 'function' ? f.label(g) : f.label }}</dt>
                <dd class="font-semibold" :data-testid="`paper-${f.id}`">{{ pnlText(f.value(g)) }}</dd>
                <p v-if="f.value(g) === null && f.reason(g)" class="text-xs text-ink-muted" :data-testid="`paper-${f.id}-reason`">{{ f.reason(g) }}</p>
                <p v-if="f.id === 'max-profit' && g.extremesBasis && g.maxProfit !== null && g.state === 'PAUSED'" class="max-w-xs text-xs text-ink-muted" data-testid="paper-max-profit-basis">{{ g.extremesBasis }}</p>
              </div>
              <button type="button" class="rounded border border-line px-2 py-1" :aria-pressed="!!greeksOpen[g.id]" :data-testid="`greeks-toggle-${g.id}`" @click="greeksOpen = { ...greeksOpen, [g.id]: !greeksOpen[g.id] }">Greeks</button>
            </dl>
            <div v-if="greeksOpen[g.id]" class="mt-2" :data-testid="`paper-greeks-${g.id}`">
              <p v-if="stale || !g.greeks" class="text-xs text-ink-muted" data-testid="paper-greeks-reason">{{ PAPER_NO_FIGURE }} {{ stale ? PAPER_PAUSED : g.greeksReason }}</p>
              <table v-else class="w-full text-left">
                <thead><tr><th>Instrument</th><th v-for="c in GREEK_COLUMNS" :key="c.key">{{ c.key === 'theta' && g.decayLeftToday ? DECAY_LEFT_TODAY_HEADING : c.label }}</th></tr></thead>
                <tbody>
                  <tr v-for="l in g.greeks.legs" :key="l.contractId" data-testid="paper-greeks-leg">
                    <td>{{ legName(g, l.contractId) }}</td>
                    <td v-for="c in GREEK_COLUMNS" :key="c.key" :data-testid="`paper-greeks-leg-${c.key}`">{{ l[c.key] }}</td>
                  </tr>
                  <tr class="font-semibold" data-testid="paper-greeks-net">
                    <td>Net</td>
                    <td v-for="c in GREEK_COLUMNS" :key="c.key" :data-testid="`paper-greeks-net-${c.key}`">{{ g.greeks.net[c.key] }}</td>
                  </tr>
                </tbody>
              </table>
              <p v-if="g.greeks && g.greeks.basis" class="mt-1 text-xs text-ink-muted" data-testid="paper-greeks-basis">{{ g.greeks.basis }}</p>
            </div>
            <p v-if="g.closedText" class="mt-1 font-semibold" data-testid="paper-closed-result">{{ g.closedText }}</p>
            <p v-if="g.stateText" class="mt-1" data-testid="paper-state">{{ g.stateText }}</p>
            <!-- ADR-311: the open legs with no price, named by the server; the totals above stay paused -->
            <p v-if="g.afterCloseText" class="mt-1 text-xs text-ink-muted" data-testid="paper-after-close">{{ g.afterCloseText }}</p>
            <p v-if="g.unpricedText" class="mt-1 text-xs text-ink-muted" data-testid="paper-unpriced">{{ g.unpricedText }}</p>
            <div class="mt-2 flex gap-3">
              <table v-if="g.positions.length || g.closed.length" class="w-full min-w-0 flex-1 text-left">
                <thead>
                  <tr><th class="w-6"><span class="sr-only">Select</span></th><th>Instrument</th><th>Lots</th><th>Avg / entry</th><th>LTP / exit</th><th>Booked</th><th>Unbooked</th><th>P&amp;L</th></tr>
                </thead>
                <tbody>
                  <tr v-for="p in g.positions.filter((x) => x.open)" :key="p.key" data-testid="paper-leg" :data-leg="p.contractId">
                    <td>
                      <input v-if="canExit(p)" type="checkbox" :checked="isTicked(g.id, p.contractId)" :data-testid="`select-leg-${g.id}-${p.contractId}`" :aria-label="`Select ${p.name}`" @change="tick(g.id, p.contractId, $event.target.checked)" />
                    </td>
                    <td data-testid="paper-instrument"><span v-if="p.side" class="mr-1 rounded bg-surface-muted px-1 font-semibold">{{ p.side }}</span> <span>{{ p.name }}</span></td>
                    <td data-testid="paper-qty">{{ p.qtyText }}<span v-if="p.qtyNote" class="block text-xs text-ink-muted" data-testid="paper-qty-note">{{ p.qtyNote }}</span></td>
                    <td data-testid="paper-avg">{{ pnlText(p.averageText) }}</td>
                    <td data-testid="paper-ltp">{{ pnlText(p.ltpText) }}<span v-if="p.ltpText !== null" class="block text-xs text-ink-muted" data-testid="paper-ltp-at">{{ istClock(p.priceAt) ?? QUOTE_TIME_UNAVAILABLE_TEXT }}</span><span v-if="!stale && p.ltpReason && p.ltpText === null" class="block text-xs text-ink-muted" data-testid="paper-ltp-reason">{{ p.ltpReason }}</span></td>
                    <td data-testid="paper-leg-booked">{{ pnlText(p.booked) }}</td>
                    <td data-testid="paper-leg-unbooked" :class="toneOf(p.unbooked)">{{ stale ? pnlText(null) : p.noPrice ?? pnlText(p.unbooked) }}</td>
                    <td data-testid="paper-leg-pnl" :class="toneOf(p.total)">{{ pnlText(p.total) }}</td>
                  </tr>
                  <!-- D-10 (ADR-207 (2)): each closed lifecycle: its entry and exit price and its own booked; no Lots 0 row -->
                  <tr v-for="c in g.closed" :key="c.key" class="text-ink-muted" data-testid="paper-closed-leg" :data-leg="c.contractId">
                    <td></td>
                    <td data-testid="paper-closed-instrument"><span class="mr-1 rounded bg-surface-muted px-1 font-semibold">{{ c.side }}</span> <span>{{ c.name }}</span> <span>(closed)</span></td>
                    <td data-testid="paper-closed-qty">{{ c.qtyText }}</td>
                    <td data-testid="paper-closed-entry">{{ pnlText(c.entryText) }}</td>
                    <td data-testid="paper-closed-exit">{{ pnlText(c.exitText) }}<span v-if="c.reasonText" class="block text-[11px] text-ink-muted" data-testid="paper-closed-reason">{{ c.reasonText }}</span></td>
                    <td data-testid="paper-closed-booked">{{ pnlText(c.booked) }}</td>
                    <td></td><td></td>
                  </tr>
                </tbody>
              </table>
              <!-- D-C50 / Sensibull 090-092: the action column. No Convert To Real Trades (ADR-165). Add orders opens the builder on
                   the strategy, where its paper position is Drafts Mode (GC-TP step 3c). -->
              <div class="flex w-36 shrink-0 flex-col gap-2" data-testid="paper-actions">
                <HeldNote :held="g.held" note-only />
                <RouterLink :to="builderLink(g)" class="rounded border border-line px-2 py-1 text-center text-accent" data-testid="paper-open-builder">Open in Builder</RouterLink>
                <RouterLink v-if="g.statusWord !== 'Completed'" :to="builderLink(g)" class="rounded border border-line px-2 py-1 text-center text-accent" data-testid="paper-add-orders">Add orders</RouterLink>
                <button v-if="g.openCount" type="button" class="rounded border border-line px-2 py-1" :aria-expanded="!!stopsOpen[g.id]" :data-testid="`stops-open-${g.id}`" @click="stopsOpen = { ...stopsOpen, [g.id]: !stopsOpen[g.id] }">Stops</button>
                <ExitButton v-if="g.openCount" :blocked="exitGate.blocked.value" :reason="exitGate.reason.value ?? (tickedOpen(g).length ? null : EXIT_TICK_TEXT)" :extra-disabled="!tickedOpen(g).length" class="rounded border border-line px-2 py-1" :data-testid="`exit-selected-${g.id}`" @click="ask(g, tickedOpen(g))">Exit ({{ tickedOpen(g).length }})</ExitButton>
              </div>
            </div>
            <!-- P10 (ADR-330 (13)): the Plan watch of an open strategy; it re-reads on this list's own good-read token -->
            <PlanWatch v-if="g.openCount" :strategy-id="g.id" :read-tick="goodReadToken" :stale="stale" compact class="mt-2" />
            <PaperStops v-if="stopsOpen[g.id]" :strategy-id="g.id" :underlying="g.underlying" :legs="stopLegs(g)" :leg-names="legNamesOf(g)" :good-read-token="goodReadToken" @changed="onStopsChanged" />
          </template>
        </div>
      </template>
    </template>
    <!-- GC-TP step 4b round 2 (REQ-109 AC-4; Sensibull 166-173): every exit goes through the shared confirm list, in lots -->
    <PaperConfirmDialog :open="!!confirm" :orders="confirm ? confirm.orders : []" :strategy-id="confirm ? confirm.id : ''" :busy="busy" :blocked="stale" :error="dialogError || (confirm && stale ? exitEndText('not_live', confirm.names) : '')" :state="dialogState" :locked="!!(confirm && unresolved[confirm.id])" @confirm="doExit" @cancel="cancelExit" @orderbook="openOrderbook" />
  </section>
</template>

<script setup>
import { NAME_FLOOR_CLASS } from '@/lib/nameFloor'
import { strategyListLabel } from '@/lib/saveDraft'
import { istClock } from '@/lib/displayFormat'
import { QUOTE_TIME_UNAVAILABLE_TEXT } from '@/lib/sharedStateText'
import { computed, onMounted, reactive, ref, shallowRef, watch } from 'vue'
import api, { NEUTRAL_ERROR, NEUTRAL_PARTS } from '@/services/api'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import PaperStops from '@/components/strategy/PaperStops.vue'
import PlanWatch from '@/components/strategy/PlanWatch.vue'
import AfterChargesTap from '@/components/common/AfterChargesTap.vue'
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'
import HeldNote from '@/components/strategy/HeldNote.vue'
import { ALL_CLOSED_TEXT, DECAY_LEFT_TODAY_HEADING, GREEK_COLUMNS, PAPER_NO_FIGURE, PAPER_PAUSED, SHOW_CLOSED_LABEL, exitRowsFor, isOpenGroup, readPaperList, visibleGroups } from '@/lib/paperList'
import { usePriceFreshness } from '@/lib/priceState'
import { EXIT_TICK_TEXT, exitEndText, usePaperExit } from '@/lib/usePaperExit'
import ExitButton from '@/components/strategy/ExitButton.vue'
import { usePaperRefresh } from '@/lib/usePaperRefresh'
import { EXITED_NOW_LABEL, HELD_TO_EXPIRY_LABEL } from '@/lib/paperDrafts'
import { PAPER_STATE, addToPaper, paperPostOutcome } from '@/lib/tracking'
import { useRouter } from 'vue-router'
import { signOf } from '@/lib/chartCard'

// ADR-330 (10): headlineAbove = the Positions page shows the Paper total in its own header, so this list omits its Total P&L figure
// (and the closed-strategies line that goes with it); it emits `summary` so that header prints the server's figure, never a sum.
// W2-B (ADR-330 (3), (12)): `exitOnlyFor` = a strategy id: the Alerts page mounts this same door for ONE exit, drawing only the
// banner, the door's note and the shared confirm list (no list, no totals). The id is one-shot, acted on by the first good read
// by the same rule as the `exit=` link (open legs, gate not blocked); `exit-closed` is emitted when its dialog ends (confirmed or cancelled).
const props = defineProps({ compact: { type: Boolean, default: false }, headlineAbove: { type: Boolean, default: false }, exitOnlyFor: { type: String, default: null } })
const emit = defineEmits(['summary', 'exit-closed'])
let exitForPending = props.exitOnlyFor
// GC-TRACK1 k27: the OPEN leg count; an unreadable open_count shows nothing (never the total). "open" only when closed ones exist.
const legsText = (g) => {
  const n = g.openCount
  if (!Number.isInteger(n) || n < 0) return ''
  const word = n === 1 ? 'leg' : 'legs'
  return n === g.positionCount ? `${n} ${word}` : `${n} open ${word}`
}
const NO_TOTAL = 'No paper total yet: prices are not live'
const BANNER = 'Paper trades - not real money'
const EMPTY = 'No paper strategies yet. Build a strategy, then press Add to Paper.'
const figures = [
  { field: 'total', label: 'Total P&L', testid: 'paper-total', reason: 'pauseReason', reasonId: 'paper-total-reason' },
  { field: 'unbooked', label: 'Unbooked P&L', testid: 'paper-unbooked', reason: 'pauseReason', reasonId: 'paper-unbooked-reason' },
  { field: 'booked', label: 'Booked P&L', testid: 'paper-booked', reasonId: 'paper-booked-reason' },
  { field: 'charges', label: 'Charges paid', testid: 'paper-charges', reason: 'chargesReason', reasonId: 'paper-charges-reason' }, // beside, never subtracted
]
// GC-TP R-19b: the card's summary line; each reads one server text and says why when it is absent
const summaryFigures = [
  { id: 'breakeven', label: 'Breakeven', value: (g) => (g.breakevens ? g.breakevens.join(', ') : null), reason: (g) => g.breakevensReason },
  // D-14 (ADR-320 (2)): on the expiry day of the trade the server sends the held figure too; both are labelled, else unchanged
  { id: 'max-profit-hold', label: 'Max Profit ' + HELD_TO_EXPIRY_LABEL.toLowerCase(), value: (g) => g.maxProfitHold, reason: () => null, only: (g) => g.maxProfitHold !== null },
  { id: 'max-profit', label: (g) => (g.maxProfitHold !== null ? 'Max Profit ' + EXITED_NOW_LABEL.toLowerCase() : 'Max Profit'), value: (g) => g.maxProfit, reason: (g) => g.maxProfitReason },
  { id: 'max-loss', label: 'Max Loss', value: (g) => g.maxLoss, reason: (g) => g.maxLossReason },
]
const greeksOpen = ref({})
// ADR-330 (19) (g.name is already unquoted and the label maker unquotes once, so it is wrapped again): name, then (#id, expiry): one distinct expiry among the group's positions prints it, several or none print only the number
const groupLabel = (g) => strategyListLabel({ name: typeof g.name === 'string' ? `"${g.name}"` : null, id: g.id, expiries: g.expiries ?? [], fallback: `Strategy ${g.id}` })
const legName = (g, contractId) => g.positions.find((p) => p.contractId === contractId)?.name ?? String(contractId)
const totalFigures = [
  { id: 'total', field: 'total', reason: 'totalReason', reasonId: 'totals-reason', label: 'Total P&L' },
  { id: 'booked', field: 'booked', reason: 'totalReason', reasonId: 'totals-booked-reason', label: 'Booked P&L' },
  { id: 'unbooked', field: 'unbooked', reason: 'totalReason', reasonId: 'totals-unbooked-reason', label: 'Unbooked P&L' },
  { id: 'decay', field: 'decay', reason: 'decayReason', reasonId: 'totals-decay-reason', label: 'Total Decay' },
  { id: 'charges', field: 'charges', reason: 'chargesReason', reasonId: 'totals-charges-reason', label: 'Charges paid' }, // D-14: says which charges
]
// the server's text, printed as sent (a missing figure is a dash); the colour follows the server's sign, read from its text
// GC-ICFIX u123 (ADR-263): the Total P&L figure is the reply's after-charges text with "(after charges)", or the before text with
// "(before charges)" and the reason (lib/tracking afterFigure); every other figure is its own text and reason, unchanged
const TODAY_FIGURE = { id: 'today', field: 'total', label: 'Today' } // D-68
const AFTER_OF = { total: 'totalAfter', booked: 'bookedAfter', unbooked: 'unbookedAfter' } // u124: Booked / Unbooked follow the same rule
const shownFig = (src, f) => {
  if (stale.value) return { label: f.label, text: null, reason: PAPER_PAUSED, breakdown: null }
  if (AFTER_OF[f.field]) {
    const a = src[AFTER_OF[f.field]]
    return { label: `${f.label} ${a.label}`.trim(), text: a.text, reason: a.reason, breakdown: a.breakdown }
  }
  return { label: f.label, text: src[f.field], reason: f.reason && src[f.field] === null ? src[f.reason] : null }
}
const pnlText = (v) => (v === null || v === undefined || stale.value ? PAPER_NO_FIGURE : v)
const toneOf = (v) => stale.value ? '' : ({ profit: 'text-profit', loss: 'text-loss' })[signOf(String(v ?? '').replace(/,/g, '').replace('−', '-'))] ?? ''
const builderLink = (g) => ({ path: '/strategy/builder', query: { strategy: String(g.id) } })

const items = ref(null)
const totals = ref(null)
const today = ref(null)
const showClosed = ref(false)
const shown = computed(() => visibleGroups(items.value ?? [], showClosed.value))
const errorParts = ref(null)
// D-05 r3: a failed or unreadable refresh with a list on screen: figures paused, no exit from old prices
const { readOk } = usePriceFreshness({ readFailed: errorParts, held: items })
const stale = computed(() => !readOk.value)
// Phase 4 (F2): the Exit gate of the page, the same one as the builder's book panel (no contracts-changed mark on this list)
const exitGate = usePaperExit({ readFailed: errorParts, held: items, busy: () => busy.value, changed: false })
const loading = ref(true)
const summary = computed(() => ({
  totalAfter: totals.value ? totals.value.totalAfter : null,
  closedNote: totals.value ? totals.value.closedNote : null,
  stale: stale.value || (!loading.value && !!errorParts.value), // a failed FIRST read (no list held) is paused too, with the same reason as the list (ADR-330 (10))
  loaded: !loading.value && items.value !== null,
}))
watch(summary, (v) => emit('summary', v), { immediate: true, flush: 'sync' })
// goodReadToken: the token of the last good read; an open Stops panel reads its own list again when it changes (S-23)
const goodReadToken = shallowRef(null)
const stopsOpen = ref({})
// R-10: a Stop row for each OPEN contract, keyed by the contract id the reply carries (a digit string sent as is)
const legNamesOf = (g) => Object.fromEntries(g.positions.map((p) => [p.contractId, p.name])) // D-44: the one leg label, for the form and the list
const stopLegs = (g) => g.positions.filter((p) => p.open).map((p) => ({ index: p.contractId, label: legNamesOf(g)[p.contractId], contractId: String(p.contractId) }))

const ticks = ref({})
const isTicked = (id, c) => !!ticks.value[id]?.includes(c)
function tick(id, c, on) {
  const rest = (ticks.value[id] ?? []).filter((x) => x !== c)
  ticks.value = { ...ticks.value, [id]: on ? [...rest, c] : rest }
}
const canExit = (p) => p.open && p.lots !== null // a quantity that is not whole lots cannot be exited in lots
const tickedOpen = (g) => g.positions.filter((p) => canExit(p) && isTicked(g.id, p.contractId))

const confirm = ref(null)
// Lane U r1 (ADR-016/017/019): the ONE rule of an unknown outcome. `unresolved[strategyId]` = { names, units, seq } is set when a POST
// ends unknown (503 / no answer / 408 / 429 / superseded). While it stands: Confirm of that strategy is off (never on a timer), a re-opened
// Exit shows the unknown sentence, and only a good re-read that STARTED after the reply decides it (stored -> done note; legs unchanged
// -> "not stored", Confirm may be on; anything else -> the usual changed-elsewhere end). `readSeq` counts reads as they start.
const unresolved = reactive({})
let readSeq = 0
const busy = ref(false)
const dialogError = ref('') // the server's refusal text, shown inside the confirm list
const dialogState = ref(PAPER_STATE.READY) // fix/paper-dialog-safe: the dialog's answer state (tracking.js PAPER_STATE)
const router = useRouter()

function show({ data, token }) {
  const hadExit = !props.compact && router?.currentRoute.value.query.exit !== undefined
  const exitId = takeExitParam() ?? takeExitFor()
  const read = readPaperList(data)
  if (read === null) {
    errorParts.value = NEUTRAL_PARTS // the open dialog stays, blocked with the not-live line (hotfix 27 Nov) // an unreadable answer keeps the last loaded list, like a failed read
  } else {
    items.value = read.groups
    totals.value = read.totals
    today.value = read.today
    errorParts.value = null
    if (dialogState.value === PAPER_STATE.REFUSED) dialogState.value = PAPER_STATE.READY // a good read unlocks a refused, unchanged Confirm; the server's text stays
    goodReadToken.value = token // the token travels with the answer from the read that made it
    settle(items.value, token?.seq ?? 0)
    openExitFromLink(exitId)
    if (!hadExit && !props.exitOnlyFor) openStopsFromLink()
  }
  loading.value = false
}
// S-14 (ADR-330 (10)): the Live card's Exit links here with `exit=<strategy id>` (Positions list only, never the compact one).
// The parameter is ONE-SHOT: consumed (dropped from the route) on the first answer of any kind, acted on only if that answer is good,
// so a later timer read or a back-navigation never opens the dialog without a new click. It acts only when `strategy` is absent or
// equal, and only on a group the list itself draws as open (isOpenGroup, the list's own rule). It never throws into show().
const EXIT_NOTE = 'This strategy has no open paper legs to exit.'
const exitNote = ref('')
function takeExitFor() { const id = exitForPending; exitForPending = null; return id === null ? null : String(id) }
function takeExitParam() {
  if (props.compact || !router) return null
  const q = router.currentRoute.value.query
  if (q.exit === undefined) return null
  const { exit, ...rest } = q
  try { router.replace({ query: rest }) } catch { /* the route stays as it is; the parameter was read once */ }
  const id = String(Array.isArray(exit) ? exit[0] : exit)
  const strategy = q.strategy === undefined ? undefined : String(Array.isArray(q.strategy) ? q.strategy[0] : q.strategy)
  return strategy !== undefined && strategy !== id ? null : id
}
// ADR-330 (21): the Live card's "Stops" link (`strategy=<id>`, no `exit`) opens that trade's Stops panel and scrolls to its card, once
// (the first good answer); an id the list does not show opens nothing and says nothing; the list is never filtered.
let stopsLinkDone = false
function openStopsFromLink() {
  if (stopsLinkDone || props.compact || !router) return
  stopsLinkDone = true
  const q = router.currentRoute.value.query.strategy
  const id = q === undefined ? null : String(Array.isArray(q) ? q[0] : q)
  const g = id === null ? null : (items.value ?? []).find((x) => x.readable && x.openCount && String(x.id) === id) // Stops is drawn only for open legs
  if (!g) return
  stopsOpen.value = { ...stopsOpen.value, [g.id]: true }
  scrollTo.value = g.id
}
const cards = {} // the drawn card element of each group, by strategy id (a function ref)
const scrollTo = ref(null) // the strategy id whose card is scrolled to once it is drawn
watch(scrollTo, (id) => { if (id !== null) { cards[id]?.scrollIntoView?.({ block: 'start' }); scrollTo.value = null } }, { flush: 'post' })
function openExitFromLink(id) {
  if (id === null) return // no new request: an earlier note stays until the user leaves
  exitNote.value = ''
  if (confirm.value || busy.value) return
  try {
    const g = (items.value ?? []).find((x) => isOpenGroup(x) && String(x.id) === id)
    const rows = g ? g.positions.filter(canExit) : []
    if (!rows.length) exitNote.value = EXIT_NOTE
    else if (exitGate.blocked.value) exitNote.value = exitGate.reason.value ?? EXIT_NOTE
    else ask(g, rows)
  } catch {
    exitNote.value = EXIT_NOTE
  }
}
// D-05 r2: a failed read keeps the last loaded list (and any open Stops panel) under an error banner marked as last loaded
function fail(e) {
  takeExitFor()
  takeExitParam() // one-shot: a failed first read consumes the parameter and opens nothing
  errorParts.value = e?.parts ?? NEUTRAL_PARTS
  loading.value = false
}

const { refresh, refreshNow } = usePaperRefresh({
  key: () => 'list',
  read: async () => { const token = { seq: ++readSeq }; return { data: (await api.get('/paper/strategies')).data, token } },
  onData: show,
  onError: fail,
})
onMounted(refresh)
// N-21: a Save / Cancel / fired stop in the Stops panel: read the list now, not at the next tick (no new timer)
function onStopsChanged() { try { refreshNow() } catch { /* the list says its own read failed */ } }

// a read that changes the open contracts of the group being exited ends the exit's open question
function settle(now, seq = 0) {
  decideUnresolved(now, seq)
  const c = confirm.value
  if (c) {
    if (busy.value || unresolved[c.id]) return // a difference is the pending exit's own doing: wait for the reply, then decide (Lane U r1)
    const g = now.find((x) => x.id === c.id)
    const stillOpen = g && g.readable && c.units.every((u) => g.positions.some((p) => p.contractId === u.id && p.units === u.units))
    if (!stillOpen) endExit('changed', c.names)
  }
}
// a good read that started after the unknown reply decides it: stored (every exited leg reduced), unchanged, or something else
function decideUnresolved(now, seq) {
  for (const id of Object.keys(unresolved)) {
    const u = unresolved[id]
    if (seq <= u.seq) continue // started before the reply: it may predate the exit
    const g = now.find((x) => String(x.id) === id)
    if (!g || !g.readable) { delete unresolved[id]; continue } // the usual changed-elsewhere end follows
    const at = (cid) => g.positions.find((p) => p.contractId === cid)?.units ?? 0
    const unchanged = u.units.every((x) => at(x.id) === x.units)
    const stored = u.units.every((x) => at(x.id) !== x.units && (x.units > 0 ? at(x.id) >= 0 && at(x.id) < x.units : at(x.id) <= 0 && at(x.id) > x.units)) // units only, never money: held count moved toward zero, same side
    delete unresolved[id]
    if (unchanged) {
      const text = exitEndText('not_stored', u.names, null, NEUTRAL_ERROR)
      if (confirm.value && String(confirm.value.id) === id) { dialogState.value = PAPER_STATE.READY; dialogError.value = text } else exitNote.value = text
    } else if (stored) {
      if (confirm.value && String(confirm.value.id) === id) { ticks.value = { ...ticks.value, [id]: [] }; cancelExit() }
      exitNote.value = exitEndText('done', u.names, {}, NEUTRAL_ERROR)
    }
  }
}
watch(confirm, (now, was) => { if (was && !now && props.exitOnlyFor) emit('exit-closed') })
// Hotfix 27 Nov (ADR-016..019, ADR-328 (4), owner T1-02): endExit is the ONE door of an Exit that ends without an order or with a
// refusal; it always leaves a sentence naming the leg(s). 'changed': the legs really changed (or the group cannot be read): the dialog
// closes, the ticks go (N-04, ADR-330 (17): nothing staged outlives it, and it never comes back by itself) and the note says why.
// 'not_live': a failed read does NOT close an open dialog: it stays, Confirm is blocked, the line is in the dialog (computed from `stale`).
// 'refused': the server's four parts in the dialog. 'busy': a note. With no dialog open every reason is the note.
function endExit(reason, legNames, parts = null) {
  const text = exitEndText(reason, legNames, parts, NEUTRAL_ERROR)
  if (reason === 'changed') { closeByPage(); exitNote.value = text; return }
  if (confirm.value && reason === 'refused') { dialogError.value = text; return }
  if (confirm.value && reason === 'not_live') return // shown in the dialog while stale
  exitNote.value = text
}
function closeByPage() {
  const c = confirm.value
  if (c) ticks.value = { ...ticks.value, [c.id]: [] }
  cancelExit()
}
function cancelExit() {
  confirm.value = null
  dialogError.value = ''
  dialogState.value = PAPER_STATE.READY
}

function ask(g, rows) {
  const orders = exitRowsFor(rows)
  const names = rows.map((p) => p.name)
  if (busy.value) return endExit('busy', names)
  if (stale.value) return endExit('not_live', names)
  if (orders === null || !orders.length) return endExit('changed', names)
  exitNote.value = ''
  dialogError.value = ''
  dialogState.value = unresolved[g.id] ? PAPER_STATE.UNKNOWN : PAPER_STATE.READY // an unresolved unknown outcome shows its sentence again, Confirm off
  confirm.value = { id: g.id, orders, names, units: rows.map((p) => ({ id: p.contractId, units: p.units })) }
}

// the dialog posts the rows as edited (lots x lot size, the typed price); a refusal stays in the dialog with the server's text
async function doExit(orders) {
  const c = confirm.value
  if (!c) return endExit('changed', [])
  if (busy.value) return endExit('busy', c.names)
  if (stale.value) return endExit('not_live', c.names) // prices paused: no POST; the dialog says which leg and why
  busy.value = true
  dialogError.value = ''
  dialogState.value = PAPER_STATE.READY
  let reply = null
  try {
    reply = await addToPaper(api, c.id, orders) // no suggestion ids: the body is exactly { orders }
  } catch (e) {
    const outcome = paperPostOutcome(e)
    dialogState.value = outcome
    if (outcome === PAPER_STATE.UNKNOWN) { unresolved[c.id] = { names: c.names, units: c.units, seq: readSeq } }
    if (outcome === PAPER_STATE.REFUSED) endExit('refused', c.names, e?.parts) // 400/409/422: nothing stored; all four parts + the legs
    busy.value = false
    return
  }
  // STORED (201): the dialog closes and is never re-offered for these rows; a failed list refresh is the list's own message
  confirm.value = null
  ticks.value = { ...ticks.value, [c.id]: [] }
  busy.value = false
  endExit('done', c.names, { orders: reply?.orders, sent: orders.length }) // the done line stays whatever the re-read does (hotfix 27 Nov, T1-02)
  try { refreshNow() } catch { /* the list says its own read failed */ }
}
// the unknown-outcome link: the strategy's builder shows its book (Orderbook) read from the server
function openOrderbook() {
  const c = confirm.value
  cancelExit()
  if (c && router) router.push({ path: '/strategy/builder', query: { strategy: String(c.id) } })
}
</script>
