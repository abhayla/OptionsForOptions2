// D-13 / D-14 (ADR-306, ADR-320 (2)): the Charges line says which charges it shows, and on the trade's expiry day the summary
// shows Max profit and Profit left twice, labelled "If held to expiry" / "If exited now". Figures are the server texts of the C2-
// shaped book of tests_app/test_charges_basis_d13_d14.py (paid 97.35, cost to close 94.90, Total after +191.25): held +386.90 /
// +195.65, exited +292.00 / +100.75. Nothing is computed here.
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import SummaryCards from '@/components/strategy/SummaryCards.vue'
import PaperBookPanel from '@/components/strategy/PaperBookPanel.vue'
import { paperLeftOf } from '@/lib/paperDrafts'

const BOOK = {
  state: 'LIVE', total: '383.50', total_text: '+383.50', total_after: '191.25', total_after_text: '+191.25',
  after_charges_reason: null, after_charges_reason_text: null, charges: '97.35', charges_text: 'Rs 97.35',
  charges_paid: '97.35', charges_paid_text: 'Rs 97.35', charges_to_close: '94.90', charges_to_close_text: 'Rs 94.90',
  max_profit: '292.00', max_profit_text: '+292.00', max_loss: '-6208.00', max_loss_text: '-6,208.00',
  profit_left: '100.75', profit_left_text: '+100.75', loss_left: '-6399.25', loss_left_text: '-6,399.25',
  profit_left_after: '100.75', profit_left_after_text: '+100.75', loss_left_after: '-6399.25', loss_left_after_text: '-6,399.25',
  extremes_reason: null, extremes_reason_text: null, extremes_charges: '192.25',
  extremes_charges_text: 'Maximum profit and maximum loss include about Rs 192.25 of charges and taxes.',
  max_profit_hold: '386.90', max_profit_hold_text: '+386.90', profit_left_hold: '195.65', profit_left_hold_text: '+195.65',
  recover: null, recover_text: null, orders: [], positions: [],
}
const t = (w, id) => w.get(`[data-testid="${id}"]`)
const card = (book) => mount(SummaryCards, { props: { left: paperLeftOf(book), maxProfit: book.max_profit_text, maxLoss: book.max_loss_text } })

describe('D-14 expiry-day pair (ADR-320 (2))', () => {
  it('on the expiry day: two labelled rows, the server texts as sent', () => {
    const w = card(BOOK)
    expect(t(w, 'expiry-pair-held-label').text()).toBe('If held to expiry')
    expect(t(w, 'expiry-pair-held-max').text()).toBe('+386.90')
    expect(t(w, 'expiry-pair-held-left').text()).toBe('+195.65')
    expect(t(w, 'expiry-pair-exited-label').text()).toBe('If exited now')
    expect(t(w, 'expiry-pair-exited-max').text()).toBe('+292.00')
    expect(t(w, 'expiry-pair-exited-left').text()).toBe('+100.75')
  })

  it('other days (no held figure from the server): no pair, the summary unchanged', () => {
    const w = card({ ...BOOK, max_profit_hold: null, max_profit_hold_text: null, profit_left_hold: null, profit_left_hold_text: null })
    expect(w.find('[data-testid="expiry-pair"]').exists()).toBe(false)
    expect(t(w, 'profit-left').text()).toBe('+100.75')
  })

  it('a paused book shows no pair (no number beside a paused figure)', () => {
    const w = card({ ...BOOK, after_charges_reason: 'prices_not_live', total_after: null, total_after_text: null })
    expect(w.find('[data-testid="expiry-pair"]').exists()).toBe(false)
  })
})

describe('D-14 the Charges line names what it shows', () => {
  it('"Charges paid" beside "Estimated cost to close", each the server text', () => {
    const w = mount(PaperBookPanel, { props: { book: BOOK, net: [] } })
    expect(t(w, 'book-charges-label').text()).toBe('Charges paid')
    expect(t(w, 'book-charges').text()).toBe('Rs 97.35')
    expect(t(w, 'book-charges-close-label').text()).toBe('Estimated cost to close')
    expect(t(w, 'book-charges-close').text()).toBe('Rs 94.90')
  })

  it('no estimate to close (prices not live): only the paid line', () => {
    const w = mount(PaperBookPanel, { props: { book: { ...BOOK, charges_to_close_text: null }, net: [] } })
    expect(w.find('[data-testid="book-charges-close"]').exists()).toBe(false)
  })
})
