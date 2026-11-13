<!-- GC-ADJ2 step 4 (REQ-161 AC-3, REQ-158 AC-5): the "Plan" entry on a tracked strategy's panel: the accepted plan's playbook name
     and its guards as the server sent them, and an Edit action that reopens the plan sheet (PUT). GC-ICFIX u111-u114 (ADR-295):
     a strategy with no plan says "No plan saved yet: default rules apply", shows the default target and stop (the server's prefill
     for the type's active playbook, with its words) and a "Set plan" button that opens the sheet to accept one (POST); nothing is
     saved by showing this. A read that failed, timed out or cannot be read says so with Retry; while it is out the card says loading.
     A shape with no playbook shows the server's generic text. -->
<template>
  <div v-if="loading || failed || read" class="mt-3 rounded-lg border border-line p-3 text-sm" data-testid="plan-entry-card">
    <p v-if="loading" data-testid="plan-entry-loading">{{ PLAN_LOADING_TEXT }}</p>
    <LoadFailed v-else-if="failed" :text="PLAN_LOAD_FAILED_TEXT" prefix="plan-entry" @retry="reload" />
    <div v-else-if="read" data-testid="plan-entry">
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
        <template v-else>
          <p data-testid="plan-entry-none">{{ read.labels.no_plan }}</p>
          <p v-if="read.prefill.target" data-testid="plan-entry-defaults">
            {{ read.labels.target }}: {{ read.prefill.target }}<template v-if="read.prefill.targetWords"> ({{ read.prefill.targetWords }})</template> / {{ read.labels.stop }}: {{ read.prefill.stop }}<template v-if="read.prefill.stopWords"> ({{ read.prefill.stopWords }})</template>
          </p>
        </template>
        <button type="button" class="mt-2 rounded border border-line bg-surface px-2 py-1 text-xs font-medium" data-testid="plan-entry-edit" @click="sheetOpen = true">
          {{ read.plan ? read.labels.edit : read.labels.set_plan }}
        </button>
      </template>
      <AdjustPlanSheet :open="sheetOpen" :strategy-id="strategyId" :edit="!!read.plan" @close="sheetOpen = false" @saved="(next) => { read = next }" />
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import AdjustPlanSheet from '@/components/strategy/AdjustPlanSheet.vue'
import LoadFailed from '@/components/common/LoadFailed.vue'
import api from '@/services/api'
import { fetchPlan } from '@/lib/adjustPlan'
import { PLAN_LOADING_TEXT, PLAN_LOAD_FAILED_TEXT } from '@/lib/sharedStateText'

const props = defineProps({ strategyId: { type: Number, default: null } })
const read = ref(null)
const loading = ref(false)
const failed = ref(false)
const sheetOpen = ref(false)

async function reload() {
  const id = props.strategyId
  read.value = null
  failed.value = false
  loading.value = false
  if (!Number.isInteger(id)) return
  loading.value = true
  try {
    const next = await fetchPlan(api, id)
    if (id !== props.strategyId) return // another strategy opened meanwhile: drop this
    if (next.kind === 'invalid') failed.value = true // fail closed: nothing is drawn from a reply that cannot be read
    else read.value = next
  } catch {
    if (id === props.strategyId) failed.value = true // network, 5xx or the 30 s limit
  } finally {
    if (id === props.strategyId) loading.value = false
  }
}
watch(() => props.strategyId, reload, { immediate: true })
</script>
