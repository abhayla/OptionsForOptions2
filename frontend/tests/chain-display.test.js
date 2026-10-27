// Row 33 attack 5 (REQ-029 AC-2/AC-3, ADR-168): the column set is one for every user; Details adds AC-3's fields.
import { describe, expect, it } from 'vitest'
import { DEFAULT_FIELDS, DETAIL_FIELDS, fieldsFor, filterRows, rowPasses } from '@/lib/chainDisplay'

const labels = (fields) => fields.map(([, label]) => label)
const cell = (over = {}) => ({ ltp: '10.00', bid: null, ask: null, oi: '100', volume: '5', ...over })
const row = (strike, ce = {}, pe = {}) => ({ strike, ce: cell(ce), pe: cell(pe) })

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

describe('chain filters (display only)', () => {
  const rows = [
    row('100.00', { oi: '50' }, { oi: '20' }),
    row('150.00', { oi: '900', bid: '9.90', ask: '10.10' }),
    row('200.00', { ltp: null, oi: null }, { ltp: '1.00', oi: '10' }),
  ]
  it('moneyness reads the calls\' side against the server ATM; no ATM hides nothing', () => {
    expect(filterRows(rows, { moneyness: 'ITM' }, '150.00').map((r) => r.strike)).toEqual(['100.00'])
    expect(filterRows(rows, { moneyness: 'ATM' }, '150.00').map((r) => r.strike)).toEqual(['150.00'])
    expect(filterRows(rows, { moneyness: 'OTM' }, '150.00').map((r) => r.strike)).toEqual(['200.00'])
    expect(filterRows(rows, { moneyness: 'ITM' }, null)).toHaveLength(3)
  })
  it('a numeric minimum passes when either side meets it; a missing value never meets it', () => {
    expect(filterRows(rows, { minOi: '60' }, null).map((r) => r.strike)).toEqual(['150.00'])
    expect(filterRows(rows, { minLtp: '5' }, null).map((r) => r.strike)).toEqual(['100.00', '150.00'])
    expect(filterRows(rows, { bidAndAsk: true }, null).map((r) => r.strike)).toEqual(['150.00'])
    expect(rowPasses(rows[2], { minOi: '11' }, null)).toBe(false)
  })
  it('filtering never changes a row or a value', () => {
    const before = JSON.stringify(rows)
    const out = filterRows(rows, { minOi: '1', minVolume: '1' }, '150.00')
    expect(out[0]).toBe(rows[0])
    expect(JSON.stringify(rows)).toBe(before)
  })
})
