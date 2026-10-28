// W-125 (REQ-079 AC-2, AC-5, AC-7; REQ-082 AC-3): pure helpers for the ready-made panel and the probability figure.
// No number is computed here: strikes and the percentage arrive from the server (ADR-008).

/** The four groups of REQ-079 AC-2, in display order, with Sensibull's names and card order (GC-UI D-C03, D-C05, D-C07).
 *  `ids` is the card order of the group; a template this list does not name (Covered Call, Cash-Secured Put, ...) still
 *  shows, after the listed ones, in the first group that lists any of its catalogue views (Others when none does).
 *  The catalogue `views` are not changed: the Learn page and shape detection (RD-096) keep reading them. */
export const VIEW_GROUPS = [
  { key: 'bullish', title: 'Bullish', views: ['bullish'], ids: ['buy_call', 'sell_put_atm', 'bull_call_spread', 'bull_put_spread', 'ratio_backspread_call',
    'calendar_spread', 'bull_condor', 'butterfly_spread', 'range_forward', 'synthetic_long', 'buy_future'] },
  { key: 'bearish', title: 'Bearish', views: ['bearish'], ids: ['buy_put', 'sell_call', 'bear_call_spread', 'bear_put_spread', 'ratio_backspread_put',
    'long_calendar_puts', 'bear_condor', 'bear_butterfly', 'risk_reversal', 'synthetic_short'] },
  { key: 'neutral', title: 'Neutral', views: ['range-bound'], ids: ['short_straddle', 'iron_butterfly', 'short_strangle', 'iron_condor', 'batman',
    'double_plateau', 'jade_lizard', 'reverse_jade_lizard'] },
  { key: 'other', title: 'Others', views: ['volatile'], ids: ['call_ratio_spread', 'put_ratio_spread', 'long_straddle', 'long_iron_butterfly',
    'long_strangle', 'reverse_iron_condor', 'strip', 'strap'] },
]

const homeGroup = (t) => {
  const listed = VIEW_GROUPS.find((g) => g.ids.includes(t.id))
  if (listed) return listed
  const views = Array.isArray(t.views) ? t.views : []
  for (const v of views) {
    const g = VIEW_GROUPS.find((x) => x.views.includes(v))
    if (g) return g
  }
  return VIEW_GROUPS[VIEW_GROUPS.length - 1] // an unknown view is shown, never dropped
}

/** The templates of one group: the group's own list in its order, then the unlisted ones in catalogue order. A template is in exactly one group. */
export function templatesInGroup(templates, group) {
  const list = Array.isArray(templates) ? templates : []
  const mine = list.filter((t) => homeGroup(t) === group)
  const rank = (t) => group.ids.indexOf(t.id)
  const listed = mine.filter((t) => rank(t) >= 0).sort((x, y) => rank(x) - rank(y))
  return [...listed, ...mine.filter((t) => rank(t) < 0)]
}

/** GC-UI D-C02 (Sensibull 116, 037): the hint line under the tabs and the link to our Learn pages. Product words, owner to read. */
export const READY_MADE_HINT = 'Please click on a ready-made strategy to load it'
export const LEARN_LINK_TEXT = 'Learn Options Strategies'
export const LEARN_PATH = '/learn/strategy-education'

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
