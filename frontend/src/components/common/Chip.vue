<!-- ADR-193 UI study a.2 / a.3: a 12 px/600 chip. `buy` / `sell` = the B/S chip (S-012); `opt` = CE / PE / FUT, neutral
     (CE and PE are told apart by text, not colour); `state` = a plain labelled state chip. Health is NOT a chip kind
     here: ADR-049 keeps the health colours for the health chip alone. -->
<script setup>
import { computed } from 'vue'

const props = defineProps({
  kind: { type: String, default: 'state', validator: (v) => ['buy', 'sell', 'opt', 'state', 'selected'].includes(v) },
  label: { type: String, required: true },
})
const TONE = {
  buy: 'bg-buy-soft text-buy',
  sell: 'bg-sell-soft text-sell',
  opt: 'bg-opt-soft text-opt',
  state: 'border border-line bg-surface-muted text-ink-muted',
  selected: 'bg-accent-soft text-accent',
}
const tone = computed(() => TONE[props.kind])
</script>

<template>
  <span class="inline-flex h-5 items-center rounded px-1.5 text-xs leading-4 font-semibold" :class="tone" :data-kind="kind" data-testid="chip">{{
    label
  }}</span>
</template>
