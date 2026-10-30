// Adjust mode of the Strategy Builder (GC-ADJ1 step 3; REQ-156 AC-1..AC-5, REQ-157 AC-1..AC-5; ADR-214 (2a), (2b), ADR-003, ADR-008).
// Pure helpers for the approach compare. Every figure shown is a string the route reply sent. Nothing here computes
// money: the filters COMPARE two decimal texts (cmpDecimal, string rules only), they never add, multiply or round.
// New file; the legacy autopilot adjustment screens compute client P&L and are REFERENCE only (not copied).

export const NO_CHANGE_ID = 'no_change'
export const UNAVAILABLE_FOR_FILTER = 'not available for this filter'
export const UNAVAILABLE_VALUE = '-'

// The criteria the filters read when the approach itself does not carry the figure (ids as the route's `criteria` names them).
export const CRITERION = Object.freeze({ cash: 'credit_debit', cost: 'charges_bidask' })

export const GROUP_TITLES = Object.freeze({
  money_now: 'Money now',
  risk_after: 'Risk after (at expiry, whole trade)',
  reward_after: 'Reward after',
  greeks_after: 'Greeks after (whole position)',
  practical: 'Practical',
})

export const KIND_TITLES = Object.freeze({ roll: 'Roll', reduce: 'Reduce', close_part: 'Close part', convert: 'Convert or re-centre', recentre: 'Convert or re-centre', exit: 'Exit' })
export const SIDE_TITLES = Object.freeze({ call: 'Call', put: 'Put', both: 'Both' })
export const KIND_ORDER = Object.freeze(['roll', 'reduce', 'close_part', 'convert', 'recentre', 'exit'])
export const SIDE_ORDER = Object.freeze(['call', 'put', 'both'])
export const RISK_CHIPS = Object.freeze([
  { id: 'capped', label: 'Loss capped' },
  { id: 'uncapped', label: 'Loss not capped' },
  { id: 'credit', label: 'Credit' },
  { id: 'debit', label: 'Debit' },
])
// at: 'most' keeps values at or under the chosen limit, 'least' keeps values at or over it (REQ-157 AC-1).
export const RANGES = Object.freeze([
  { id: 'debit', label: 'Largest debit I accept', at: 'most' },
  { id: 'max_loss', label: 'Max loss at most', at: 'most' },
  { id: 'pop', label: 'Chance of profit at least', at: 'least' },
  { id: 'charges', label: 'Charges + bid-ask at most', at: 'most' },
  { id: 'orders', label: 'Orders to place at most', at: 'most' },
])

const DEC = /^-?\d+(\.\d+)?$/

/** Compares two plain decimal texts by string rules (sign, integer digits, then digits): -1, 0, 1; null when either is not a
 *  plain decimal. No number is parsed (ADR-008), so no digit is lost and nothing is computed. */
export function cmpDecimal(a, b) {
  const x = String(a ?? '').replace(/,/g, '').trim()
  const y = String(b ?? '').replace(/,/g, '').trim()
  if (!DEC.test(x) || !DEC.test(y)) return null
  const neg = (t) => t.startsWith('-')
  const body = (t) => {
    const [i, f = ''] = (neg(t) ? t.slice(1) : t).split('.')
    return [i.replace(/^0+(?=\d)/, ''), f.replace(/0+$/, '')]
  }
  const [xi, xf] = body(x)
  const [yi, yf] = body(y)
  const zero = (i, f) => i === '0' && f === ''
  const xs = zero(xi, xf) ? 0 : neg(x) ? -1 : 1
  const ys = zero(yi, yf) ? 0 : neg(y) ? -1 : 1
  if (xs !== ys) return xs < ys ? -1 : 1
  if (xs === 0) return 0
  let m = 0
  if (xi.length !== yi.length) m = xi.length < yi.length ? -1 : 1
  else if (xi !== yi) m = xi < yi ? -1 : 1
  else {
    const w = xf.length > yf.length ? xf.length : yf.length
    const a2 = xf.padEnd(w, '0')
    const b2 = yf.padEnd(w, '0')
    m = a2 === b2 ? 0 : a2 < b2 ? -1 : 1
  }
  return xs < 0 ? -m : m
}

/** The smallest and largest of some decimal texts, as the texts themselves; null for an empty list. */
export function spanOf(values) {
  const ok = values.filter((v) => cmpDecimal(v, v) !== null)
  if (!ok.length) return null
  const sorted = [...ok].sort((p, q) => cmpDecimal(p, q))
  return { min: sorted[0], max: sorted[sorted.length - 1] }
}

export const isNoChange = (a) => a?.id === NO_CHANGE_ID
export const isRefused = (a) => typeof a?.refusal === 'string' && a.refusal !== ''

/** REQ-156 AC-1 / AC-4: the approaches in the table: No change first, then the reply's own (catalogue) order; refused ones
 *  are left out (they are listed apart). Never sorted by Leads on. */
export function tableApproaches(reply) {
  const list = (reply?.approaches ?? []).filter((a) => !isRefused(a))
  return [...list.filter(isNoChange), ...list.filter((a) => !isNoChange(a))]
}
export const refusedApproaches = (reply) => (reply?.approaches ?? []).filter(isRefused)

const criterionValue = (criteria, id, approachId) => {
  const v = criteria?.find((c) => c.id === id)?.values?.[approachId]
  return v && v.unavailable_reason == null && v.value != null && cmpDecimal(v.value, v.value) !== null ? v.value : undefined
}

/** The figure a range filter reads for one approach, as text, or undefined when the reply gives none ("not available").
 *  debit: the debit as a positive text, or null for a credit (a credit passes a debit limit). */
export function filterValue(reply, a, rangeId) {
  const whole = a.after?.after_charges ?? a.after?.gross
  switch (rangeId) {
    case 'debit': {
      const cash = criterionValue(reply.criteria, CRITERION.cash, a.id)
      if (cash === undefined) return undefined
      return cash.startsWith('-') ? cash.slice(1) : null
    }
    case 'max_loss':
      return whole ? whole.max_loss : undefined // 'UNLIMITED' is a known answer, not a number
    case 'pop':
      return a.pop && !a.pop.not_available && a.pop.value != null ? a.pop.value : undefined
    case 'charges':
      return criterionValue(reply.criteria, CRITERION.cost, a.id) ?? (a.charges?.this_adjustment ?? undefined)
    case 'orders':
      return Array.isArray(a.trades) ? String(a.trades.length) : undefined // a count of orders, not money
    default:
      return undefined
  }
}

/** 'capped' | 'uncapped' | undefined, and 'credit' | 'debit' | undefined, from the reply's own figures. */
export function riskFacts(reply, a) {
  const whole = a.after?.after_charges ?? a.after?.gross
  const cash = criterionValue(reply.criteria, CRITERION.cash, a.id)
  return {
    cap: whole ? (whole.max_loss === 'UNLIMITED' ? 'uncapped' : 'capped') : undefined,
    flow: cash === undefined ? undefined : cash.startsWith('-') ? 'debit' : 'credit',
  }
}

/** REQ-157 AC-2: the choices and ranges, built only from the approaches the filters act on (all but No change). */
export function buildFacets(reply) {
  const subject = tableApproaches(reply).filter((a) => !isNoChange(a))
  const count = (pick, order) => {
    const found = new Map()
    for (const a of subject) {
      const k = pick(a)
      if (k != null) found.set(k, (found.get(k) ?? 0) + 1)
    }
    const known = order.filter((k) => found.has(k))
    const rest = [...found.keys()].filter((k) => !order.includes(k))
    return [...known, ...rest].map((id) => ({ id, count: found.get(id) }))
  }
  const risk = RISK_CHIPS.map((c) => ({ ...c, count: subject.filter((a) => { const f = riskFacts(reply, a); return f.cap === c.id || f.flow === c.id }).length })).filter((c) => c.count > 0)
  const ranges = {}
  for (const r of RANGES) {
    const span = spanOf(subject.map((a) => filterValue(reply, a, r.id)).filter((v) => v != null && v !== 'UNLIMITED'))
    if (span) ranges[r.id] = span
  }
  return {
    kinds: count((a) => a.kind, KIND_ORDER),
    sides: count((a) => a.side, SIDE_ORDER),
    risk,
    ranges,
  }
}

export const EMPTY_FILTERS = () => ({ kinds: [], sides: [], risk: [], limits: {} })
export const filtersActive = (f) => f.kinds.length > 0 || f.sides.length > 0 || f.risk.length > 0 || Object.keys(f.limits).length > 0

/** The result of the filters for one approach: { kept, unavailable } where `unavailable` lists the active filters the reply
 *  gives no value for (the approach stays shown, marked, REQ-157 AC-4). No change is always kept (AC-3). */
export function judge(reply, a, f) {
  if (isNoChange(a)) return { kept: true, unavailable: [] }
  const unavailable = []
  let kept = true
  const choice = (selected, value, name) => {
    if (!selected.length) return
    if (value == null) unavailable.push(name)
    else if (!selected.includes(value)) kept = false
  }
  choice(f.kinds, a.kind, 'kind')
  choice(f.sides, a.side, 'side')
  const facts = riskFacts(reply, a)
  choice(f.risk.filter((r) => r === 'capped' || r === 'uncapped'), facts.cap, 'loss')
  choice(f.risk.filter((r) => r === 'credit' || r === 'debit'), facts.flow, 'credit or debit')
  for (const r of RANGES) {
    const limit = f.limits[r.id]
    if (limit == null) continue
    const v = filterValue(reply, a, r.id)
    if (v === undefined) unavailable.push(r.id)
    else if (v === null) continue // a credit under a debit limit
    else if (v === 'UNLIMITED') kept = false
    else {
      const c = cmpDecimal(v, limit)
      if (c !== null && (r.at === 'most' ? c > 0 : c < 0)) kept = false
    }
  }
  return { kept, unavailable }
}

/** The approaches the filters keep (table order), each with its unavailable-filter list. */
export function applyFilters(reply, f) {
  return tableApproaches(reply).map((a) => ({ a, ...judge(reply, a, f) })).filter((x) => x.kept)
}

export const showingText = (shown, total) => `Showing ${shown} of ${total} approaches`

/** The legs of one approach as builder legs: each after-leg is matched to the catalogue contract with the same trading symbol
 *  (the catalogue answer of its expiry); the price is the approach's own entry. Null when any leg has no contract (fail closed). */
export function legsFromApproach(underlying, approach, contracts, capturedAt) {
  const bySymbol = new Map(contracts.map((c) => [c.symbol, c]))
  const out = []
  for (const [i, l] of (approach.after_legs ?? []).entries()) {
    const c = bySymbol.get(l.tradingsymbol)
    if (!c) return null
    out.push({
      id: `adjust-${i}`,
      underlying,
      instrument_id: `${c.exchange_segment}:${c.exchange_token}`,
      contract_id: c.contract_id,
      symbol: c.symbol,
      expiry: c.expiry,
      instrument_type: c.instrument_type,
      strike: c.strike,
      lot_size: c.lot_size,
      action: l.side,
      lots: l.lots,
      planned_entry: l.entry,
      captured_at: capturedAt ?? null,
      source: null,
      reason_code: capturedAt ? null : 'needs_reprice',
    })
  }
  return out.length ? out : null
}
