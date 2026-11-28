// Lane FJ (R3) coordinator item (b) (FC3 item 7, D-5). Real case: the paper book panel printed "Checked at 03:22:40 IST" (the server's answer time, it moves on every read)
// beside the market-closed banner that shows the close time, so the two times read as one. Now each is labelled: "Prices as of <price time>" and "Checked at <answer time>",
// both through the one stamp formatter (istStamp). A time that cannot be read prints no line (never "Time not available"). Spec basis: ADR-330 (56), ADR-088.
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('@/services/api', () => ({ default: { get: () => Promise.reject(new Error('no read')), post: () => Promise.reject(new Error('no read')) } }))
import PaperBookPanel from '@/components/strategy/PaperBookPanel.vue'

const pos = { contract_id: 1, contract_text: 'NIFTY C1', net_quantity: -65, average_text: '75.65', ltp_text: '76.80', booked_text: '0.00', unbooked_text: '1.00', total_text: '1.00', price_state: 'live' }
const book = (over = {}) => ({ strategy_id: 138, name: '"Condor"', orders: [], state: 'LIVE', as_of: null, answered_at: '2026-11-27T12:52:40Z', last_price_at: null, total_text: '+26.00',
  total_after_text: '+24.50', after_charges_reason: null, charges_text: '1.50', positions: [pos], ...over })
const lines = (b) => {
  const w = mount(PaperBookPanel, { props: { book: b, net: [] } })
  const q = (id) => (w.find(`[data-testid="${id}"]`).exists() ? w.find(`[data-testid="${id}"]`).text() : null)
  const out = { prices: q('book-prices-as-of'), checked: q('book-read-at') }
  w.unmount()
  return out
}

describe('paper book panel: price time and read time, each labelled', () => {
  it('both known (market closed: a close time and a later read): two labelled lines', () => {
    expect(lines(book({ last_price_at: '2026-11-27T10:00:00Z' }))).toEqual({ prices: 'Prices as of 15:30:00 IST', checked: 'Checked at 18:22:40 IST' })
  })
  it('a price from an earlier day carries its date', () => {
    expect(lines(book({ last_price_at: '2026-11-26T10:00:00Z' }))).toEqual({ prices: 'Prices as of 26 Nov 2026, 15:30:00 IST', checked: 'Checked at 18:22:40 IST' })
  })
  it('no price time: only "Checked at" (as before)', () => {
    expect(lines(book())).toEqual({ prices: null, checked: 'Checked at 18:22:40 IST' })
  })
  it('price time unreadable: no price line, never "Time not available"', () => {
    expect(lines(book({ last_price_at: 'garbage' }))).toEqual({ prices: null, checked: 'Checked at 18:22:40 IST' })
  })
  it('no answer time: only the price line, with its whole date (nothing names today); neither: none', () => {
    expect(lines(book({ answered_at: null, last_price_at: '2026-11-27T10:00:00Z' }))).toEqual({ prices: 'Prices as of 27 Nov 2026, 15:30:00 IST', checked: null })
    expect(lines(book({ answered_at: null }))).toEqual({ prices: null, checked: null })
  })
})
