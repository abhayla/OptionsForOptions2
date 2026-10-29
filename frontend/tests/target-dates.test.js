// GC-TP step 6b (REQ-084 AC-2): the date slider's stops, built from the real reply's valuation time and first expiry
// (tests/fixtures/outcome-target.json: valued 2026-10-08 09:20:09 IST, first expiry 2026-10-13).
import { describe, expect, it } from 'vitest'
import mid from './fixtures/outcome-target.json'
import { dateStops, debounced, firstExpiry, targetFields } from '@/lib/targetBlock'

const stops = dateStops(mid.valuation, firstExpiry(mid.legs))

describe('date stops', () => {
  it('start at the reply valuation, go daily to the expiry day, then 15-minute steps to 15:30 IST', () => {
    expect(firstExpiry(mid.legs)).toBe('2026-10-13')
    expect(stops[0]).toBe(mid.valuation)
    expect(stops.slice(1, 5)).toEqual(['2026-10-09', '2026-10-10', '2026-10-11', '2026-10-12'].map((d) => `${d}T09:20:00+05:30`))
    expect(stops[5]).toBe('2026-10-13T09:15:00+05:30')
    expect(stops[6]).toBe('2026-10-13T09:30:00+05:30')
    expect(stops.at(-1)).toBe('2026-10-13T15:30:00+05:30')
    expect(stops).toHaveLength(1 + 4 + 26)
  })
  it('a valuation on the expiry day itself only has the later 15-minute steps; none past the close', () => {
    const same = dateStops('2026-10-13T10:07:00+05:30', '2026-10-13')
    expect(same[1]).toBe('2026-10-13T10:15:00+05:30')
    expect(dateStops('2026-10-13T16:00:00+05:30', '2026-10-13')).toEqual(['2026-10-13T16:00:00+05:30'])
    expect(dateStops(undefined, '2026-10-13')).toEqual([])
    expect(dateStops(mid.valuation, null)).toEqual([])
  })
})

describe('request fields', () => {
  it('nothing moved sends nothing; only the moved fields go out', () => {
    expect(targetFields({ level: '', dateIndex: 0 }, stops)).toEqual({})
    expect(targetFields(undefined, stops)).toEqual({})
    expect(targetFields({ level: '22300', dateIndex: 0 }, stops)).toEqual({ target_level: '22300' })
    expect(targetFields({ level: '', dateIndex: 2 }, stops)).toEqual({ target_at: stops[2] })
    expect(targetFields({ level: '22300', dateIndex: 2 }, stops)).toEqual({ target_level: '22300', target_at: stops[2] })
  })
})

describe('debounce', () => {
  it('runs once, after the last call', async () => {
    let n = 0
    const d = debounced(() => { n += 1 }, 20)
    d(); d(); d()
    await new Promise((r) => setTimeout(r, 60))
    expect(n).toBe(1)
  })
})
