<!-- GC-ADJ2 step 4 (REQ-161 AC-3, REQ-158 AC-5): the "Plan" entry on a tracked strategy's panel: the accepted plan's playbook name
     and its guards as the server sent them, and an Edit action that reopens the plan sheet (PUT). A strategy with no plan yet
     says so and the same button opens the sheet to accept one (POST). A shape with no playbook shows the server's generic
     text. A read that fails or cannot be read shows nothing: no word is invented here. -->
<template>
  <div v-if="read" class="mt-3 rounded-lg border border-line p-3 text-sm" data-testid="plan-entry">
    <p class="font-semibold" data-testid="plan-entry-title">{{ read.labels.plan_entry }}</p>
    <p v-if="read.kind === 'generic'" data-testid="plan-entry-generic">{{ read.text }}</p>
    <template v-else>
      <template v-if="read.plan">
        <p data-testid="plan-entry-playbook">{{ read.labels.playbook }}: {{ read.plan.playbookName }}</p>
        <p data-testid="plan-entry-guards">
          {{ read.labels.target }}: {{ read.plan.target }}<template v-if="read.plan.targetWords"> ({{ read.plan.targetWords }})</template> / {{ read.labels.stop }}: {{ read.plan.stop }}<template v-if="read.plan.stopWords"> ({{ read.plan.stopWords }})</template> /
          {{ read.labels.max_adjustments }}: {{ read.plan.maxAdjustments }} / {{ read.labels.time_exit }}: {{ read.plan.timeExit }}
        </p>
      </template>
      <p v-else data-testid="plan-entry-none">{{ read.labels.no_plan }}</p>
      <button type="button" class="mt-2 rounded border border-line bg-surface px-2 py-1 text-xs font-medium" data-testid="plan-entry-edit" @click="sheetOpen = true">
        {{ read.plan ? read.labels.edit : read.labels.plan_entry }}
      </button>
    </template>
    <AdjustPlanSheet :open="sheetOpen" :strategy-id="strategyId" :edit="!!read.plan" @close="sheetOpen = false" @saved="(next) => { read = next }" />
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import AdjustPlanSheet from '@/components/strategy/AdjustPlanSheet.vue'
import api from '@/services/api'
import { fetchPlan } from '@/lib/adjustPlan'

const props = defineProps({ strategyId: { type: Number, default: null } })
const read = ref(null)
const sheetOpen = ref(false)

async function reload() {
  const id = props.strategyId
  read.value = null
  if (!Number.isInteger(id)) return
  try {
    const next = await fetchPlan(api, id)
    if (id === props.strategyId && next.kind !== 'invalid') read.value = next // another strategy opened meanwhile: drop this
  } catch {
    if (id === props.strategyId) read.value = null
  }
}
watch(() => props.strategyId, reload, { immediate: true })
</script>
