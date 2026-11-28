// GC-ADJ2 step 4 (REQ-161 AC-1..AC-4, REQ-158 AC-5): the strategy plan sheet's one reading of GET/POST/PUT
// /api/strategies/{id}/adjustment-plan. Every word on the sheet is the server's (labels, playbook names, the generic text);
// the browser computes nothing: the percents are the server's decimal strings, the clock is the server's hour and minute,
// only re-shaped for an <input type="time"> and back. An answer this module cannot read is `invalid` (fail closed).

import { markSaved } from '@/lib/planSaveClock'
const planPath = (id) => `/strategies/${id}/adjustment-plan`

const clockText = (c) => (c && Number.isInteger(c.hour) && Number.isInteger(c.minute)
  ? `${String(c.hour).padStart(2, '0')}:${String(c.minute).padStart(2, '0')}` : '')
const parts = (v) => (v && typeof v === 'object' && typeof v.what_happened === 'string' ? v : null)
const text = (v) => (typeof v === 'string' ? v : '')
// The server's generic text as a plain string, a catalogue object ({ what_happened }) or null (local copy of the shared rule: lib/serverText.js is on another branch)
const genericText = (v) => (typeof v === 'string' ? v : parts(v)?.what_happened ?? '')
const decimal = (v) => (typeof v === 'string' ? v : '')
const count = (v) => (Number.isInteger(v) ? String(v) : '')

/** The sheet's form values from a prefill or plan (server values as text; empty text = the server holds none). */
export const formOf = (src) => ({
  playbookId: src?.playbook_id ?? null,
  target: decimal(src?.target), stop: decimal(src?.stop), stopShown: decimal(src?.stop), maxAdjustments: count(src?.max_adjustments),
  timeExit: clockText(src?.time_exit), timeExitOn: text(src?.time_exit_on), // ADR-330 (7): blank date = expiry day
  timeExitShown: clockText(src?.time_exit), timeExitOnShown: text(src?.time_exit_on), // as the sheet showed them
  targetWords: text(src?.target_words), stopWords: text(src?.stop_words), // what the numbers are, the server's words
  // ADR-330 (5): the same two levels in rupees, both figures the server's; the box last edited is the one saved
  targetRupees: decimal(src?.target_rupees), stopRupees: decimal(src?.stop_rupees),
  stopRupeesShown: decimal(src?.stop_rupees),
  targetRupeeWords: text(src?.target_rupee_words), stopRupeeWords: text(src?.stop_rupee_words),
  stopWarning: text(src?.stop_warning), // ADR-330 (25): the server's line when the rupee stop is above the max loss
  // I-208: which box of each pair holds what the user typed (the other was filled by the server); both true = both are sent
  targetTyped: { percent: false, rupees: false }, stopTyped: { percent: false, rupees: false },
  targetLast: src?.target_source === 'rupees' ? 'rupees' : 'percent', stopLast: src?.stop_source === 'rupees' ? 'rupees' : 'percent',
})

/** The one reading of the answer: { kind: 'generic', text } | { kind: 'sheet', ... } | { kind: 'invalid' }. */
export function readPlan(body) {
  if (!body || typeof body !== 'object' || typeof body.generic !== 'boolean' || !body.labels || typeof body.labels !== 'object') {
    return { kind: 'invalid' }
  }
  const labels = Object.fromEntries(Object.entries(body.labels).map(([k, v]) => [k, text(v)]))
  if (body.generic) return { kind: 'generic', labels, text: genericText(body.generic_text) }
  if (!Array.isArray(body.playbooks) || !body.prefill || !Number.isInteger(body.prefill.playbook_id)) return { kind: 'invalid' }
  return {
    kind: 'sheet',
    labels,
    typeName: text(body.type_name),
    playbooks: body.playbooks.map((p) => ({ id: p.id, name: text(p.name), draft: !!p.draft, active: !!p.active, system: !!p.is_system })),
    plan: body.plan ? {
      playbookId: body.plan.playbook_id ?? null,
      playbookName: text(body.plan.playbook_name),
      target: decimal(body.plan.target), stop: decimal(body.plan.stop),
      targetWords: text(body.plan.target_words), stopWords: text(body.plan.stop_words),
      targetRupees: decimal(body.plan.target_rupees), stopRupees: decimal(body.plan.stop_rupees), // I-197: the plan's own levels in rupees, the server's strings
      changed: Array.isArray(body.plan.changed) ? body.plan.changed.filter((x) => typeof x === 'string') : [], // ADR-330 (9): the server's markers
      switchedOff: Array.isArray(body.plan.switched_off) ? body.plan.switched_off.filter((x) => typeof x === 'string') : [],
      maxAdjustments: count(body.plan.max_adjustments), timeExit: clockText(body.plan.time_exit), timeExitOn: text(body.plan.time_exit_on),
    } : null,
    prefill: formOf(body.prefill),
    // T2-19: only a reset reply fills these (what the plan had changed / switched off just before it), as the server sent them
    // F7 (Lane FC): why no stop is shown (the expiry kind is not known): the server's catalogue sentence, '' when it sent none
    stopKindReason: parts(body.stop_kind_reason)?.what_happened || text(body.stop_kind_reason),
    putBack: Array.isArray(body.put_back) ? body.put_back.filter((x) => typeof x === 'string') : [],
    putBackOff: Array.isArray(body.put_back_off) ? body.put_back_off.filter((x) => typeof x === 'string') : [],
  }
}

/** The plan read's own limit (GC-ICFIX issue 2: under load it took 12-18 s); the client's global 10 s stays for every other request. */
export const PLAN_READ_TIMEOUT_MS = 30000

/** GET the sheet; `pickId` refills every field from that playbook (REQ-161 AC-2). Throws the client error. */
export async function fetchPlan(client, strategyId, pickId = null) {
  const { data } = await client.get(pickId === null ? planPath(strategyId) : `${planPath(strategyId)}?playbook_id=${pickId}`,
    { timeout: PLAN_READ_TIMEOUT_MS })
  return readPlan(data)
}

/** The body for "Use playbook as is": the playbook alone, the server copies it unchanged. `accept: true` says the user
 *  chose this playbook (ADR-330 (45): accepting a playbook, also the same one again, is a new acceptance; #753). */
export const asIsBody = (playbookId) => ({ playbook_id: playbookId, accept: true })

/** The body for Save: the playbook and every field as typed; the server checks each and names the one that is not valid.
 *  Of each percent / rupee pair only the box last edited is sent (ADR-330 (5)); the other is the server's derived figure.
 *  `picked`: the user chose a playbook in the sheet's selector -> `accept: true` (a new acceptance, #753); a pure edit of
 *  levels never sends it, so it never stamps the acceptance time (ADR-330 (45)). */
export function saveBody(form, picked = false) {
  const body = { playbook_id: form.playbookId }
  if (picked) body.accept = true
  const bothTyped = (typed, a, b) => !!typed?.percent && !!typed?.rupees && (a ?? '').trim() !== '' && (b ?? '').trim() !== ''
  // I-208: both boxes typed by the user and the server could not tie them together: send both, the server names a clash
  if (bothTyped(form.targetTyped, form.target, form.targetRupees)) { body.target = form.target.trim(); body.target_rupees = form.targetRupees.trim() }
  else if (form.targetLast === 'rupees') body.target_rupees = (form.targetRupees ?? '').trim() // "" clears the level
  else body.target = form.target.trim() // ADR-305: an empty Target is sent as "" = no target alert for this trade
  // ADR-252 addendum: a stop left as the sheet showed it is not sent (the server also compares; this is the first layer)
  if (bothTyped(form.stopTyped, form.stop, form.stopRupees)) {
    body.stop = form.stop.trim(); body.stop_rupees = form.stopRupees.trim()
  } else if (form.stopLast === 'rupees') {
    if ((form.stopRupees ?? '').trim() !== (form.stopRupeesShown ?? '').trim()) body.stop_rupees = form.stopRupees.trim()
  } else if (form.stop.trim() !== '' && form.stop.trim() !== (form.stopShown ?? '').trim()) body.stop = form.stop.trim()
  if (form.maxAdjustments.trim() !== '') body.max_adjustments = form.maxAdjustments.trim()
  // ADR-330 (7): one time on one day; a blank date is sent as "" = expiry day (the server judges the day). Sent only
  // when the time or the date changed in the sheet, so a saved date that has passed never blocks an unrelated edit;
  // a date typed without a time is sent with the empty time, so the server names the field (never silently dropped).
  const at = (form.timeExit ?? '').trim()
  const on = (form.timeExitOn ?? '').trim()
  const changed = at !== (form.timeExitShown ?? '').trim() || on !== (form.timeExitOnShown ?? '').trim()
  if (changed && (at !== '' || on !== '')) body.time_exit = { at, on }
  return body
}

const levelsPath = (id, typed) => {
  const q = Object.entries(typed).filter(([, v]) => typeof v === 'string' && v.trim() !== '')
    .map(([k, v]) => `${k}=${encodeURIComponent(v.trim())}`).join('&')
  return `${planPath(id)}/levels${q ? `?${q}` : ''}`
}
const level = (l) => (l && typeof l === 'object'
  ? { percent: decimal(l.percent), rupees: decimal(l.rupees), words: text(l.words), rupeeWords: text(l.rupee_words), warning: text(l.warning) } : null)

/** GET .../adjustment-plan/levels (with the picked playbook_id, so the sentence is the one the save will say) for the box just typed in (`{ target }`, `{ target_rupees }`, `{ stop }` or
 *  `{ stop_rupees }`): the server works out both figures and the hint words; the browser computes nothing (ADR-008).
 *  Returns `{ target, stop }` (each `{ percent, rupees, words, rupeeWords }` or null). Throws the client error. */
export async function fetchLevels(client, strategyId, typed, playbookId = null, picked = false) {
  const { data } = await client.get(levelsPath(strategyId, { ...typed, playbook_id: playbookId == null ? '' : String(playbookId), accept: picked ? 'true' : '' }))
  return { target: level(data?.target), stop: level(data?.stop) }
}

/** The plan SAVE's own limit (Lane R hotfix plan-save-1127: the shared 10 s gave up on a save the server then stored). Set per request,
 *  never on the client. The server's own bound is a 4 s price read (routes/adjustment_plan PLAN_SAVE_PRICE_BUDGET_S); 30 s covers it. */
export const PLAN_SAVE_TIMEOUT_MS = 30000
const SAVE_CONFIG = Object.freeze({ timeout: PLAN_SAVE_TIMEOUT_MS })

/** The save count moves only for a save the browser can read (a 200 it cannot read is "not confirmed", never counted as saved). */
const saved = (strategyId, read) => {
  if (read.kind !== 'invalid') markSaved(strategyId)
  return read
}

/** POST (accept) or PUT (edit the plan later). Returns the new reading; throws the client error. Never re-sent here (no auto retry). */
export async function sendPlan(client, strategyId, body, edit) {
  const { data } = edit ? await client.put(planPath(strategyId), body, SAVE_CONFIG) : await client.post(planPath(strategyId), body, SAVE_CONFIG)
  return saved(strategyId, readPlan(data))
}

export { isRefusal } from '@/lib/planSaveResult' // the one rule lives in planSaveResult.js

/** D-TG2-1: a reset marker key ("triggers.T-01") is never shown. Its name is the trigger's label in the trade's own rules; a key with no
 *  readable label (unknown, empty, or the rules could not be read) reads this plain fallback (pending owner read). */
export const MARKER_FALLBACK_TEXT = 'a condition of the playbook'
/** `labels`: trigger id -> label from GET .../adjustment-plan/rules. One name per marker, the fallback at most once. */
export function markerNames(keys, labels) {
  const out = []
  for (const k of Array.isArray(keys) ? keys : []) {
    const m = /^triggers\.([A-Za-z0-9-]+)$/.exec(String(k))
    const label = m && typeof labels?.[m[1]] === 'string' ? labels[m[1]].trim() : ''
    const name = label || MARKER_FALLBACK_TEXT
    if (!out.includes(name)) out.push(name)
  }
  return out
}
/** The trade's own trigger labels (id -> label) for the reset markers; {} when the read fails (every marker then reads the fallback). */
export async function fetchTriggerLabels(client, strategyId) {
  try {
    const { data } = await client.get(`${planPath(strategyId)}/rules`)
    return Object.fromEntries(Object.entries(data?.body?.triggers ?? {}).map(([id, t]) => [id, typeof t?.label === 'string' ? t.label : '']))
  } catch {
    return {}
  }
}

/** ADR-330 (9), (32) "Reset to playbook": the server puts the playbook's conditions back (the typed levels stay) and answers the sheet. Throws the client error. */
export async function resetPlan(client, strategyId) {
  const { data } = await client.post(`${planPath(strategyId)}/reset`, undefined, SAVE_CONFIG)
  return saved(strategyId, readPlan(data))
}

/** "Customise triggers": the editor opened on THIS trade's own rules (issue 7), never on a playbook other trades follow. */
export const customiseUrl = (strategyId) => `/strategies/adjustments?trade=${strategyId}`
