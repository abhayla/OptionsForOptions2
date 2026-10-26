<script setup>
// ADR-099: Zerodha's margin for the planned orders, in the outcome screen's margin slot. Display only: the amounts are
// the API's own strings and the shortfall flag is the server's Decimal comparison; the browser never reads, parses or
// compares money (ADR-008). Without figures (no Kite login, Zerodha could not be read, a leg not listed) the answer's
// catalogue text is shown as it is. The Checked-at time uses the one ADR-088 formatter.
// REQ-117 (W-132): the line asks the flag `basket_margin_quote`. `capabilities` is the server's flag body: null while
// it is being read (nothing is drawn), then the line only when the flag is on; otherwise the plain reason, no figures.
import { computed } from 'vue'
import { istTime } from '@/lib/displayFormat'
import { MARGIN_LINE_HIDDEN_REASON, capabilityOn } from '@/lib/brokerCapabilities'
import FigureHint from '@/components/common/FigureHint.vue'

const props = defineProps({
  margin: { type: Object, required: true },
  capabilities: { type: Object, default: null },
})

const pending = computed(() => props.capabilities === null)
const quoteOn = computed(() => capabilityOn(props.capabilities, 'basket_margin_quote'))
const checked = computed(() => props.margin.state === 'CHECKED' && typeof props.margin.needed === 'string'
  && typeof props.margin.available === 'string' && typeof props.margin.checked_at === 'string')
const short = computed(() => checked.value && props.margin.shortfall === true)
// REQ-055 AC-4: the server's own line (both figures and the ways forward), shown as it is; an older answer without
// the field keeps the plain line, so a cached answer still shows the shortfall.
const FALLBACK_SHORTFALL = 'Available funds are below the margin needed.'
const shortfallText = computed(() => (typeof props.margin.shortfall_reason === 'string' && props.margin.shortfall_reason
  ? props.margin.shortfall_reason : FALLBACK_SHORTFALL))
</script>

<template>
  <div v-if="!pending" class="mt-2 text-sm min-w-0 break-words" data-testid="margin" :data-margin-state="quoteOn ? margin.state : 'HIDDEN'">
    <p v-if="!quoteOn" class="text-ink-muted" data-testid="margin-hidden-reason">{{ MARGIN_LINE_HIDDEN_REASON }}</p>
    <template v-else-if="checked">
      <div class="flex flex-wrap items-center">
        <p :class="short ? 'text-red-700 font-medium' : 'text-ink-muted'" data-testid="margin-figures">
          Margin (Zerodha): Rs {{ margin.needed }} needed, Rs {{ margin.available }} available
        </p>
        <FigureHint id="margin_needed" />
        <FigureHint id="funds_needed" />
        <FigureHint id="margin_available" />
      </div>
      <p v-if="short" class="text-red-700" data-testid="margin-shortfall">{{ shortfallText }}</p>
      <p class="text-ink-muted" data-testid="margin-checked-at">Checked at {{ istTime(margin.checked_at) }}</p>
    </template>
    <p v-else class="text-ink-muted" data-testid="margin-text">{{ margin.reason }}</p>
  </div>
</template>
