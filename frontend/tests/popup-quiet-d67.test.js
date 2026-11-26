// D-67 (ADR-326 (5)): the SERVER says when an adjustment pop-up is due (record.popup_due); the browser raises the toast
// only for a due record and keeps counting every open record in the bell. Real case 23 Nov 2026: condor C10 (strategy
// 166, gamma 2.95 % vs 2 %) and C11 (167, tested delta 0.3809 vs 0.35) popped up 1 to 3 minutes after opening.
import { describe, it, expect, beforeEach } from 'vitest'
import { openRecords, resetOpenRecords, takeOpportunities, bellCount, resetPaperAlerts } from '@/lib/paperAlerts'

const rec = (id, due, outcome = 'open') => ({ id, outcome, condition: `rule ${id}`, popup_due: due })
const reply = (...recs) => ({ groups: [{ group: 'g', strategy_id: 166, strategy_name: 'C10', records: recs }] })

beforeEach(() => {
  resetPaperAlerts()
  resetOpenRecords()
})

describe('the toast waits for the server\'s popup_due', () => {
  it('a record quiet on a later poll raises nothing, but the bell counts it', () => {
    takeOpportunities(reply())
    const fresh = takeOpportunities(reply(rec(1, false)))
    expect(fresh).toEqual([])
    expect(openRecords.list).toHaveLength(1)
    expect(bellCount()).toBe(1)
  })
  it('the same record raises exactly once when the server turns it due, and not again', () => {
    takeOpportunities(reply())
    takeOpportunities(reply(rec(1, false)))
    expect(takeOpportunities(reply(rec(1, true))).map((r) => r.id)).toEqual([1])
    expect(takeOpportunities(reply(rec(1, true)))).toEqual([])
  })
  it('a record already due raises at once on a later poll (rule true after entry)', () => {
    takeOpportunities(reply())
    expect(takeOpportunities(reply(rec(2, true))).map((r) => r.id)).toEqual([2])
  })
  it('first read never raises, a quiet record on it raises when due later', () => {
    expect(takeOpportunities(reply(rec(1, true), rec(2, false)))).toEqual([])
    expect(takeOpportunities(reply(rec(1, true), rec(2, true))).map((r) => r.id)).toEqual([2])
  })
  it('a reply without the field (entry time unknown) is due: fail open toward telling the trader', () => {
    takeOpportunities(reply())
    const bare = { id: 3, outcome: 'open', condition: 'rule 3' }
    expect(takeOpportunities(reply(bare)).map((r) => r.id)).toEqual([3])
  })
  it('a record that cleared while quiet never raises', () => {
    takeOpportunities(reply())
    takeOpportunities(reply(rec(1, false)))
    expect(takeOpportunities(reply(rec(1, false, 'lapsed')))).toEqual([])
    expect(bellCount()).toBe(0)
  })
})
