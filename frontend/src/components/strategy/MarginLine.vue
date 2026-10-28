<script setup>
// ADR-099: the margin for the planned orders, in the outcome screen's margin slot. Display only: the figures are in the
// server's own text (REQ-055 AC-3: Zerodha's figure and ours are named apart there, never relabelled in the browser)
// and the shortfall flag is the server's Decimal comparison; the browser never reads, parses or
// compares money (ADR-008). Without figures (no Kite login, Zerodha could not be read, a leg not listed) the answer's
// catalogue text is shown as it is. The Checked-at time uses the one ADR-088 formatter.
// REQ-117 (W-132): the line asks the flag `basket_margin_quote`. `capabilities` is the server's flag body: null while
// it is being read (nothing is drawn), then the line only when the flag is on; otherwise the plain reason, no figures.
// W-193 (ADR-193 UI-118, UI-119; walkthrough I-8): Block 3 "Funds & Margins" of the summary card. Margin needed and
// Margin available are the server's `needed` / `available` strings as sent, each with ONE labelled "?" (the three bare
// marks are gone). The server's sentence naming Zerodha's figure and ours apart stays visible under them. On a shortfall
// the block gets a 4 px loss-coloured left border and one line; the server's four-part message is drawn ONCE, as a second
// root that the summary card's grid places under all three blocks (so it is never repeated beside the figures).
// "Funds needed" is absent: the reply has no such figure yet (REQ-081; D-A38 parked, finding F-62).
// GC-UI step 3b (ADR-202 (1), (4), ADR-204): the two figures are the server's REQ-152 display strings (`needed_display`,
// `available_display`, '-' when absent), the exact values and the "Checked at" read time sit in the figures' "?"
// (D-A40), and the shortfall is ONE visible line with the server's full message behind More (D-A41); the full-width
// paragraph under the summary is gone.
import { computed, ref } from 'vue'
import { istTime } from '@/lib/displayFormat'
import { displayOrDash, exactLine } from '@/lib/summaryFigures'
import { MARGIN_LINE_HIDDEN_REASON, capabilityOn } from '@/lib/brokerCapabilities'
import FigureHint from '@/components/common/FigureHint.vue'

const props = defineProps({
  margin: { type: Object, required: true },
  capabilities: { type: Object, default: null },
})

const pending = computed(() => props.capabilities === null)
const quoteOn = computed(() => capabilityOn(props.capabilities, 'basket_margin_quote'))
const checked = computed(() => props.margin.state === 'CHECKED' && typeof props.margin.needed === 'string'
  && typeof props.margin.available === 'string' && typeof props.margin.reason === 'string' && typeof props.margin.checked_at === 'string')
const short = computed(() => quoteOn.value && checked.value && props.margin.shortfall === true)
// REQ-055 AC-4: the server's own message (both figures and the ways forward), shown as it is; an older answer without
// the field keeps the plain line, so a cached answer still shows the shortfall.
const FALLBACK_SHORTFALL = 'Available funds are below the margin needed.'
const hasServerMessage = computed(() => typeof props.margin.shortfall_reason === 'string' && props.margin.shortfall_reason !== '')
const shortfallText = computed(() => (hasServerMessage.value ? props.margin.shortfall_reason : FALLBACK_SHORTFALL))
// I-8: the server's shortfall message already carries both figures, so the figures sentence is not printed a second time.
const showFigures = computed(() => !(short.value && hasServerMessage.value))
const openShort = ref(false)
const checkedAtLine = computed(() => `Checked at ${istTime(props.margin.checked_at)}`)
</script>

<template>
  <div
    v-if="!pending"
    :class="['min-w-0 break-words text-sm', short ? 'border-l-4 border-loss pl-3' : '@2xl:border-l @2xl:border-line @2xl:pl-4']"
    data-testid="margin"
    :data-margin-state="quoteOn ? margin.state : 'HIDDEN'"
    :data-short="short ? 'true' : 'false'"
  >
    <h3 class="text-[13px] font-semibold text-ink" data-testid="funds-margins-title">Funds &amp; Margins</h3>
    <p v-if="!quoteOn" class="mt-1 text-[13px] text-ink-muted" data-testid="margin-hidden-reason">{{ MARGIN_LINE_HIDDEN_REASON }}</p>
    <template v-else-if="checked">
      <dl class="mt-0.5 text-[13px]">
        <div class="flex min-h-6 items-center justify-between gap-2">
          <dt class="flex items-center text-ink-muted">Margin needed<FigureHint id="margin_needed" :lines="[exactLine(margin.needed)]" /></dt>
          <dd class="num font-medium text-ink" data-testid="margin-needed" :data-raw="margin.needed">{{ displayOrDash(margin.needed_display) }}</dd>
        </div>
        <div class="flex min-h-6 items-center justify-between gap-2">
          <dt class="flex items-center text-ink-muted">Margin available<FigureHint id="margin_available" :lines="[checkedAtLine, exactLine(margin.available)]" /></dt>
          <dd class="num font-medium text-ink" data-testid="margin-available" :data-raw="margin.available">{{ displayOrDash(margin.available_display) }}</dd>
        </div>
      </dl>
      <!-- D-A41 (ADR-202 (4), money safety): the warning stays visible in ONE line; the server's full message (both
           figures and the ways forward) is one tap away behind More, every word kept -->
      <div v-if="short" class="mt-0.5 text-[13px] text-loss" data-testid="margin-shortfall">
        <p class="flex flex-wrap items-baseline gap-x-1">
          <span class="font-medium" data-testid="margin-short-line">Not enough funds for this strategy</span>
          <button type="button" class="text-xs underline" :aria-expanded="openShort ? 'true' : 'false'" data-testid="margin-shortfall-more" @click="openShort = !openShort">{{ openShort ? 'Less' : 'More' }}</button>
        </p>
        <p v-if="openShort" class="mt-0.5 text-xs" data-testid="margin-shortfall-text">{{ shortfallText }}</p>
      </div>
      <!-- row 26f (issue #561): the funds_needed mark sits with the server's figures sentence (its "is needed" figure) -->
      <div v-if="showFigures" class="mt-0.5 flex items-start text-xs text-ink-muted">
        <p data-testid="margin-figures">{{ margin.reason }}</p>
        <FigureHint id="funds_needed" />
      </div>
    </template>
    <p v-else class="mt-1 text-[13px] text-ink-muted" data-testid="margin-text">{{ margin.reason }}</p>
  </div>
</template>
