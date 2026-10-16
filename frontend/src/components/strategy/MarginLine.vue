<script setup>
// ADR-099: Zerodha's margin for the planned orders, in the outcome screen's margin slot. Display only: the amounts are
// the API's own strings and the shortfall flag is the server's Decimal comparison; the browser never reads, parses or
// compares money (ADR-008). Without figures (no Kite login, Zerodha could not be read, a leg not listed) the answer's
// catalogue text is shown as it is. The Checked-at time uses the one ADR-088 formatter.
import { computed } from 'vue'
import { istTime } from '@/lib/displayFormat'

const props = defineProps({ margin: { type: Object, required: true } })

const checked = computed(() => props.margin.state === 'CHECKED' && typeof props.margin.needed === 'string'
  && typeof props.margin.available === 'string' && typeof props.margin.checked_at === 'string')
const short = computed(() => checked.value && props.margin.shortfall === true)
</script>

<template>
  <div class="mt-2 text-sm min-w-0 break-words" data-testid="margin" :data-margin-state="margin.state">
    <template v-if="checked">
      <p :class="short ? 'text-red-700 font-medium' : 'text-ink-muted'" data-testid="margin-figures">
        Margin (Zerodha): Rs {{ margin.needed }} needed, Rs {{ margin.available }} available
      </p>
      <p v-if="short" class="text-red-700" data-testid="margin-shortfall">Available funds are below the margin needed.</p>
      <p class="text-ink-muted" data-testid="margin-checked-at">Checked at {{ istTime(margin.checked_at) }}</p>
    </template>
    <p v-else class="text-ink-muted" data-testid="margin-text">{{ margin.reason }}</p>
  </div>
</template>
