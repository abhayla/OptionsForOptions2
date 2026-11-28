// The one place the paper triggers path, the reply shape check and the armed index-exit filter live (modular doors
// Phase 6, F7). No Vue import. PaperStops.vue and TrackingPanel.vue each keep their own failure policy and timing.
// Spec basis: REQ-109 AC-8 (the stops panel reads the strategy's triggers).

export const triggersPath = (strategyId) => `/paper/strategies/${strategyId}/triggers`
// FC3 (28 Nov, Lane FD2's route): a real-mode trade's armed and fired exits, the paper read's exact reply shape (ADR-330 (58))
export const realTriggersPath = (strategyId) => `/real/strategies/${strategyId}/triggers`

// The triggers array of a reply's data, or null when the reply has none (a reply without the array is a failure).
export const triggerListOf = (data) => (Array.isArray(data?.triggers) ? data.triggers : null)

// ADR-330 (64): a real position never gets a paper stop; an old armed paper stop on one comes back with state "not_applicable".
// It is not live: no armed badge, no count, no Cancel or Keep, and its row reads exactly this sentence (pending owner read).
// Any other state, an unknown or an absent one included, keeps its old behaviour.
export const NOT_APPLICABLE_REAL_TEXT = 'Not applicable: real position.'
export const isNotApplicable = (x) => x?.state === 'not_applicable'
/** FJ2-2: the row's own sentence is the server's `not_applicable_text`; the constant is only the fallback (absent, empty or not text). */
export const notApplicableTextOf = (x) => (typeof x?.not_applicable_text === 'string' && x.not_applicable_text.trim() !== '' ? x.not_applicable_text.trim() : NOT_APPLICABLE_REAL_TEXT)

// The Conditional exits still on the screen: armed and fired ones; cancelled ones and per-leg stops are dropped.
export const armedIndexExits = (list) => list.filter((x) => x.kind === 'conditional_exit' && x.state !== 'cancelled')

// I-24 (Lane FC): a real-mode trade's exits are read from the real route (FC3, 28 Nov); when that read FAILS they are neither
// shown nor called "none": the card says this sentence (pending owner read; ADR-330 (58): paper and real read alike, this is the gap).
export const EXITS_REAL_UNREADABLE_TEXT = 'Exits of a real-mode trade cannot be read here yet.'

// What the Plan card prints about exits: { kind: 'rows' | 'none' | 'failed' | 'real_unreadable', rows }. Any mode but 'real' is read as paper.
export function exitsViewOf(mode, exits, failed) {
  if (failed) return mode === 'real' ? { kind: 'real_unreadable', rows: [] } : { kind: 'failed', rows: [] } // the sentence is for a failed real read only
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
