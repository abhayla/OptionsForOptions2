<!-- GC-ADJ2 step 4 (REQ-161 AC-1..AC-4, REQ-158 AC-5; mockup screen 4 "When tracking starts: this strategy's plan"): the plan
     sheet. It opens after the paper orders are placed (or from the tracking panel's Plan entry, `edit`), pre-filled from the
     server: the strategy plan if it has one, else the type's active playbook. "Use playbook as is" accepts in one click;
     picking another playbook refills every field from the server's prefill for it; Save sends the fields as typed and the
     server names the one that is not valid. A shape with no playbook shows the server's generic text and Close only.
     Every word is the server's; the browser computes nothing. -->
<template>
  <Modal :open="open" :title="labels.title || ' '" @close="emit('close')">
    <div data-testid="plan-sheet">
      <LoadFailed v-if="loadError && !sheet" :text="loadError" prefix="plan-sheet" @retry="load()" />
      <p v-else-if="loading && !sheet" class="text-sm text-ink-muted" data-testid="plan-sheet-loading">{{ PLAN_LOADING_TEXT }}</p>
      <template v-else-if="sheet && sheet.kind === 'generic'">
        <p class="text-sm" data-testid="plan-sheet-generic">{{ sheet.text }}</p>
      </template>
      <template v-else-if="sheet && sheet.kind === 'sheet'">
        <p v-if="loadError" class="text-sm" role="alert" data-testid="plan-sheet-pick-error">{{ loadError }}</p>
        <p class="text-sm text-ink-muted" data-testid="plan-sheet-type">{{ sheet.typeName }}</p>
        <label class="mt-3 block text-sm font-medium">{{ labels.playbook }}
          <select class="mt-1 h-10 w-full rounded border border-line px-2" data-testid="plan-playbook" :value="form.playbookId" :disabled="busy" @change="pick($event.target.value)">
            <option v-for="p in sheet.playbooks" :key="p.id" :value="p.id">{{ p.name }}</option>
          </select>
        </label>
        <p v-if="refilledFrom" class="mt-1 text-xs text-ink-muted" data-testid="plan-refilled">{{ PLAN_REFILLED_TEXT(refilledFrom) }}</p>
        <div class="mt-3 grid grid-cols-2 gap-3">
          <label class="block text-sm font-medium">{{ labels.target }}
            <input v-model="form.target" class="mt-1 h-10 w-full rounded border border-line px-2" inputmode="decimal" data-testid="plan-target" @input="typed('target')" />
            <span v-if="form.targetWords" class="mt-1 block text-xs font-normal text-ink-muted" data-testid="plan-target-words">{{ form.targetWords }}</span>
          </label>
          <label class="block text-sm font-medium">{{ labels.target_rupees }}
            <input v-model="form.targetRupees" class="mt-1 h-10 w-full rounded border border-line px-2" inputmode="decimal" data-testid="plan-target-rupees" @input="typed('target_rupees')" />
            <span v-if="form.targetRupeeWords" class="mt-1 block text-xs font-normal text-ink-muted" data-testid="plan-target-rupee-words">{{ form.targetRupeeWords }}</span>
          </label>
          <label class="block text-sm font-medium">{{ labels.stop }}
            <input v-model="form.stop" class="mt-1 h-10 w-full rounded border border-line px-2" inputmode="decimal" data-testid="plan-stop" @input="typed('stop')" />
            <span v-if="form.stopWords" class="mt-1 block text-xs font-normal text-ink-muted" data-testid="plan-stop-words">{{ form.stopWords }}</span>
          </label>
          <label class="block text-sm font-medium">{{ labels.stop_rupees }}
            <input v-model="form.stopRupees" class="mt-1 h-10 w-full rounded border border-line px-2" inputmode="decimal" data-testid="plan-stop-rupees" @input="typed('stop_rupees')" />
            <span v-if="form.stopRupeeWords" class="mt-1 block text-xs font-normal text-ink-muted" data-testid="plan-stop-rupee-words">{{ form.stopRupeeWords }}</span>
            <span v-if="form.stopWarning" class="mt-1 block text-xs font-normal text-ink-muted" data-testid="plan-stop-warning">{{ form.stopWarning }}</span>
          </label>
          <label class="block text-sm font-medium">{{ labels.max_adjustments }}
            <input v-model="form.maxAdjustments" class="mt-1 h-10 w-full rounded border border-line px-2" inputmode="numeric" data-testid="plan-max" />
          </label>
          <label class="block text-sm font-medium">{{ labels.time_exit }}
            <input v-model="form.timeExit" type="time" class="mt-1 h-10 w-full rounded border border-line px-2" data-testid="plan-time" />
          </label>
          <label class="block text-sm font-medium">{{ labels.time_exit_on }}
            <input v-model="form.timeExitOn" type="date" class="mt-1 h-10 w-full rounded border border-line px-2" data-testid="plan-time-on" />
          </label>
        </div>
        <button type="button" class="mt-3 text-sm font-semibold text-accent underline" data-testid="plan-customise" :disabled="busy" @click="customise">{{ labels.customise }}</button>
      </template>
      <AlertStylePicker v-if="open && sheet" :strategy-id="strategyId" />
    </div>
    <template v-if="errorParts" #status>
      <ErrorMessage :parts="errorParts" compact prefix="plan-error" data-testid="plan-error" />
    </template>
    <template #actions>
      <button type="button" class="h-10 rounded-lg border border-line px-3 font-medium" data-testid="plan-close" @click="emit('close')">{{ labels.close }}</button>
      <template v-if="sheet && sheet.kind === 'sheet'">
        <button type="button" class="h-10 rounded-lg border border-line px-3 font-medium disabled:opacity-50" data-testid="plan-save" :disabled="busy" @click="save">{{ labels.save }}</button>
        <button type="button" class="h-10 rounded-lg bg-accent px-3 font-medium text-white disabled:opacity-50" data-testid="plan-use-as-is" :disabled="busy" @click="useAsIs">{{ labels.use_as_is }}</button>
      </template>
    </template>
  </Modal>
</template>

<script setup>
import { computed, inject, ref, watch } from 'vue'
import { routerKey } from 'vue-router'
import Modal from '@/components/common/Modal.vue'
import LoadFailed from '@/components/common/LoadFailed.vue'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import AlertStylePicker from '@/components/strategy/AlertStylePicker.vue'
import api, { NEUTRAL_PARTS } from '@/services/api'
import { PLAN_LOADING_TEXT, PLAN_LOAD_FAILED_TEXT, PLAN_PICK_TIMED_OUT_TEXT, PLAN_REFILLED_TEXT, PLAN_TIMED_OUT_TEXT } from '@/lib/sharedStateText'
import { asIsBody, customiseUrl, fetchLevels, fetchPlan, formOf, saveBody, sendPlan } from '@/lib/adjustPlan'

const props = defineProps({
  open: { type: Boolean, default: false },
  strategyId: { type: Number, default: null },
  // true: the strategy already has a plan and Save edits it (PUT); false: the first plan is accepted (POST)
  edit: { type: Boolean, default: false },
})
const emit = defineEmits(['close', 'saved'])
const router = inject(routerKey, null)

const sheet = ref(null)
const form = ref(formOf(null))
const busy = ref(false)
const loadError = ref('')
const loading = ref(false)
const errorParts = ref(null)
const labels = computed(() => sheet.value?.labels ?? {})
const refilledFrom = ref('') // the playbook name the fields were just refilled from; empty on open, reopen and failed reads

async function load(pickId = null, pickName = '') {
  const id = props.strategyId
  loadError.value = ''
  refilledFrom.value = ''
  errorParts.value = null
  loading.value = true
  try {
    const read = await fetchPlan(api, id, pickId)
    if (id !== props.strategyId) return // another strategy was opened while this read was out
    if (read.kind === 'invalid') {
      sheet.value = null
      loadError.value = PLAN_LOAD_FAILED_TEXT
      return
    }
    sheet.value = read
    if (read.kind === 'sheet') {
      form.value = { ...read.prefill }
      if (pickId !== null) refilledFrom.value = pickName
    }
  } catch (e) {
    if (id !== props.strategyId) return
    const timedOut = e?.code === 'ECONNABORTED'
    if (pickId !== null && sheet.value?.kind === 'sheet') { // D-38: a pick that failed leaves the sheet and what was typed as they are
      loadError.value = timedOut ? PLAN_PICK_TIMED_OUT_TEXT : PLAN_LOAD_FAILED_TEXT
      return
    }
    sheet.value = null
    loadError.value = timedOut ? PLAN_TIMED_OUT_TEXT : PLAN_LOAD_FAILED_TEXT
  } finally {
    if (id === props.strategyId) loading.value = false
  }
}
const levelsRun = { target: 0, stop: 0 } // per level, only the newest reply is applied (a slow earlier one never overwrites a later one)
/** ADR-330 (5) / S-12: typing in one box of a percent / rupee pair asks the server for both figures and the hint words;
 *  the other box and the hints are filled from the reply (the browser computes nothing). The typed box is the one saved. */
async function typed(field) {
  const isTarget = field.startsWith('target')
  const rupees = field.endsWith('_rupees')
  const f = form.value
  if (isTarget) f.targetLast = rupees ? 'rupees' : 'percent'
  else f.stopLast = rupees ? 'rupees' : 'percent'
  const own = isTarget ? (rupees ? f.targetRupees : f.target) : (rupees ? f.stopRupees : f.stop)
  const other = isTarget ? (rupees ? 'target' : 'targetRupees') : (rupees ? 'stop' : 'stopRupees')
  const words = isTarget ? ['targetWords', 'targetRupeeWords'] : ['stopWords', 'stopRupeeWords', 'stopWarning']
  const level = isTarget ? 'target' : 'stop'
  const run = ++levelsRun[level]
  if (own.trim() === '') { f[other] = ''; words.forEach((k) => { f[k] = '' }); return } // nothing typed: nothing to show
  try {
    const got = (await fetchLevels(api, props.strategyId, { [field]: own }, f.playbookId))[level]
    if (run !== levelsRun[level] || form.value !== f) return
    if (!got) return
    f[other] = rupees ? got.percent : got.rupees
    f[words[0]] = got.words
    f[words[1]] = got.rupeeWords
    if (!isTarget) f.stopWarning = got.warning
  } catch (e) {
    if (run !== levelsRun[level]) return
    f[other] = '' // a level the server will not read shows no figure (fail closed); Save names the field
    words.forEach((k) => { f[k] = '' })
  }
}
function pick(value) {
  const chosen = sheet.value?.playbooks.find((p) => String(p.id) === value)
  if (chosen) load(chosen.id, chosen.name) // every field refills from the server's prefill for that playbook (REQ-161 AC-2)
}
async function send(body) {
  if (busy.value) return
  busy.value = true
  errorParts.value = null
  try {
    const read = await sendPlan(api, props.strategyId, body, props.edit)
    if (read.kind === 'invalid') {
      errorParts.value = NEUTRAL_PARTS
      return
    }
    emit('saved', read)
    emit('close')
  } catch (e) {
    errorParts.value = e?.parts ?? NEUTRAL_PARTS // nothing is recorded locally on any refusal
  } finally {
    busy.value = false
  }
}
const useAsIs = () => send(asIsBody(form.value.playbookId))
const save = () => send(saveBody(form.value))
function customise() {
  const url = customiseUrl(props.strategyId)
  emit('close')
  router?.push(url)
}

watch(() => [props.open, props.strategyId], ([isOpen, id]) => {
  if (isOpen && Number.isInteger(id)) load()
}, { immediate: true })
</script>
