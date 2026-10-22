// W-125 (REQ-079 AC-2, AC-5, AC-7; REQ-082 AC-3): pure helpers for the ready-made panel and the probability figure.
// No number is computed here: strikes and the percentage arrive from the server (ADR-008).

/** Catalogue market views -> the four groups of REQ-079 AC-2, in display order. */
export const VIEW_GROUPS = [
  { key: 'bullish', title: 'Bullish', views: ['bullish'] },
  { key: 'bearish', title: 'Bearish', views: ['bearish'] },
  { key: 'neutral', title: 'Neutral', views: ['range-bound'] },
  { key: 'other', title: 'Other', views: ['volatile'] },
]

/** The templates of one group, in catalogue order. A template lands in the first group that lists any of its views. */
export function templatesInGroup(templates, group) {
  const list = Array.isArray(templates) ? templates : []
  return list.filter((t) => Array.isArray(t.views) && t.views.some((v) => group.views.includes(v)))
}

/** Quick-pick distances shown per underlying (REQ-079 AC-7 defaults; the server refuses any other distance). */
export const QUICK_PICK_DISTANCES = { NIFTY: [50, 100, 150, 200], SENSEX: [100, 200, 300, 400] }

/** REQ-079 AC-5, verbatim shape: "Replace the 2 legs in the builder?" */
export function replacePrompt(count) {
  return `Replace the ${count} ${count === 1 ? 'leg' : 'legs'} in the builder?`
}

/** A server answer leg -> a builder leg (ordinary, editable; no planned entry until the user prices it). */
export function builderLeg(leg, underlying, index) {
  return {
    id: `ready-made-${index}`,
    underlying,
    instrument_id: leg.instrument_id,
    symbol: leg.symbol,
    action: leg.action,
    lots: 1,
    planned_entry: null,
    captured_at: null,
    source: 'ready-made',
    fixed_rule_label: leg.label,
  }
}

export const POP_LABEL = "model estimate from today's prices, not a forecast"

/** REQ-082 AC-3: whole percent plus the label; a dash with the server's reason otherwise (AC-5). */
export function popText(pop) {
  if (!pop || typeof pop !== 'object') return null
  if (Number.isInteger(pop.percent)) return `Probability of profit: ${pop.percent}% (${POP_LABEL})`
  return typeof pop.reason === 'string' ? `Probability of profit: - (${pop.reason})` : null
}
