// The one place the paper triggers path, the reply shape check and the armed index-exit filter live (modular doors
// Phase 6, F7). No Vue import. PaperStops.vue and TrackingPanel.vue each keep their own failure policy and timing.
// Spec basis: REQ-109 AC-8 (the stops panel reads the strategy's triggers).

export const triggersPath = (strategyId) => `/paper/strategies/${strategyId}/triggers`

// The triggers array of a reply's data, or null when the reply has none (a reply without the array is a failure).
export const triggerListOf = (data) => (Array.isArray(data?.triggers) ? data.triggers : null)

// The Conditional exits still on the screen: armed and fired ones; cancelled ones and per-leg stops are dropped.
export const armedIndexExits = (list) => list.filter((x) => x.kind === 'conditional_exit' && x.state !== 'cancelled')

// #774, ADR-330 (48) (owner, 27 Nov): a leg's stop goes with a move of that leg; afterwards the app offers a new one on the new leg through the
// existing leg-stop control. The words are pending owner read (pinned by tests/paper-move-stop-offer-774.test.js).
export const STOP_OFFER_LABEL = (leg) => `Set a stop on ${leg}`

// The ids of the leg stops armed in `before` that `after` (a re-read of the same list) no longer holds armed. Both are triggers arrays.
// Nothing is guessed: a stop the re-read still shows armed, or an id it does not know, is not "removed" unless the list says it is not armed.
export function legStopsGone(before, after) {
  const now = new Map(after.map((x) => [x.id, x]))
  return before.filter((x) => x.kind === 'leg_stop' && x.state === 'armed' && now.has(x.id) && now.get(x.id).state !== 'armed').map((x) => x.id)
}
