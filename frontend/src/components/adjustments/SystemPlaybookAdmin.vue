<!-- GC-SET step 9 (REQ-169 AC-1..AC-3, ADR-222 (10)): the admin's controls for a SYSTEM playbook, beside the same
     step-by-step editor a user sees (AdjustmentsPage owns the editor and the Test step; this adds no second editor).
     Rendered only for the admin (stores/viewer). Save posts the working body with a required reason as a new version;
     "Restore this version" and "Approve" post a reason too. The reason is typed here and sent; the server does not echo
     it back, so the list shows who and when. Every refusal is the server's sentence, shown as it is. -->
<template>
  <section v-if="viewer.isAdmin" class="mt-3 rounded-lg border border-line bg-surface p-3 text-sm" data-testid="sys-admin">
    <div class="flex flex-wrap items-end gap-2">
      <button v-if="!editing" type="button" class="btn" data-testid="sys-edit" @click="editing = true">Edit system playbook</button>
      <label class="flex flex-col gap-1 text-xs font-medium text-ink-muted">Reason for this change (required)
        <input v-model="reason" class="field w-96" maxlength="300" data-testid="sys-reason">
      </label>
      <template v-if="editing">
        <button type="button" class="btn btn-primary" data-testid="sys-save" :disabled="busy" @click="save">Save as a new version</button>
        <button type="button" class="btn" data-testid="sys-cancel" @click="editing = false">Done editing</button>
      </template>
      <button v-if="isDraft" type="button" class="btn" data-testid="sys-approve" :disabled="busy" @click="approve">Approve</button>
      <span v-if="top" class="text-ink-muted" data-testid="sys-version">Version {{ top.version }}</span>
    </div>
    <p v-if="formError" class="mt-2 text-error" role="alert" data-testid="sys-form-error">{{ formError }}</p>
    <p v-if="refused" class="mt-2 rounded-lg border border-error bg-error-soft px-3 py-2 text-error" role="alert" data-testid="sys-refusal">{{ refused }}</p>
    <p v-if="notice" class="mt-2" data-testid="sys-notice">{{ notice }}</p>
    <div v-if="versions.length">
      <h3 class="mb-1 mt-3 text-xs font-semibold text-ink-muted">Earlier versions</h3>
      <ul class="space-y-1" data-testid="sys-versions">
        <li v-for="v in versions" :key="v.version" class="flex flex-wrap items-center gap-2" :data-testid="`sys-version-${v.version}`">
          <span>Version {{ v.version }}{{ v.current ? ' (current)' : '' }}{{ v.draft ? ' - Draft' : '' }}</span>
          <span class="text-ink-muted">saved by {{ v.saved_by }} on {{ when(v.saved_at) }}</span>
          <span v-if="v.restored_from" class="text-ink-muted">restored from version {{ v.restored_from }}</span>
          <button v-if="!v.current" type="button" class="btn btn-sm" :data-testid="`sys-restore-${v.version}`" :disabled="busy" @click="restore(v.version)">Restore this version</button>
        </li>
      </ul>
    </div>
  </section>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import api from '@/services/api'
import { useViewer } from '@/stores/viewer'
import { refusalText } from '@/lib/playbookEditor'

const props = defineProps({ strategyType: { type: String, required: true }, work: { type: Object, default: null } })
const emit = defineEmits(['applied'])
const viewer = useViewer()
const editing = ref(false)
const reason = ref('')
const versions = ref([])
const busy = ref(false)
const formError = ref(null)
const refused = ref(null)
const notice = ref(null)
const base = computed(() => `/system-playbooks/${props.strategyType}`)
const top = computed(() => versions.value.find((v) => v.current) ?? null)
const isDraft = computed(() => top.value?.draft === true)
// the server's own sentence: the catalogue refusal of this API ({reason}) or the editor's explanation parts
const sentence = (err) => err?.reason ?? err?.data?.reason ?? refusalText(err) ?? err?.message ?? null
const when = (iso) => { const d = new Date(iso); return Number.isNaN(d.getTime()) ? String(iso) : d.toLocaleString() }

async function load() {
  if (!viewer.isAdmin || !props.strategyType) { versions.value = []; return }
  try { versions.value = (await api.get(`${base.value}/versions`)).data.versions } catch (err) { versions.value = []; refused.value = sentence(err) }
}
watch(() => [viewer.isAdmin, props.strategyType], () => { editing.value = false; refused.value = null; notice.value = null; load() }, { immediate: true })

async function send(path, payload) {
  formError.value = null; refused.value = null; notice.value = null
  const why = reason.value.trim()
  if (!why) { formError.value = 'Say why you are making this change.'; return }
  if (!top.value) { refused.value = 'The current version has not been read yet.'; return }
  busy.value = true
  try {
    const res = await api.post(`${base.value}${path}`, { ...payload, reason: why, base_version: top.value.version })
    reason.value = ''
    notice.value = `Saved as version ${res.data.version}.`
    emit('applied', res.data.body)
    await load()
  } catch (err) { refused.value = sentence(err) } finally { busy.value = false }
}
const save = () => send('/versions', { body: props.work })
const restore = (version) => send(`/versions/${version}/restore`, {})
const approve = () => send('/approve', {})
</script>

<style scoped>
.btn { height: 2.25rem; padding: 0 0.75rem; border: 1px solid var(--color-line); border-radius: 0.5rem; background: var(--color-surface);
  color: var(--color-ink); font-weight: 500; font-size: 0.875rem; cursor: pointer; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary { background: var(--color-accent); border-color: var(--color-accent); color: var(--color-surface); }
.btn-sm { height: 1.75rem; padding: 0 0.5rem; font-size: 0.75rem; }
.field { height: 2rem; padding: 0 0.5rem; border: 1px solid var(--color-line); border-radius: 0.375rem; background: var(--color-surface);
  color: var(--color-ink); font-size: 0.875rem; }
</style>
