// Live-push matching (W-073; REQ-035 AC-4, ADR-008, #234 item 1). Pure string functions; no number is ever parsed.
// The server normalizes what it echoes (lots as an int, a planned entry as a two-decimal Money string), so a draft URL
// holding lots "2" or entry "042.70" must still match the echoed legs 2 / "42.70". Anything unparseable is null and
// never matches (fail closed: the page keeps its own REST state).

/** Lots as canonical digit text ("2", 2 and "02" -> "2"), or null when not a whole number of at least 1. */
export function canonicalLots(v) {
  let text
  if (typeof v === 'number') {
    if (!Number.isSafeInteger(v)) return null
    text = String(v)
  } else if (typeof v === 'string') {
    text = v
  } else {
    return null
  }
  if (!/^\d+$/.test(text)) return null
  const stripped = text.replace(/^0+/, '')
  return stripped === '' ? null : stripped
}

/** A planned entry as the API's canonical decimal text: whole part without leading zeros, exactly two decimals
 *  ("042.70" -> "42.70", "5" -> "5.00", "0.1" -> "0.10"). null when it is not a plain decimal of at most two places. */
export function canonicalMoney(v) {
  if (typeof v !== 'string') return null
  const m = /^(\d+)(?:\.(\d{1,2}))?$/.exec(v)
  if (!m) return null
  const whole = m[1].replace(/^0+/, '') || '0'
  const frac = (m[2] ?? '').padEnd(2, '0')
  return `${whole}.${frac}`
}

/** True when a pushed answer belongs to the strategy on screen: same legs (instrument, action, lots, planned entry), in
 *  order, compared on normalized values. */
export function matchesLegs(body, draft) {
  const got = body?.legs
  if (!draft || !Array.isArray(got) || got.length !== draft.legs.length) return false
  return draft.legs.every((l, i) => {
    const g = got[i]
    if (!g) return false
    const lots = canonicalLots(l.lots)
    const entry = canonicalMoney(l.planned_entry)
    if (lots === null || entry === null) return false
    return g.instrument_id === l.instrument_id && g.action === l.action
      && canonicalLots(g.lots) === lots && canonicalMoney(g.planned_entry) === entry
  })
}
