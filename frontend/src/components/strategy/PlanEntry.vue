<!-- GC-ADJ2 step 4 (REQ-161 AC-3, REQ-158 AC-5): the "Plan" entry on a tracked strategy's panel: the accepted plan's playbook name
     and its guards as the server sent them, and an Edit action that reopens the plan sheet (PUT). GC-ICFIX u111-u114 (ADR-295, ADR-304 (3)):
     a strategy with no plan says "No plan: nothing is watched for this strategy" and a "Set plan" button that opens the sheet to accept one (POST);
     nothing is saved by showing this. The target and stop lines are the rule check's own `limits` rows (the panel's one read of the check,
     passed in): each row's `text` is the server's sentence and the browser derives nothing from the numbers. A rule that is not being checked
     says so with its reason and no number; a check that failed says could-not-load with Retry; while it is out the card says loading.
     A plan read that failed, timed out or cannot be read says so with Retry too. A shape with no playbook shows the server's generic text. -->
<template>
  <div v-if="loading || failed || read" class="mt-3 rounded-lg border border-line p-3 text-sm" data-testid="plan-entry-card">
    <p v-if="loading" data-testid="plan-entry-loading">{{ PLAN_LOADING_TEXT }}</p>
    <LoadFailed v-else-if="failed" :text="PLAN_LOAD_FAILED_TEXT" prefix="plan-entry" @retry="reload" />
    <div v-else-if="read" data-testid="plan-entry">
      <p class="font-semibold" data-testid="plan-entry-title">{{ read.labels.plan_entry }}</p>
      <p v-if="read.kind === 'generic'" data-testid="plan-entry-generic">{{ read.text }}</p>
      <template v-else>
        <p v-if="read.plan" data-testid="plan-entry-playbook">{{ read.labels.playbook }}: {{ read.plan.playbookName }}</p>
        <p v-else data-testid="plan-entry-none">{{ read.labels.no_plan }}</p>
        <p v-if="checkStatus === 'loading'" data-testid="plan-entry-limits-loading">{{ LIMITS_LOADING_TEXT }}</p>
        <p v-else-if="!limits && checkRefusal" data-testid="plan-entry-limits-refused">{{ checkRefusal }}</p>
        <LoadFailed v-else-if="!limits" :text="LIMITS_LOAD_FAILED_TEXT" prefix="plan-entry-limits" @retry="$emit('retry-check')" />
        <p v-else-if="limits.paused" data-testid="plan-entry-limits-paused">{{ limits.paused }}</p>
        <p v-else-if="!limits.rows.length" data-testid="plan-entry-limits-none">{{ LIMITS_NONE_TEXT }}</p>
        <template v-else>
          <template v-for="row in limits.rows" :key="row.id">
            <p v-if="row.text" :class="row.muted ? 'text-ink-muted' : ''" :data-testid="`plan-entry-limit-${row.id}`">{{ row.text }}</p>
            <LoadFailed v-else :text="LIMITS_LOAD_FAILED_TEXT" :prefix="`plan-entry-limit-${row.id}`" @retry="$emit('retry-check')" />
          </template>
        </template>
        <!-- GC-ICFIX u141: the check's own read time (the server's text; an older server sends none -> nothing shown) -->
        <p v-if="limits && check.as_of_text" class="text-xs text-ink-muted" data-testid="plan-entry-limits-as-of">{{ check.as_of_text }}</p>
        <p v-if="limits && checkStale" class="text-xs text-red-700" data-testid="plan-entry-limits-stale">{{ checkStaleLine(checkRefusal) }}</p>
        <p v-if="read.plan" data-testid="plan-entry-guards">
          {{ read.labels.max_adjustments }}: {{ read.plan.maxAdjustments }} / {{ read.labels.time_exit }}: {{ read.plan.timeExit }}{{ read.plan.timeExitOn ? ` ${read.plan.timeExitOn}` : '' }}
        </p>
        <button type="button" class="mt-2 rounded border border-line bg-surface px-2 py-1 text-xs font-medium" data-testid="plan-entry-edit" @click="sheetOpen = true">
          {{ read.plan ? read.labels.edit : read.labels.set_plan }}
        </button>
      </template>
      <!-- S-11: the sheet back from Customise triggers is reopened by the save bar (SaveDraftBar), which Drafts Mode also draws -->
      <AdjustPlanSheet :open="sheetOpen" :strategy-id="strategyId" :edit="!!read.plan" @close="sheetOpen = false" @saved="(next) => { read = next }" />
    </div>
    <!-- GC-ICLIVE D-24: the armed (or fired) index conditional exits, the server's level text; a failed read says so, never "none set" -->
    <p v-for="x in exits" :key="x.id" class="mt-1" :data-testid="`plan-entry-exit-${x.id}`">{{ exitLineText(x.direction, x.level_text, x.state) }}</p>
    <p v-if="exitsFailed" class="mt-1 text-xs text-red-700" data-testid="plan-entry-exits-failed">{{ EXITS_LOAD_FAILED_TEXT }}</p>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import AdjustPlanSheet from '@/components/strategy/AdjustPlanSheet.vue'
import LoadFailed from '@/components/common/LoadFailed.vue'
import api from '@/services/api'
import { fetchPlan } from '@/lib/adjustPlan'
import { checkStaleLine, EXITS_LOAD_FAILED_TEXT, exitLineText, LIMITS_LOADING_TEXT, LIMITS_LOAD_FAILED_TEXT, LIMITS_NONE_TEXT, PLAN_LOADING_TEXT, PLAN_LOAD_FAILED_TEXT } from '@/lib/sharedStateText'

// the rule check's reply and the state of the panel's one read of it: 'loading' | 'ok' | 'failed'
const props = defineProps({
  strategyId: { type: Number, default: null },
  check: { type: Object, default: null },
  checkStatus: { type: String, default: 'loading' },
  checkRefusal: { type: String, default: '' }, // the server's sentence when the last check read was refused
  checkStale: { type: Boolean, default: false }, // a background re-read failed: the lines are the last good ones
  exits: { type: Array, default: () => [] }, // GC-ICLIVE D-24: the armed / fired index conditional exits (GET /paper/strategies/{id}/triggers)
  exitsFailed: { type: Boolean, default: false }, // the exits read failed: said so, never "none set"
})
defineEmits(['retry-check'])
const read = ref(null)
const loading = ref(false)
const failed = ref(false)
const sheetOpen = ref(false)
const KNOWN_STATES = ['checked', 'not_checked', 'already_true']
// the limit lines as the rule check sent them; null -> could-not-load (a failed read, or a reply that is not the check's shape)
const limits = computed(() => {
  const c = props.check
  if (props.checkStatus !== 'ok' || !c || !Array.isArray(c.limits)) return null
  if (c.paused) return typeof c.paused.text === 'string' && c.paused.text ? { paused: c.paused.text, rows: [] } : null // never an object
  // an empty list means "no rules" only where the server says there is no playbook; any other empty answer is not one we can read
  if (!c.limits.length && c.playbook?.source !== 'none') return null
  const rows = c.limits.map((l) => ({ id: l.rule_id, text: KNOWN_STATES.includes(l.state) && typeof l.text === 'string' ? l.text : null,
    muted: l.state === 'already_true' })) // ADR-296: an already-true line is grey, never red
  return { paused: null, rows }
})

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
    else {
      read.value = next
    }
  } catch {
    if (id === props.strategyId) failed.value = true // network, 5xx or the 30 s limit
  } finally {
    if (id === props.strategyId) loading.value = false
  }
}
watch(() => props.strategyId, reload, { immediate: true })
</script>
