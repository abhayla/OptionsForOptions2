<!-- GC-ADJ2 step 6 (REQ-163 AC-1..AC-3; F-74; ADR-214): a strategy's adjustment history and whole-trade totals.
     Columns and tiles after the GC-ADJ2 mockup's history screen (When, Step, Orders, Cash, Booked, Why, and the
     fill-state column whose header the server sends).
     Every figure and sentence is the server's text (ADR-008: the browser computes nothing); read only when the user
     opens the section, so the tracking panel's own reads are unchanged. Phone width: the table scrolls in its own box. -->
<template>
  <details class="mt-3 rounded border border-line" data-testid="adjust-steps" @toggle="onToggle">
    <summary class="cursor-pointer px-3 py-2 text-sm font-semibold">Adjustment history</summary>
    <div class="px-3 pb-3">
      <p v-if="error" class="text-sm text-red-700" data-testid="steps-error">{{ error }}</p>
      <p v-if="loading" class="text-sm text-ink-muted" data-testid="steps-loading">{{ LOADING_TEXT }}</p>
      <p v-else-if="data && data.rows.length === 0" class="text-sm text-ink-muted" data-testid="steps-none">{{ NONE_TEXT }}</p>
      <template v-if="data">
        <dl class="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4" data-testid="steps-totals">
          <div v-for="tile in tiles" :key="tile.id" :data-testid="`steps-total-${tile.id}`">
            <dt class="text-ink-muted">{{ tile.label }}</dt>
            <dd class="font-semibold tabular-nums"><AfterChargesTap :breakdown="tile.breakdown ?? null">{{ tile.value }}</AfterChargesTap></dd>
            <dd v-if="tile.reason" class="text-xs text-ink-muted" :data-testid="`steps-reason-${tile.id}`">{{ tile.reason }}</dd>
          </div>
        </dl>
        <div class="mt-3 overflow-x-auto" data-testid="steps-scroll">
          <table class="min-w-[44rem] w-full text-sm">
            <thead>
              <tr class="border-b border-line text-ink-muted">
                <th v-for="c in [...COLUMNS, data.fill_column_text]" :key="c" scope="col" class="py-1.5 pr-3 text-left font-medium">{{ c }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(r, i) in data.rows" :key="i" class="border-b border-line align-top" data-testid="steps-row">
                <td class="py-1.5 pr-3 tabular-nums">{{ istTime(r.at) }}</td>
                <td class="py-1.5 pr-3 font-semibold">
                  <span data-testid="steps-step">{{ stepText(r) }}</span>
                  <span v-if="r.approach_text" class="block text-xs font-normal" data-testid="steps-approach">{{ r.approach_text }}</span>
                </td>
                <td class="py-1.5 pr-3">
                  <span v-for="(o, j) in r.orders" :key="j" class="block" data-testid="steps-order">
                    {{ o.side === 'BUY' ? 'B' : 'S' }} {{ o.contract_text }} x {{ o.quantity }} @ {{ o.price_text }}
                  </span>
                </td>
                <td class="py-1.5 pr-3 text-right tabular-nums" data-testid="steps-cash">{{ r.cash_text }}</td>
                <td class="py-1.5 pr-3 text-right tabular-nums" data-testid="steps-booked">{{ r.booked_pending ?? r.booked_text }}</td>
                <td class="py-1.5 pr-3" data-testid="steps-why">
                  {{ r.why_text }}
                  <span v-for="(w, j) in r.why_lines ?? []" :key="j" class="block text-xs" data-testid="steps-why-line">{{ w }}</span>
                </td>
                <td class="py-1.5 pr-3" data-testid="steps-fill">{{ r.fill_text }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </div>
  </details>
</template>

<script setup>
import { computed, ref } from 'vue'
import api, { NEUTRAL_PARTS } from '@/services/api'
import { istTime } from '@/lib/displayFormat'
import { serverSentence } from '@/lib/serverText'
import { BEFORE_CHARGES, afterFigure } from '@/lib/tracking'
import AfterChargesTap from '@/components/common/AfterChargesTap.vue'

const props = defineProps({ strategyId: { type: Number, required: true } })
const COLUMNS = ['When', 'Step', 'Orders', 'Cash', 'Booked', 'Why'] // the fill-state header is the server's text
const STEP_WORDS = { entry: 'Entry', settle: 'Settled at expiry', stop: 'Stop' }
const DASH = '-'
// D-27: the section is never an empty block - it says it is reading, or that no step is recorded
const LOADING_TEXT = 'Reading the adjustment history...'
const NONE_TEXT = 'No entry or adjustment is recorded for this strategy yet.'

const data = ref(null)
const error = ref('')
const loading = ref(false)

const stepText = (r) => (r.is_exit === true ? 'Exit' : r.step === 'adjustment' ? `Adjustment ${r.number}` : STEP_WORDS[r.step])

const tiles = computed(() => {
  const t = data.value?.totals
  if (!t) return []
  const reasonOf = (v) => serverSentence(v) ?? null // a string, null or the error object (lib/serverText)
  const pnl = afterFigure(t, t.pnl_text ?? null, reasonOf(t.open_reason_text)) // GC-ICFIX (ADR-263): the whole-trade P&L after charges, labelled
  return [
    { id: 'pnl', label: `Whole-trade P&L ${pnl.label}`.trim(), value: pnl.text ?? DASH, reason: pnl.reason, breakdown: pnl.breakdown },
    { id: 'booked', label: `Booked so far ${BEFORE_CHARGES}`, value: t.booked_text },
    { id: 'open', label: `Open legs now ${BEFORE_CHARGES}`, value: t.open_pnl_text ?? DASH, reason: t.open_pnl_text ? null : reasonOf(t.open_reason_text) },
    { id: 'credit', label: 'Total credit collected', value: t.credit_text },
    { id: 'left', label: 'Premium still left to earn', value: t.premium_left_text ?? DASH, reason: t.premium_left_text ? null : reasonOf(t.premium_reason_text) },
    { id: 'used', label: 'Adjustments used', value: `${t.adjustments_used} of ${t.adjustments_max ?? DASH}`, reason: reasonOf(t.max_reason_text) },
    { id: 'charges', label: 'Charges paid', value: t.charges_text ?? DASH, reason: t.charges_text ? null : reasonOf(t.charges_reason_text) },
  ]
})

// every opening reads again (an adjustment made since the last opening must show); a read still pending is not started twice
async function onToggle(e) {
  if (!e.target.open || loading.value) return
  loading.value = true
  try {
    data.value = (await api.get(`/strategies/${props.strategyId}/adjustment-history`)).data
    error.value = ''
  } catch (err) {
    error.value = (err?.parts ?? NEUTRAL_PARTS).what_happened
  } finally {
    loading.value = false
  }
}
</script>
