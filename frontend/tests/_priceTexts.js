// GC-UI D-PX test helper: gives a hand-built or recorded reply the server's two-decimal `*_display` price texts, so a test
// of a screen that prints only those texts has them. The padding below stands in for the SERVER's rounding (the backend
// tests in tests/outcome/test_price_display.py prove the real texts); no screen code does this.
const PRICE_FIELDS = ['ltp', 'planned_entry', 'per_unit', 'bid', 'ask', 'entry_price', 'current_price', 'exit_price']

const twoDecimals = (s) => {
  const m = /^(\d+)(?:\.(\d{1,2}))?$/.exec(s)
  return m ? `${m[1]}.${(m[2] ?? '').padEnd(2, '0')}` : null
}

/** A deep copy where every price field holding a plain decimal string gets `<field>_display` (null beside a null value). */
export function withPriceTexts(value) {
  if (Array.isArray(value)) return value.map(withPriceTexts)
  if (value === null || typeof value !== 'object') return value
  const out = {}
  for (const [k, v] of Object.entries(value)) out[k] = withPriceTexts(v)
  for (const f of PRICE_FIELDS) {
    if (!(f in value)) continue
    if (value[f] === null) out[`${f}_display`] = null
    else if (typeof value[f] === 'string' && twoDecimals(value[f])) out[`${f}_display`] = twoDecimals(value[f])
  }
  return out
}
