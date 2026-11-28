// Lane F3 I-91 (D-8): a closed row printed empty Unbooked and P&L cells. Real case: TC walk, a Positions closed row (NIFTY 3 Nov 22950 CE
// sold 2 lots 100.00 -> 80.00, booked +3,000.00). The reader keeps the server's own Unbooked / P&L text and its reason when it sends them;
// ClosedRows prints the two cells only then, never an empty one; no figure is formed here (ADR-008).
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import REAL from './fixtures/paper-list-r19b/paused.json'
import { readPaperList } from '@/lib/paperList'
import ClosedRows from '@/components/strategy/ClosedRows.vue'

const ROW = { contract_id: 11, contract_text: 'NIFTY 3 Nov 22950 CE', side: 'SELL', quantity: 150, lots: 2, average_entry_text: '100.00', average_exit_text: '80.00', booked_text: '+3,000.00', opened_at: '2026-11-03T04:00:00Z', reason_text: null }
const readRows = (extra) => {
  const d = JSON.parse(JSON.stringify(REAL)); d.strategies[0].closed = [{ ...ROW, ...extra }]
  return readPaperList(d).groups[0].closed
}
const cell = (w, id) => w.find(`[data-testid="${id}"]`)

describe('I-91 closed rows: Unbooked and P&L', () => {
  it('server sent both: the reader keeps them as sent and ClosedRows prints them', () => {
    const [c] = readRows({ unbooked_text: '0.00', pnl_text: '+3,000.00' })
    expect(c.unbooked).toBe('0.00'); expect(c.pnl).toBe('+3,000.00')
    const w = mount(ClosedRows, { props: { rows: [{ ...ROW, unbooked_text: '0.00', pnl_text: '+3,000.00' }] } })
    expect(cell(w, 'closed-unbooked').text()).toBe('0.00'); expect(cell(w, 'closed-pnl').text()).toBe('+3,000.00')
  })
  it('server sent a reason instead: the reason is printed, never an empty cell', () => {
    const [c] = readRows({ unbooked_text: null, pnl_text: null, pnl_reason_text: 'Closed at expiry; settlement price not read.' })
    expect(c.pnl).toBe(null); expect(c.pnlReason).toBe('Closed at expiry; settlement price not read.')
    const w = mount(ClosedRows, { props: { rows: [{ ...ROW, pnl_text: null, pnl_reason_text: 'Closed at expiry; settlement price not read.' }] } })
    expect(cell(w, 'closed-pnl').text()).toBe('Closed at expiry; settlement price not read.')
  })
  it('server sent neither (an older answer): no extra columns, no empty cells; Booked stays', () => {
    const w = mount(ClosedRows, { props: { rows: [ROW] } })
    expect(w.findAll('th').length).toBe(5)
    expect(cell(w, 'closed-unbooked').exists()).toBe(false)
    expect(cell(w, 'closed-booked').text()).toBe('+3,000.00')
  })
  it('ambiguous (blank strings): treated as absent', () => {
    const [c] = readRows({ unbooked_text: '  ', pnl_text: '' })
    expect(c.unbooked).toBe(null); expect(c.pnl).toBe(null)
  })
})
