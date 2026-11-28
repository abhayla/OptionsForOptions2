// The one place the paper triggers path, the reply shape check and the armed index-exit filter live (modular doors
// Phase 6, F7). No Vue import. PaperStops.vue and TrackingPanel.vue each keep their own failure policy and timing.
// Spec basis: REQ-109 AC-8 (the stops panel reads the strategy's triggers).

export const triggersPath = (strategyId) => `/paper/strategies/${strategyId}/triggers`
// FC3 (28 Nov, Lane FD2's route): a real-mode trade's armed and fired exits, the paper read's exact reply shape (ADR-330 (58))
export const realTriggersPath = (strategyId) => `/real/strategies/${strategyId}/triggers`

// The triggers array of a reply's data, or null when the reply has none (a reply without the array is a failure).
export const triggerListOf = (data) => (Array.isArray(data?.triggers) ? data.triggers : null)

// Owner 28 Nov (withdraws ADR-330 (64)): a real position gets stops like a paper one (stored in the app; nothing is sent to Zerodha).
// The state "not_applicable" is now only for a position whose kind cannot be read (unknown, fail closed): not live, no armed badge, no count,
// no Cancel or Keep, and its row reads the server's `not_applicable_text`, else this sentence (pending owner read). Any other state keeps its behaviour.
export const NOT_APPLICABLE_TEXT = 'Not applicable: this position cannot be read as paper or real.'
export const isNotApplicable = (x) => x?.state === 'not_applicable'
/** The row's own sentence is the server's `not_applicable_text`; the constant is only the fallback (absent, empty or not text). */
export const notApplicableTextOf = (x) => (typeof x?.not_applicable_text === 'string' && x.not_applicable_text.trim() !== '' ? x.not_applicable_text.trim() : NOT_APPLICABLE_TEXT)

// The Conditional exits still on the screen: armed and fired ones; cancelled ones and per-leg stops are dropped.
export const armedIndexExits = (list) => list.filter((x) => x.kind === 'conditional_exit' && x.state !== 'cancelled')

// What the Plan card prints about exits: { kind: 'rows' | 'none' | 'failed', rows }. A real trade reads like a paper one (owner 28 Nov): a failed read is
// said so, never "none". Real and paper exits come from their routes (triggersPath / realTriggersPath) with the same reply shape.
export function exitsViewOf(exits, failed) {
  if (failed) return { kind: 'failed', rows: [] }
  const rows = Array.isArray(exits) ? exits : []
  return { kind: rows.length ? 'rows' : 'none', rows }
}

// #774, ADR-330 (48) (owner, 27 Nov): a leg's stop goes with a move of that leg; afterwards the app offers a new one on the new leg through the
// existing leg-stop control. The words are pending owner read (pinned by tests/paper-move-stop-offer-774.test.js).
export const STOP_OFFER_LABEL = (leg) => `Set a stop on ${leg}`

// The ids of the leg stops armed in `before` that `after` (a re-read of the same list) no longer holds armed. Both are triggers arrays.
// Nothing is guessed: a stop the re-read still shows armed, or an id it does not know, is not "removed" unless the list says it is not armed.
export function legStopsGone(before, after) {
  const now = new Map(after.map((x) => [x.id, x]))
  return before.filter((x) => x.kind === 'leg_stop' && x.state === 'armed' && now.has(x.id) && now.get(x.id).state !== 'armed' && !isNotApplicable(now.get(x.id))).map((x) => x.id)
}
