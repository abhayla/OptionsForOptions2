// REQ-109 AC-5: a PAUSED paper book prints "<sentence>, as of <time>" from the server's as_of / totals_as_of; no time is
// never replaced by a made-up one. REAL is the route's own paused reply (tests/fixtures/paper-list-r19b/paused.json).
import { describe, it, expect } from 'vitest'
import REAL from './fixtures/paper-list-r19b/paused.json'
import { readPaperList, withAsOf, PAPER_PAUSED, PAPER_NOT_CONNECTED } from '@/lib/paperList'
import { istTime } from '@/lib/displayFormat'

const AT = '2026-10-08T03:49:00Z'
const clone = () => JSON.parse(JSON.stringify(REAL))
const first = (d) => readPaperList(d).groups[0]

describe('REQ-109 AC-5: paused text carries the quote time', () => {
  it('time known: the card state text and the reason print the sentence, as of the IST time', () => {
    const d = clone()
    d.strategies[0].as_of = AT
    const g = first(d)
    expect(g.stateText).toBe(`${PAPER_PAUSED}, as of ${istTime(AT)}`)
    expect(g.pauseReason).toBe(`${d.strategies[0].pause_reason_text}, as of ${istTime(AT)}`)
    expect(istTime(AT)).toMatch(/09:19:00 IST$/)
  })
  it('no known quote time (null): the sentence as sent, no time', () => {
    const d = clone()
    d.strategies[0].as_of = null
    const g = first(d)
    expect(g.stateText).toBe(PAPER_PAUSED)
    expect(g.pauseReason).toBe(d.strategies[0].pause_reason_text)
  })
  it('unreadable time: no made-up time', () => {
    expect(withAsOf('x', 'not a time')).toBe('x')
    expect(withAsOf(null, AT)).toBe(null)
  })
  it('book not paused: an as_of is never printed', () => {
    const d = clone()
    Object.assign(d.strategies[0], { state: 'LIVE', as_of: AT })
    expect(first(d).stateText).toBe('')
    expect(first(d).pauseReason).toBe(d.strategies[0].pause_reason_text)
  })
  it('NOT_CONNECTED keeps its current text (no time)', () => {
    const d = clone()
    Object.assign(d.strategies[0], { state: 'NOT_CONNECTED', as_of: null })
    expect(first(d).stateText).toBe(PAPER_NOT_CONNECTED)
  })
  it('totals strip: the totals reason carries totals_as_of', () => {
    const d = clone()
    Object.assign(d.totals, { totals_reason_text: PAPER_PAUSED, totals_as_of: AT })
    expect(readPaperList(d).totals.totalReason).toBe(`${PAPER_PAUSED}, as of ${istTime(AT)}`)
    d.totals.totals_as_of = null
    expect(readPaperList(d).totals.totalReason).toBe(PAPER_PAUSED)
  })
})
