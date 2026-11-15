// GC-ICFIX issue 24 (ADR-311, REQ-109 AC-5 as narrowed): one open leg without a price. The totals stay paused (a state, never a
// number); the pause line names the leg; the legs table shows every priced leg's own figure and "no price" (never 0, never a
// blank) for the other. Every text is the server's, printed as sent (ADR-008): nothing is formed here.
import { describe, it, expect } from 'vitest'
import REAL from './fixtures/paper-list-r19b/paused.json'
import { readTracking, sharedTotal } from '@/lib/tracking'
import { readPaperStrategy, readPaperList } from '@/lib/paperList'

const AT = '2026-10-08T03:49:00Z'
const NAMED = 'No price for: NIFTY 13 Oct 23000 CE.'
const leg = (n, extra) => ({
  instrument_id: `NSE_FO:${n}`, action: 'SELL', instrument: 'CE', strike: '22800.00', expiry: '2026-10-13', quantity: 65,
  entry_price_display: '39.15', price_state: 'live', current_price_display: '45.15', exited_at: null, exit_price_display: null,
  pnl_text: '-390.00', pnl_kind: 'unbooked', no_price_text: null, ...extra,
})
const paused = () => ({
  state: 'PAUSED', as_of: AT, paper_pnl_text: null, unpriced_text: NAMED, detections: [],
  legs: [leg(1), leg(2, { action: 'BUY', strike: '23000.00', price_state: 'missing', current_price_display: null, pnl_text: null, pnl_kind: null, no_price_text: 'no price' }), leg(3, { pnl_text: '+780.00' })],
})

describe('ADR-311: the builder legs table', () => {
  const r = readTracking(paused())
  it('priced legs show their own figure as sent; the unpriced leg says "no price", not 0 and not a dash', () => {
    expect(r.kind).toBe('paused')
    expect(r.legs.map((l) => l.pnl)).toEqual(['-390.00', 'no price', '+780.00'])
    expect(r.legs[1].pnl).not.toMatch(/0\.00|—/)
  })
  it('the total is the paused state with no figure', () => {
    expect(r.figure).toBeNull()
    expect(r.text).toMatch(/^Paper P&L paused - prices not live, as of /)
  })
  it('the pause line names the leg without a price', () => {
    expect(r.unpriced).toBe(NAMED)
  })
  it('an older reply without the field reads as before: dash, no naming', () => {
    const old = paused()
    old.legs[1].no_price_text = undefined
    delete old.unpriced_text
    const o = readTracking(old)
    expect(o.legs[1].pnl).toBe('—')
    expect(o.unpriced).toBeNull()
  })
})

describe('ADR-311: Booked shows while the totals are paused (the reason applies per figure)', () => {
  const book = () => {
    const d = JSON.parse(JSON.stringify(REAL.strategies[0]))
    Object.assign(d, { state: 'PAUSED', booked_text: '0.00', booked_after_text: '-36.09', booked_after_reason: null, total_text: null,
      total_after_text: null, unbooked_text: null, unbooked_after_text: null, after_charges_reason: 'prices_not_live', after_charges_reason_text: null })
    return d
  }
  it('Booked keeps its after-charges figure; Total and Unbooked show the paused state, no number', () => {
    const g = readPaperStrategy(book())
    expect([g.bookedAfter.kind, g.bookedAfter.text]).toEqual(['after', '-36.09'])
    expect([g.totalAfter.kind, g.totalAfter.text]).toEqual(['paused', null])
    expect([g.unbookedAfter.kind, g.unbookedAfter.text]).toEqual(['paused', null])
  })
  it('charges paid unknown: Booked says its OWN reason, not the price pause', () => {
    const d = book()
    Object.assign(d, { booked_after_text: null, booked_after_reason: 'rates_unavailable', booked_after_reason_text: 'Charges could not be read' })
    const g = readPaperStrategy(d)
    expect(g.bookedAfter.kind).toBe('before')
    expect(g.bookedAfter.reason).toBe('Charges could not be read')
  })
})

describe('ADR-311: the all-strategies row shows the server Booked after, or its reason (no sum here)', () => {
  const row = (extra) => ({ booked_text: '0.00', total_text: null, unbooked_text: null, total_after_text: null, unbooked_after_text: null,
    after_charges_reason: 'prices_not_live', booked_after_text: null, booked_after_reason: null, ...extra })
  it('given: shown as sent while total and unbooked show the paused state', () => {
    const t = readPaperList({ strategies: [], totals: row({ booked_after_text: '-36.09' }) }).totals
    expect([t.bookedAfter.kind, t.bookedAfter.text]).toEqual(['after', '-36.09'])
    expect([t.totalAfter.kind, t.unbookedAfter.kind]).toEqual(['paused', 'paused'])
  })
  it('absent: its own reason, not the price pause', () => {
    const t = readPaperList({ strategies: [], totals: row({ booked_after_reason: 'not_priced', booked_after_reason_text: 'Some charges could not be priced' }) }).totals
    expect([t.bookedAfter.kind, t.bookedAfter.reason]).toEqual(['before', 'Some charges could not be priced'])
  })
})

describe('ADR-311: the one shared total and the Paper tab', () => {
  it('sharedTotal: paused = no number, the as-of line, and the named legs', () => {
    const t = sharedTotal({ ...paused(), state: 'PAUSED', total_text: null, answered_at: AT })
    expect(t.text).toBeNull()
    expect(t.line).toMatch(/^Paper P&L paused - prices not live, as of /)
    expect(t.unpriced).toBe(NAMED)
  })
  it('the Paper tab: an open position without a price shows "no price"; the strategy carries the named legs', () => {
    const d = JSON.parse(JSON.stringify(REAL.strategies[0]))
    const p = d.positions[0]
    Object.assign(p, { net_quantity: p.lot_size, unbooked_text: null, no_price_text: 'no price' })
    d.unpriced_text = NAMED
    const g = readPaperStrategy(d)
    expect(g.readable).toBe(true)
    expect(g.unpricedText).toBe(NAMED)
    expect(g.positions[0].unbooked).toBeNull()
    expect(g.positions[0].noPrice).toBe('no price')
    expect(g.total).toBeNull() // totals stay paused
  })
})
