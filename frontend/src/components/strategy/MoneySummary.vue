<!-- REQ-081 AC-1, AC-2: the net premium line (Get / Pay, per unit) and the Charges action. Display only: every figure is the
     server's own string (summary.net_premium, charges_breakdown); the browser parses, adds and compares no money (ADR-008).
     An absent net premium is '-' with the server's reason, never 0.00 and never a partial sum. Net premium: screen 012. -->
<!-- GC-UI step 3b (D-A04 / D-A21, REQ-152 AC-1, AC-2): the net premium total is the server's whole-rupee `amount_display`
     after Get / Pay (the server's side), the per-unit price keeps paise as sent, and the server's exact sentence
     ("Pay ₹5,707.00") is in the net premium "?" (REQ-152 AC-3). An older reply without `amount_display` shows "-". -->
<script setup>
import { computed } from "vue";
import FigureHint from "@/components/common/FigureHint.vue";
import ChargesBreakdown from "@/components/strategy/ChargesBreakdown.vue";
import { displayOrDash } from "@/lib/summaryFigures";

const SIDE_WORD = { get: "Get", pay: "Pay" };
const props = defineProps({
  netPremium: { type: Object, default: null }, // summary.net_premium: {amount, side, per_unit, text, reason}; null with no legs
  charges: { type: Object, default: null }, // charges_breakdown; null when no rates or a leg cannot be priced
});
const netText = computed(() => {
  const shown = displayOrDash(props.netPremium?.amount_display);
  const side = SIDE_WORD[props.netPremium?.side];
  return shown !== "-" && side ? `${side} ${shown}` : shown;
});
</script>

<template>
  <div
    v-if="netPremium || charges"
    class="mt-4 px-4 text-sm min-w-0 break-words"
    data-testid="money-summary"
  >
    <div
      v-if="netPremium"
      class="flex flex-wrap items-center gap-1"
      data-testid="net-premium"
    >
      <span class="text-gray-500">Net premium: </span>
      <template v-if="netPremium.text">
        <span class="font-medium" data-testid="net-premium-text" :data-raw="netPremium.text">{{
          netText
        }}</span>
        <span
          v-if="netPremium.per_unit"
          class="text-gray-500"
          data-testid="net-premium-per-unit"
          >({{ netPremium.per_unit }} per unit)</span
        >
        <FigureHint id="net_premium" :lines="[netPremium.text]" />
      </template>
      <template v-else>
        <span class="font-medium" data-testid="net-premium-text">-</span>
        <span
          v-if="netPremium.reason"
          class="text-gray-500"
          data-testid="net-premium-reason"
          >({{ netPremium.reason }})</span
        >
      </template>
    </div>
    <ChargesBreakdown v-if="charges" class="mt-1" :breakdown="charges" />
  </div>
</template>
