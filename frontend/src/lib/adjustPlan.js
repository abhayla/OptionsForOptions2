// GC-ADJ2 step 4 (REQ-161 AC-1..AC-4, REQ-158 AC-5): the strategy plan sheet's one reading of GET/POST/PUT
// /api/strategies/{id}/adjustment-plan. Every word on the sheet is the server's (labels, playbook names, the generic text);
// the browser computes nothing: the percents are the server's decimal strings, the clock is the server's hour and minute,
// only re-shaped for an <input type="time"> and back. An answer this module cannot read is `invalid` (fail closed).

const planPath = (id) => `/strategies/${id}/adjustment-plan`

const clockText = (c) => (c && Number.isInteger(c.hour) && Number.isInteger(c.minute)
  ? `${String(c.hour).padStart(2, '0')}:${String(c.minute).padStart(2, '0')}` : '')
const parts = (v) => (v && typeof v === 'object' && typeof v.what_happened === 'string' ? v : null)
const text = (v) => (typeof v === 'string' ? v : '')
const decimal = (v) => (typeof v === 'string' ? v : '')
const count = (v) => (Number.isInteger(v) ? String(v) : '')

/** The sheet's form values from a prefill or plan (server values as text; empty text = the server holds none). */
export const formOf = (src) => ({
  playbookId: src?.playbook_id ?? null,
  target: decimal(src?.target), stop: decimal(src?.stop), stopShown: decimal(src?.stop), maxAdjustments: count(src?.max_adjustments),
  timeExit: clockText(src?.time_exit),
  targetWords: text(src?.target_words), stopWords: text(src?.stop_words), // what the numbers are, the server's words
})

const readRule = (r) => {
  if (!r || typeof r !== 'object' || typeof r.on !== 'boolean' || !Array.isArray(r.stages)) return null
  const stages = r.stages.map((s) => ({ name: text(s?.name), value: decimal(s?.value) }))
  if (stages.some((s) => !s.name || !s.value) || (r.on && stages.length === 0)) return null // fail closed: a number nothing names is not shown
  return { on: r.on, stages: r.on ? stages : [] }
}
/** The target and stop rules in force as the server's check reads them (per stage); a rule that cannot be read is null. */
const readRules = (b) => (b && typeof b === 'object' ? { target: readRule(b.target), stop: readRule(b.stop) } : { target: null, stop: null })

/** One rule as a sentence from the server's words: "50 % of max profit (80 % at Last day)", or "not being checked" when it is off.
 *  `unitKey` is the label holding the unit words. null when the rule or a word it needs is missing (the caller then says could-not-load). */
export function ruleText(rule, labels, unitKey) {
  if (!rule) return null
  if (!rule.on) return labels.not_checked || null
  if (!labels[unitKey] || !labels.at_stage) return null
  const later = rule.stages.slice(1).filter((s, i) => s.value !== rule.stages[i].value).map((s) => `${s.value} ${labels.at_stage} ${s.name}`)
  return `${rule.stages[0].value} ${labels[unitKey]}${later.length ? ` (${later.join(', ')})` : ''}`
}

/** The one reading of the answer: { kind: 'generic', text } | { kind: 'sheet', ... } | { kind: 'invalid' }. */
export function readPlan(body) {
  if (!body || typeof body !== 'object' || typeof body.generic !== 'boolean' || !body.labels || typeof body.labels !== 'object') {
    return { kind: 'invalid' }
  }
  const labels = Object.fromEntries(Object.entries(body.labels).map(([k, v]) => [k, text(v)]))
  if (body.generic) return { kind: 'generic', labels, text: parts(body.generic_text)?.what_happened ?? '' }
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
      maxAdjustments: count(body.plan.max_adjustments), timeExit: clockText(body.plan.time_exit),
    } : null,
    prefill: formOf(body.prefill),
    rules: readRules(body.rules_in_force),
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

/** The body for "Use playbook as is": the playbook alone, the server copies it unchanged. */
export const asIsBody = (playbookId) => ({ playbook_id: playbookId })

/** The body for Save: the playbook and every field as typed; the server checks each and names the one that is not valid. */
export function saveBody(form) {
  const body = { playbook_id: form.playbookId }
  if (form.target.trim() !== '') body.target = form.target.trim()
  // ADR-252 addendum: a stop left as the sheet showed it is not sent (the server also compares; this is the first layer)
  if (form.stop.trim() !== '' && form.stop.trim() !== (form.stopShown ?? '').trim()) body.stop = form.stop.trim()
  if (form.maxAdjustments.trim() !== '') body.max_adjustments = form.maxAdjustments.trim()
  if (form.timeExit.trim() !== '') body.time_exit = form.timeExit.trim()
  return body
}

/** POST (accept) or PUT (edit the plan later). Returns the new reading; throws the client error. */
export async function sendPlan(client, strategyId, body, edit) {
  const { data } = edit ? await client.put(planPath(strategyId), body) : await client.post(planPath(strategyId), body)
  return readPlan(data)
}

/** "Customise triggers": the playbook editor route, opening that playbook. */
export const customiseUrl = (playbookId) => `/strategies/adjustments?playbook=${playbookId}`
