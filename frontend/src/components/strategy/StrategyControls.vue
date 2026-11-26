<!-- Strike Controls of the Strategy Builder (W-158; REQ-078 AC-2, AC-3, AC-6; ADR-186 (2)-(4)). Adapted from this repo's own branch
     build/W-126-a1-leg-rows (StrategyControls.vue): the Shift / Width / Hedge steppers only (the multiplier and Reset Prices live in
     LegList.vue). Sensibull study screens 108-110 and bundle-findings 7.2 (group "Strike Controls"). A stepper is on only when the
     server's `controls` said so, and is disabled with the server's reason otherwise; a click emits only the control and its
     direction. No strike, total or reason is built here (ADR-008; finding browser-infers-a-server-permission).
     GC-UI 3a D-A17 / D-A19 (ADR-193, ADR-202 (1)): each control is one boxed stepper "[-][ value ][+]"; a control that does not
     apply is greyed, its reason verbatim in the box's tooltip and behind its (i), with no visible reason line. The value box shows
     only what REQ-078 defines today: the Shift total (AC-3); Width and Hedge show their name (their values are D-A18, Later),
     never an invented number. -->
<script setup>
import { computed } from "vue";
import Tooltip from "@/components/common/Tooltip.vue";
import { EXPIRY_LIST_UNREADABLE, NO_OTHER_EXPIRY } from "@/composables/useExpiryChoices";
import { expiryWithDays } from "@/lib/displayFormat";
import { shiftText } from "@/lib/legEdit";

const props = defineProps({
  controls: { type: Object, required: true }, // controlsFrom(reply): { shift, width, hedge, shiftTotal, reasons }
  locked: { type: Boolean, default: false }, // N-35: the page's one blocked rule (ADR-328 (4)); off for every stepper, `lockReason` as the title
  lockReason: { type: String, default: null },
  // D-48 (REQ-078 AC-11): the listed expiries [{ expiry, days }] and the read state ('loading' | 'read' | 'failed'); the one
  // "Change expiry" select puts EVERY leg on the chosen date. `expiryOffReason`: a leg has an Exit waiting.
  expiries: { type: Array, default: () => [] },
  expiryState: { type: String, default: "loading" },
  expiryOffReason: { type: String, default: null },
  legExpiries: { type: Array, default: () => [] }, // the expiry text of each leg: the select is off when no listed expiry differs from them (AC-13)
});
const emit = defineEmits(["edit"]);

const expiryOff = computed(() => {
  if (props.locked) return props.lockReason;
  if (props.expiryOffReason) return props.expiryOffReason;
  if (props.expiryState === "failed") return EXPIRY_LIST_UNREADABLE;
  if (props.expiryState === "read" && !props.expiries.some((e) => props.legExpiries.some((x) => x !== e.expiry))) return NO_OTHER_EXPIRY;
  return props.expiryState === "loading" ? "The expiry list is loading." : null;
});
const pickAll = (event) => {
  const value = event.target.value;
  event.target.value = ""; // the select is only a chooser: the legs show their own expiry
  if (value) emit("edit", { control: "expiry", expiry: value });
};

const STEPPERS = [
  { id: "shift", label: "Shift" },
  { id: "width", label: "Width" },
  { id: "hedge", label: "Hedge" },
];
</script>

<template>
  <div data-testid="strategy-controls" role="group" aria-label="Strike Controls">
    <span class="sr-only">Strike Controls</span>
    <div class="flex flex-wrap items-center gap-2 whitespace-nowrap sm:flex-nowrap">
      <div
        v-for="c in STEPPERS"
        :key="c.id"
        class="flex min-w-0 flex-1 items-center gap-1"
        :data-testid="`control-${c.id}`"
      >
        <span
          class="flex h-8 min-w-0 flex-1 items-stretch overflow-hidden rounded border border-line"
          :class="controls[c.id] ? '' : 'opacity-50'"
          :title="controls[c.id] ? undefined : controls.reasons[c.id]"
          :data-testid="`${c.id}-stepper`"
        >
          <button
            type="button"
            class="h-8 w-8 shrink-0 border-r border-line disabled:cursor-not-allowed"
            :disabled="locked || !controls[c.id]"
            :title="locked ? lockReason : undefined"
            :aria-label="`${c.label} down`"
            :data-testid="`${c.id}-minus`"
            @click="emit('edit', { control: c.id, direction: -1 })"
          >
            -
          </button>
          <span
            class="flex min-w-0 flex-1 items-center justify-center gap-1 px-1"
            :data-testid="`${c.id}-value`"
          >
            <span class="text-ink-muted">{{ c.label }}</span>
            <span
              v-if="c.id === 'shift'"
              class="num"
              data-testid="shift-total"
            >{{ shiftText(controls.shiftTotal) }}</span>
          </span>
          <button
            type="button"
            class="h-8 w-8 shrink-0 border-l border-line disabled:cursor-not-allowed"
            :disabled="locked || !controls[c.id]"
            :title="locked ? lockReason : undefined"
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
        >{{ controls.reasons[c.id] }}</span>
      </div>
      <div class="flex min-w-0 flex-1 items-center gap-1" data-testid="control-expiry">
        <select
          class="h-8 min-w-0 flex-1 rounded border border-line bg-transparent px-1 text-ink-muted disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="expiryOff !== null"
          :title="expiryOff ?? 'Put every leg on this expiry'"
          aria-label="Change expiry of all legs"
          data-testid="expiry-all"
          @change="pickAll"
        >
          <option value="">Change expiry</option>
          <option v-for="e in expiries" :key="e.expiry" :value="e.expiry">{{ expiryWithDays(e.expiry, e.days) }}</option>
        </select>
        <span v-if="expiryOff !== null && !locked" class="sr-only" data-testid="expiry-all-reason">{{ expiryOff }}</span>
      </div>
    </div>
  </div>
</template>
