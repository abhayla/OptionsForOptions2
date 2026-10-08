<!-- Copied/adapted from abhayla/algochanakya@bf9faf7:frontend/src/components/strategy/PnLCell.vue (ADR-047).
     Changed: the cell TEXT is the API's `display` string as given (the legacy "1.2K" / toLocaleString formatting is
     removed); the value, max profit and max loss props are the API's strings and are parsed for the colour intensity
     ONLY. On the no-client-maths scan's allowlist by name for that reason (tests/strategy-table.test.js). -->
<template>
  <td :class="['px-2 py-2 text-right text-xs font-medium transition-all', cellClass]">
    {{ display }}
  </td>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  display: { type: String, default: '' }, // the text to show, exactly as the API sent it
  value: { type: String, default: null }, // the API's value string, used for the colour only
  maxProfit: { type: String, default: null },
  maxLoss: { type: String, default: null },
  isTotal: { type: Boolean, default: false },
})

const cellClass = computed(() => {
  if (props.value === null || props.value === undefined || props.value === '') return 'bg-gray-50 text-gray-500'
  const v = Number(props.value)
  if (Number.isNaN(v)) return 'bg-gray-50 text-gray-500'

  if (v > 0) {
    const i = Math.min(v / (Number(props.maxProfit) || 1), 1)
    if (props.isTotal) return i > 0.5 ? 'bg-green-600 text-white font-bold' : 'bg-green-400 text-white font-semibold'
    if (i > 0.6) return 'bg-green-400 text-green-950'
    if (i > 0.3) return 'bg-green-200 text-green-800'
    return 'bg-green-100 text-green-700'
  } else if (v < 0) {
    const i = Math.min(Math.abs(v) / (Math.abs(Number(props.maxLoss)) || 1), 1)
    if (props.isTotal) return i > 0.5 ? 'bg-red-600 text-white font-bold' : 'bg-red-400 text-white font-semibold'
    if (i > 0.6) return 'bg-red-400 text-red-950'
    if (i > 0.3) return 'bg-red-200 text-red-800'
    return 'bg-red-100 text-red-700'
  }
  return 'bg-gray-50 text-gray-600'
})
</script>
