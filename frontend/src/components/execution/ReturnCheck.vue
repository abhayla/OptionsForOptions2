<!-- "Check with Zerodha" (W-104; REQ-073 AC-3, ADR-097 (2)). Only the owner's click calls the return route
     (POST /api/strategies/{id}/execution/return); nothing runs on mount. The answer is shown as the server gave it:
     each plan's state word, the mismatch count, whether execution is blocked, and per contract Zerodha's units against
     the platform's. Refusals show the catalogue message. No number is computed here (ADR-008). New file, copy from: none. -->
<script setup>
import { ref } from 'vue'
import api, { NEUTRAL_PARTS } from '@/services/api'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import { istTime } from '@/lib/displayFormat'

const props = defineProps({ strategyId: { type: Number, required: true } })

const busy = ref(false)
const result = ref(null)
const errorParts = ref(null)

async function check() {
  if (busy.value) return
  busy.value = true
  errorParts.value = null
  try {
    result.value = (await api.post(`/strategies/${props.strategyId}/execution/return`)).data
  } catch (e) {
    result.value = null
    errorParts.value = e?.parts ?? NEUTRAL_PARTS
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section class="mt-4" data-testid="return-check">
    <button type="button" data-testid="check-with-zerodha" class="rounded border border-line px-3 py-1" :disabled="busy" @click="check">
      Check with Zerodha
    </button>
    <ErrorMessage v-if="errorParts" class="mt-2" :parts="errorParts" compact prefix="return-error" />
    <div v-if="result" class="mt-2 text-sm" data-testid="return-result">
      <p>Read from Zerodha at <span data-testid="return-read-at">{{ istTime(result.read_at) }}</span>.</p>
      <ul>
        <li v-for="p in result.plans" :key="p.plan_number" data-testid="return-plan" :data-plan="p.plan_number" :data-state="p.state">
          Plan {{ p.plan_number }} ({{ p.action }}): <span data-testid="return-plan-state">{{ p.state }}</span>
        </li>
      </ul>
      <p>Mismatches: <span data-testid="return-mismatches">{{ result.mismatches }}</span></p>
      <p v-if="result.blocked" data-testid="return-blocked">Execution is blocked until the mismatch is resolved.</p>
      <table v-if="result.contracts.length" class="mt-1">
        <thead><tr><th>Contract</th><th>Zerodha units</th><th>This platform's units</th><th>Mismatch</th></tr></thead>
        <tbody>
          <tr v-for="c in result.contracts" :key="c.tradingsymbol" data-testid="return-contract">
            <td>{{ c.tradingsymbol }}</td><td>{{ c.zerodha_units }}</td><td>{{ c.platform_units }}</td><td>{{ c.mismatch ?? 'none' }}</td>
          </tr>
        </tbody>
      </table>
      <p v-if="result.realised_pnl != null">Realised P&amp;L: <span data-testid="return-realised">{{ result.realised_pnl }}</span></p>
    </div>
  </section>
</template>
