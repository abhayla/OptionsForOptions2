// GC-ICLIVE D-64 (owner decision): after the 15:30 close the page says "Market closed. Open legs that expire today settle at 15:45."
// in place of the paused / "No price for" text; the server decides "after close" and sends `after_close_text` (one place).
// Real case 24 Nov 2026: C2 157 at 15:30 read "Paper P&L paused - prices not live, as of Time not available" and "Total P&L -".
import { describe, expect, it } from 'vitest'
import { readPaperStrategy } from '@/lib/paperList'
import { sharedTotal, readTracking } from '@/lib/tracking'

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
    expect(shown.line).toBe('Paper P&L paused - prices not live, as of Time not available')
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

describe('the tracking view', () => {
  it('a paused book with the server line says the line, not the paused sentence', () => {
    const view = readTracking({ state: 'PAUSED', as_of: null, legs: [], detections: [], unpriced_legs: [], unpriced_text: null, after_close_text: LINE })
    expect(view.text).toBe(LINE)
  })
})
