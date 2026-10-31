<!-- GC-ADJ2 step 3 (REQ-160 AC-1..AC-4, REQ-158 AC-3/AC-4, REQ-159): Strategies > Adjustments, the playbook editor.
     Pick a strategy type and a playbook (system first, then the user's own); the playbook opens with every value filled
     in. Seven steps edit the working copy; the plain-words summary beside it is rebuilt from that copy; Test sends the
     UNSAVED copy to POST /api/playbooks/test. Every refusal is the server's sentence, shown verbatim. The browser
     computes no figure: values, thresholds and stage days are the body's or the answer's own (ADR-008). System or own,
     Draft and active come from the server's answer (is_system, draft, active), never inferred here. -->
<template>
  <section class="pb" data-testid="adjustments-page">
    <header class="pbbar">
      <label>Strategy type
        <select :value="typeKey" data-testid="pb-type" @change="pickType($event.target.value)">
          <option v-for="t in types" :key="t.key" :value="t.key">{{ t.name }}</option>
        </select>
      </label>
      <label>Playbook
        <select :value="pickedId" data-testid="pb-pick" @change="pickPlaybook($event.target.value)">
          <option v-for="p in playbooks" :key="p.id" :value="p.id">{{ p.name }}{{ p.draft ? ' (Draft)' : '' }}{{ p.active ? ' - active' : '' }}</option>
        </select>
      </label>
      <span v-if="listEmpty" data-testid="pb-list-empty">No playbook for this type yet.</span>
      <span v-if="current" class="chips">
        <span class="chip" data-testid="pb-owner">{{ current.is_system ? 'System playbook' : 'Yours' }}</span>
        <span v-if="current.draft" class="chip warn" data-testid="pb-draft">Draft</span>
        <span v-if="current.active" class="chip ok" data-testid="pb-active">Active</span>
        <span v-if="dirty" class="chip warn" data-testid="pb-dirty">Unsaved changes</span>
      </span>
    </header>

    <p v-if="refusal" class="refusal" role="alert" data-testid="pb-refusal">{{ refusal }}</p>
    <p v-if="notice" class="notice" data-testid="pb-notice">{{ notice }}</p>

    <div v-if="current && work" class="pbactions">
      <button v-if="!current.active" type="button" data-testid="pb-activate" @click="activate">Make active</button>
      <button v-if="!current.is_system" type="button" data-testid="pb-save" :disabled="!dirty" @click="saveInPlace">Save changes</button>
      <button v-if="!current.is_system" type="button" data-testid="pb-delete" @click="remove">Delete</button>
      <label>New playbook name <input v-model="newName" data-testid="pb-new-name" maxlength="80"></label>
      <button type="button" data-testid="pb-save-as" :disabled="!newName" @click="saveAsNew">Save as new playbook</button>
      <span v-if="current.is_system && dirty" data-testid="pb-system-hint">You changed a system playbook. Save it as a new playbook to keep the changes.</span>
    </div>

    <div v-if="current && work" class="pbgrid">
      <nav class="pbsteps" aria-label="Playbook sections" data-testid="pb-steps">
        <button v-for="([key, name], i) in STEPS" :key="key" type="button" :aria-current="key === step ? 'true' : 'false'" :data-testid="`pb-step-${key}`" @click="step = key">
          <span class="idx">{{ i + 1 }}</span> {{ name }}
        </button>
      </nav>

      <div class="pbbody" data-testid="pb-body">
        <div class="kinds">
          <button v-for="[k, label] in EXPIRY_KINDS" :key="k" type="button" :aria-pressed="k === kind ? 'true' : 'false'" :data-testid="`pb-kind-${k}`" @click="kind = k">{{ label }}</button>
        </div>

        <template v-if="step === 'basics'">
          <h2>Expiry and stages</h2>
          <div class="tw"><table>
            <thead><tr><th>Stage name</th><th>From (days left)</th><th>To (days left)</th><th></th></tr></thead>
            <tbody>
              <tr v-for="(s, i) in work.stages[kind]" :key="`${kind}-${i}`">
                <td><input v-model="s.name" :data-testid="`pb-stage-name-${i}`"></td>
                <td><input v-model.number="s.from" type="number" min="0"></td>
                <td><input type="number" min="0" :value="s.to ?? ''" placeholder="open" @change="s.to = $event.target.value === '' ? null : $event.target.valueAsNumber"></td>
                <td><button type="button" :data-testid="`pb-stage-remove-${i}`" :disabled="work.stages[kind].length < 2" @click="removeStage(work, kind, i)">Remove</button></td>
              </tr>
            </tbody>
          </table></div>
          <button type="button" data-testid="pb-stage-add" @click="addStage(work, kind, 'New stage')">Add a stage</button>
        </template>

        <template v-else-if="step === 'when'">
          <h2>When to look</h2>
          <div class="tw"><table>
            <thead><tr><th>On</th><th>Trigger</th><th v-for="(s, i) in work.stages[kind]" :key="i">{{ s.name }}</th></tr></thead>
            <tbody>
              <tr v-for="[id, t] in triggerRows" :key="id" :class="{ greyed: t.greyed }" :data-testid="`pb-trigger-${id}`">
                <td><input v-model="t.on" type="checkbox" :aria-label="`${t.label} on`"></td>
                <td>{{ t.label }}<span v-if="t.unit && t.unit !== 'time'"> ({{ t.unit }})</span><small v-if="t.greyed" class="why">{{ t.greyed }}</small></td>
                <td v-for="(s, i) in work.stages[kind]" :key="i"><input v-model="t[kind][i]" :data-testid="`pb-value-${id}-${i}`" size="6"></td>
              </tr>
            </tbody>
          </table></div>
          <h3>Rules</h3>
          <ul>
            <li v-for="r in work.rules" :key="r.id" :data-testid="`pb-rule-${r.id}`">
              {{ r.id }}: {{ (r.any_of ?? r.all_of).join(r.all_of ? ' AND ' : ' OR ') }}
              <button type="button" @click="flipRule(r)">{{ r.all_of ? 'Fire when any holds (OR)' : 'Fire only when all hold (AND)' }}</button>
            </li>
          </ul>
        </template>

        <template v-else-if="step === 'show'">
          <h2>Approaches to show</h2>
          <ul>
            <li v-for="id in allApproaches" :key="id"><label><input type="checkbox" :checked="work.approaches.applicable.includes(id)" @change="flipApproach(id)"> {{ id }}</label></li>
            <li v-for="g in work.approaches.greyed" :key="g.id" class="greyed">{{ g.id }} <small class="why">{{ g.reason }}</small></li>
          </ul>
        </template>

        <template v-else-if="step === 'days'">
          <h2>Days and dates</h2>
          <div class="tw"><table>
            <thead><tr><th>On</th><th>When</th><th>Time</th><th>Action</th><th>%</th></tr></thead>
            <tbody>
              <tr v-for="(r, i) in work.day_rules" :key="i">
                <td><input v-model="r.on" type="checkbox"></td><td>{{ r.when }}<span v-if="r.date"> {{ r.date }}</span></td>
                <td><input v-model="r.at" size="5"></td><td>{{ r.action }}</td>
                <td><input v-if="r.percent !== undefined" v-model="r.percent" size="4"></td>
              </tr>
            </tbody>
          </table></div>
        </template>

        <template v-else-if="step === 'sits'">
          <h2>Situations</h2>
          <p class="note">Possible approaches for each situation, never one best.</p>
          <ul><li v-for="s in work.situations" :key="s.id"><b>{{ s.id }} {{ s.name }}</b>: {{ s.rule }}</li></ul>
        </template>

        <template v-else-if="step === 'limits'">
          <h2>Limits and guards</h2>
          <div class="tw"><table><tbody>
            <tr v-for="(v, k) in work.guards" :key="k"><th>{{ k }}</th><td><input v-if="typeof v === 'number'" v-model.number="work.guards[k]" type="number" :data-testid="`pb-guard-${k}`"><input v-else v-model="work.guards[k]" :data-testid="`pb-guard-${k}`"></td></tr>
          </tbody></table></div>
        </template>

        <template v-else>
          <h2>Test on my strategies</h2>
          <p class="note" data-testid="pb-past-note">{{ pastNote || 'Testing against past expiries is not in this version.' }}</p>
          <button type="button" data-testid="pb-run-test" :disabled="testing" @click="runTest">Test {{ dirty ? 'unsaved changes' : 'this playbook' }}</button>
          <p v-if="testRefusal" role="alert" data-testid="pb-test-refusal">{{ testRefusal }}</p>
          <p v-if="answer && answer.none_text" data-testid="pb-test-none">{{ said(answer.none_text) }}</p>
          <div v-for="s in answer?.strategies ?? []" :key="s.strategy_id" class="tw" :data-testid="`pb-test-${s.strategy_id}`">
            <h3>{{ said(s.name) }}<span v-if="s.stage.name"> - {{ s.stage.name }}</span></h3>
            <p v-if="s.withheld">{{ said(s.withheld) }}</p>
            <table>
              <thead><tr><th>Result</th><th>Trigger</th><th>Value read</th><th>Rule</th><th>Reason</th></tr></thead>
              <tbody>
                <tr v-for="row in s.results.map((r) => testRow(r, work))" :key="row.key" :data-testid="`pb-test-row-${row.key}`">
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

      <aside class="pbsum" data-testid="pb-summary">
        <h2>This playbook in plain words</h2>
        <div v-for="line in summary" :key="line.key" :data-testid="`pb-sum-${line.key}`">
          <p>{{ line.text }}</p>
          <ul v-if="line.items"><li v-for="(it, i) in line.items" :key="i">{{ it }}</li></ul>
        </div>
      </aside>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import api from '@/services/api'
import { STEPS, EXPIRY_KINDS, addStage, clone, isDirty, refusalText, removeStage, said, summaryLines, testRow } from '@/lib/playbookEditor'

const types = ref([])
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
const pastNote = ref(null)
let readSeq = 0 // newest read wins: an answer for an earlier pick is dropped (state read after await)
let testSeq = 0

const dirty = computed(() => isDirty(work.value, saved.value))
const typeName = computed(() => said(types.value.find((t) => t.key === typeKey.value)?.name) || typeKey.value)
const summary = computed(() => summaryLines(work.value, typeName.value, kind.value))
const triggerRows = computed(() => Object.entries(work.value?.triggers ?? {}))
const allApproaches = computed(() => [...(work.value?.approaches.applicable ?? []), ...(work.value?.approaches.off_in_playbook ?? [])].sort())
const fail = (err) => { refusal.value = refusalText(err) ?? err?.message ?? null }

// the select's own value first, then the read: the handler never reads a value v-model has not written yet
function pickType(key) { typeKey.value = key; loadList() }
function pickPlaybook(id) { pickedId.value = playbooks.value.find((p) => String(p.id) === id)?.id ?? null; openPicked() }
function flipRule(r) {
  if (r.all_of) { r.any_of = r.all_of; delete r.all_of } else { r.all_of = r.any_of; delete r.any_of }
}
function flipApproach(id) {
  const a = work.value.approaches
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
    const res = await api.post('/playbooks/test', { type: typeKey.value, body: work.value })
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

onMounted(loadTypes)
</script>

<style scoped>
.pbbar, .pbactions, .kinds { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 8px; }
.pbgrid { display: grid; grid-template-columns: 200px 1fr 300px; gap: 12px; }
.pbsteps { display: flex; flex-direction: column; gap: 2px; }
.pbsteps button { text-align: left; border: 0; background: transparent; padding: 8px; border-radius: 6px; }
.pbsteps button[aria-current='true'] { background: var(--accent-soft, #eef); font-weight: 600; }
.tw { overflow-x: auto; max-width: 100%; }
.greyed { opacity: 0.6; }
.why { display: block; color: var(--muted, #666); }
.chip { border: 1px solid currentColor; border-radius: 10px; padding: 0 8px; margin-right: 4px; }
.refusal { color: var(--danger, #b00); }
@media (max-width: 760px) {
  .pbgrid { grid-template-columns: 1fr; }
  .pbsteps { flex-direction: row; overflow-x: auto; }
  .pbsteps button { white-space: nowrap; }
}
</style>
