// S-25 (owner 25 Nov): Orderbook Qty 65 and Price 101.20 read as one number "65101.20". Class assertions (jsdom has no layout).
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import PaperBookPanel from '@/components/strategy/PaperBookPanel.vue'

const book = {
  positions: [], closed: [], state: 'LIVE', total_text: '0.00',
  orders: [{ id: 1, side: 'SELL', contract_text: 'NIFTY 25500 PE 2026-11-24', quantity: 65, price_text: '101.20', kind: 'open', placed_at: '2026-11-23T05:50:00Z' }],
}
const pad = (el) => /(^|\s)p[xlr]-\d/.test(el.attributes('class') ?? '')

describe('S-25 Orderbook columns do not run together', () => {
  const w = mount(PaperBookPanel, { props: { book, net: [], showOrders: 1 } })
  it('qty and price are separate cells, each with horizontal padding and tabular figures', () => {
    const q = w.find('[data-testid="order-qty"]')
    const p = w.find('[data-testid="order-price"]')
    expect(q.element).not.toBe(p.element)
    expect(q.text()).toBe('65')
    expect(p.text()).toBe('101.20')
    for (const c of [q, p]) { expect(pad(c)).toBe(true); expect(c.classes()).toContain('tabular-nums') }
  })
  it('every th and td of the table carries horizontal padding; Qty and Price headers are right-aligned', () => {
    const cells = w.findAll('[data-testid="order-table"] th, [data-testid="order-table"] td')
    expect(cells.length).toBeGreaterThan(0)
    for (const c of cells) expect(pad(c), c.html()).toBe(true)
    const ths = w.findAll('[data-testid="order-table"] th')
    for (const label of ['Qty', 'Price']) {
      const th = ths.find((t) => t.text() === label)
      expect(th.classes()).toContain('text-right')
      expect(pad(th)).toBe(true)
    }
  })
})
