<!-- Leg rows of the Strategy Builder (W-148; REQ-076 AC-1, AC-4, AC-6, AC-8, AC-9, AC-10; REQ-080 AC-7). Adapted from this
     repo's own branch build/W-126-a1-leg-rows (LegList.vue), REQ-076 parts only; typed price and Reset Prices (REQ-077)
     and Shift / Width / Hedge (REQ-078) are not here. One row per leg: tick | Buy/Sell | expiry | strike with - and + |
     CE/PE | lots | Hedge mark | depth icon. Every change is emitted as ONE edit and the page draws the server's reply.
     Nothing is computed here (ADR-008). The tick is page state only (REQ-076 AC-7). A futures leg has no stepper. -->
<script setup>
import { computed, ref } from 'vue'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import DepthPopup from '@/components/strategy/DepthPopup.vue'
import { contractName, expiryWithDays, istTime } from '@/lib/displayFormat'
import { NOT_CONNECTED_LABEL, REPRICE_PROMPT } from '@/lib/legPicker'
import {
  CUSTOM_STRATEGY, LEFT_OUT_LABEL, LEGS_CLEARED, MULTIPLIER_CHOICES, MULTIPLIER_MAX, MULTIPLIER_MIN, NO_LEGS_YET, PLANNED_ENTRY_LABEL, YOUR_PRICE_LABEL,
  NO_CONTROLS, canStep, movedMarker, priceReasonText, removeAllPrompt, replacedPriceNote, showsControls,
} from '@/lib/legEdit'
import StrategyControls from '@/components/strategy/StrategyControls.vue'

const props = defineProps({
  legs: { type: Array, required: true },
  shapeName: { type: String, default: null }, // the server's name; null = no reply yet (nothing is invented here)
  hasReply: { type: Boolean, default: false }, // a reply named the shape (a null name then means Custom Strategy)
  updating: { type: Boolean, default: false },
  errorParts: { type: Object, default: null },
  errorIndex: { type: Number, default: null }, // the leg whose typed price was refused: its error shows under that field (REQ-077 AC-2)
  ltpById: { type: Object, default: () => ({}) }, // the outcome's own per-leg LTP strings by instrument id (REQ-077 AC-6)
  controls: { type: Object, default: () => NO_CONTROLS }, // REQ-078 AC-2: controlsFrom(the newest reply); nothing applies until one arrives
  undoOffered: { type: Boolean, default: false }, // REQ-135 AC-1: the page holds the cleared legs for 10 seconds
})
const emit = defineEmits(['edit', 'add-leg', 'pick-chain', 'remove', 'edit-leg', 'clear-all', 'undo-clear'])

const multiplier = ref(1)
const confirmingClear = ref(false) // REQ-135 AC-1: the 'Remove all N legs?' question is open
const legUnit = ref('lots') // REQ-076 AC-5: lots by default; Quantity draws the reply's own quantity (no multiplication here)
const typedText = ref({}) // the text in each row's price field, by index: sent as typed, never parsed here
const depthFor = ref(null) // the leg whose depth popup is open

const selectedCount = computed(() => props.legs.filter((l) => l.included !== false).length)
const shown = computed(() => (props.hasReply ? props.shapeName ?? CUSTOM_STRATEGY : null))
const legName = (l) => contractName(l)
// REQ-078 AC-8: one sentence per leg whose typed price the newest reply replaced (the legs carry the reply's flag)
const replacedNotes = computed(() => props.legs.flatMap((l, i) => (l.replaced_typed === true ? [replacedPriceNote(i + 1, l)] : [])))
// ADR-085: a leg saved without a planned entry says so and offers Reprice (REQ-077 AC-7); Edit and Reprice both open the picker's own edit form
const needsReprice = (l) => l.planned_entry == null && l.reason_code === 'needs_reprice'

function confirmClear() {
  confirmingClear.value = false
  emit('clear-all')
}
function setPrice(index) {
  const text = typedText.value[index]
  if (typeof text === 'string' && text.trim() !== '') emit('edit', { control: 'price', index, price: text.trim() })
}
function resetLeg(index) {
  typedText.value = { ...typedText.value, [index]: '' }
  emit('edit', { control: 'reset_leg', index })
}
function resetPrices() {
  typedText.value = {}
  emit('edit', { control: 'reset_prices' })
}
const entryLabel = (l) => (l.typed === true ? YOUR_PRICE_LABEL : PLANNED_ENTRY_LABEL)

function setMultiplier(index) {
  const choice = MULTIPLIER_CHOICES[index] // chosen from the fixed list: nothing is parsed from text
  if (choice !== undefined) emit('edit', { control: 'multiplier', multiplier: choice })
}
</script>

<template>
  <div class="mt-3 text-sm" data-testid="leg-edit-list" :data-updating="updating ? 'true' : 'false'">
    <p v-if="undoOffered" class="mb-1" data-testid="clear-undo-bar">
      {{ LEGS_CLEARED }} <button type="button" class="underline" data-testid="clear-undo" @click="emit('undo-clear')">Undo</button>
    </p>
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
        <select v-model="multiplier" class="rounded border border-line px-1" data-testid="multiplier" @change="setMultiplier($event.target.selectedIndex)">
          <option v-for="n in MULTIPLIER_CHOICES" :key="n" :value="n">{{ n }}</option>
        </select>
      </label>
      <StrategyControls v-if="showsControls(legs)" :controls="controls" @edit="(e) => emit('edit', e)" />
      <label class="mt-1 flex items-center gap-2">Show
        <select v-model="legUnit" class="rounded border border-line px-1" data-testid="lots-quantity-switch">
          <option  value="lots">Lots</option>
          <option  value="quantity">Quantity</option>
        </select>
      </label>
      <button type="button" class="mt-1 rounded border border-line px-2 py-1" data-testid="reset-prices" @click="resetPrices">Reset Prices</button>
      <button type="button" class="mt-1 ml-2 rounded border border-line px-2 py-1" data-testid="clear-all-legs" @click="confirmingClear = true">Clear all legs</button>
      <span v-if="confirmingClear" class="ml-2" data-testid="clear-confirm">
        <span data-testid="clear-confirm-text">{{ removeAllPrompt(legs.length) }}</span>
        <button type="button" class="ml-1 rounded border border-line px-2" data-testid="clear-confirm-yes" @click="confirmClear">Confirm</button>
        <button type="button" class="ml-1 rounded border border-line px-2" data-testid="clear-confirm-no" @click="confirmingClear = false">Cancel</button>
      </span>
      <ErrorMessage v-if="errorParts && errorIndex === null" class="mt-2" :parts="errorParts" compact prefix="edit-error" data-testid="edit-error" />
      <p v-for="n in replacedNotes" :key="n" class="mt-1 text-ink-muted" data-testid="replaced-note">{{ n }}</p>
      <ul>
        <li
          v-for="(leg, i) in legs" :key="leg.id ?? i" class="flex flex-wrap items-center gap-2 py-1"
          :class="leg.included === false ? 'text-ink-muted opacity-60' : ''" :data-testid="'leg-row'" :data-index="i" :data-included="leg.included === false ? 'false' : 'true'"
          :data-instrument-id="leg.instrument_id" :data-action="leg.action" :data-lots="leg.lots" :data-entry="leg.planned_entry ?? ''"
          :data-captured="leg.captured_at ?? ''" :data-strike="leg.strike ?? ''" :data-type="leg.instrument_type" :data-expiry="leg.expiry">
          <input type="checkbox" :checked="leg.included !== false" :aria-label="`Include leg ${i + 1} in the numbers`" data-testid="leg-tick" @change="emit('edit', { control: 'include', index: i, included: $event.target.checked })" />
          <span :class="leg.action === 'BUY' ? 'tag tag-buy' : 'tag tag-sell'">{{ leg.action }}</span>
          <span data-testid="leg-expiry">{{ expiryWithDays(leg.expiry, leg.days_to_expiry) }}</span>
          <span v-if="canStep(leg)" class="flex items-center gap-1">
            <button type="button" class="rounded border border-line px-1" aria-label="Previous strike" data-testid="strike-minus" @click="emit('edit', { control: 'step', index: i, direction: -1 })">-</button>
            <span data-testid="leg-strike">{{ leg.strike }}</span>
            <button type="button" class="rounded border border-line px-1" aria-label="Next strike" data-testid="strike-plus" @click="emit('edit', { control: 'step', index: i, direction: 1 })">+</button>
          </span>
          <span :class="`tag tag-${(leg.instrument_type ?? '').toLowerCase()}`" data-testid="leg-type">{{ leg.instrument_type }}</span>
          <span v-if="legUnit === 'quantity'" data-testid="leg-quantity">{{ leg.quantity ?? '' }}</span>
          <span v-else data-testid="leg-lots">{{ leg.lots }} lot</span>
          <span v-if="leg.hedge === true" class="tag" data-testid="hedge-mark">Hedge</span>
          <span class="sr-only" data-testid="leg-name">{{ legName(leg) }}</span>
          <span v-if="leg.planned_entry != null" data-testid="leg-entry">{{ entryLabel(leg) }} {{ leg.planned_entry }}</span>
          <span v-if="leg.planned_entry != null && leg.captured_at != null" class="text-ink-muted" data-testid="leg-captured">{{ leg.typed === true ? 'typed' : 'captured' }} {{ istTime(leg.captured_at) }}</span>
          <template v-else>
            <span data-testid="leg-unpriced">{{ NOT_CONNECTED_LABEL }}</span>
            <span v-if="leg.planned_entry == null && priceReasonText(leg.price_reason)" class="text-ink-muted" data-testid="leg-price-reason">{{ priceReasonText(leg.price_reason) }}</span>
          </template>
          <span v-if="movedMarker(leg, ltpById[leg.instrument_id])" class="text-ink-muted" data-testid="price-moved">{{ movedMarker(leg, ltpById[leg.instrument_id]) }}</span>
          <input v-model="typedText[i]" type="text" inputmode="decimal" class="w-20 rounded border border-line px-1" :aria-label="`Your price for leg ${i + 1}`" data-testid="price-input" @keydown.enter="setPrice(i)" />
          <button type="button" class="rounded border border-line px-1" data-testid="price-set" @click="setPrice(i)">Set price</button>
          <button type="button" class="underline" data-testid="reset-leg" @click="resetLeg(i)">Reset</button>
          <span v-if="leg.included === false" data-testid="left-out-label">{{ LEFT_OUT_LABEL }}</span>
          <span v-if="leg.block" class="text-ink-muted" data-testid="leg-block">{{ leg.block }}</span>
          <template v-if="needsReprice(leg)">
            <span data-testid="leg-reprice-prompt">{{ REPRICE_PROMPT }}</span>
            <button type="button" data-testid="reprice-leg" class="underline" @click="emit('edit-leg', i)">Reprice</button>
          </template>
          <button type="button" data-testid="depth-icon" class="underline" :aria-label="`Market depth for ${legName(leg)}`" title="Market depth" @click="depthFor = depthFor === i ? null : i">Depth</button>
          <button type="button" data-testid="edit-leg" class="underline" @click="emit('edit-leg', i)">Edit</button>
          <button type="button" class="underline" data-testid="remove-leg" :aria-label="`Remove ${legName(leg)}`" @click="emit('remove', i)">Remove</button>
          <ErrorMessage v-if="errorParts && errorIndex === i" class="w-full" :parts="errorParts" compact prefix="price-error" data-testid="price-error" />
          <DepthPopup v-if="depthFor === i" class="w-full" :instrument-id="leg.instrument_id" :title="legName(leg)" @close="depthFor = null" />
        </li>
      </ul>
    </template>
  </div>
</template>
