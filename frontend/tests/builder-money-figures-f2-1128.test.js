// Lane F2 item 3 (I-41, tests only): the builder's money figures as Lane TD read them on frozen prices (scenario ADJ-08 / ADJ-13,
// RESULTS-lane-td I-41). Real case: "TD walk, table total and D-11, D-14 pass, re-buy steps blocked; O-4 the table total does not move
// with the Add booked P&L switch and OFF shows whole rupees". Every figure is the server's string, printed as sent (ADR-008: no sum
// or rounding here). The table total is NOT changed by this lane (Question for the owner (b)).
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import SummaryCards from '@/components/strategy/SummaryCards.vue'
import { paperLeftOf } from '@/lib/paperDrafts'
import { OPEN_LEGS_ONLY_TEXT, bookedFields } from '@/lib/targetBlock'

const t = (w, id) => w.get(`[data-testid="${id}"]`)
const card = (book, over = {}) => mount(SummaryCards, { props: { left: paperLeftOf(book), maxProfit: book.max_profit_text, maxLoss: book.max_loss_text, ...over } })

describe('D-14 (ADR-320 (2)), ADJ-08 on the expiry day, strategy 4: the pair as the server sent it', () => {
  const BOOK = { max_profit_text: '+5,009.47', profit_left_text: '+429.00', profit_left_after_text: '+429.00', max_profit_hold_text: '+5,104.10',
    profit_left_hold_text: '+523.63', total_after_text: '+4,580.47', loss_left_text: '-1.00', loss_left_after_text: '-1.00', max_loss_text: '-1.00' }
  it('If held to expiry +5,104.10 / +523.63 and If exited now +5,009.47 / +429.00', () => {
    const w = card(BOOK)
    expect(t(w, 'expiry-pair-held-label').text()).toBe('If held to expiry')
    expect(t(w, 'expiry-pair-held-max').text()).toBe('+5,104.10')
    expect(t(w, 'expiry-pair-held-left').text()).toBe('+523.63')
    expect(t(w, 'expiry-pair-exited-label').text()).toBe('If exited now')
    expect(t(w, 'expiry-pair-exited-max').text()).toBe('+5,009.47')
    expect(t(w, 'expiry-pair-exited-left').text()).toBe('+429.00')
  })
  it('a day that is not the expiry day (no hold text): no pair', () => {
    const { max_profit_hold_text: _a, profit_left_hold_text: _b, ...plain } = BOOK
    expect(card(plain).find('[data-testid="expiry-pair"]').exists()).toBe(false)
  })
})

describe('D-11 (ADR-209), ADJ-13 strategy 3, booked +962: the tiles are the server\'s texts for the switch ON and OFF', () => {
  it('ON: Max Profit +4,823.72 / Max Loss -21,176.28, paise as sent', () => {
    const w = card({}, { maxProfit: '+4,823.72', maxLoss: '-21,176.28', left: null })
    expect(t(w, 'max-profit').text()).toBe('+4,823.72')
    expect(t(w, 'max-loss').text()).toBe('-21,176.28')
  })
  it('OFF: +3,967 / -22,033 printed as sent (O-4: whole rupees come from the server, the browser does not re-format them)', () => {
    const w = card({}, { maxProfit: '+3,967', maxLoss: '-22,033', left: null })
    expect(t(w, 'max-profit').text()).toBe('+3,967')
    expect(t(w, 'max-loss').text()).toBe('-22,033')
  })
  it('the switch sends include_booked:false only when OFF, and names the strategy only when it is a paper one', () => {
    expect(bookedFields(3, true)).toEqual({ paper_strategy_id: 3 })
    expect(bookedFields(3, false)).toEqual({ paper_strategy_id: 3, include_booked: false })
    expect(bookedFields(null, false)).toEqual({})
  })
  it('the note under the OFF tiles is the one sentence', () => {
    expect(OPEN_LEGS_ONLY_TEXT).toBe('Open legs only: the booked P&L is not included. Max Profit and Max Loss are after charges estimated at entry prices; breakevens are before charges.')
  })
  it('Profit left with the recover line (ADR-302): +7,338.50 includes Rs 1,836.71 needed to recover the current loss', () => {
    const book = { max_profit_text: '+5,501.79', profit_left_text: '+7,338.50', profit_left_after_text: '+7,338.50', loss_left_text: '-18,661.50',
      loss_left_after_text: '-18,661.50', max_loss_text: '-20,498.21', total_after_text: '-1,836.71', recover_text: '1,836.71' }
    const w = card(book)
    expect(t(w, 'profit-left').text()).toContain('+7,338.50')
    expect(t(w, 'profit-left-recover').text()).toContain('1,836.71')
    expect(t(w, 'profit-left-recover').text()).toContain('needed to recover the current loss')
    expect(t(w, 'loss-left').text()).toContain('-18,661.50')
  })
})
