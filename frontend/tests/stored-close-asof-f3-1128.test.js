// Lane F3 I-199 (Lane RA2 note): a book whose state is LIVE with a non-null as_of and no broker session is a stored close: the row prints
// "As of <time>" beside the P&L. A LIVE book with no as_of prints nothing. Real case: T1-20 / the seeded stored close in tests_app
// test_stored_close_paper_pnl_ra2_1128 (state LIVE, as_of = oldest price time).
import { describe, it, expect } from 'vitest'
import REAL from './fixtures/paper-list-r19b/paused.json'
import { readPaperList, STORED_CLOSE_PREFIX } from '@/lib/paperList'
import { istTime } from '@/lib/displayFormat'

const AT = '2026-11-27T10:00:00Z'
const clone = () => JSON.parse(JSON.stringify(REAL))
const first = (d) => readPaperList(d).groups[0]
describe('I-199 stored close prints its time', () => {
  it('LIVE with as_of: "As of <time> IST" in the row state text', () => {
    const d = clone(); Object.assign(d.strategies[0], { state: 'LIVE', as_of: AT })
    expect(first(d).stateText).toBe(`${STORED_CLOSE_PREFIX} ${istTime(AT)}`)
    expect(first(d).stateText).toBe("As of 27 Nov 2026, 15:30:00 IST")
  })
  it('LIVE with no as_of, or an unreadable one: nothing printed', () => {
    const d = clone(); Object.assign(d.strategies[0], { state: 'LIVE', as_of: null })
    expect(first(d).stateText).toBe('')
    Object.assign(d.strategies[0], { as_of: 'garbage' })
    expect(first(d).stateText).toBe('')
  })
  it('PAUSED keeps its paused sentence with the time (not the stored-close line)', () => {
    const d = clone(); Object.assign(d.strategies[0], { state: 'PAUSED', as_of: AT })
    expect(first(d).stateText).toContain('paused')
  })
})
