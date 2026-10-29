// W-072 / REQ-039 AC-3 under ADR-086: the one contract-name formatter and the one India-time formatter.
// Run once with TZ=America/New_York as well: the output must not move with the machine's zone.
import { describe, it, expect } from 'vitest'
import { CONTRACT_UNAVAILABLE, TIME_UNAVAILABLE, contractName, istTime, nameFromPool, strikeLabel, groupMoney } from '@/lib/displayFormat'

const ce = { underlying: 'NIFTY', expiry: '2026-10-19', strike: '23200.00', instrument_type: 'CE', instrument_id: 'NSE_FO:47171', symbol: 'NIFTY26O1923200CE' }

describe('contractName', () => {
  it('names a CE by underlying, day, short month, strike and type (the ADR example)', () => {
    expect(contractName(ce)).toBe('NIFTY 19 Oct 23200 CE')
  })
  it('never shows the instrument id or the broker trading symbol', () => {
    expect(contractName(ce)).not.toContain('NSE_FO')
    expect(contractName(ce)).not.toContain('NIFTY26O')
  })
  it('keeps a real fraction of a strike and drops only a zero fraction', () => {
    expect(contractName({ ...ce, strike: '23212.50' })).toBe('NIFTY 19 Oct 23212.5 CE')
    expect(contractName({ ...ce, strike: '23200' })).toBe('NIFTY 19 Oct 23200 CE')
  })
  it('a PE and a FUT (no strike)', () => {
    expect(contractName({ ...ce, instrument_type: 'PE', strike: '22400.00' })).toBe('NIFTY 19 Oct 22400 PE')
    expect(contractName({ underlying: 'SENSEX', expiry: '2026-10-27', strike: null, instrument_type: 'FUT' })).toBe('SENSEX 27 Oct FUT')
  })
  it('reads the type from `instrument` on an outcome answer leg', () => {
    expect(contractName({ underlying: 'NIFTY', expiry: '2026-10-13', strike: '22800.00', instrument: 'CE' })).toBe('NIFTY 13 Oct 22800 CE')
  })
  it('a leg missing a field shows the fixed wording, never the id', () => {
    for (const bad of [{ ...ce, expiry: null }, { ...ce, strike: null }, { ...ce, instrument_type: undefined }, { instrument_id: 'NSE_FO:47171' }, null]) {
      expect(contractName(bad)).toBe(CONTRACT_UNAVAILABLE)
    }
  })
})

describe('nameFromPool', () => {
  const answerLeg = { instrument_id: 'NSE_FO:47171', symbol: 'NIFTY26O1923200CE', instrument: null, strike: null, expiry: null }
  it('fills the missing fields from the page draft legs by instrument id', () => {
    expect(nameFromPool(answerLeg, [ce], 'NIFTY')).toBe('NIFTY 19 Oct 23200 CE')
  })
  it('a draft-URL leg (no contract fields) is named from the answer leg and the answer underlying', () => {
    const draftLeg = { instrument_id: 'NSE_FO:47171', action: 'SELL', lots: 1 }
    const answer = { instrument_id: 'NSE_FO:47171', instrument: 'CE', strike: '23200.00', expiry: '2026-10-19' }
    expect(nameFromPool(answer, [draftLeg], 'NIFTY')).toBe('NIFTY 19 Oct 23200 CE')
    expect(nameFromPool({ ...answer, expiry: null }, [draftLeg], 'NIFTY')).toBe(CONTRACT_UNAVAILABLE)
  })
  it('still missing after the lookup: the fixed wording', () => {
    expect(nameFromPool(answerLeg, [], 'NIFTY')).toBe(CONTRACT_UNAVAILABLE)
  })
})

describe('istTime', () => {
  it('shows an instant with an offset in India time with seconds and the word IST', () => {
    expect(istTime('2026-10-15T11:59:59.362869+05:30')).toBe('15 Oct 2026, 11:59:59 IST')
  })
  it('converts a UTC instant to India time whatever the machine zone', () => {
    expect(istTime('2026-10-15T06:29:59Z')).toBe('15 Oct 2026, 11:59:59 IST')
    expect(istTime('2026-10-15T20:00:00-04:00')).toBe('16 Oct 2026, 05:30:00 IST') // crosses midnight in India
  })
  it('September is Sep, a single-digit day has no leading zero', () => {
    expect(istTime('2026-09-03T09:15:00+05:30')).toBe('3 Sep 2026, 09:15:00 IST')
  })
  it('an unparseable value, or one with no zone, shows the fixed wording, never the raw string', () => {
    for (const bad of ['not a time', '', null, undefined, '2026-10-15T11:59:59', '2026-13-45T99:99:99+05:30']) {
      expect(istTime(bad)).toBe(TIME_UNAVAILABLE)
    }
  })
})

import { daysByExpiry, expiryWithDays } from '@/lib/displayFormat'
describe('REQ-135 AC-2: expiryWithDays prints the server\'s count and counts nothing', () => {
  it('prints the day count as sent, "Today (0 days)" for 0, the date as sent for a missing or unreadable count', () => {
    expect(expiryWithDays('2026-10-27', 6)).toBe('27 Oct (6 days)')
    expect(expiryWithDays('2026-10-21', 0)).toBe('Today (0 days)')
    // REQ-148 AC-2 (G-065): no count from the server -> the date alone, never the raw ISO text and never a count
    expect(expiryWithDays('2026-10-27', null)).toBe('27 Oct')
    expect(expiryWithDays('2026-10-27', undefined)).toBe('27 Oct')
    expect(expiryWithDays('2026-10-27', '6')).toBe('27 Oct') // a string is not a count
    expect(expiryWithDays('2026-10-27', -1)).toBe('27 Oct')
    expect(expiryWithDays('2026-11-09', 13)).toBe('9 Nov (13 days)') // the moved leg of G-065
    expect(expiryWithDays('2026-11-09', null)).not.toMatch(/2026/)
    expect(expiryWithDays(null, 3)).toBe('')
    expect(daysByExpiry([{ expiry: '2026-10-27', days: 6 }, { days: 1 }])).toEqual({ '2026-10-27': 6 })
    expect(daysByExpiry(undefined)).toEqual({})
  })
})

describe('strikeLabel (#582 item 8: strikes print as Sensibull prints them)', () => {
  it("drops a whole-number strike's decimals and keeps a real fraction", () => {
    expect(strikeLabel('22150.00')).toBe('22150')
    expect(strikeLabel('22150.50')).toBe('22150.5')
    expect(strikeLabel('22150.25')).toBe('22150.25')
    expect(strikeLabel('22150')).toBe('22150')
  })
  it('returns empty, null and non-numeric input unchanged', () => {
    expect(strikeLabel('')).toBe('')
    expect(strikeLabel(null)).toBe(null)
    expect(strikeLabel(undefined)).toBe(undefined)
    expect(strikeLabel('abc')).toBe('abc')
    expect(strikeLabel('-')).toBe('-')
  })
})

describe('groupMoney edge cases (#582 item 3)', () => {
  it('groups a negative figure, leaves an empty string and null alone', () => {
    expect(groupMoney('-12345.60')).toBe('-12,345.60')
    expect(groupMoney('12345.60')).toBe('12,345.60')
    expect(groupMoney('')).toBe('')
    expect(groupMoney(null)).toBe(null)
  })
})
