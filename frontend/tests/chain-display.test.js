// Row 33 attack 5 (REQ-029 AC-2/AC-3, ADR-168): the column set is one for every user; Details adds AC-3's fields.
import { describe, expect, it } from 'vitest'
import { DEFAULT_FIELDS, DETAIL_FIELDS, GREEK_KEYS, anyServerFilter, fieldsFor, filterParams, filterRows, greeksStaleLabel } from '@/lib/chainDisplay'

const labels = (fields) => fields.map(([, label]) => label)

describe('chain columns (attack 5)', () => {
  it('Details off shows exactly AC-2\'s default columns plus IV', () => {
    expect(labels(fieldsFor(false))).toEqual(['LTP', 'Change', 'OI', 'Volume', 'IV'])
  })
  it('Details on adds Bid, Ask, OI Change, Delta, Gamma, Theta, Vega, keeping IV', () => {
    expect(labels(fieldsFor(true))).toEqual(['LTP', 'Change', 'OI', 'Volume', 'IV', 'Bid', 'Ask', 'OI Change', 'Delta', 'Gamma', 'Theta', 'Vega'])
  })
  it('the set is the same with no level present: a level argument changes nothing (ADR-168)', () => {
    expect(fieldsFor.length).toBe(1)
    for (const level of ['guided', 'standard', 'advanced', undefined]) {
      expect(fieldsFor(false, level)).toEqual(fieldsFor(false))
      expect(fieldsFor(true, level)).toEqual(fieldsFor(true))
    }
    expect(fieldsFor(false)).toEqual(DEFAULT_FIELDS)
    expect(fieldsFor(true)).toEqual([...DEFAULT_FIELDS, ...DETAIL_FIELDS])
  })
})

describe('chain filters (no browser maths, ADR-008)', () => {
  const rows = [{ strike: '100.00', moneyness: 'ITM' }, { strike: '150.00', moneyness: 'ATM' }, { strike: '200.00', moneyness: 'OTM' }]
  it('moneyness matches the server\'s word only; ALL keeps every row, in order, as the same objects', () => {
    expect(filterRows(rows, 'ITM').map((r) => r.strike)).toEqual(['100.00'])
    expect(filterRows(rows, 'ATM').map((r) => r.strike)).toEqual(['150.00'])
    expect(filterRows(rows, 'OTM').map((r) => r.strike)).toEqual(['200.00'])
    expect(filterRows(rows, 'ALL')).toEqual(rows)
    expect(filterRows(rows, 'ALL')[0]).toBe(rows[0])
  })
  it('the numeric filters become request fields, the typed text passed on untouched; unset ones are left out', () => {
    expect(filterParams({})).toEqual({})
    expect(filterParams({ minOi: ' 2000 ', minVolume: '', minLtp: '12.50', bidAndAsk: true }))
      .toEqual({ min_oi: '2000', min_ltp: '12.50', bid_and_ask: true })
    expect(anyServerFilter({ moneyness: 'ITM' })).toBe(false)
    expect(anyServerFilter({ minVolume: '5' })).toBe(true)
  })
})

describe('stale and delayed spot label (REQ-072 AC-2, round 2)', () => {
  const stale = { greeks_label: 'stale since 09:20 IST' }
  const delayed = { greeks_label: 'delayed, as of 09:20 IST' }
  it('every IV and Greek column carries the server\'s label exactly as sent, STALE and DELAYED alike', () => {
    for (const key of GREEK_KEYS) {
      expect(greeksStaleLabel(stale, key)).toBe('stale since 09:20 IST')
      expect(greeksStaleLabel(delayed, key)).toBe('delayed, as of 09:20 IST')
    }
    expect(GREEK_KEYS).toEqual(['iv', 'delta', 'gamma', 'theta', 'vega'])
  })
  it('a live spot (no label), a missing view and the non-Greek columns carry none', () => {
    for (const key of GREEK_KEYS) {
      expect(greeksStaleLabel({ greeks_label: null }, key)).toBe('')
      expect(greeksStaleLabel({}, key)).toBe('')
      expect(greeksStaleLabel(null, key)).toBe('')
    }
    for (const key of ['ltp', 'oi', 'volume', 'bid']) expect(greeksStaleLabel(stale, key)).toBe('')
  })
})
