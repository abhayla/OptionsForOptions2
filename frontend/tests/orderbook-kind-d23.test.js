// D-23 (REQ-109 AC-8, ADR-207): a stop-out exit is written by the server as kind "stop" (settle: "settle"); the Orderbook's
// Kind column says so. Real case: C4 160, the 4 stop-out exits, 25500 PE read "B Add 130 @64.30" and looked like a new buy.
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import PaperBookPanel from '@/components/strategy/PaperBookPanel.vue'
import { paperKindLabel } from '@/lib/paperDrafts'

const order = (id, side, contract_text, quantity, price_text, kind) => ({
  id, side, contract_text, quantity, price_text, kind, placed_at: '2026-11-23T05:50:00Z',
})
const book = {
  positions: [], closed: [], state: 'LIVE', total_text: '₹0.00',
  orders: [
    order(1, 'SELL', 'NIFTY 25500 PE 2026-11-24', 130, '₹64.30', 'open'),
    order(2, 'BUY', 'NIFTY 25500 PE 2026-11-24', 130, '₹64.30', 'stop'),
    order(3, 'BUY', 'NIFTY 25400 PE 2026-11-24', 130, '₹10.00', 'add'),
    order(4, 'SELL', 'NIFTY 25400 PE 2026-11-24', 130, '₹10.00', 'exit'),
    order(5, 'SELL', 'NIFTY 25000 PE 2026-11-24', 130, '₹0.05', 'settle'),
  ],
}

describe('Orderbook Kind column (D-23)', () => {
  it('names a stop-out exit Stop, never Add', () => {
    const w = mount(PaperBookPanel, { props: { book, net: [], showOrders: 1 } })
    const kinds = w.findAll('[data-testid="order-kind"]').map((c) => c.text())
    expect(kinds).toEqual(['Open', 'Stop', 'Add', 'Exit', 'Settled'])
  })

  it('the shared label maps every server kind to its own word', () => {
    expect(['open', 'add', 'exit', 'stop', 'settle'].map(paperKindLabel)).toEqual(['Add', 'Add', 'Exit', 'Stop', 'Settled'])
  })
})
