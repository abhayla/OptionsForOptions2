<!-- GC-ADJ2 step 3 (REQ-160 AC-1..AC-4, REQ-158 AC-3/AC-4, REQ-159): Strategies > Adjustments, the playbook editor.
     Pick a strategy type and a playbook (system first, then the user's own); the playbook opens with every value filled
     in. Seven steps edit the working copy; the plain-words summary beside it is rebuilt from that copy; Test sends the
     UNSAVED copy to POST /api/playbooks/test. Every refusal is the server's sentence, shown verbatim. The browser
     computes no figure: values, thresholds and stage days are the body's or the answer's own (ADR-008). System or own,
     Draft and active come from the server's answer (is_system, draft, active), never inferred here. -->
<template>
  <section class="pb mx-auto max-w-[1400px] p-4 text-ink" data-testid="adjustments-page">
    <header class="flex flex-wrap items-end gap-3 rounded-lg border border-line bg-surface p-3">
      <label class="flex flex-col gap-1 text-xs font-medium text-ink-muted">Strategy type
        <select :value="typeKey" class="h-9 min-w-48 rounded-lg border border-line bg-surface px-2 text-sm text-ink" data-testid="pb-type" @change="pickType($event.target.value)">
          <option v-for="t in types" :key="t.key" :value="t.key">{{ t.name }}</option>
        </select>
      </label>
      <label class="flex flex-col gap-1 text-xs font-medium text-ink-muted">Playbook
        <select :value="pickedId" class="h-9 min-w-64 rounded-lg border border-line bg-surface px-2 text-sm text-ink" data-testid="pb-pick" @change="pickPlaybook($event.target.value)">
          <option v-for="p in playbooks" :key="p.id" :value="p.id">{{ p.name }}{{ p.draft ? ' (Draft)' : '' }}{{ p.active ? ' - active' : '' }}</option>
        </select>
      </label>
      <span v-if="listEmpty" class="text-sm text-ink-muted" data-testid="pb-list-empty">No playbook for this type yet.</span>
      <span v-if="current" class="flex flex-wrap items-center gap-1 pb-1 text-xs font-semibold">
        <span class="chip border-line bg-surface-muted text-ink-muted" data-testid="pb-owner">{{ current.is_system ? 'System playbook' : 'Yours' }}</span>
        <span v-if="current.draft" class="chip border-warn bg-warn-soft text-warn" data-testid="pb-draft">Draft</span>
        <span v-if="current.active" class="chip border-accent bg-accent-soft text-accent" data-testid="pb-active">Active</span>
        <span v-if="dirty" class="chip border-warn bg-warn-soft text-warn" data-testid="pb-dirty">Unsaved changes</span>
      </span>
    </header>

    <p v-if="refusal" class="mt-3 rounded-lg border border-error bg-error-soft px-3 py-2 text-sm text-error" role="alert" data-testid="pb-refusal">{{ refusal }}</p>
    <p v-if="notice" class="mt-3 rounded-lg border border-line bg-surface-muted px-3 py-2 text-sm" data-testid="pb-notice">{{ notice }}</p>

    <div v-if="current && work" class="mt-3 flex flex-wrap items-end gap-2">
      <button v-if="!current.active" type="button" class="btn" data-testid="pb-activate" @click="activate">Make active</button>
      <button v-if="!current.is_system" type="button" class="btn" data-testid="pb-save" :disabled="!dirty" @click="saveInPlace">Save changes</button>
      <button v-if="!current.is_system" type="button" class="btn" data-testid="pb-delete" @click="remove">Delete</button>
      <label class="flex flex-col gap-1 text-xs font-medium text-ink-muted">New playbook name <input v-model="newName" class="field w-64" data-testid="pb-new-name" maxlength="80"></label>
      <button type="button" class="btn btn-primary" data-testid="pb-save-as" :disabled="!newName" @click="saveAsNew">Save as new playbook</button>
      <span v-if="current.is_system && dirty" class="text-sm text-warn" data-testid="pb-system-hint">You changed a system playbook. Save it as a new playbook to keep the changes.</span>
    </div>

    <div v-if="current && work" class="pbgrid mt-3">
      <nav class="pbsteps rounded-lg border border-line bg-surface p-2" aria-label="Playbook sections" data-testid="pb-steps">
        <button v-for="([key, name], i) in STEPS" :key="key" type="button" class="step" :aria-current="key === step ? 'true' : 'false'" :data-testid="`pb-step-${key}`" @click="step = key">
          <span class="idx">{{ i + 1 }}</span> {{ name }}
        </button>
      </nav>

      <div class="min-w-0 rounded-lg border border-line bg-surface p-4" data-testid="pb-body">
        <div class="mb-3 inline-flex rounded-lg border border-line p-0.5">
          <button v-for="[k, label] in EXPIRY_KINDS" :key="k" type="button" class="seg" :aria-pressed="k === kind ? 'true' : 'false'" :data-testid="`pb-kind-${k}`" @click="kind = k">{{ label }}</button>
        </div>

        <template v-if="step === 'basics'">
          <h2 class="h2">Expiry and stages</h2>
          <p v-if="!stages.length" class="text-sm text-ink-muted" data-testid="pb-stages-none">{{ labels.noValues }}</p>
          <div v-else class="tw"><table class="tbl">
            <thead><tr><th>Stage name</th><th>From (days left)</th><th>To (days left)</th><th></th></tr></thead>
            <tbody>
              <tr v-for="(s, i) in stages" :key="`${kind}-${i}`">
                <td><input v-model="s.name" class="field w-full" :data-testid="`pb-stage-name-${i}`"></td>
                <td><input v-model.number="s.from" class="field w-24" type="number" min="0"></td>
                <td><input class="field w-24" type="number" min="0" :value="s.to ?? ''" placeholder="open" @change="s.to = $event.target.value === '' ? null : $event.target.valueAsNumber"></td>
                <td><button type="button" class="btn btn-sm" :data-testid="`pb-stage-remove-${i}`" :disabled="stages.length < 2" @click="removeStage(work, kind, i)">Remove</button></td>
              </tr>
            </tbody>
          </table></div>
          <button v-if="stages.length" type="button" class="btn mt-3" data-testid="pb-stage-add" @click="addStage(work, kind, 'New stage')">Add a stage</button>
        </template>

        <template v-else-if="step === 'when'">
          <h2 class="h2">When to look</h2>
          <div class="tw"><table class="tbl">
            <thead><tr><th>On</th><th>Trigger</th><th v-for="(s, i) in stages" :key="i">{{ s.name }}</th></tr></thead>
            <tbody>
              <tr v-for="[id, t] in triggerRows" :key="id" :class="{ greyed: t.greyed }" :data-testid="`pb-trigger-${id}`">
                <td><input v-model="t.on" type="checkbox" class="h-4 w-4 accent-accent" :aria-label="`${t.label} on`"></td>
                <td class="min-w-56">{{ t.label }}<span v-if="t.unit && t.unit !== 'time'" class="text-ink-muted"> ({{ t.unit }})</span><small v-if="t.greyed" class="why">{{ t.greyed }}</small></td>
                <template v-if="valuesOf(t, kind)">
                  <td v-for="(s, i) in stages" :key="i"><input :value="t[kind][i] ?? ''" class="field w-20" :data-testid="`pb-value-${id}-${i}`" @input="t[kind][i] = $event.target.value"></td>
                </template>
                <td v-else :colspan="stages.length || 1" class="text-sm text-ink-muted" :data-testid="`pb-novalue-${id}`">{{ labels.noValues }}</td>
              </tr>
            </tbody>
          </table></div>
          <h3 class="h3">Rules</h3>
          <ul class="space-y-1 text-sm">
            <li v-for="r in work.rules ?? []" :key="r.id" class="flex flex-wrap items-center gap-2" :data-testid="`pb-rule-${r.id}`">
              {{ r.id }}: {{ ruleMembers(r).members.join(ruleMembers(r).all ? ' AND ' : ' OR ') }}
              <button v-if="ruleMembers(r).members.length" type="button" class="btn btn-sm" @click="flipRule(r)">{{ ruleMembers(r).all ? 'Fire when any holds (OR)' : 'Fire only when all hold (AND)' }}</button>
            </li>
          </ul>
        </template>

        <template v-else-if="step === 'show'">
          <h2 class="h2">Approaches to show</h2>
          <ul class="space-y-1 text-sm">
            <li v-for="id in allApproaches" :key="id"><label class="flex items-center gap-2"><input type="checkbox" class="h-4 w-4 accent-accent" :checked="approaches.applicable.includes(id)" @change="flipApproach(id)"> {{ labels.approaches[id] ?? id }}</label></li>
            <li v-for="g in approaches.greyed" :key="g.id" class="greyed">{{ labels.approaches[g.id] ?? g.id }} <small class="why">{{ g.reason }}</small></li>
          </ul>
        </template>

        <template v-else-if="step === 'days'">
          <h2 class="h2">Days and dates</h2>
          <div class="tw"><table class="tbl">
            <thead><tr><th>On</th><th>When</th><th>Time</th><th>Action</th><th>%</th></tr></thead>
            <tbody>
              <tr v-for="(r, i) in work.day_rules ?? []" :key="i">
                <td><input v-model="r.on" type="checkbox" class="h-4 w-4 accent-accent"></td><td>{{ labels.dayKinds[r.when] ?? r.when }}<span v-if="r.date"> {{ r.date }}</span></td>
                <td><input v-model="r.at" class="field w-20"></td><td>{{ labels.dayActions[String(r.action)] ?? r.action }}</td>
                <td><input v-if="r.percent !== undefined" v-model="r.percent" class="field w-16"></td>
              </tr>
            </tbody>
          </table></div>
        </template>

        <template v-else-if="step === 'sits'">
          <h2 class="h2">Situations</h2>
          <p class="mb-2 text-sm text-ink-muted">Possible approaches for each situation, never one best.</p>
          <ul class="space-y-2 text-sm"><li v-for="s in work.situations ?? []" :key="s.id"><b>{{ s.id }} {{ s.name }}</b>: {{ s.rule }}</li></ul>
        </template>

        <template v-else-if="step === 'limits'">
          <h2 class="h2">Limits and guards</h2>
          <div class="grid gap-3">
            <label v-for="(v, k) in work.guards ?? {}" :key="k" class="flex flex-col gap-1 text-sm">
              <span class="font-medium" :data-testid="`pb-guard-label-${k}`">{{ labels.guards[k] ?? '' }}</span>
              <input v-if="typeof v === 'number'" v-model.number="work.guards[k]" class="field w-full" type="number" :data-testid="`pb-guard-${k}`">
              <input v-else v-model="work.guards[k]" class="field w-full" :data-testid="`pb-guard-${k}`">
            </label>
          </div>
        </template>

        <template v-else>
          <h2 class="h2">Test on my strategies</h2>
          <p class="mb-3 text-sm text-ink-muted" data-testid="pb-past-note">{{ pastNote || labels.pastNote }}</p>
          <button type="button" class="btn btn-primary" data-testid="pb-run-test" :disabled="testing" @click="runTest">Test {{ dirty ? 'unsaved changes' : 'this playbook' }}</button>
          <p v-if="testRefusal" class="mt-3 rounded-lg border border-error bg-error-soft px-3 py-2 text-sm text-error" role="alert" data-testid="pb-test-refusal">{{ testRefusal }}</p>
          <p v-if="answer && answer.none_text" class="mt-3 text-sm" data-testid="pb-test-none">{{ said(answer.none_text) }}</p>
          <div v-for="s in answer?.strategies ?? []" :key="s.strategy_id" class="tw mt-4" :data-testid="`pb-test-${s.strategy_id}`">
            <h3 class="h3">{{ said(s.name) }}<span v-if="s.stage?.name"> - {{ s.stage.name }}</span></h3>
            <p v-if="s.withheld" class="text-sm text-warn">{{ said(s.withheld) }}</p>
            <table class="tbl">
              <thead><tr><th>Result</th><th>Trigger</th><th>Value read</th><th>Rule</th><th>Reason</th></tr></thead>
              <tbody>
                <tr v-for="row in (s.results ?? []).map((r) => testRow(r, work))" :key="row.key" :data-testid="`pb-test-row-${row.key}`">
                  <td>{{ row.kindText }}</td><td>{{ row.label }}</td>
                  <td>{{ row.value ?? '' }}{{ row.value != null && row.unit ? ' ' + row.unit : '' }}</td>
                  <td>{{ row.threshold ?? '' }}{{ row.threshold != null && row.unit ? ' ' + row.unit : '' }}</td>
                  <td>{{ row.reason }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </div>

      <aside class="pbsum rounded-lg border border-line bg-surface-muted p-4 text-sm" data-testid="pb-summary">
        <h2 class="h2">This playbook in plain words</h2>
        <div v-for="line in summary" :key="line.key" class="mb-2" :data-testid="`pb-sum-${line.key}`">
          <p>{{ line.text }}</p>
          <ul v-if="line.items" class="ml-4 list-disc text-ink-muted"><li v-for="(it, i) in line.items" :key="i">{{ it }}</li></ul>
        </div>
      </aside>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import api from '@/services/api'
import { STEPS, EXPIRY_KINDS, addStage, clone, isDirty, labelMaps, refusalText, removeStage, ruleMembers, said, stagesOf, summaryLines,
  testRow, valuesOf } from '@/lib/playbookEditor'

const route = useRoute()
const types = ref([])
const labels = ref(labelMaps(null)) // every word the body does not carry (GET /playbooks/labels)
const typeKey = ref(null)
const playbooks = ref([])
const listEmpty = ref(false)
const pickedId = ref(null)
const current = ref(null) // the read answer (without the body)
const saved = ref(null) // the body as read or last saved
const work = ref(null) // the working copy the steps edit
const step = ref('basics')
const kind = ref('weekly')
const newName = ref('')
const refusal = ref(null)
const notice = ref(null)
const answer = ref(null)
const testRefusal = ref(null)
const testing = ref(false)
// GC-ADJ2 finding 22: the server bounds each strategy's reads at 8 s, 4 at a time (measured 18.4 s for ~25 saved
// strategies on ofo_dev), longer than the client's 10 s default; as StrategyPriceChart's history read does
const PLAYBOOK_TEST_TIMEOUT_MS = 60000
const pastNote = ref(null)
let readSeq = 0 // newest read wins: an answer for an earlier pick is dropped (state read after await)
let testSeq = 0

const dirty = computed(() => isDirty(work.value, saved.value))
const typeName = computed(() => said(types.value.find((t) => t.key === typeKey.value)?.name) || typeKey.value)
const summary = computed(() => summaryLines(work.value, typeName.value, kind.value, labels.value))
const triggerRows = computed(() => Object.entries(work.value?.triggers ?? {}))
const stages = computed(() => stagesOf(work.value, kind.value))
// a body without an approaches block (or one list of it) reads as empty lists, never a crash
const approaches = computed(() => {
  const a = work.value?.approaches ?? {}
  return { applicable: a.applicable ?? [], off_in_playbook: a.off_in_playbook ?? [], greyed: a.greyed ?? [] }
})
const allApproaches = computed(() => [...approaches.value.applicable, ...approaches.value.off_in_playbook].sort())
const fail = (err) => { refusal.value = refusalText(err) ?? err?.message ?? null }

// the select's own value first, then the read: the handler never reads a value v-model has not written yet
function pickType(key) { typeKey.value = key; loadList() }
function pickPlaybook(id) { pickedId.value = playbooks.value.find((p) => String(p.id) === id)?.id ?? null; openPicked() }
function flipRule(r) {
  if (!ruleMembers(r).members.length) return
  if (r.all_of) { r.any_of = r.all_of; delete r.all_of } else { r.all_of = r.any_of; delete r.any_of }
}
function flipApproach(id) {
  const a = work.value.approaches
  if (!a) return
  a.applicable ??= []
  a.off_in_playbook ??= []
  if (a.applicable.includes(id)) { a.applicable = a.applicable.filter((x) => x !== id); a.off_in_playbook.push(id) }
  else { a.off_in_playbook = a.off_in_playbook.filter((x) => x !== id); a.applicable.push(id) }
}

async function loadTypes() {
  try {
    const res = await api.get('/playbooks/types')
    types.value = res.data.types
    if (!typeKey.value && types.value.length) typeKey.value = types.value[0].key
    await loadList()
  } catch (err) { fail(err) }
}

async function loadList(keepId = null) {
  const key = typeKey.value
  refusal.value = null
  try {
    const res = await api.get('/playbooks', { params: { type: key } })
    if (key !== typeKey.value) return // the user picked another type while this was in flight
    playbooks.value = res.data.playbooks
    listEmpty.value = playbooks.value.length === 0
    pickedId.value = keepId ?? playbooks.value.find((p) => p.active)?.id ?? playbooks.value[0]?.id ?? null
    if (pickedId.value != null) await openPicked()
    else { current.value = null; work.value = null; saved.value = null }
  } catch (err) { fail(err) }
}

function show(pb) {
  const { body, ...meta } = pb
  current.value = meta
  saved.value = clone(body)
  work.value = clone(body)
  answer.value = null
  testRefusal.value = null
}

async function openPicked() {
  const id = pickedId.value
  const seq = ++readSeq
  refusal.value = null
  notice.value = null
  try {
    const res = await api.get(`/playbooks/${id}`)
    if (seq !== readSeq) return
    show(res.data)
  } catch (err) {
    if (seq !== readSeq) return
    current.value = null; work.value = null; saved.value = null // the editor is not opened on a failed read
    fail(err)
  }
}

async function act(call, after) {
  refusal.value = null
  notice.value = null
  try { await after((await call()).data) } catch (err) { fail(err) }
}
const activate = () => act(() => api.post(`/playbooks/${current.value.id}/activate`), async (pb) => { show(pb); await loadList(pb.id) })
const saveInPlace = () => act(() => api.put(`/playbooks/${current.value.id}`, { body: work.value, version: current.value.version }), async (pb) => { show(pb); await loadList(pb.id) })
const saveAsNew = () => act(() => api.post('/playbooks', { type: typeKey.value, name: newName.value, body: work.value }), async (pb) => { newName.value = ''; show(pb); await loadList(pb.id) })
const remove = () => act(() => api.delete(`/playbooks/${current.value.id}`), async (out) => { await loadList(); notice.value = out.message ? said(out.message) : null })

async function runTest() {
  const seq = ++testSeq
  testing.value = true
  testRefusal.value = null
  answer.value = null
  try {
    const res = await api.post('/playbooks/test', { type: typeKey.value, body: work.value }, { timeout: PLAYBOOK_TEST_TIMEOUT_MS })
    if (seq !== testSeq) return
    answer.value = res.data
    pastNote.value = said(res.data.past_note)
  } catch (err) {
    if (seq !== testSeq) return
    testRefusal.value = refusalText(err) ?? err?.message ?? null
  } finally {
    if (seq === testSeq) testing.value = false
  }
}

async function loadLabels() {
  try { labels.value = labelMaps((await api.get('/playbooks/labels')).data) } catch (err) { fail(err) }
}

/** ?playbook=<id> (the plan sheet's Customise triggers link): open that playbook, on its own type's list. */
async function openFromLink(id) {
  const seq = ++readSeq
  try {
    const res = await api.get(`/playbooks/${id}`)
    if (seq !== readSeq) return
    typeKey.value = res.data.type
    await loadList(res.data.id)
  } catch (err) {
    if (seq === readSeq) fail(err) // the editor stays closed; the server's sentence says why
  }
}

onMounted(async () => {
  await loadLabels()
  const linked = route?.query?.playbook
  if (typeof linked === 'string' && /^[0-9]+$/.test(linked)) {
    try { types.value = (await api.get('/playbooks/types')).data.types } catch (err) { fail(err); return }
    await openFromLink(linked)
  } else await loadTypes()
})
</script>

<style scoped>
/* round 3: the app's look (theme colours from style.css, the builder's button and field shapes) */
.btn { height: 2.25rem; padding: 0 0.75rem; border: 1px solid var(--color-line); border-radius: 0.5rem; background: var(--color-surface);
  color: var(--color-ink); font-weight: 500; font-size: 0.875rem; cursor: pointer; }
.btn:hover:not(:disabled) { background: var(--color-surface-muted); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary { background: var(--color-accent); border-color: var(--color-accent); color: var(--color-surface); }
.btn-primary:hover:not(:disabled) { background: var(--color-accent-hover); }
.btn-sm { height: 1.75rem; padding: 0 0.5rem; font-size: 0.75rem; }
.field { height: 2rem; padding: 0 0.5rem; border: 1px solid var(--color-line); border-radius: 0.375rem; background: var(--color-surface);
  color: var(--color-ink); font-size: 0.875rem; }
.field:focus { outline: 2px solid var(--color-accent-soft); border-color: var(--color-accent); }
.chip { border: 1px solid; border-radius: 999px; padding: 0.125rem 0.5rem; }
.h2 { margin-bottom: 0.75rem; font-size: 1rem; font-weight: 600; }
.h3 { margin: 1rem 0 0.5rem; font-size: 0.875rem; font-weight: 600; }
.pbgrid { display: grid; grid-template-columns: 220px minmax(0, 1fr) 300px; gap: 12px; align-items: start; }
.pbsteps { display: flex; flex-direction: column; gap: 2px; }
.step { display: flex; align-items: center; gap: 8px; text-align: left; border: 0; background: transparent; padding: 8px;
  border-radius: 6px; font-size: 0.875rem; color: var(--color-ink-muted); cursor: pointer; }
.step:hover { background: var(--color-surface-muted); }
.step[aria-current='true'] { background: var(--color-accent-soft); color: var(--color-accent); font-weight: 600; }
.idx { display: inline-flex; width: 1.5rem; height: 1.5rem; align-items: center; justify-content: center; border-radius: 999px;
  border: 1px solid currentColor; font-size: 0.75rem; }
.seg { height: 1.875rem; padding: 0 0.75rem; border: 0; border-radius: 0.375rem; background: transparent; font-size: 0.8125rem;
  color: var(--color-ink-muted); cursor: pointer; }
.seg[aria-pressed='true'] { background: var(--color-accent); color: var(--color-surface); font-weight: 600; }
.tw { overflow-x: auto; max-width: 100%; }
.tbl { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
.tbl th { text-align: left; font-size: 0.75rem; font-weight: 600; color: var(--color-ink-muted); padding: 6px 8px;
  border-bottom: 1px solid var(--color-line); white-space: nowrap; }
.tbl td { padding: 6px 8px; border-bottom: 1px solid var(--color-line); vertical-align: middle; }
.greyed { opacity: 0.6; }
.why { display: block; color: var(--color-ink-muted); }
@media (max-width: 1099px) {
  .pbgrid { grid-template-columns: 1fr; }
  .pbsteps { flex-direction: row; overflow-x: auto; }
  .step { white-space: nowrap; flex: none; }
}
</style>
