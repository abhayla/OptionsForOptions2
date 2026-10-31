<!-- GC-ADJ2 step 6 (REQ-163 AC-1..AC-3; F-74; ADR-214): a strategy's adjustment history and whole-trade totals.
     Columns and tiles after the GC-ADJ2 mockup's history screen (When, Step, Orders, Cash, Booked, Why, Zerodha).
     Every figure and sentence is the server's text (ADR-008: the browser computes nothing); read only when the user
     opens the section, so the tracking panel's own reads are unchanged. Phone width: the table scrolls in its own box. -->
<template>
  <details class="mt-3 rounded border border-line" data-testid="adjust-history" @toggle="onToggle">
    <summary class="cursor-pointer px-3 py-2 text-sm font-semibold">Adjustment history</summary>
    <div class="px-3 pb-3">
      <p v-if="error" class="text-sm text-red-700" data-testid="history-error">{{ error }}</p>
      <template v-if="data">
        <dl class="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4" data-testid="history-totals">
          <div v-for="tile in tiles" :key="tile.id" :data-testid="`history-total-${tile.id}`">
            <dt class="text-ink-muted">{{ tile.label }}</dt>
            <dd class="font-semibold tabular-nums">{{ tile.value }}</dd>
            <dd v-if="tile.reason" class="text-xs text-ink-muted" :data-testid="`history-reason-${tile.id}`">{{ tile.reason }}</dd>
          </div>
        </dl>
        <div class="mt-3 overflow-x-auto" data-testid="history-scroll">
          <table class="min-w-[44rem] w-full text-sm">
            <thead>
              <tr class="border-b border-line text-ink-muted">
                <th v-for="c in COLUMNS" :key="c" scope="col" class="py-1.5 pr-3 text-left font-medium">{{ c }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(r, i) in data.rows" :key="i" class="border-b border-line align-top" data-testid="history-row">
                <td class="py-1.5 pr-3 tabular-nums">{{ istTime(r.at) }}</td>
                <td class="py-1.5 pr-3 font-semibold" data-testid="history-step">{{ stepText(r) }}</td>
                <td class="py-1.5 pr-3">
                  <span v-for="(o, j) in r.orders" :key="j" class="block" data-testid="history-order">
                    {{ o.side === 'BUY' ? 'B' : 'S' }} {{ o.contract_text }} x {{ o.quantity }} @ {{ o.price_text }}
                  </span>
                </td>
                <td class="py-1.5 pr-3 text-right tabular-nums" data-testid="history-cash">{{ r.cash_text }}</td>
                <td class="py-1.5 pr-3 text-right tabular-nums" data-testid="history-booked">{{ r.booked_pending ?? r.booked_text }}</td>
                <td class="py-1.5 pr-3" data-testid="history-why">{{ r.why_text ?? r.rule_id }}</td>
                <td class="py-1.5 pr-3" data-testid="history-fill">{{ r.fill_text ?? FILL_WORDS[r.fill] }}</td>
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
import api, { NEUTRAL_ERROR } from '@/services/api'
import { istTime } from '@/lib/displayFormat'

const props = defineProps({ strategyId: { type: Number, required: true } })
const COLUMNS = ['When', 'Step', 'Orders', 'Cash', 'Booked', 'Why', 'Zerodha']
const STEP_WORDS = { entry: 'Entry', settle: 'Settled at expiry', stop: 'Stop' }
// REQ-112 AC-3 fill states of a real strategy (a paper row carries the server's own words instead)
const FILL_WORDS = { confirmed: 'Confirmed by Zerodha', unconfirmed: 'Not confirmed by Zerodha', failed: 'Answer failed' }
const DASH = '-'

const data = ref(null)
const error = ref('')
let loaded = false

const stepText = (r) => (r.step === 'adjustment' ? `Adjustment ${r.number}` : STEP_WORDS[r.step])

const tiles = computed(() => {
  const t = data.value?.totals
  if (!t) return []
  const priceReason = t.prices_reason_text?.what_happened ?? t.prices_reason_text
  const reasonOf = (v) => (v && typeof v === 'object' ? v.what_happened : v)
  return [
    { id: 'pnl', label: 'Whole-trade P&L', value: t.pnl_text ?? DASH, reason: t.pnl_text ? null : reasonOf(priceReason) },
    { id: 'booked', label: 'Booked so far', value: t.booked_text },
    { id: 'open', label: 'Open legs now', value: t.open_pnl_text ?? DASH, reason: t.open_pnl_text ? null : reasonOf(priceReason) },
    { id: 'credit', label: 'Total credit collected', value: t.credit_text },
    { id: 'left', label: 'Premium still left to earn', value: t.premium_left_text ?? DASH, reason: t.premium_left_text ? null : reasonOf(priceReason) },
    { id: 'used', label: 'Adjustments used', value: `${t.adjustments_used} of ${t.adjustments_max ?? DASH}`, reason: reasonOf(t.max_reason_text) },
    { id: 'charges', label: 'Charges paid', value: t.charges_text ?? DASH, reason: t.charges_text ? null : reasonOf(t.charges_reason_text) },
  ]
})

async function onToggle(e) {
  if (!e.target.open || loaded) return
  loaded = true
  try {
    data.value = (await api.get(`/strategies/${props.strategyId}/adjustment-history`)).data
  } catch (err) {
    loaded = false
    error.value = err?.parts?.what_happened ?? NEUTRAL_ERROR
  }
}
</script>
