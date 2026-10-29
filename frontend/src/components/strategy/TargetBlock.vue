<!-- GC-TP step 6b (REQ-084 AC-1, AC-2, AC-5, AC-6, AC-7; ADR-208; Sensibull study screen 020, catalogue 57-58, layout only):
     the what-if Target block above the payoff graph. An index-level slider with a number box and Reset, a date slider with
     back / forward steppers and Reset. The block only SENDS the pick (an event); every figure it shows is the reply's own text
     (the `target` block of the outcome reply): the target P&L, the breakevens at the target date, the Greeks or their
     "no time left" sentence, the estimate label, the clamp sentences. R-19a: it sits BELOW the payoff graph (ChartCard's
     `target` slot) and shows the move from spot beside the level and the days to expiry beside the date. No money or level is computed here (ADR-008): the level
     slider's min / max / step are the reply's limits, the date slider's positions come from the page (lib/targetBlock.js).
     The sliders show from the first reply (the plain reply carries the limits, Sensibull 020); Reset on both sends no target. -->
<script setup>
import { computed, ref, watch } from 'vue'
import { istTime } from '@/lib/displayFormat'
import { isWholePoints } from '@/lib/targetBlock'

const props = defineProps({
  target: { type: Object, default: null }, // the reply's `target` block (the limits; the figures once a target was asked)
  pick: { type: Object, required: true }, // { level, dateIndex } the page keeps
  stopCount: { type: Number, default: 0 }, // how many positions the date slider has
  stale: { type: Boolean, default: false }, // the last request failed or was superseded by a push: the figures are the last good answer
})
const emit = defineEmits(['level', 'date', 'reset-level', 'reset-date'])

const GREEKS = ['delta', 'gamma', 'theta', 'vega']
const t = computed(() => props.target)
const limits = computed(() => t.value?.limits ?? null)
const levelValue = computed(() => props.pick.level || t.value?.level || '')
const boxText = ref(levelValue.value)
watch(levelValue, (v) => { boxText.value = v })
const dateRefused = computed(() => t.value?.at_refused_reason ?? null)
const dateOff = computed(() => !!dateRefused.value || props.stopCount < 2)
const lastStop = computed(() => (props.stopCount > 1 ? props.stopCount - 1 : 0))
const clamps = computed(() => [t.value?.level_clamp_text, t.value?.at_clamp_text].filter(Boolean))
const atText = computed(() => (t.value?.at ? istTime(t.value.at) : ''))

const onBox = (e) => {
  boxText.value = e.target.value
  if (isWholePoints(boxText.value)) emit('level', boxText.value.trim())
}
</script>

<template>
  <div class="mt-3 border-t border-line pt-1" data-testid="target-block" :data-stale="stale ? 'true' : 'false'">
    <div class="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
      <h3 class="text-sm font-semibold">Target</h3>
    </div>
    <div class="grid gap-4 px-4 pb-4 md:grid-cols-2">
      <div data-testid="target-level-control">
        <div class="mb-1 flex items-center justify-between text-sm">
          <label for="target-level-slider" class="text-ink-muted">Index level</label>
          <span class="tabular-nums" data-testid="target-level-text">{{ t?.level ?? '' }}</span>
        </div>
        <div class="flex items-center gap-2">
          <input
            id="target-level-slider" type="range" class="w-full" data-testid="target-level-slider"
            :min="limits?.min" :max="limits?.max" :step="limits?.step" :value="levelValue" :disabled="!limits"
            @input="emit('level', $event.target.value)"
          />
          <input
            type="text" inputmode="numeric" class="w-24 rounded border border-line bg-surface px-2 py-0.5 text-right tabular-nums"
            aria-label="Target index level" data-testid="target-level-box" :value="boxText" @input="onBox"
          />
          <button type="button" class="text-sm text-accent" data-testid="target-level-reset" :disabled="!pick.level" @click="emit('reset-level')">Reset</button>
        </div>
        <!-- R-19a (Sensibull 020): the level's move from spot, the reply's text; "-" with the reply's reason when absent -->
        <div class="mt-1 text-xs text-ink-muted tabular-nums" data-testid="target-move">
          <span data-testid="target-move-text">{{ !stale && t?.move_pct_display ? t.move_pct_display : '-' }}</span>
          <span v-if="!t?.move_pct_display && t?.move_pct_reason" class="ml-2" data-testid="target-move-reason">{{ t.move_pct_reason }}</span>
        </div>
      </div>
      <div data-testid="target-date-control">
        <div class="mb-1 flex items-center justify-between text-sm">
          <label for="target-date-slider" class="text-ink-muted">Date</label>
          <span class="tabular-nums" data-testid="target-date-text">{{ atText }}</span>
        </div>
        <div class="flex items-center gap-2">
          <button type="button" class="rounded border border-line px-2" aria-label="Earlier" data-testid="target-date-back" :disabled="dateOff || pick.dateIndex <= 0" @click="emit('date', pick.dateIndex - 1)">&lt;</button>
          <input
            id="target-date-slider" type="range" class="w-full" data-testid="target-date-slider"
            min="0" :max="lastStop" step="1" :value="pick.dateIndex" :disabled="dateOff"
            @input="emit('date', $event.target.valueAsNumber)"
          />
          <button type="button" class="rounded border border-line px-2" aria-label="Later" data-testid="target-date-forward" :disabled="dateOff || pick.dateIndex >= lastStop" @click="emit('date', pick.dateIndex + 1)">&gt;</button>
          <button type="button" class="text-sm text-accent" data-testid="target-date-reset" :disabled="pick.dateIndex <= 0" @click="emit('reset-date')">Reset</button>
        </div>
        <div class="mt-1 text-xs text-ink-muted tabular-nums" data-testid="target-days">{{ !stale && t?.days_to_expiry_display ? t.days_to_expiry_display : '-' }}</div>
        <p v-if="dateRefused" class="mt-1 text-xs text-ink-muted" data-testid="target-date-reason">{{ dateRefused }}</p>
      </div>
      <p v-for="c in clamps" :key="c" class="text-xs text-ink-muted md:col-span-2" data-testid="target-clamp">{{ c }}</p>
      <p v-if="stale && t?.stale_text" class="text-xs text-warn md:col-span-2" data-testid="target-stale">{{ t.stale_text }}</p>
      <div v-if="t?.kind" class="grid gap-3 text-sm md:col-span-2 md:grid-cols-3" :class="stale ? 'opacity-60' : ''" data-testid="target-figures">
        <div>
          <div class="text-ink-muted">P&amp;L at target</div>
          <div class="text-base font-semibold tabular-nums" data-testid="target-pnl">{{ t.pnl?.display ?? '' }}</div>
          <div v-if="t.includes_booked_text" class="text-xs text-ink-muted" data-testid="target-booked">{{ t.includes_booked_text }}</div>
          <div v-else-if="t.booked_unreadable_text" class="text-xs text-warn" data-testid="target-booked-unreadable">{{ t.booked_unreadable_text }}</div>
          <div v-if="t.output_label" class="text-xs text-ink-muted" data-testid="target-label">{{ t.output_label }}</div>
        </div>
        <div>
          <div class="text-ink-muted">Breakeven at target</div>
          <div v-if="t.breakevens_display" class="tabular-nums">
            <span v-for="b in t.breakevens_display" :key="b" class="mr-3" data-testid="target-breakeven">{{ b }}</span>
          </div>
          <div v-else-if="t.breakevens_reason" class="text-xs text-ink-muted" data-testid="target-breakeven-reason">{{ t.breakevens_reason }}</div>
        </div>
        <div v-if="t.greeks">
          <div class="text-ink-muted">Greeks at target</div>
          <div v-if="t.greeks.total" class="flex flex-wrap gap-3 tabular-nums" data-testid="target-greeks-total">
            <span v-for="g in GREEKS" :key="g"><span class="text-ink-muted">{{ g }}</span> {{ t.greeks.total[g] }}</span>
          </div>
          <div v-else-if="t.greeks.unavailable_text" class="text-xs text-ink-muted" data-testid="target-greeks-unavailable">{{ t.greeks.unavailable_text }}</div>
        </div>
      </div>
    </div>
  </div>
</template>
