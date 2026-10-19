// W-119 (REQ-024, REQ-026, REQ-028; ADR-003, ADR-008): the Guided Strategy Builder's choices and its pure helpers.
// Nothing here computes money: index levels and strikes are only SELECTED from the catalogue (grid values come from the
// grid), and every max profit / max loss / breakeven comes from the server engine (POST /api/strategies/outcome).

/** REQ-024 AC-6, verbatim. */
export const PATHS = Object.freeze([
  { key: 'guided', title: 'Guided Strategy Builder', subtitle: 'Help me build a strategy' },
  { key: 'advanced', title: 'Advanced Manual Builder', subtitle: 'I know what I want' },
])

/** REQ-024 AC-3, verbatim labels; each maps to the catalogue's own `objectives` / `views` tags (REQ-028: templates are data). */
export const OBJECTIVES = Object.freeze([
  { key: 'earn-premium', label: 'Earn premium', match: { objective: 'income' } },
  { key: 'limit-risk', label: 'Limit risk', match: { objective: 'hedge' } },
  { key: 'rises', label: 'Benefit if market rises', match: { view: 'bullish' } },
  { key: 'falls', label: 'Benefit if market falls', match: { view: 'bearish' } },
  { key: 'big-move', label: 'Trade a big move', match: { view: 'volatile' } },
  { key: 'know', label: 'I already know my strategy', match: null },
])

/** REQ-024 AC-7, the simple market views; 'not-sure' leads to the range flow (REQ-026 AC-1). */
export const MARKET_VIEWS = Object.freeze([
  { key: 'bullish', label: 'Bullish', tag: 'bullish' },
  { key: 'bearish', label: 'Bearish', tag: 'bearish' },
  { key: 'neutral', label: 'Neutral', tag: 'range-bound' },
  { key: 'big-move', label: 'Big move', tag: 'volatile' },
  { key: 'not-sure', label: 'Not sure', tag: null },
])

export const LEVEL_ORDER = ['Beginner', 'Intermediate', 'Advanced']
/** REQ-026 AC-5: list step and the Admin-setting defaults (NIFTY 3,000 / SENSEX 9,000 points; no Admin screen yet). */
export const RANGE_STEP = 100
export const RANGE_CAP = Object.freeze({ NIFTY: 3000, SENSEX: 9000 })
/** How many cards show before 'See more' (REQ-024 AC-8: 2-4). */
export const CARDS_SHOWN = 4

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const dayMonth = (iso) => `${Number(iso.slice(8, 10))} ${MONTHS[Number(iso.slice(5, 7)) - 1]}`

/** REQ-026 AC-2: expiries as real dates with labels ('This Week — 24 Sep', 'Next Week', 'Monthly', 'Next Monthly').
 *  An expiry is monthly when no later expiry falls in the same month. `isoDates` are sorted ascending. */
export function expiryLabels(isoDates) {
  let monthlySeen = 0
  return isoDates.map((iso, i) => {
    const monthly = !isoDates.some((o) => o > iso && o.slice(0, 7) === iso.slice(0, 7))
    let label = null
    if (monthly) {
      monthlySeen += 1
      label = monthlySeen === 1 ? 'Monthly' : monthlySeen === 2 ? 'Next Monthly' : null
    } else {
      label = i === 0 ? 'This Week' : i === 1 ? 'Next Week' : null
    }
    return { value: iso, label: label ? `${label} — ${dayMonth(iso)}` : dayMonth(iso) }
  })
}

/** Listed option strikes of the chosen expiry, ascending, as numbers (for selection only). */
export function listedStrikes(contracts) {
  return [...new Set(contracts.filter((c) => c.strike !== null && c.instrument_type !== 'FUT').map((c) => Number(c.strike)))]
    .sort((a, b) => a - b)
}

/** REQ-026 AC-3/AC-5/AC-6: the lower list holds the current level and every listed 100-point strike below it, the upper
 *  list the current level and every one above, out to the furthest listed strike, capped per index. Values are strings. */
export function rangeLists(currentText, contracts, underlying) {
  const current = Number(currentText)
  const cap = RANGE_CAP[underlying]
  if (currentText === null || !Number.isFinite(current) || cap === undefined) throw new Error('no current level') // fail closed
  const grid = listedStrikes(contracts).filter((s) => s % RANGE_STEP === 0 && Math.abs(s - current) <= cap)
  return {
    lower: [currentText, ...grid.filter((s) => s < current).reverse().map(String)],
    upper: [currentText, ...grid.filter((s) => s > current).map(String)],
  }
}

/** The market view a chosen range implies (REQ-026 AC-1 "the platform derives the market characteristics"). Provisional
 *  rule, not in the spec: one side more than twice the other is directional, otherwise range-bound. */
export function viewFromRange(currentText, lowerText, upperText) {
  const c = Number(currentText)
  const down = c - Number(lowerText)
  const up = Number(upperText) - c
  if (down < 0 || up < 0) throw new Error('range must hold the current level') // REQ-026 AC-6
  if (up > 2 * down) return 'bullish'
  if (down > 2 * up) return 'bearish'
  return 'range-bound'
}

/** Templates matching the objective and the view, Beginner first (REQ-068 AC-2 levels). `fallback` says nothing matched
 *  both and the list is the view's alone (REQ-068 AC-4: if none fit, say so). */
export function matchTemplates(templates, objectiveKey, viewTag) {
  const objective = OBJECTIVES.find((o) => o.key === objectiveKey)
  if (!objective) throw new Error('unknown objective')
  const byLevel = (list) => [...list].sort((a, b) => LEVEL_ORDER.indexOf(a.level) - LEVEL_ORDER.indexOf(b.level))
  if (objective.match === null) return { list: byLevel(templates), fallback: false }
  const fitsObjective = (t) => (objective.match.objective ? t.objectives.includes(objective.match.objective)
    : t.views.includes(objective.match.view))
  const fitsView = (t) => viewTag === null || t.views.includes(viewTag)
  const both = templates.filter((t) => fitsObjective(t) && fitsView(t))
  if (both.length) return { list: byLevel(both), fallback: false }
  return { list: byLevel(templates.filter(fitsView)), fallback: true }
}

/** One template's default legs on the chosen expiry: ATM is the listed strike nearest the current level, a step is the
 *  smallest gap between listed strikes. Returns null when any leg is not a listed near-expiry option (never substituted,
 *  ADR-018). */
export function expandTemplate(template, contracts, currentText) {
  const strikes = listedStrikes(contracts)
  const current = Number(currentText)
  if (!strikes.length || currentText === null || !Number.isFinite(current) || !Array.isArray(template.legs)) return null
  const gaps = strikes.slice(1).map((s, i) => s - strikes[i]).filter((g) => g > 0)
  const step = gaps.length ? Math.min(...gaps) : null
  const atm = strikes.reduce((best, s) => (Math.abs(s - current) < Math.abs(best - current) ? s : best), strikes[0])
  const legs = []
  for (const leg of template.legs) {
    if (leg.instrument === 'FUT' || leg.expiry_slot !== 'near' || leg.strike_steps === null) return null
    if (step === null && leg.strike_steps !== 0) return null
    const strike = atm + leg.strike_steps * (step ?? 0)
    const c = contracts.find((x) => x.instrument_type === leg.instrument && x.strike !== null && Number(x.strike) === strike)
    if (!c) return null
    legs.push({ instrument_id: `${c.exchange_segment}:${c.exchange_token}`, action: leg.action, lots: leg.quantity_multiplier,
      symbol: c.symbol, instrument_type: c.instrument_type, strike: c.strike, expiry: c.expiry })
  }
  return legs
}

/** ADR-003: words a guided screen must never show. */
export const FORBIDDEN_WORDS = ['you should', 'best', 'recommended trade', 'guaranteed', 'top pick']
