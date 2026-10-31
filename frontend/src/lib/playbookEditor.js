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

/** A stage's days as words: "5+ days left", "2-4 days left", "1 day left". The numbers are the body's own. */
export function stageLabel(s) {
  if (s.to === null || s.to === undefined) return `${s.from}+ days left`
  if (s.from === s.to) return `${s.from} day${s.from === 1 ? '' : 's'} left`
  return `${s.from}-${s.to} days left`
}

/** Add a stage at the end of one expiry kind: every trigger gets an empty value there (not checked in that stage),
 *  so each value list keeps the stage count (the body rule). */
export function addStage(work, kind, name) {
  work.stages[kind].push({ name, from: 0, to: 0 })
  for (const t of Object.values(work.triggers)) if (Array.isArray(t[kind])) t[kind].push('')
}

/** Remove stage ``index`` of one expiry kind, and its value from every trigger. */
export function removeStage(work, kind, index) {
  work.stages[kind].splice(index, 1)
  for (const t of Object.values(work.triggers)) if (Array.isArray(t[kind])) t[kind].splice(index, 1)
}

const unitText = (u) => (u && u !== 'time' ? ` ${u}` : '')

/** The plain-words summary (REQ-160 AC-1): built from the body only, so it changes as the values change. */
export function summaryLines(body, typeName, kind) {
  if (!body) return []
  const stages = body.stages?.[kind] ?? []
  const looks = Object.entries(body.triggers ?? {})
    .filter(([, t]) => t.on && !t.greyed && (t[kind] ?? []).some((v) => v !== ''))
    .map(([id, t]) => ({ id, text: `${t.label}: ${(t[kind] ?? []).map((v) => (v === '' ? '-' : v)).join(' / ')}${unitText(t.unit)}` }))
  const both = (body.rules ?? []).filter((r) => Array.isArray(r.all_of)).map((r) => `${r.id}: only when ${r.all_of.join(' and ')} all hold`)
  const shown = body.approaches?.applicable?.length ?? 0
  const days = (body.day_rules ?? []).filter((r) => r.on).map((r) => `${r.when}${r.date ? ' ' + r.date : ''} at ${r.at}`)
  const g = body.guards ?? {}
  return [
    { key: 'type', text: `${typeName}, ${kind} expiry. Stages: ${stages.map((s) => `${s.name} (${stageLabel(s)})`).join(', ')}.` },
    { key: 'looks', text: 'Looks at an adjustment when (numbers per stage):', items: looks.map((x) => x.text) },
    ...(both.length ? [{ key: 'rules', text: 'Combined rules:', items: both }] : []),
    { key: 'shows', text: `Shows ${shown} approaches.` },
    { key: 'days', text: 'Day rules:', items: days.length ? days : ['none'] },
    { key: 'plan', text: `Plan: target ${g.profit_target_pct_of_max_profit ?? '-'}% of max profit, stop at ${g.stop_line_pct_of_max_loss ?? '-'}% of max loss, at most ${g.max_adjustments ?? '-'} adjustments.` },
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
