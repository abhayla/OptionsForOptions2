<!-- GC-TP step 7b (REQ-109 AC-8; ADR-207 (5); RD-121; Sensibull Conditional Exits, catalogue 221-224): arm a Conditional exit
     (the index crosses above / below a level: exit all legs) or a per-leg Stop on one paper strategy, list its triggers
     and cancel the armed ones. Paper only: the exits are recorded in the app and nothing is sent to Zerodha. A level is
     judged on its text (a multiple of 0.05, not zero) and sent as typed; every level and contract shown is the server's text
     (ADR-008). A refusal shows the server's words, never swallowed. -->
<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import api, { NEUTRAL_ERROR } from '@/services/api'
import { paperPriceOk, paperPriceReason } from '@/lib/tracking'
import { expiryText, istClock } from '@/lib/displayFormat'
import { PAPER_STOP_RISK_LOADING_TEXT } from '@/lib/sharedStateText'
import { CLOSED_REFERENCE_TEXT, NOT_LIVE_LABEL, lastCloseUnavailableText, useIndexAnswer } from '@/composables/useIndexLive'
import { triggerListOf, triggersPath } from '@/lib/paperTriggers'

const props = defineProps({
  strategyId: { type: Number, required: true },
  underlying: { type: String, default: '' },
  // the strategy's open legs: { index, label, contractId, ltpText? } (ltpText: the leg's price as the server sent it, null when not live)
  legs: { type: Array, default: () => [] },
  // D-44: contract id -> the leg label the form rows use (every position of the strategy, open or closed), so the list names a
  // stop's leg the same way; a contract not in it keeps the server's contract text
  legNames: { type: Object, default: () => ({}) },
  // the token of the parent list's last good read: a new one makes the stops list read again (S-23)
  goodReadToken: { type: Object, default: null },
  // #774 (ADR-330 (48)): the offer after a move shows the one leg-stop control only (same route, same Save), not the conditional exit or the list
  legStopOnly: { type: Boolean, default: false },
})

// N-21: after a good Save or Cancel, or when a re-read shows a fired stop, the parent list reads at once (its legs and book
// move with a stop); the panel has no timer of its own
const emit = defineEmits(['changed'])

const LABEL = 'Paper - exits are recorded in the app, not sent to Zerodha'
const AT_LEAST_ONE = 'Enter at least one level'
const LIST_STALE = 'Could not refresh this list. It shows the last read.'
const path = triggersPath(props.strategyId)
const riskPath = `/paper/strategies/${props.strategyId}/leg-stop-risk`

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
// D2: a stop whose contract is not among the open legs shows the server's contract text; its ISO date reads through the app's one date rule (expiryText)
const serverLegText = (text) => (typeof text === 'string' ? text.replace(/\d{4}-\d{2}-\d{2}/g, (d) => expiryText(d) ?? d) : null)
const stopReason = (i) => paperPriceReason(stopOf(i).level)

// W2-B (ADR-330 (6), ADR-008): while a leg and a valid level are typed, ask the server what the trade becomes if this stop fires and
// print its sentence as sent (GET .../leg-stop-risk). It informs only: Save never reads it, and every state but "yes" prints nothing
// (no, cannot_tell, a failed or unreadable answer, a 404, a refused level). One debounced read per leg after the typing pauses (no timer
// loop); an answer counts only if the box still holds the leg and level it was asked for, and only the newest ask per leg is kept.
const RISK_DEBOUNCE_MS = 400
const risk = ref({}) // leg index -> { key, text }: the server's sentence for exactly that contract and level
const riskKey = (leg) => `${leg.contractId}|${typed(stopOf(leg.index).level)}`
const riskNow = (leg) => (risk.value[leg.index]?.key === riskKey(leg) && !stopReason(leg.index) ? risk.value[leg.index] : null)
const riskText = (leg) => riskNow(leg)?.text ?? ''
const riskLoading = (leg) => riskPending.value[leg.index] === riskKey(leg) && !riskText(leg) && !stopReason(leg.index)
const riskLines = (leg) => riskNow(leg)?.lines ?? null
// ADR-330 (55): the server's three lines, each printed on its own line as sent; anything but three non-empty texts is not used
const threeLines = (v) => (Array.isArray(v) && v.length === 3 && v.every((x) => typeof x === 'string' && x !== '') ? v : null)
const riskPending = ref({}) // UX-A02: leg index -> the key being worked out (waiting to ask, or asked and not answered)
const riskTimers = {}
const riskLast = {} // leg index -> the key last asked
const riskAsk = {} // leg index -> the newest ask's number
function dropRisk(index) {
  if (risk.value[index]) { const { [index]: _gone, ...rest } = risk.value; risk.value = rest }
}
async function askRisk(leg, key) {
  const n = (riskAsk[leg.index] = (riskAsk[leg.index] ?? 0) + 1)
  let text = ''
  let lines = null
  try {
    const data = (await api.get(`${riskPath}?contract_id=${encodeURIComponent(leg.contractId)}&level=${encodeURIComponent(typed(stopOf(leg.index).level))}`)).data
    if (data?.state === 'yes' && typeof data.warning_text === 'string') { text = data.warning_text; lines = threeLines(data.warning_lines) }
  } catch { /* an error says nothing: the stop can still be saved */ }
  if (n !== riskAsk[leg.index] || key !== riskKey(leg)) return // an older answer, or the boxes moved on
  if (riskPending.value[leg.index] === key) { const { [leg.index]: _done, ...rest } = riskPending.value; riskPending.value = rest }
  if (text) risk.value = { ...risk.value, [leg.index]: { key, text, lines } }
  else dropRisk(leg.index)
}
watch(stop, () => {
  for (const leg of props.legs) {
    const key = riskKey(leg)
    if (risk.value[leg.index] && risk.value[leg.index].key !== key) dropRisk(leg.index) // the level or leg changed: the old sentence goes at once
    if (riskTimers[leg.index]?.key === key || riskLast[leg.index] === key) continue // already waiting or asked for this exact leg and level (a direction change asks nothing new)
    clearTimeout(riskTimers[leg.index]?.id)
    riskAsk[leg.index] = (riskAsk[leg.index] ?? 0) + 1 // anything still in flight is now old
    delete riskTimers[leg.index]
    delete riskLast[leg.index]
    if (riskPending.value[leg.index] !== undefined) { const { [leg.index]: _gone, ...rest } = riskPending.value; riskPending.value = rest } // the old key is no longer being worked out
    if (!typed(stopOf(leg.index).level) || stopReason(leg.index)) continue
    riskPending.value = { ...riskPending.value, [leg.index]: key }
    riskTimers[leg.index] = { key, id: setTimeout(() => { delete riskTimers[leg.index]; riskLast[leg.index] = key; askRisk(leg, key) }, RISK_DEBOUNCE_MS) }
  }
}, { deep: true })
onBeforeUnmount(() => Object.values(riskTimers).forEach((t) => clearTimeout(t.id)))

// D-05: a Save ends in exactly one line: "Saved: ...", "Already set: ..." or "Not saved: ..." (ADR-317 (5))
const NO_ANSWER = 'Not saved: could not get an answer from the server. Your levels are still in the boxes, press Save again.'
const refusal = (e) => e?.parts?.what_happened || NEUTRAL_ERROR
const notSaved = (e) => (e?.status >= 400 && e.status < 500 && e?.parts?.what_happened ? `Not saved: ${e.parts.what_happened}` : NO_ANSWER)

// Returns the reply data on success (a reply without a triggers array is a failure), null otherwise.
async function run(call, saving = false, notify = false) {
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
      if (notify) emit('changed')
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
  // ADR-330 (56): a closed market is not "unavailable": the same last value the strip shows, with its time (read of the one index answer)
  if (index.marketClosed() && typeof row?.value === 'string' && clock) return `${props.underlying} last ${index.shownValue(row)} as of ${clock}`
  // I-29: a closed market with no value for this index is not "Index values unavailable." (that is the feed-down word); it says the close is missing
  if (index.marketClosed() && props.underlying) return lastCloseUnavailableText(props.underlying)
  return index.rowNotLive(row) ? NOT_LIVE_LABEL : ''
})
// I-29: after the close a level is judged against the last close: one line, only while the server's answer says the market is closed
const referenceLine = computed(() => (index.marketClosed() ? CLOSED_REFERENCE_TEXT : ''))

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
    if (list) {
      const hadFired = (triggers.value ?? []).some((x) => x.state === 'fired')
      triggers.value = list
      listError.value = ''
      if (!hadFired && list.some((x) => x.state === 'fired')) emit('changed')
    } else listError.value = LIST_STALE
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
  const data = await run(() => api.post(path, body), true, true)
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
  const data = await run(() => api.post(path, { kind: 'leg_stop', contract_id: leg.contractId, direction: s.direction, level: typed(s.level) }), true, true)
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
const cancel = (t) => run(() => api.delete(`${path}/${t.id}`), false, true)
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
    <p v-if="referenceLine" class="text-xs text-ink-muted" data-testid="stops-reference">{{ referenceLine }}</p>

    <!-- D-44 round 1: from lg up the form (first) and the list of stops (second) sit side by side; narrower they stack -->
    <div class="grid gap-x-6 lg:grid-cols-2" data-testid="stops-columns">
    <div :key="strategyId" class="min-w-0" data-testid="stops-form">
    <div v-if="!legStopOnly" class="mt-2" data-testid="conditional-exit">
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
        <label class="flex items-center gap-1 text-xs" :data-testid="`stop-dirword-${l.index}`"><span>Stop when the price goes</span><select :value="stopOf(l.index).direction" class="rounded border border-line px-1 py-0.5" :data-testid="`stop-direction-${l.index}`" :aria-label="`Stop direction for ${l.label}`" @change="setStop(l.index, { direction: $event.target.value })">
          <option value="above">Above</option>
          <option value="below">Below</option>
        </select></label>
        <label class="flex items-center gap-1 text-xs" :data-testid="`stop-box-${l.index}`"><span>Stop price</span><input :value="stopOf(l.index).level" type="text" inputmode="decimal" placeholder="Stop price" class="w-24 rounded border border-line px-1 py-0.5" :data-testid="`stop-level-${l.index}`" :aria-label="`Stop price for ${l.label}`" @input="setStop(l.index, { level: $event.target.value })" /></label>
        <!-- FA2 item 4 (UX-A02, pending owner read): what the leg costs now, from the leg's own price; never a guess -->
        <span class="text-xs text-ink-muted" :data-testid="`stop-cost-${l.index}`">{{ typeof l.ltpText === 'string' && l.ltpText ? `Costs now ${l.ltpText}` : 'Costs now: not priced' }}</span>
        <button type="button" class="rounded border border-line px-3 py-1" :disabled="busy || !!stopReason(l.index)" :data-testid="`stop-save-${l.index}`" @click="saveStop(l)">{{ busy ? 'Saving...' : 'Save' }}</button>
        <span class="block min-h-4 basis-full whitespace-pre-line text-xs text-ink-muted" :data-testid="`stop-risk-slot-${l.index}`"><span v-if="riskLoading(l)" :data-testid="`stop-risk-loading-${l.index}`">{{ PAPER_STOP_RISK_LOADING_TEXT }}</span><span v-else-if="riskText(l)" :data-testid="`stop-risk-${l.index}`"><template v-if="riskLines(l)"><span v-for="(t, n) in riskLines(l)" :key="n" class="block" :data-testid="`stop-risk-line-${l.index}-${n}`">{{ t }}</span></template><template v-else>{{ riskText(l) }}</template></span></span>
        <span class="block min-h-4 basis-full text-xs text-ink-muted" :data-testid="`stop-reason-slot-${l.index}`"><span v-if="stopReason(l.index) && typed(stopOf(l.index).level)" :data-testid="`stop-reason-${l.index}`">{{ stopReason(l.index) }}</span></span>
      </div>
    </div>

    <!-- S-26: one reserved status slot, so a line appearing or going does not move the boxes the user is typing in -->
    <div class="mt-2 min-h-5" data-testid="stops-status-slot">
      <p v-if="error" class="text-red-700" role="alert" data-testid="stops-error">{{ error }}</p>
      <p v-else-if="saved" class="text-xs text-ink-muted" role="status" data-testid="stops-saved">{{ saved }}</p>
    </div>

    </div>

    <div v-if="!legStopOnly" class="min-w-0" data-testid="stops-list">
    <div class="mt-2" data-testid="triggers">
      <p class="font-medium">Stops on this strategy</p>
      <div class="min-h-4" data-testid="stops-list-slot"><p v-if="listError" class="text-xs text-ink-muted" data-testid="stops-list-error">{{ listError }}</p></div>
      <p v-if="triggers && !triggers.length" class="text-xs text-ink-muted" data-testid="stops-empty">No stops set.</p>
      <ul v-else-if="triggers">
        <li v-for="t in triggers" :key="t.id" class="flex flex-wrap items-center gap-2 border-b border-line py-1" data-testid="trigger-row" :data-trigger-id="t.id">
          <span>{{ t.kind === 'leg_stop' ? (legNames[t.contract_id] ?? serverLegText(t.contract_text) ?? 'Leg stop') : 'Conditional exit' }}</span>
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
