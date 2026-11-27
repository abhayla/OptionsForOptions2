// The one place the paper triggers path, the reply shape check and the armed index-exit filter live (modular doors
// Phase 6, F7). No Vue import. PaperStops.vue and TrackingPanel.vue each keep their own failure policy and timing.
// Spec basis: REQ-109 AC-8 (the stops panel reads the strategy's triggers).

export const triggersPath = (strategyId) => `/paper/strategies/${strategyId}/triggers`

// The triggers array of a reply's data, or null when the reply has none (a reply without the array is a failure).
export const triggerListOf = (data) => (Array.isArray(data?.triggers) ? data.triggers : null)

// The Conditional exits still on the screen: armed and fired ones; cancelled ones and per-leg stops are dropped.
export const armedIndexExits = (list) => list.filter((x) => x.kind === 'conditional_exit' && x.state !== 'cancelled')
