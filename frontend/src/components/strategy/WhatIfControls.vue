<!-- What-if controls (W-127; REQ-084 AC-1..AC-5, AC-7). Follows Sensibull screen 020 (catalogue "WHAT-IF"): a target level
     slider with a number box, a target date control, each with its own Reset; the IV offset follows the lower panel's
     "Offset" box with a Reset (screen 020, "Strikewise IVs ... Offset ... Reset IVs"; per-leg edits are not built).
     Every figure shown is the server's string; the controls only SEND text (REQ-034 AC-6, ADR-008). -->
<template>
  <section class="rounded border border-line bg-surface p-3" data-testid="whatif-controls">
    <h3 class="text-sm font-medium">What if</h3>
    <p class="text-xs text-ink-muted" data-testid="whatif-label">{{ whatif.estimate_label }}</p>

    <div class="mt-2 grid gap-3 sm:grid-cols-3">
      <label class="text-xs" for="whatif-level">
        {{ underlying }} target
        <input
id="whatif-level" data-testid="whatif-level" type="range" class="w-full" :min="whatif.level_min"
               :max="whatif.level_max" :step="whatif.level_step" :value="whatif.target_level" @change="setLevel($event.target.value)" />
        <input
data-testid="whatif-level-box" type="text" inputmode="numeric" class="w-24 rounded border border-line px-1"
               :value="levelText" @change="setLevel($event.target.value)" />
        <button type="button" data-testid="whatif-level-reset" class="ml-1 underline" @click="reset('targetLevel')">Reset</button>
      </label>

      <label class="text-xs" for="whatif-time">
        Date and time (IST)
        <input
id="whatif-time" data-testid="whatif-time" type="datetime-local" class="w-full rounded border border-line px-1"
               :disabled="!whatif.estimated_available && !!whatif.estimated_reason && noIv"
               :min="toLocalInput(whatif.time_min)" :max="toLocalInput(whatif.time_max)"
               :value="toLocalInput(whatif.target_time)" @change="setTime($event.target.value)" />
        <button type="button" data-testid="whatif-time-reset" class="underline" @click="reset('targetTime')">Reset</button>
      </label>

      <label class="text-xs" for="whatif-iv">
        IV change (volatility points)
        <input
id="whatif-iv" data-testid="whatif-iv" type="text" inputmode="decimal" class="w-20 rounded border border-line px-1"
               :value="modelValue.ivOffset" placeholder="0.0" :aria-invalid="!offsetOk" @change="setOffset($event.target.value)" />
        <button type="button" data-testid="whatif-iv-reset" class="ml-1 underline" @click="reset('ivOffset')">Reset</button>
        <span v-if="!offsetOk" class="block text-danger" data-testid="whatif-iv-format">Use steps of 0.1, for example 2.0 or -1.5.</span>
      </label>
    </div>

    <p v-for="note in whatif.clamp_notes" :key="note" class="mt-1 text-xs" data-testid="whatif-clamp">{{ note }}</p>
    <p v-if="whatif.estimated_reason" class="mt-1 text-xs" data-testid="whatif-reason">{{ whatif.estimated_reason }}</p>

    <dl class="mt-2 grid gap-1 text-sm sm:grid-cols-3" data-testid="whatif-figures">
      <div>
        <dt class="text-xs text-ink-muted">At expiry at {{ whatif.target_level }}</dt>
        <dd data-testid="whatif-expiry-pnl">{{ whatif.target_expiry_pnl }}</dd>
      </div>
      <div v-if="whatif.estimated_available">
        <dt class="text-xs text-ink-muted">Estimated on {{ whatif.target_time }}</dt>
        <dd data-testid="whatif-estimated-pnl">{{ whatif.target_estimated_pnl }}</dd>
      </div>
      <div v-if="whatif.estimated_available">
        <dt class="text-xs text-ink-muted">Breakeven at that date</dt>
        <dd data-testid="whatif-breakevens">{{ whatif.estimated_breakevens.join(', ') || 'none in range' }}</dd>
      </div>
    </dl>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { isLevelText, isOffsetText, fromLocalInput, toLocalInput } from '@/lib/whatifChoice'

const props = defineProps({
  whatif: { type: Object, required: true }, // the outcome reply's `whatif` block, as sent
  modelValue: { type: Object, required: true }, // { targetLevel, targetTime, ivOffset } as typed
  underlying: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue'])

const noIv = computed(() => props.whatif.estimated_points.length === 0)
const offsetOk = computed(() => isOffsetText(props.modelValue.ivOffset))
// the number box shows what the user typed, else the level the server used (a string, as sent)
const levelText = computed(() => props.modelValue.targetLevel || props.whatif.target_level)

const update = (patch) => emit('update:modelValue', { ...props.modelValue, ...patch })
const setLevel = (text) => isLevelText(text) && update({ targetLevel: String(text).trim() })
const setTime = (value) => update({ targetTime: fromLocalInput(value) })
const setOffset = (text) => update({ ivOffset: String(text).trim() })
const reset = (key) => update({ [key]: '' })
</script>
