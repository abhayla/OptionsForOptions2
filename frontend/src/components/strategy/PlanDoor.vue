<!-- ADR-330 (54): the Plan button of a running trade on Positions (beside Exit and Stops, real and paper rows alike). It opens the ONE plan
     sheet, AdjustPlanSheet, the same component the builder's "Edit plan" / "Set plan" opens (one sheet, two doors, one module). Nothing is
     read until the button is pressed; the read says whether the trade already has a plan (Save then edits it, PUT) or not (Save accepts the
     first one, POST). A read that fails or cannot be understood says so and opens nothing (fail closed). The sheet's every word is the server's.
     pending owner read: PLAN_BUTTON_LABEL, PLAN_OPEN_FAILED_TEXT. -->
<template>
  <div class="contents">
    <button type="button" class="rounded border border-line px-2 py-1" :disabled="busy" :data-testid="`plan-open-${tag}-${strategyId}`" @click="open">{{ PLAN_BUTTON_LABEL }}</button>
    <p v-if="failed" class="text-xs text-red-700" role="alert" :data-testid="`plan-open-failed-${tag}-${strategyId}`">{{ PLAN_OPEN_FAILED_TEXT }}</p>
    <AdjustPlanSheet v-if="read" :open="sheetOpen" :strategy-id="strategyId" :edit="!!read.plan" @close="sheetOpen = false" @saved="(next) => { read = next }" />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import AdjustPlanSheet from '@/components/strategy/AdjustPlanSheet.vue'
import api from '@/services/api'
import { fetchPlan } from '@/lib/adjustPlan'
import { PLAN_BUTTON_LABEL, PLAN_OPEN_FAILED_TEXT } from '@/lib/sharedStateText'

const props = defineProps({
  strategyId: { type: Number, required: true },
  tag: { type: String, required: true }, // 'real' | 'paper': only for the test ids; the sheet is the same for both
})
const read = ref(null)
const sheetOpen = ref(false)
const busy = ref(false)
const failed = ref(false)

async function open() {
  if (busy.value) return
  busy.value = true
  failed.value = false
  const id = props.strategyId
  try {
    const next = await fetchPlan(api, id)
    if (next.kind === 'invalid') failed.value = true // fail closed: nothing opens on a reply that cannot be read
    else if (next.kind === 'generic' || next.kind === 'sheet') { read.value = next; sheetOpen.value = true }
    else failed.value = true
  } catch {
    failed.value = true
  } finally {
    busy.value = false
  }
}
</script>
