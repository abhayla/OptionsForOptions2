<!-- GC-TP step 7b (REQ-109 AC-8; ADR-207 (5); RD-121; Sensibull Conditional Exits, catalogue 221-224): arm a Conditional exit
     (the index crosses above / below a level: exit all legs) or a per-leg Stop on one paper strategy, list its triggers
     and cancel the armed ones. Paper only: the exits are recorded in the app and nothing is sent to Zerodha. A level is
     judged on its text (a multiple of 0.05, not zero) and sent as typed; every level and contract shown is the server's text
     (ADR-008). A refusal shows the server's words, never swallowed. -->
<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import api, { NEUTRAL_ERROR } from '@/services/api'
import { paperPriceOk, paperPriceReason } from '@/lib/tracking'
import { istClock } from '@/lib/displayFormat'
import { NOT_LIVE_LABEL, useIndexAnswer } from '@/composables/useIndexLive'
import { triggerListOf, triggersPath } from '@/lib/paperTriggers'

const props = defineProps({
  strategyId: { type: Number, required: true },
  underlying: { type: String, default: '' },
  // the strategy's open legs: { index, label, contractId }
  legs: { type: Array, default: () => [] },
  // D-44: contract id -> the leg label the form rows use (every position of the strategy, open or closed), so the list names a
  // stop's leg the same way; a contract not in it keeps the server's contract text
  legNames: { type: Object, default: () => ({}) },
  // the token of the parent list's last good read: a new one makes the stops list read again (S-23)
  goodReadToken: { type: Object, default: null },
})

const LABEL = 'Paper - exits are recorded in the app, not sent to Zerodha'
const AT_LEAST_ONE = 'Enter at least one level'
const LIST_STALE = 'Could not refresh this list. It shows the last read.'
const path = triggersPath(props.strategyId)

const triggers = ref(null) // null = not read (or unreadable)
const error = ref('')
const busy = ref(false)
const listError = ref('') // S-23: a failed quiet reread; the last list stays on screen
const saved = ref('') // the one-line confirmation of the last save
const above = ref('')
const below = ref('')
const stop = ref({}) // leg index -> { level, direction }

const typed = (v) => String(v ?? '').trim()
const stopOf = (i) => stop.value[i] ?? { level: '', direction: 'above' }
const setStop = (i, patch) => { stop.value = { ...stop.value, [i]: { ...stopOf(i), ...patch } } }

const ceReason = computed(() => {
  const set = [above.value, below.value].map(typed).filter(Boolean)
  if (!set.length) return AT_LEAST_ONE
  const bad = set.find((x) => !paperPriceOk(x))
  return bad === undefined ? '' : paperPriceReason(bad)
})
const stopReason = (i) => paperPriceReason(stopOf(i).level)

// D-05: a Save ends in exactly one line: "Saved: ...", "Already set: ..." or "Not saved: ..." (ADR-317 (5))
const NO_ANSWER = 'Not saved: could not get an answer from the server. Your levels are still in the boxes, press Save again.'
const refusal = (e) => e?.parts?.what_happened || NEUTRAL_ERROR
const notSaved = (e) => (e?.status >= 400 && e.status < 500 && e?.parts?.what_happened ? `Not saved: ${e.parts.what_happened}` : NO_ANSWER)

// Returns the reply data on success (a reply without a triggers array is a failure), null otherwise.
async function run(call, saving = false) {
  if (busy.value) return null
  busy.value = true
  gen += 1
  error.value = ''
  saved.value = ''
  try {
    const data = (await call()).data
    const list = triggerListOf(data)
    if (list) {
      triggers.value = list
      return data
    }
    triggers.value = null
    error.value = saving ? NO_ANSWER : NEUTRAL_ERROR
    return null
  } catch (e) {
    error.value = saving ? notSaved(e) : refusal(e)
    return null
  } finally {
    busy.value = false
  }
}

onMounted(() => run(() => api.get(path)))

// S-19: the index level the levels are judged against, from the one reader every index screen uses (no price text of its own)
const index = useIndexAnswer()
onMounted(index.start)
const indexLine = computed(() => {
  const row = index.rowFor(props.underlying)
  const clock = row?.at ? istClock(row.at) : null
  if (index.rowLive(row) && typeof row?.value === 'string' && clock) return `${props.underlying} now ${index.shownValue(row)} as of ${clock}`
  return index.rowNotLive(row) ? NOT_LIVE_LABEL : ''
})

// S-23: a trigger can fire on the server (state armed -> fired) while this panel is open. Root cause: the list was read once on
// mount only. Follow the parent list's good-read token (its one timer; none here). Quiet: not through run(), so a Saved / Not saved
// line is untouched; skipped while a save or cancel is in flight; a failure keeps the last list and has its own line.
let gen = 0
async function reread() {
  if (busy.value) return
  const mine = gen
  try {
    const list = triggerListOf((await api.get(path)).data)
    if (mine !== gen) return // an action ran meanwhile: its answer is newer
    if (list) { triggers.value = list; listError.value = '' } else listError.value = LIST_STALE
  } catch {
    if (mine === gen) listError.value = LIST_STALE
  }
}
// N-01: the one clear rule for the status line of every form here (conditional exit, leg stop, keep, cancel): it goes only when
// the user edits a level or direction, or presses a button again (run() clears it). A list refresh never clears it.
watch(() => props.goodReadToken, (t, old) => { if (t && t !== old) reread() })
watch([above, below, stop], () => { if (!busy.value) error.value = '' })

async function saveExit() {
  if (ceReason.value) return
  const body = { kind: 'conditional_exit' }
  if (typed(above.value)) body.above = typed(above.value)
  if (typed(below.value)) body.below = typed(below.value)
  const data = await run(() => api.post(path, body), true)
  if (data) {
    // D-05 r3: the line is built only from the server's answer: already_armed names the submitted levels it did NOT store
    const dupDirs = data.already_set ? ['above', 'below'] : (data.already_armed ?? [])
    const lv = [['above', body.above], ['below', body.below]].filter(([, v]) => v).map(([d, v]) => ({ d, v, dup: dupDirs.includes(d) }))
    const line = (list) => `exit ${list.map((x) => `${x.d} ${x.v}`).join(' and ')}`
    const fresh = lv.filter((x) => !x.dup)
    const dups = lv.filter((x) => x.dup)
    saved.value = !dups.length ? `Saved: ${line(fresh)}` : !fresh.length ? `Already set: ${line(dups)}` : `Saved: ${line(fresh)}. Already set: ${line(dups)}`
    above.value = ''
    below.value = ''
    showSaved((x) => x.kind === 'conditional_exit' && (body.above ? x.direction === 'above' : x.direction === 'below'))
  }
}
async function saveStop(leg) {
  if (stopReason(leg.index)) return
  const s = stopOf(leg.index)
  const data = await run(() => api.post(path, { kind: 'leg_stop', contract_id: leg.contractId, direction: s.direction, level: typed(s.level) }), true)
  if (data) {
    saved.value = `${data.already_set || data.already_armed?.length ? 'Already set' : 'Saved'}: stop ${s.direction} ${typed(s.level)}`
    setStop(leg.index, { level: '' })
    showSaved((x) => x.kind === 'leg_stop' && String(x.contract_id) === String(leg.contractId) && x.direction === s.direction)
  }
}
// D-44: after a successful Save the list can sit below the fold; bring the row just saved into view (nothing on a failure)
const rootEl = ref(null)
function showSaved(match) {
  nextTick(() => {
    const row = (triggers.value ?? []).find(match)
    const el = (row && rootEl.value?.querySelector(`[data-trigger-id="${row.id}"]`)) ?? rootEl.value?.querySelector('[data-testid="triggers"]')
    el?.scrollIntoView?.({ block: 'nearest' })
  })
}
const cancel = (t) => run(() => api.delete(`${path}/${t.id}`))
// D-03: same level, stored again after the change to the legs. Ends in one line: Kept / Already kept (the exit was not marked,
// so the server stored nothing) / Not saved (same path as Save). The level is written as the row writes it.
async function keep(t) {
  const data = await run(() => api.post(`${path}/${t.id}/keep`), true)
  if (!data) return
  const level = String(t.level_text ?? '').match(/[\d,]+(?:\.\d+)?$/)?.[0] ?? t.level
  const again = data.triggers.some((x) => x.id === t.id && x.state === 'armed')
  saved.value = `${again ? 'Already kept' : 'Kept'}: exit ${t.direction} ${level}`
}
</script>

<template>
  <div ref="rootEl" class="mt-2 rounded border border-line p-2" data-testid="paper-stops">
    <p class="text-xs font-semibold" data-testid="stops-label">{{ LABEL }}</p>
    <p class="min-h-5 text-xs text-ink-muted" data-testid="stops-index">{{ indexLine }}</p>

    <!-- D-44 round 1: from lg up the form (first) and the list of stops (second) sit side by side; narrower they stack -->
    <div class="grid gap-x-6 lg:grid-cols-2" data-testid="stops-columns">
    <div :key="strategyId" class="min-w-0" data-testid="stops-form">
    <div class="mt-2" data-testid="conditional-exit">
      <p class="font-medium">Conditional exit{{ underlying ? ` - ${underlying}` : '' }}</p>
      <p class="text-xs text-ink-muted">Exit all legs when the index crosses a level. Fill one or both.</p>
      <div class="mt-1 flex flex-wrap items-end gap-3">
        <label class="text-xs">Above<input v-model="above" type="text" inputmode="decimal" class="ml-1 w-28 rounded border border-line px-1 py-0.5 text-sm" data-testid="ce-above" /></label>
        <label class="text-xs">Below<input v-model="below" type="text" inputmode="decimal" class="ml-1 w-28 rounded border border-line px-1 py-0.5 text-sm" data-testid="ce-below" /></label>
        <button type="button" class="rounded border border-line px-3 py-1" :disabled="busy || !!ceReason" data-testid="ce-save" @click="saveExit">{{ busy ? 'Saving...' : 'Save' }}</button>
      </div>
      <div class="min-h-4" data-testid="ce-reason-slot"><p v-if="ceReason && !(saved && ceReason === AT_LEAST_ONE)" class="text-xs text-ink-muted" data-testid="ce-reason">{{ ceReason }}</p></div>
    </div>

    <div v-if="legs.length" class="mt-2" data-testid="leg-stops">
      <p class="font-medium">Stop on a leg</p>
      <div v-for="l in legs" :key="l.index" class="mt-1 flex flex-wrap items-center gap-2" :data-testid="`stop-row-${l.index}`">
        <span class="min-w-40">{{ l.label }}</span>
        <select :value="stopOf(l.index).direction" class="rounded border border-line px-1 py-0.5" :data-testid="`stop-direction-${l.index}`" :aria-label="`Stop direction for ${l.label}`" @change="setStop(l.index, { direction: $event.target.value })">
          <option value="above">Above</option>
          <option value="below">Below</option>
        </select>
        <input :value="stopOf(l.index).level" type="text" inputmode="decimal" placeholder="Stop price" class="w-24 rounded border border-line px-1 py-0.5" :data-testid="`stop-level-${l.index}`" :aria-label="`Stop price for ${l.label}`" @input="setStop(l.index, { level: $event.target.value })" />
        <button type="button" class="rounded border border-line px-3 py-1" :disabled="busy || !!stopReason(l.index)" :data-testid="`stop-save-${l.index}`" @click="saveStop(l)">{{ busy ? 'Saving...' : 'Save' }}</button>
        <span class="block min-h-4 basis-full text-xs text-ink-muted" :data-testid="`stop-reason-slot-${l.index}`"><span v-if="stopReason(l.index) && typed(stopOf(l.index).level)" :data-testid="`stop-reason-${l.index}`">{{ stopReason(l.index) }}</span></span>
      </div>
    </div>

    <!-- S-26: one reserved status slot, so a line appearing or going does not move the boxes the user is typing in -->
    <div class="mt-2 min-h-5" data-testid="stops-status-slot">
      <p v-if="error" class="text-red-700" role="alert" data-testid="stops-error">{{ error }}</p>
      <p v-else-if="saved" class="text-xs text-ink-muted" role="status" data-testid="stops-saved">{{ saved }}</p>
    </div>

    </div>

    <div class="min-w-0" data-testid="stops-list">
    <div class="mt-2" data-testid="triggers">
      <p class="font-medium">Stops on this strategy</p>
      <div class="min-h-4" data-testid="stops-list-slot"><p v-if="listError" class="text-xs text-ink-muted" data-testid="stops-list-error">{{ listError }}</p></div>
      <p v-if="triggers && !triggers.length" class="text-xs text-ink-muted" data-testid="stops-empty">No stops set.</p>
      <ul v-else-if="triggers">
        <li v-for="t in triggers" :key="t.id" class="flex flex-wrap items-center gap-2 border-b border-line py-1" data-testid="trigger-row" :data-trigger-id="t.id">
          <span>{{ t.kind === 'leg_stop' ? (legNames[t.contract_id] ?? t.contract_text ?? 'Leg stop') : 'Conditional exit' }}</span>
          <span class="font-medium" data-testid="trigger-direction">{{ t.direction === 'above' ? 'Above' : t.direction === 'below' ? 'Below' : '' }}</span>
          <span data-testid="trigger-level">{{ t.level_text }}</span>
          <span class="rounded bg-surface-muted px-1" data-testid="trigger-state">{{ t.state }}</span>
          <button v-if="t.state === 'armed'" type="button" class="rounded border border-line px-2 py-0.5" :disabled="busy" :data-testid="`trigger-cancel-${t.id}`" @click="cancel(t)">Cancel</button>
          <template v-if="t.state === 'armed' && t.set_before_adjustment">
            <span class="rounded bg-surface-muted px-1 text-xs font-medium" data-testid="trigger-adjusted">set before the last adjustment</span>
            <button type="button" class="rounded border border-line px-2 py-0.5" :disabled="busy" :data-testid="`trigger-keep-${t.id}`" @click="keep(t)">Keep this level</button>
            <p class="w-full text-xs text-ink-muted" data-testid="trigger-adjustment-note">{{ t.adjustment_note }}</p>
          </template>
        </li>
      </ul>
    </div>
    </div>
    </div>
  </div>
</template>
