<!-- Leg rows of the Strategy Builder (W-148; REQ-076 AC-1, AC-4, AC-6, AC-8, AC-9, AC-10; REQ-080 AC-7). Adapted from this
     repo's own branch build/W-126-a1-leg-rows (LegList.vue), REQ-076 parts only; typed price and Reset Prices (REQ-077)
     and Shift / Width / Hedge (REQ-078) are not here. One row per leg: tick | Buy/Sell | expiry | strike with - and + |
     CE/PE | lots | Hedge mark | depth icon. Every change is emitted as ONE edit and the page draws the server's reply.
     Nothing is computed here (ADR-008). The tick is page state only (REQ-076 AC-7). A futures leg has no stepper. -->
<script setup>
import { computed, ref } from 'vue'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import DepthPopup from '@/components/strategy/DepthPopup.vue'
import { contractName } from '@/lib/displayFormat'
import { CUSTOM_STRATEGY, LEFT_OUT_LABEL, MULTIPLIER_MAX, MULTIPLIER_MIN, NO_LEGS_YET, canStep, multiplierShape } from '@/lib/legEdit'

const props = defineProps({
  legs: { type: Array, required: true },
  shapeName: { type: String, default: null }, // the server's name; null = no reply yet (nothing is invented here)
  hasReply: { type: Boolean, default: false }, // a reply named the shape (a null name then means Custom Strategy)
  updating: { type: Boolean, default: false },
  errorParts: { type: Object, default: null },
})
const emit = defineEmits(['edit', 'add-leg', 'pick-chain'])

const multiplier = ref('1')
const multiplierBad = ref(false)
const depthFor = ref(null) // the leg whose depth popup is open

const selectedCount = computed(() => props.legs.filter((l) => l.included !== false).length)
const shown = computed(() => (props.hasReply ? props.shapeName ?? CUSTOM_STRATEGY : null))
const legName = (l) => contractName(l)

function setMultiplier(text) {
  if (!multiplierShape(text)) {
    multiplierBad.value = true // not digits: nothing is sent; digits out of 1..50 go to the server, which refuses them
    return
  }
  multiplierBad.value = false
  emit('edit', { control: 'multiplier', multiplier: parseInt(text.trim(), 10) })
}
</script>

<template>
  <div class="mt-3 text-sm" data-testid="leg-edit-list" :data-updating="updating ? 'true' : 'false'">
    <div v-if="!legs.length" data-testid="no-legs">
      <p class="text-ink-muted" data-testid="no-legs-text">{{ NO_LEGS_YET }}</p>
      <button type="button" class="mr-2 rounded border border-line px-2 py-1" data-testid="no-legs-add" @click="emit('add-leg')">Add leg</button>
      <button type="button" class="rounded border border-line px-2 py-1" data-testid="no-legs-chain" @click="emit('pick-chain')">Pick from Option Chain</button>
    </div>
    <template v-else>
      <p class="text-ink-muted" data-testid="leg-edit-header">
        {{ selectedCount }} selected<span v-if="shown" data-testid="shape-name"> - {{ shown }}</span>
        <span v-if="updating" class="ml-2" data-testid="numbers-updating">Updating the numbers...</span>
      </p>
      <label class="mt-1 flex items-center gap-2">Strategy multiplier ({{ MULTIPLIER_MIN }} to {{ MULTIPLIER_MAX }})
        <input v-model="multiplier" class="w-16 rounded border border-line px-1" inputmode="numeric" data-testid="multiplier" @change="setMultiplier($event.target.value)" />
      </label>
      <p v-if="multiplierBad" class="text-ink-muted" data-testid="multiplier-shape">Type a whole number from {{ MULTIPLIER_MIN }} to {{ MULTIPLIER_MAX }}.</p>
      <ErrorMessage v-if="errorParts" class="mt-2" :parts="errorParts" compact prefix="edit-error" data-testid="edit-error" />
      <ul>
        <li
          v-for="(leg, i) in legs" :key="leg.id ?? i" class="flex flex-wrap items-center gap-2 py-1"
          :class="leg.included === false ? 'text-ink-muted opacity-60' : ''" :data-testid="`leg-edit-row-${i}`" :data-included="leg.included === false ? 'false' : 'true'">
          <input type="checkbox" :checked="leg.included !== false" :aria-label="`Include leg ${i + 1} in the numbers`" data-testid="leg-tick" @change="emit('edit', { control: 'include', index: i, included: $event.target.checked })" />
          <span :class="leg.action === 'BUY' ? 'tag tag-buy' : 'tag tag-sell'">{{ leg.action }}</span>
          <span data-testid="leg-expiry">{{ leg.expiry ?? '' }}</span>
          <span v-if="canStep(leg)" class="flex items-center gap-1">
            <button type="button" class="rounded border border-line px-1" aria-label="Previous strike" data-testid="strike-minus" @click="emit('edit', { control: 'step', index: i, direction: -1 })">-</button>
            <span data-testid="leg-strike">{{ leg.strike }}</span>
            <button type="button" class="rounded border border-line px-1" aria-label="Next strike" data-testid="strike-plus" @click="emit('edit', { control: 'step', index: i, direction: 1 })">+</button>
          </span>
          <span :class="`tag tag-${(leg.instrument_type ?? '').toLowerCase()}`" data-testid="leg-type">{{ leg.instrument_type }}</span>
          <span data-testid="leg-lots">{{ leg.lots }} lot</span>
          <span v-if="leg.hedge === true" class="tag" data-testid="hedge-mark">Hedge</span>
          <span v-if="leg.included === false" data-testid="left-out-label">{{ LEFT_OUT_LABEL }}</span>
          <span v-if="leg.block" class="text-ink-muted" data-testid="leg-block">{{ leg.block }}</span>
          <button type="button" data-testid="leg-depth-icon" class="underline" :aria-label="`Market depth for ${legName(leg)}`" title="Market depth" @click="depthFor = depthFor === i ? null : i">Depth</button>
          <DepthPopup v-if="depthFor === i" class="w-full" :instrument-id="leg.instrument_id" :title="legName(leg)" @close="depthFor = null" />
        </li>
      </ul>
    </template>
  </div>
</template>
