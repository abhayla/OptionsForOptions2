<!-- Leg rows of the Strategy Builder (W-126; REQ-076 AC-1/AC-6/AC-8, REQ-077 AC-1/AC-5/AC-9). One row per leg, after
     Sensibull screens 011/012: tick | Buy/Sell | expiry | strike with -/+ | CE/PE | lots | editable price with a corner
     marker. The tick state is page state only: it is never saved (REQ-076 AC-7). A futures leg has no stepper.
     Every change is emitted as ONE edit; the server answers with the new legs. Nothing is computed here (ADR-008). -->
<template>
  <div v-if="legs.length" class="mt-3 text-sm" data-testid="leg-list">
    <p class="text-ink-muted" data-testid="leg-list-header">
      {{ selectedCount }} selected<span v-if="shape" data-testid="shape-label"> - {{ shape }}</span>
    </p>
    <ul>
      <li v-for="(leg, i) in legs" :key="leg.id ?? i" class="flex flex-wrap items-center gap-2 py-1" :data-testid="`leg-row-${i}`">
        <input type="checkbox" :checked="leg.included !== false" :aria-label="`Include leg ${i + 1}`" data-testid="leg-tick" @change="emit('edit', { control: 'include', index: i, included: $event.target.checked })" />
        <span :class="leg.action === 'BUY' ? 'tag tag-buy' : 'tag tag-sell'">{{ leg.action }}</span>
        <span data-testid="leg-expiry">{{ leg.expiry ?? '' }}</span>
        <span v-if="leg.instrument_type !== 'FUT'" class="flex items-center gap-1">
          <button type="button" class="rounded border border-line px-1" data-testid="strike-minus" @click="emit('edit', { control: 'step', index: i, direction: -1 })">-</button>
          <span data-testid="leg-strike">{{ leg.strike }}</span>
          <button type="button" class="rounded border border-line px-1" data-testid="strike-plus" @click="emit('edit', { control: 'step', index: i, direction: 1 })">+</button>
        </span>
        <span :class="`tag tag-${(leg.instrument_type ?? '').toLowerCase()}`">{{ leg.instrument_type }}</span>
        <span data-testid="leg-lots">{{ leg.lots }}</span>
        <label class="flex items-center gap-1">
          <span class="sr-only">Planned entry of leg {{ i + 1 }}</span>
          <input :value="leg.planned_entry ?? ''" class="w-24 rounded border border-line px-1" inputmode="decimal" :data-testid="`leg-price-${i}`" @change="typePrice(i, $event.target.value)" />
          <span v-if="leg.typed" title="You typed this price" data-testid="typed-marker">typed</span>
        </label>
        <span v-if="leg.planned_entry == null" class="text-ink-muted" data-testid="leg-unpriced">{{ REPRICE_PROMPT }}</span>
        <span v-if="priceBad === i" class="text-ink-muted" data-testid="price-shape">Type a price such as 81.35.</span>
      </li>
    </ul>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { REPRICE_PROMPT } from '@/lib/legPicker'
import { priceShape } from '@/lib/legEdit'

const props = defineProps({
  legs: { type: Array, required: true },
  shape: { type: String, default: null },
})
const emit = defineEmits(['edit'])

const priceBad = ref(-1)
const selectedCount = computed(() => props.legs.filter((l) => l.included !== false).length)

function typePrice(index, text) {
  if (!priceShape(text)) {
    priceBad.value = index
    return
  }
  priceBad.value = -1
  emit('edit', { control: 'price', index, price: text })
}
</script>
