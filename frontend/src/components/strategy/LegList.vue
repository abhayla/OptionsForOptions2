<!-- Region B strategy card of the Strategy Builder (W-192, ADR-193 UI-104..UI-107 + Revision 1; was W-148 leg rows: REQ-076
     AC-1, AC-4, AC-6, AC-8, AC-9, AC-10; REQ-077 AC-1, AC-5..AC-7; REQ-080 AC-7; REQ-135 AC-1, AC-2). Card header (name, Clear
     all), selection row (tick state, count, shape name, Reset Prices), the compact leg table (one fixed-width row per leg that
     never wraps at 480 px; a visible second line only for a typed price, a moved price, a missing entry or a refusal), Strike
     Controls, and the multiplier row (the page's money figures sit in its `money` slot). ADR-195: with any leg unticked the
     label shows only the count, no Hedge mark is drawn, and Width / Hedge are off with their reason. Every change is ONE emitted
     edit and the page draws the server's reply; nothing is computed here (ADR-008). The Lots / Quantity choice is the page's
     (Settings popover, UI-103). -->
<script setup>
import { computed, nextTick, ref } from 'vue'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import Icon from '@/components/common/Icon.vue'
import DepthPopup from '@/components/strategy/DepthPopup.vue'
import StrategyControls from '@/components/strategy/StrategyControls.vue'
import { useOutsideClose } from '@/composables/useOutsideClose'
import { capturedCaption, contractName, expiryWithDays, istTime } from '@/lib/displayFormat'
import { NOT_CONNECTED_LABEL, REPRICE_PROMPT } from '@/lib/legPicker'
import {
  CUSTOM_STRATEGY, LEFT_OUT_LABEL, LEGS_CLEARED, LEG_CARD_PADDING_PX, LEG_ROW_COLUMNS, MULTIPLIER_CHOICES, MULTIPLIER_MAX, MULTIPLIER_MIN,
  NO_CONTROLS, NO_LEGS_YET, PLANNED_ENTRY_LABEL, YOUR_PRICE_LABEL,
  anyUnticked, canStep, controlsForSelection, movedMarker, priceReasonText, removeAllPrompt, replacedPriceNote, showsControls,
} from '@/lib/legEdit'

const props = defineProps({
  legs: { type: Array, required: true },
  shapeName: { type: String, default: null }, // the server's name; null = no reply yet (nothing is invented here)
  hasReply: { type: Boolean, default: false }, // a reply named the shape (a null name then means Custom Strategy)
  updating: { type: Boolean, default: false },
  errorParts: { type: Object, default: null },
  errorIndex: { type: Number, default: null }, // the leg whose typed price was refused: its error shows under that row (REQ-077 AC-2)
  ltpById: { type: Object, default: () => ({}) }, // the outcome's own per-leg LTP strings by instrument id (REQ-077 AC-6)
  controls: { type: Object, default: () => NO_CONTROLS }, // REQ-078 AC-2: controlsFrom(the newest reply)
  undoOffered: { type: Boolean, default: false }, // REQ-135 AC-1: the page holds the cleared legs for 10 seconds
  legUnit: { type: String, default: 'lots' }, // REQ-076 AC-5: 'lots' | 'quantity', chosen in the page's Settings popover
  strategyName: { type: String, default: null }, // the open saved strategy's name, else the card reads "New Strategy"
})
const emit = defineEmits(['edit', 'add-leg', 'pick-chain', 'remove', 'edit-leg', 'clear-all', 'undo-clear'])

const multiplier = ref(1)
const confirmingClear = ref(false) // REQ-135 AC-1: the 'Remove all N legs?' question is open
const typedText = ref({}) // the text in each row's price field, by index: sent as typed, never parsed here
const depthFor = ref(null) // the leg whose depth popover is open
const menuFor = ref(null) // the leg whose price menu (capture time, Set price, Reset) is open
const menuRoots = {} // price-menu wrapper and trigger button by leg index (focus returns to the trigger on close)
const menuButtons = {}
async function closeMenu() {
  const i = menuFor.value
  if (i === null) return
  menuFor.value = null
  await nextTick()
  menuButtons[i]?.focus?.()
}
useOutsideClose(() => menuFor.value !== null, () => menuRoots[menuFor.value], closeMenu)

const gridColumns = `${LEG_ROW_COLUMNS.slice(0, 3).map((w) => `${w}px`).join(' ')} minmax(${LEG_ROW_COLUMNS[3]}px, 1fr) ${LEG_ROW_COLUMNS.slice(4).map((w) => `${w}px`).join(' ')}`
// Review B (ADR-165 (7)): below 640 px a leg row is two lines (contract on line 1; price, depth, edit, remove on line 2),
// so the table fits a 390 px phone. The desktop columns are a CSS variable the phone class replaces.
const gridStyle = { '--leg-cols': gridColumns }
const cardPadding = { paddingLeft: `${LEG_CARD_PADDING_PX}px`, paddingRight: `${LEG_CARD_PADDING_PX}px` }
const selectedCount = computed(() => props.legs.filter((l) => l.included !== false).length)
const someLeftOut = computed(() => anyUnticked(props.legs))
// ADR-195: no shape name while any leg is left out; otherwise the server's name (Custom Strategy when it named none)
const shown = computed(() => (someLeftOut.value || !props.hasReply ? null : props.shapeName ?? CUSTOM_STRATEGY))
const shownControls = computed(() => controlsForSelection(props.controls, props.legs))
const tickState = computed(() => (selectedCount.value === props.legs.length ? 'all' : selectedCount.value === 0 ? 'none' : 'some'))
const legName = (l) => contractName(l)
const replacedNotes = computed(() => props.legs.flatMap((l, i) => (l.replaced_typed === true ? [replacedPriceNote(i + 1, l)] : [])))
const needsReprice = (l) => l.planned_entry == null && l.reason_code === 'needs_reprice'
const moved = (l) => movedMarker(l, props.ltpById[l.instrument_id])
// Revision 1 (REQ-077 AC-1, AC-6, AC-7): a second line only when something must stay visible
// a leg without both a planned entry and its capture time keeps the not-connected label (REQ-077 AC-5)
const unpriced = (l) => !(l.planned_entry != null && l.captured_at != null)
const needsSecondLine = (l, i) => l.included === false || l.typed === true || !!moved(l) || unpriced(l) || !!l.block || (props.errorParts && props.errorIndex === i)
const entryLabel = (l) => (l.typed === true ? YOUR_PRICE_LABEL : PLANNED_ENTRY_LABEL)
// REQ-077 AC-1: a captured price (not typed, not moved) shows its capture time as a small caption under the price
const showsCaption = (l) => l.typed !== true && !moved(l) && !unpriced(l)
const capturedText = (l) => `${l.typed === true ? 'typed' : 'captured'} ${istTime(l.captured_at)}`
// Review 3 (REQ-077 AC-1): the caption names the capture and carries the date unless it is today (India time), so a draft
// reopened from yesterday never reads as a price taken today
const caption = (l) => capturedCaption(l.captured_at)

function confirmClear() {
  confirmingClear.value = false
  emit('clear-all')
}
function setPrice(index) {
  const text = typedText.value[index]
  if (typeof text === 'string' && text.trim() !== '') emit('edit', { control: 'price', index, price: text.trim() })
  closeMenu()
}
function resetLeg(index) {
  typedText.value = { ...typedText.value, [index]: '' }
  closeMenu()
  emit('edit', { control: 'reset_leg', index })
}
function resetPrices() {
  typedText.value = {}
  emit('edit', { control: 'reset_prices' })
}
function setMultiplier(index) {
  const choice = MULTIPLIER_CHOICES[index] // chosen from the fixed list: nothing is parsed from text
  if (choice !== undefined) emit('edit', { control: 'multiplier', multiplier: choice })
}
</script>

<template>
  <div class="rounded-t-lg border border-b-0 border-line bg-surface text-sm" data-testid="leg-edit-list" :data-updating="updating ? 'true' : 'false'">
    <div class="flex h-12 items-center justify-between border-b border-line" :style="cardPadding" data-testid="strategy-card-header">
      <p role="heading" aria-level="2" class="truncate text-base font-semibold" data-testid="strategy-card-name">{{ strategyName || 'New Strategy' }}</p>
      <span v-if="legs.length" class="flex items-center gap-2">
        <button type="button" class="text-accent" data-testid="clear-all-legs" @click="confirmingClear = true">Clear all</button>
      </span>
    </div>
    <p v-if="confirmingClear" class="flex items-center gap-1 border-b border-line py-2" :style="cardPadding" data-testid="clear-confirm">
      <span data-testid="clear-confirm-text">{{ removeAllPrompt(legs.length) }}</span>
      <button type="button" class="ml-1 rounded border border-line px-2" data-testid="clear-confirm-yes" @click="confirmClear">Confirm</button>
      <button type="button" class="ml-1 rounded border border-line px-2" data-testid="clear-confirm-no" @click="confirmingClear = false">Cancel</button>
    </p>
    <p v-if="undoOffered" class="py-2" :style="cardPadding" data-testid="clear-undo-bar">
      {{ LEGS_CLEARED }} <button type="button" class="text-accent underline" data-testid="clear-undo" @click="emit('undo-clear')">Undo</button>
    </p>

    <div v-if="!legs.length" class="py-6 text-center" :style="cardPadding" data-testid="no-legs">
      <p class="font-medium" data-testid="no-legs-text">{{ NO_LEGS_YET }}</p>
      <p class="mt-1 text-xs text-ink-muted">Pick strikes, or start from a ready-made shape below.</p>
      <div class="mt-3 flex justify-center gap-2">
        <button type="button" class="rounded bg-accent px-3 py-1 text-white" data-testid="no-legs-add" @click="emit('add-leg')">Add leg</button>
        <button type="button" class="rounded border border-line px-3 py-1" data-testid="no-legs-chain" @click="emit('pick-chain')">Pick from Option Chain</button>
      </div>
    </div>

    <template v-else>
      <div class="flex h-8 items-center justify-between" :style="cardPadding">
        <p class="flex min-w-0 items-center gap-2 text-ink-muted" data-testid="leg-edit-header">
          <span
            role="img" class="inline-flex w-4 justify-center" :data-state="tickState" data-testid="tick-all-state"
            :aria-label="`${tickState === 'all' ? 'All' : tickState === 'some' ? 'Some' : 'None'} legs selected: ${selectedCount} of ${legs.length}`"
          ><Icon :name="tickState === 'none' ? 'close' : tickState === 'some' ? 'more' : 'check'" :size="14" /></span>
          <span class="truncate">{{ selectedCount }} selected<span v-if="shown" data-testid="shape-name"> - {{ shown }}</span></span>
          <span v-if="updating" class="ml-1" data-testid="numbers-updating">Updating the numbers...</span>
        </p>
        <button type="button" class="flex items-center gap-1 text-accent" data-testid="reset-prices" @click="resetPrices">
          <Icon name="refresh" :size="14" />Reset Prices
        </button>
      </div>
      <ErrorMessage v-if="errorParts && errorIndex === null" class="mx-3 mb-2" :parts="errorParts" compact prefix="edit-error" data-testid="edit-error" />
      <p v-for="n in replacedNotes" :key="n" class="text-ink-muted" :style="cardPadding" data-testid="replaced-note">{{ n }}</p>

      <div class="leg-grid grid items-center whitespace-nowrap text-xs text-ink-muted max-[639px]:hidden" :style="{ ...cardPadding, ...gridStyle }" aria-hidden="true" data-testid="leg-table-head">
        <span></span><span>B/S</span><span>Expiry</span><span class="text-center">Strike</span><span>Type</span><span>Lots</span><span class="text-right" data-testid="price-head">{{ PLANNED_ENTRY_LABEL }}</span><span></span><span></span><span></span>
      </div>
      <ul data-testid="leg-table">
        <li
          v-for="(leg, i) in legs" :key="leg.id ?? i" class="border-t border-line py-1" :style="cardPadding"
          :class="leg.included === false ? 'text-ink-muted opacity-60' : ''" :title="leg.included === false ? LEFT_OUT_LABEL : undefined"
          :data-testid="'leg-row'" :data-index="i" :data-included="leg.included === false ? 'false' : 'true'"
          :data-instrument-id="leg.instrument_id" :data-action="leg.action" :data-lots="leg.lots" :data-entry="leg.planned_entry ?? ''"
          :data-captured="leg.captured_at ?? ''" :data-strike="leg.strike ?? ''" :data-type="leg.instrument_type" :data-expiry="leg.expiry">
          <div class="leg-grid leg-phone grid h-7 flex-nowrap items-center whitespace-nowrap max-[639px]:h-auto max-[639px]:gap-y-1" :style="gridStyle" data-testid="leg-row-line">
            <input type="checkbox" :checked="leg.included !== false" :aria-label="`Include leg ${i + 1} in the numbers`" data-testid="leg-tick" @change="emit('edit', { control: 'include', index: i, included: $event.target.checked })" />
            <span :class="leg.action === 'BUY' ? 'tag tag-buy' : 'tag tag-sell'" class="w-6 text-center" :title="leg.action">{{ leg.action === 'BUY' ? 'B' : 'S' }}<span class="sr-only">{{ leg.action }}</span></span>
            <span class="overflow-hidden text-xs" :title="expiryWithDays(leg.expiry, leg.days_to_expiry)" data-testid="leg-expiry">{{ expiryWithDays(leg.expiry, leg.days_to_expiry) }}</span>
            <span class="flex items-center justify-center gap-1 overflow-hidden">
              <template v-if="canStep(leg)">
                <button type="button" class="rounded border border-line px-1 leading-4" aria-label="Previous strike" data-testid="strike-minus" @click="emit('edit', { control: 'step', index: i, direction: -1 })">-</button>
                <span data-testid="leg-strike">{{ leg.strike }}</span>
                <button type="button" class="rounded border border-line px-1 leading-4" aria-label="Next strike" data-testid="strike-plus" @click="emit('edit', { control: 'step', index: i, direction: 1 })">+</button>
              </template>
              <span v-else class="text-ink-muted" aria-label="No strike for a futures leg">-</span>
              <span v-if="leg.hedge === true && !someLeftOut" class="tag px-1 text-[10px]" title="Hedge" aria-label="Hedge" data-testid="hedge-mark">H</span>
            </span>
            <span :class="`tag tag-${(leg.instrument_type ?? '').toLowerCase()}`" data-testid="leg-type">{{ leg.instrument_type }}</span>
            <span v-if="legUnit === 'quantity'" data-testid="leg-quantity">{{ leg.quantity ?? '' }}</span>
            <span v-else data-testid="leg-lots">{{ leg.lots }} lot</span>
            <span :ref="(el) => (menuRoots[i] = el)" class="leg-line2-price relative flex items-center justify-end" @keydown.esc="closeMenu">
              <input
                v-model="typedText[i]" type="text" inputmode="decimal" class="num w-[8ch] min-w-[8ch] rounded border px-1 text-right"
                :class="leg.typed === true ? 'border-accent' : 'border-line'" :placeholder="leg.planned_entry ?? ''"
                :title="leg.planned_entry != null && leg.captured_at != null ? `${entryLabel(leg)}, ${capturedText(leg)}` : undefined"
                :aria-label="`Your price for leg ${i + 1}`" data-testid="price-input" @keydown.enter="setPrice(i)"
              />
              <button
                :ref="(el) => (menuButtons[i] = el)" type="button" class="px-0.5" aria-haspopup="menu" :aria-expanded="menuFor === i ? 'true' : 'false'" :aria-label="`Price options for leg ${i + 1}`"
                data-testid="price-menu" @click="menuFor === i ? closeMenu() : (menuFor = i)"
              ><Icon name="chevron" :size="12" /></button>
              <span
                v-show="menuFor === i" role="menu" class="absolute right-0 top-full z-20 mt-1 w-56 max-[639px]:left-0 max-[639px]:right-auto whitespace-normal rounded border border-line bg-surface p-2 text-left shadow"
                data-testid="price-menu-panel"
              >
                <span v-if="leg.planned_entry != null && leg.captured_at != null" class="block text-ink-muted" data-testid="leg-captured">{{ capturedText(leg) }}</span>
                <button type="button" role="menuitem" class="block text-accent" data-testid="price-set" @click="setPrice(i)">Set price</button>
                <button type="button" role="menuitem" class="block text-accent" data-testid="reset-leg" @click="resetLeg(i)">Reset</button>
              </span>
            </span>
            <span class="leg-line2 relative">
              <button type="button" data-testid="depth-icon" :aria-label="`Market depth for ${legName(leg)}`" title="Market depth" @click="depthFor = depthFor === i ? null : i"><Icon name="table" :size="14" /></button>
              <DepthPopup v-if="depthFor === i" class="absolute right-0 top-full z-20" :instrument-id="leg.instrument_id" :title="legName(leg)" @close="depthFor = null" />
            </span>
            <button type="button" class="leg-line2" data-testid="edit-leg" :aria-label="`Edit ${legName(leg)}`" title="Edit" @click="emit('edit-leg', i)"><Icon name="pencil" :size="14" /></button>
            <button type="button" class="leg-line2" data-testid="remove-leg" :aria-label="`Remove ${legName(leg)}`" title="Remove" @click="emit('remove', i)"><Icon name="trash" :size="14" /></button>
          </div>
          <div v-if="showsCaption(leg)" class="leg-grid grid text-xs text-ink-muted" :style="gridStyle" data-testid="leg-caption-line">
            <span class="whitespace-nowrap text-right [grid-column:1/8] max-[639px]:[grid-column:1/-1] max-[639px]:text-left" data-testid="leg-caption" :title="capturedText(leg)">{{ caption(leg) }}</span>
          </div>
          <span class="sr-only" data-testid="leg-name">{{ legName(leg) }}</span>
          <span v-if="leg.planned_entry != null" class="sr-only" data-testid="leg-entry">{{ entryLabel(leg) }} {{ leg.planned_entry }}</span>
          <div v-if="needsSecondLine(leg, i)" class="pl-6 text-xs text-ink-muted" data-testid="leg-second-line">
            <span v-if="leg.included === false" class="mr-2" data-testid="left-out-label">{{ LEFT_OUT_LABEL }}</span>
            <span v-if="leg.typed === true && leg.planned_entry != null" class="mr-2" data-testid="leg-typed-line">{{ YOUR_PRICE_LABEL }}, {{ capturedText(leg) }}</span>
            <span v-if="moved(leg)" class="mr-2" data-testid="price-moved">{{ moved(leg) }}</span>
            <template v-if="unpriced(leg)">
              <span class="mr-2" data-testid="leg-unpriced">{{ NOT_CONNECTED_LABEL }}</span>
              <span v-if="leg.planned_entry == null && priceReasonText(leg.price_reason)" class="mr-2" data-testid="leg-price-reason">{{ priceReasonText(leg.price_reason) }}</span>
            </template>
            <template v-if="needsReprice(leg)">
              <span data-testid="leg-reprice-prompt">{{ REPRICE_PROMPT }}</span>
              <button type="button" data-testid="reprice-leg" class="ml-1 text-accent underline" @click="emit('edit-leg', i)">Reprice</button>
            </template>
            <span v-if="leg.block" class="mr-2" data-testid="leg-block">{{ leg.block }}</span>
            <ErrorMessage v-if="errorParts && errorIndex === i" :parts="errorParts" compact prefix="price-error" data-testid="price-error" />
          </div>
        </li>
      </ul>

      <div v-if="showsControls(legs)" class="border-t border-line py-2" :style="cardPadding">
        <StrategyControls :controls="shownControls" @edit="(e) => emit('edit', e)" />
      </div>
      <div class="flex min-h-10 items-center justify-between gap-3 border-t border-line py-2" :style="cardPadding" data-testid="money-row">
        <label class="flex items-center gap-2" :title="`Strategy multiplier (${MULTIPLIER_MIN} to ${MULTIPLIER_MAX})`">Multiplier
          <select v-model="multiplier" class="rounded border border-line px-1" data-testid="multiplier" @change="setMultiplier($event.target.selectedIndex)">
            <option v-for="n in MULTIPLIER_CHOICES" :key="n" :value="n">{{ n }}</option>
          </select>
        </label>
        <div class="min-w-0"><slot name="money" /></div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.leg-grid {
  grid-template-columns: var(--leg-cols);
}
/* Review B: the phone layout. Line 1 = tick, B/S, expiry, strike, type, lots; line 2 = the price field and menu under
   the contract, then depth, edit and remove under the type and lots columns. */
@media (max-width: 639px) {
  .leg-grid {
    grid-template-columns: 22px 26px minmax(0, 1fr) auto 34px 44px;
  }
  .leg-phone > .leg-line2-price {
    grid-row: 2;
    grid-column: 1 / 4;
    justify-content: flex-start;
  }
  .leg-phone > .leg-line2 {
    grid-row: 2;
  }
}
</style>
