// D-10 (ADR-207 (2), REQ-109 AC-4): the builder's Net Positions shows each CLOSED lifecycle in its own Closed section with its
// entry, exit and booked; the open row of the same contract (reopened) is separate. Real case: C1 155, short 25400 PE +643.50.
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import PaperBookPanel from '@/components/strategy/PaperBookPanel.vue'

const open = {
  contract_id: 7, contract_text: 'NIFTY 25400 PE 2026-11-24', net_quantity: 150, lot_size: 75, average_text: '₹90.00', ltp_text: '₹95.00',
  booked_text: '₹0.00', unbooked_text: '₹750.00', total_text: '₹750.00', price_state: 'live',
}
const closed = {
  contract_id: 7, contract_text: 'NIFTY 25400 PE 2026-11-24', side: 'SELL', quantity: 150, lots: 2, average_entry_text: '₹120.00',
  average_exit_text: '₹115.71', booked_text: '₹643.50', opened_at: '2026-11-23T04:00:00Z',
}
const book = (over = {}) => ({ positions: [open], closed: [closed], orders: [], state: 'LIVE', total_text: '₹1,393.50', ...over })

describe('Net Positions: closed lifecycles (D-10)', () => {
  it('shows the closed short with entry, exit and its own booked, and the new long with booked zero', () => {
    const w = mount(PaperBookPanel, { props: { book: book(), net: [{ contract_id: 7, lots: 2 }] } })
    const rows = w.findAll('[data-testid="closed-row"]')
    expect(rows).toHaveLength(1)
    expect(rows[0].get('[data-testid="closed-entry"]').text()).toBe('₹120.00')
    expect(rows[0].get('[data-testid="closed-exit"]').text()).toBe('₹115.71')
    expect(rows[0].get('[data-testid="closed-booked"]').text()).toBe('₹643.50')
    expect(w.findAll('[data-testid="net-row"]')).toHaveLength(1)
    expect(w.get('[data-testid="net-booked"]').text()).toBe('₹0.00')
  })

  it('shows the server sentence for a fully closed book and no closed section when nothing closed', () => {
    const w = mount(PaperBookPanel, { props: { book: book({ closed_text: 'Closed: result ₹94.50 after charges.' }), net: [] } })
    expect(w.get('[data-testid="closed-result"]').text()).toBe('Closed: result ₹94.50 after charges.')
    const none = mount(PaperBookPanel, { props: { book: book({ closed: [] }), net: [] } })
    expect(none.find('[data-testid="closed-list"]').exists()).toBe(false)
  })
})

// D-22 / D-71 round 2: the closed trade's own page opens on Net Positions, so each closed row carries WHY it closed (the server's
// reason text: a stop with the index value at that moment, or "Paper - settled at expiry: ... closed at ...") without a click.
describe('Net Positions closed rows show the reason (D-22, D-71)', () => {
  const stopRow = { ...closed, contract_id: 8, contract_text: 'NIFTY 25500 PE 2026-11-24', reason_text: 'Stop-loss on the index: NIFTY crossed above 25,720.00; NIFTY was at 25,721.40 at that moment' }
  const settledRow = { ...closed, contract_id: 9, contract_text: 'NIFTY 25400 PE 2026-11-24', reason_text: 'Paper - settled at expiry: NIFTY closed at 25,641.35' }
  const plain = { ...closed, contract_id: 10, contract_text: 'NIFTY 25300 PE 2026-11-24' }
  it('in the panel default view, a fired stop and a settlement each show their reason; a manual exit shows none', () => {
    const w = mount(PaperBookPanel, { props: { book: book({ positions: [], closed: [stopRow, settledRow, plain] }), net: [] } })
    expect(w.findAll('[data-testid="closed-reason"]').map((n) => n.text())).toEqual([stopRow.reason_text, settledRow.reason_text])
  })
})
