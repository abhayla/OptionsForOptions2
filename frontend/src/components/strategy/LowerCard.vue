<!-- GC-UI step 4 round b2 (D-B43, D-B45, D-B46; Sensibull sb-03 layout only): the card under the chart. Two columns now:
     Greeks (the reply's TOTAL row Delta, Theta, Decay, Gamma, Vega with the Per unit / Per position toggle, as the
     Greeks tab) and the Standard Deviation table (the reply's `standard_deviation.rows`). Strikewise IVs editing
     (D-B42) and Target Day Futures (D-B44) are Later and leave no placeholder. Every figure is the server's display
     text (ADR-008): no sum, percent or rounding here; text the server left empty prints "—". -->
<script setup>
import { computed, ref } from 'vue'
import Card from '@/components/common/Card.vue'
import FigureHint from '@/components/common/FigureHint.vue'
import { GREEK_COLUMNS, greekModeHeading, greekRows, greekText } from '@/lib/chartCard'

const props = defineProps({
  table: { type: Object, default: null },
  legs: { type: Array, default: null },
  sd: { type: Object, default: null }, // the reply's standard_deviation block
})

const mode = ref('unit') // REQ-084 AC-8: Per unit (default) or Per position
const names = GREEK_COLUMNS.filter((c) => c.id !== 'iv')
const rows = computed(() => greekRows(props.table, props.legs))
const totalRow = computed(() => (rows.value ?? []).find((r) => r.isTotal) ?? null)
const heading = computed(() => greekModeHeading(rows.value, mode.value))
const sdRows = computed(() => (props.sd?.available && Array.isArray(props.sd.rows) ? props.sd.rows : []))
const sdReason = computed(() => {
  if (!props.sd) return 'Standard deviation is not available for this reply.'
  if (!props.sd.available) return props.sd.reason ? `Standard deviation: ${props.sd.reason}` : 'Standard deviation is not available for this reply.'
  return sdRows.value.length ? '' : 'Standard deviation has no rows for this reply.'
})
const show = (v) => (String(v ?? '').trim() || '—')
</script>

<template>
  <Card class="mt-4" data-testid="lower-card">
    <div class="grid gap-6 md:grid-cols-2">
      <section data-column="greeks" data-testid="lower-column">
        <div class="mb-2 flex items-center justify-between gap-3">
          <h3 class="text-sm font-semibold">Greeks <span class="font-normal text-ink-muted" data-testid="lower-greeks-heading">{{ totalRow ? heading : '' }}</span></h3>
          <div role="group" aria-label="Portfolio Greeks units" class="inline-flex overflow-hidden rounded border border-line text-sm">
            <button
              type="button"
              :aria-pressed="mode === 'unit' ? 'true' : 'false'"
              :class="['px-3 py-1', mode === 'unit' ? 'bg-accent-soft font-semibold' : '']"
              data-testid="lower-greeks-mode-unit"
              @click="mode = 'unit'"
            >Per unit</button>
            <button
              type="button"
              :aria-pressed="mode === 'position' ? 'true' : 'false'"
              :class="['px-3 py-1', mode === 'position' ? 'bg-accent-soft font-semibold' : '']"
              data-testid="lower-greeks-mode-position"
              @click="mode = 'position'"
            >Per position</button>
          </div>
        </div>
        <dl v-if="totalRow" class="text-sm">
          <div v-for="c in names" :key="c.id" class="flex items-center justify-between border-b border-line py-1.5">
            <dt data-testid="lower-greek-name">{{ c.label }}<FigureHint v-if="c.id === 'decay'" id="decay" /></dt>
            <dd class="tabular-nums" :data-field="c.id" data-testid="lower-greek-value">{{ greekText(totalRow.values[c.id], c.id, mode) }}</dd>
          </div>
        </dl>
        <p v-else class="text-sm text-ink-muted" data-testid="lower-greeks-empty">Portfolio Greeks are not available for this reply.</p>
      </section>

      <section data-column="sd" data-testid="lower-column">
        <h3 class="mb-2 text-sm font-semibold">Standard Deviation</h3>
        <table v-if="sdRows.length" class="w-full text-sm" data-testid="lower-sd-table">
          <thead>
            <tr class="border-b border-line text-left text-ink-muted">
              <th scope="col" class="py-1.5 font-medium">SD</th>
              <th scope="col" class="py-1.5 text-right font-medium">Move</th>
              <th scope="col" class="py-1.5 text-right font-medium">Lower</th>
              <th scope="col" class="py-1.5 text-right font-medium">Upper</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in sdRows" :key="r.sd ?? r.label" class="border-b border-line" data-testid="lower-sd-row">
              <td class="py-1.5" data-testid="lower-sd-cell">{{ show(r.label) }}</td>
              <td class="py-1.5 text-right tabular-nums" data-testid="lower-sd-cell">{{ show(r.move_display) }}</td>
              <td class="py-1.5 text-right tabular-nums" data-testid="lower-sd-cell">{{ show(r.lower_display) }}</td>
              <td class="py-1.5 text-right tabular-nums" data-testid="lower-sd-cell">{{ show(r.upper_display) }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="text-sm text-ink-muted" data-testid="lower-sd-empty">{{ sdReason }}</p>
      </section>
    </div>
  </Card>
</template>
