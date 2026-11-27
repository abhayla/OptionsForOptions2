// GC-ICLIVE D-64 (owner decision): after the 15:30 close the page says "Market closed. Open legs that expire today settle at 15:45."
// in place of the paused / "No price for" text; the server decides "after close" and sends `after_close_text` (one place).
// Real case 24 Nov 2026: C2 157 at 15:30 read the old "..., as of Time not available" and "Total P&L -".
import { describe, expect, it } from 'vitest'
import { readPaperStrategy } from '@/lib/paperList'
import { readTracking, sharedTotal } from '@/lib/tracking'

const LINE = 'Market closed. Open legs that expire today settle at 15:45.'
const book = (over = {}) => ({
  state: 'PAUSED', as_of: null, answered_at: '2026-11-24T10:05:00Z', total_text: null, unpriced_text: 'No price for: NIFTY 24 Nov 25600 CE', pause_reason_text: 'Prices are not live',
  positions: [], closed: [], ...over,
})

describe('the shared total line', () => {
  it('value: the server line replaces the paused sentence and the raw time', () => {
    const shown = sharedTotal(book({ after_close_text: LINE }))
    expect(shown.line).toBe(LINE)
    expect(shown.unpriced).toBeNull()
  })
  it('no line from the server: the paused sentence is unchanged (before 15:30, after settlement)', () => {
    const shown = sharedTotal(book())
    expect(shown.line).toBe('Paper P&L paused - prices not live')
    expect(shown.unpriced).toBe('No price for: NIFTY 24 Nov 25600 CE')
  })
})

describe('the Positions card', () => {
  const s = { strategy_id: 157, name: '"C2"', underlying: 'NIFTY', state: 'PAUSED', status_word: 'Running', open_count: 1, position_count: 1, positions: [], closed: [], total_text: null, unpriced_text: 'No price for: NIFTY 24 Nov 25600 CE', pause_reason_text: 'Prices are not live' }
  it('value: the card carries the server line and no "No price for" text beside it', () => {
    const card = readPaperStrategy({ ...s, after_close_text: LINE })
    expect(card.afterCloseText).toBe(LINE)
    expect(card.unpricedText).toBeNull()
  })
  it('nothing to show: no line, the naming of the unpriced legs stays', () => {
    const card = readPaperStrategy(s)
    expect(card.afterCloseText).toBeNull()
    expect(card.unpricedText).toBe('No price for: NIFTY 24 Nov 25600 CE')
  })
  it('an unreadable line (a number) is not shown', () => {
    expect(readPaperStrategy({ ...s, after_close_text: 5 }).afterCloseText).toBeNull()
  })
})

describe('a leg that has a price after the close', () => {
  const pos = (over) => ({ contract_id: 1, contract_text: 'NIFTY 25 Nov 25300 PE', instrument: 'PE', strike: '25300.00', expiry: '2026-11-25', net_quantity: -65, lot_size: 65, average: '10.00', average_text: '10.00', ltp: '74.55', ltp_text: '74.55', price_state: 'live', price_state_text: null, price_at: '2026-11-24T10:05:00Z', unbooked: '-4.00', unbooked_text: '-4.00', ...over })
  const card = (positions) => readPaperStrategy({ strategy_id: 164, name: '"C9"', underlying: 'NIFTY', state: 'PAUSED', status_word: 'Running', open_count: 2, position_count: 2, closed: [], total_text: null, unpriced_text: 'No price for: NIFTY 25 Nov 25000 PE', after_close_text: LINE, pause_reason_text: 'Prices are not live', positions })
  it('value: the priced leg keeps its price and figure beside the line; the unpriced one has none', () => {
    const shown = card([pos({}), pos({ contract_id: 2, ltp: null, ltp_text: null, price_state: 'no_quote', unbooked: null, unbooked_text: null })])
    expect(shown.afterCloseText).toBe(LINE)
    expect(shown.positions[0].ltpText).toBe('74.55')
    expect(shown.positions[0].unbookedText ?? shown.positions[0].unbooked).toBeTruthy()
    expect(shown.positions[1].ltpText).toBeNull()
  })
})

describe('the tracking view (the builder paper line)', () => {
  const body = (over = {}) => ({ state: 'PAUSED', as_of: null, legs: [], detections: [], unpriced_legs: [], unpriced_text: 'No price for: NIFTY 25 Nov 25300 PE', ...over })
  it('value: a paused answer with the server line says the line and not the paused sentence', () => {
    const view = readTracking(body({ after_close_text: LINE }))
    expect(view.text).toBe(LINE)
    expect(view.unpriced).toBeNull()
  })
  it('nothing to show: no line keeps the paused sentence', () => {
    expect(readTracking(body()).text).toBe('Paper P&L paused - prices not live')
  })
})
