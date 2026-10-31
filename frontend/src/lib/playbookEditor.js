// GC-ADJ2 step 3 (REQ-160 AC-1, AC-2; REQ-159): the playbook editor's pure helpers. A body is the server's playbook body
// (docs/design/playbook-body-v1.md); every value in it is the body's own string, shown as it is and never computed on
// (ADR-008). Trigger labels and units come from the body (contract finding 10: the check answer leaves them out).

/** The seven steps of REQ-160 AC-1, in order (names as in the mockup's step list). */
export const STEPS = Object.freeze([
  ['basics', 'Expiry and stages'],
  ['when', 'When to look'],
  ['show', 'Approaches to show'],
  ['days', 'Days and dates'],
  ['sits', 'Situations'],
  ['limits', 'Limits and guards'],
  ['test', 'Test on my strategies'],
])
export const EXPIRY_KINDS = Object.freeze([['weekly', 'Weekly expiry'], ['monthly', 'Monthly expiry']])

/** A deep copy the editor may change without touching the read answer. */
export const clone = (body) => JSON.parse(JSON.stringify(body))
/** Unsaved changes: the working body differs from the body as read (or as last saved). */
export const isDirty = (work, saved) => work != null && saved != null && JSON.stringify(work) !== JSON.stringify(saved)

// Round 3 (owner's browser): every read of a body list goes through these, so each answer state renders. A body list
// can be stated (a non-empty list), null (all 12 system bodies: T-02, T-18, T-20, T-20b, T-21), missing, or empty.
/** One expiry kind's stages: the body's list, or [] when it is null, missing or not a list. */
export const stagesOf = (body, kind) => (Array.isArray(body?.stages?.[kind]) ? body.stages[kind] : [])
/** One trigger's values for an expiry kind: the body's list, or null when it has none (null, missing, empty). The
 *  editor then shows the no-values line and no inputs, and never creates a list the body did not have. */
export const valuesOf = (trigger, kind) => (Array.isArray(trigger?.[kind]) && trigger[kind].length ? trigger[kind] : null)
/** A rule's members and joiner: any_of (OR) or all_of (AND); a rule with neither has no members. */
export function ruleMembers(r) {
  if (Array.isArray(r?.all_of)) return { members: r.all_of, all: true }
  return { members: Array.isArray(r?.any_of) ? r.any_of : [], all: false }
}

/** Add a stage at the end of one expiry kind: every trigger gets an empty value there (not checked in that stage),
 *  so each value list keeps the stage count (the body rule). A trigger with no list for that kind keeps none. */
export function addStage(work, kind, name) {
  if (!Array.isArray(work?.stages?.[kind])) return
  work.stages[kind].push({ name, from: 0, to: 0 })
  for (const t of Object.values(work.triggers ?? {})) if (Array.isArray(t[kind])) t[kind].push('')
}

/** Remove stage ``index`` of one expiry kind, and its value from every trigger. */
export function removeStage(work, kind, index) {
  if (!Array.isArray(work?.stages?.[kind])) return
  work.stages[kind].splice(index, 1)
  for (const t of Object.values(work.triggers ?? {})) if (Array.isArray(t[kind])) t[kind].splice(index, 1)
}

/** Fill a catalogue sentence's {slot}s with the body's own strings (never a computed figure). A slot with no value
 *  stays as written, so a missing value shows rather than vanishing. */
export const fill = (template, slots) => (template ?? '').replace(/\{(\w+)\}/g, (m, k) => (slots[k] ?? m))

/** The labels answer (GET /playbooks/labels) as lookups: key -> text. */
export function labelMaps(answer) {
  const map = (list) => Object.fromEntries((list ?? []).map((x) => [x.key, said(x.text)]))
  return { approaches: map(answer?.approaches), dayKinds: map(answer?.day_kinds), dayActions: map(answer?.day_actions),
    summary: map(answer?.summary), guards: map(answer?.guards), pastNote: said(answer?.past_note),
    noValues: said(answer?.no_values) }
}

/** A stage's days in the catalogue's words. */
export function stageText(s, t) {
  const slots = { name: s.name, from: String(s.from), to: String(s.to) }
  if (s.to === null || s.to === undefined) return fill(t.stage_open, slots)
  return fill(s.from === s.to ? t.stage_single : t.stage_span, slots)
}

/** The plain-words summary (REQ-160 AC-1): the catalogue's sentences filled from the body, so it changes as the values
 *  change. No labels yet -> no summary (the browser types no sentence of its own). */
export function summaryLines(body, typeName, kind, labels) {
  const t = labels?.summary ?? {}
  if (!body || !t.type_line) return []
  const stages = stagesOf(body, kind)
  const looks = Object.values(body.triggers ?? {})
    .filter((x) => x.on && !x.greyed && (valuesOf(x, kind) ?? []).some((v) => v !== ''))
    .map((x) => {
      const slots = { label: x.label, values: valuesOf(x, kind).map((v) => (v === '' || v == null ? '-' : v)).join(' / '), unit: x.unit }
      return fill(x.unit && x.unit !== 'time' ? t.trigger_unit : t.trigger, slots)
    })
  const both = (body.rules ?? []).filter((r) => ruleMembers(r).all).map((r) => fill(t.rule_all, { id: r.id, members: r.all_of.join(t.joiner_and) }))
  const days = (body.day_rules ?? []).filter((r) => r.on).map((r) => fill(t.day_rule, {
    when: `${labels.dayKinds?.[r.when] ?? r.when}${r.date ? ' ' + r.date : ''}`, at: r.at, action: labels.dayActions?.[String(r.action)] ?? String(r.action) }))
  const g = body.guards ?? {}
  return [
    { key: 'type', text: fill(t.type_line, { type: typeName, kind: t[`kind_${kind}`], stages: stages.map((s) => stageText(s, t)).join(', ') }) },
    { key: 'looks', text: t.looks_head, items: looks },
    ...(both.length ? [{ key: 'rules', text: t.rules_head, items: both }] : []),
    { key: 'shows', text: fill(t.shows, { count: String(body.approaches?.applicable?.length ?? 0) }) },
    { key: 'days', text: t.days_head, items: days.length ? days : [t.days_none] },
    { key: 'plan', text: fill(t.plan, { target: g.profit_target_pct_of_max_profit, stop: g.stop_line_pct_of_max_loss,
      max: g.max_adjustments === undefined ? undefined : String(g.max_adjustments) }) },
  ]
}

/** A catalogue answer shown as text: a plain string, or a four-part message's first part. */
export const said = (v) => (v == null ? '' : typeof v === 'string' ? v : v.what_happened ?? '')

/** The server's refusal sentence, verbatim; null when the failure carries no catalogue message. */
export const refusalText = (err) => err?.parts?.what_happened ?? null

/** One Test answer row with the trigger's label and unit from the working body. */
export function testRow(r, body) {
  const t = body?.triggers?.[r.trigger_id] ?? {}
  const kind = r.kind === 'flag' ? 'Would flag' : r.kind === 'not_checked' ? 'Not checked' : said(r.wording) || 'Already true when tracking started'
  return { key: `${r.rule_id}-${r.trigger_id}`, kind: r.kind, kindText: kind, label: t.label ?? r.trigger_id, unit: t.unit && t.unit !== 'time' ? t.unit : '',
    value: r.value, threshold: r.threshold, reason: said(r.reason) }
}
