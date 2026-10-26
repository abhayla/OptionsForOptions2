<!-- Strike Controls of the Strategy Builder (W-158; REQ-078 AC-2, AC-3, AC-6; ADR-186 (2)-(4)). Adapted from this repo's own branch
     build/W-126-a1-leg-rows (StrategyControls.vue): the Shift / Width / Hedge steppers only (the multiplier and Reset Prices live in
     LegList.vue). Sensibull study screens 108-110 and bundle-findings 7.2 (group "Strike Controls"). A stepper is on only when the
     server's `controls` said so, and is disabled with the server's reason otherwise; a click emits only the control and its
     direction. No strike, total or reason is built here (ADR-008; finding browser-infers-a-server-permission). -->
<script setup>
import Tooltip from "@/components/common/Tooltip.vue";
import { shiftText } from "@/lib/legEdit";

defineProps({
  controls: { type: Object, required: true }, // controlsFrom(reply): { shift, width, hedge, shiftTotal, reasons }
});
const emit = defineEmits(["edit"]);

const STEPPERS = [
  { id: "shift", label: "Shift" },
  { id: "width", label: "Width" },
  { id: "hedge", label: "Hedge" },
];
</script>

<template>
  <div data-testid="strategy-controls" role="group" aria-label="Strike Controls">
  <div class="flex flex-wrap items-center gap-y-2 whitespace-nowrap sm:flex-nowrap sm:divide-x sm:divide-line">
    <span class="sr-only">Strike Controls</span>
    <div
      v-for="c in STEPPERS"
      :key="c.id"
      class="flex items-center gap-2 pr-3 sm:px-3 sm:first:pl-0"
      :data-testid="`control-${c.id}`"
    >
      <span class="text-ink-muted"
        >{{ c.label
        }}<span v-if="c.id === 'shift' && controls.shiftTotal" data-testid="shift-total">
          {{ shiftText(controls.shiftTotal) }}</span
        ></span
      >
      <span class="flex gap-1">
        <button
          type="button"
          class="rounded border border-line px-2"
          :disabled="!controls[c.id]"
          :title="controls[c.id] ? '' : controls.reasons[c.id]"
          :aria-label="`${c.label} down`"
          :data-testid="`${c.id}-minus`"
          @click="emit('edit', { control: c.id, direction: -1 })"
        >
          -
        </button>
        <button
          type="button"
          class="rounded border border-line px-2"
          :disabled="!controls[c.id]"
          :title="controls[c.id] ? '' : controls.reasons[c.id]"
          :aria-label="`${c.label} up`"
          :data-testid="`${c.id}-plus`"
          @click="emit('edit', { control: c.id, direction: 1 })"
        >
          +
        </button>
      </span>
      <Tooltip
        v-if="!controls[c.id]"
        :text="controls.reasons[c.id]"
        :label="`Why ${c.label} is off`"
      />
      <span
        v-if="!controls[c.id]"
        class="sr-only"
        :data-testid="`${c.id}-reason`"
        >{{ controls.reasons[c.id] }}</span
      >
    </div>
  </div>
  <p
    v-for="c in STEPPERS.filter((x) => !controls[x.id])"
    :key="c.id"
    class="mt-1 whitespace-normal text-xs text-ink-muted"
    :data-testid="`${c.id}-reason-visible`"
  >
    {{ c.label }}: {{ controls.reasons[c.id] }}
  </p>
  </div>
</template>
