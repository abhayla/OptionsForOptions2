<!-- GC-ADJ2 step 4 (REQ-161 AC-1..AC-4, REQ-158 AC-5; mockup screen 4 "When tracking starts: this strategy's plan"): the plan
     sheet. It opens after the paper orders are placed (or from the tracking panel's Plan entry, `edit`), pre-filled from the
     server: the strategy plan if it has one, else the type's active playbook. "Use playbook as is" accepts in one click;
     picking another playbook refills every field from the server's prefill for it; Save sends the fields as typed and the
     server names the one that is not valid. A shape with no playbook shows the server's generic text and Close only.
     Every word is the server's; the browser computes nothing. -->
<template>
  <Modal :open="open" :title="labels.title || ' '" @close="emit('close')">
    <div data-testid="plan-sheet">
      <p v-if="loadError" class="text-sm text-red-700" data-testid="plan-sheet-error">{{ loadError }}</p>
      <template v-else-if="sheet && sheet.kind === 'generic'">
        <p class="text-sm" data-testid="plan-sheet-generic">{{ sheet.text }}</p>
      </template>
      <template v-else-if="sheet && sheet.kind === 'sheet'">
        <p class="text-sm text-ink-muted" data-testid="plan-sheet-type">{{ sheet.typeName }}</p>
        <label class="mt-3 block text-sm font-medium">{{ labels.playbook }}
          <select class="mt-1 h-10 w-full rounded border border-line px-2" data-testid="plan-playbook" :value="form.playbookId" :disabled="busy" @change="pick($event.target.value)">
            <option v-for="p in sheet.playbooks" :key="p.id" :value="p.id">{{ p.name }}</option>
          </select>
        </label>
        <div class="mt-3 grid grid-cols-2 gap-3">
          <label class="block text-sm font-medium">{{ labels.target }}
            <input v-model="form.target" class="mt-1 h-10 w-full rounded border border-line px-2" inputmode="decimal" data-testid="plan-target" />
          </label>
          <label class="block text-sm font-medium">{{ labels.stop }}
            <input v-model="form.stop" class="mt-1 h-10 w-full rounded border border-line px-2" inputmode="decimal" data-testid="plan-stop" />
          </label>
          <label class="block text-sm font-medium">{{ labels.max_adjustments }}
            <input v-model="form.maxAdjustments" class="mt-1 h-10 w-full rounded border border-line px-2" inputmode="numeric" data-testid="plan-max" />
          </label>
          <label class="block text-sm font-medium">{{ labels.time_exit }}
            <input v-model="form.timeExit" type="time" class="mt-1 h-10 w-full rounded border border-line px-2" data-testid="plan-time" />
          </label>
        </div>
        <button type="button" class="mt-3 text-sm font-semibold text-accent underline" data-testid="plan-customise" :disabled="busy" @click="customise">{{ labels.customise }}</button>
      </template>
      <ErrorMessage v-if="errorParts" class="mt-3" :parts="errorParts" compact prefix="plan-error" data-testid="plan-error" />
    </div>
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
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import api, { NEUTRAL_PARTS } from '@/services/api'
import { asIsBody, customiseUrl, fetchPlan, formOf, saveBody, sendPlan } from '@/lib/adjustPlan'

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
const errorParts = ref(null)
const labels = computed(() => sheet.value?.labels ?? {})

async function load(pickId = null) {
  const id = props.strategyId
  loadError.value = ''
  errorParts.value = null
  try {
    const read = await fetchPlan(api, id, pickId)
    if (id !== props.strategyId) return // another strategy was opened while this read was out
    if (read.kind === 'invalid') {
      sheet.value = null
      loadError.value = NEUTRAL_PARTS.what_happened
      return
    }
    sheet.value = read
    if (read.kind === 'sheet') form.value = { ...read.prefill }
  } catch (e) {
    if (id !== props.strategyId) return
    sheet.value = null
    loadError.value = (e?.parts ?? NEUTRAL_PARTS).what_happened || NEUTRAL_PARTS.what_happened
  }
}
function pick(value) {
  const chosen = sheet.value?.playbooks.find((p) => String(p.id) === value)
  if (chosen) load(chosen.id) // every field refills from the server's prefill for that playbook (REQ-161 AC-2)
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
  const url = customiseUrl(form.value.playbookId)
  emit('close')
  router?.push(url)
}

watch(() => [props.open, props.strategyId], ([isOpen, id]) => {
  if (isOpen && Number.isInteger(id)) load()
}, { immediate: true })
</script>
