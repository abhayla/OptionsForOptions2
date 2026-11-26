// D-63 round 3 (ADR-263, ADR-306): with charges known the P&L Table TOTAL is after charges while its open and closed rows are
// before charges, so the tab shows the reply's two charges lines between the rows and the TOTAL, each labelled, as the server
// sent them. Hand check on this book: open unbooked 750.00 + closed booked 643.50 = 1,393.50 before charges;
// 1,393.50 - paid 40.00 - to close 20.00 = 1,333.50 = the TOTAL (all texts below are the reply's; the page does no sum).
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import real from './fixtures/outcome-condor.json'
import { sharedTotal } from '@/lib/tracking'

vi.mock('chart.js/auto', () => ({ default: class { constructor() {} destroy() {} } }))
import ChartCard from '@/components/strategy/ChartCard.vue'

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const book = { state: 'LIVE', total_text: '₹1,393.50', total_after_text: '₹1,333.50', after_charges_reason: null, charges_paid_text: '₹40.00', charges_to_close_text: '₹20.00' }
const charges = (b) => ({ paid: b.charges_paid_text ?? b.charges_text ?? null, close: b.charges_to_close_text ?? null })
const card = (b) => mount(ChartCard, { attachTo: document.body, props: { points: real.payoff.points, spot: real.spot_level, table: real.table, legs: real.legs, paperTotal: sharedTotal(b), charges: charges(b) } })

describe('D-63 round 3: charges lines on the P&L Table', () => {
  it('after charges: Charges paid and Estimated cost to close sit before the TOTAL row, as sent', () => {
    const w = card(book)
    const panel = t(w, 'panel-pnl')
    expect(panel.get('[data-testid="pnl-charges-paid"]').text()).toContain('Charges paid')
    expect(panel.get('[data-testid="pnl-charges-paid"]').text()).toContain('₹40.00')
    expect(panel.get('[data-testid="pnl-charges-close"]').text()).toContain('Estimated cost to close')
    expect(panel.get('[data-testid="pnl-charges-close"]').text()).toContain('₹20.00')
    const rows = panel.findAll('tbody tr').map((r) => r.attributes('data-testid') ?? r.attributes('data-row'))
    expect(rows.indexOf('pnl-charges-paid')).toBeGreaterThan(-1)
    expect(rows.indexOf('pnl-charges-paid')).toBeLessThan(rows.indexOf('TOTAL'))
    expect(panel.find('[data-row="TOTAL"]').text()).toContain('₹1,333.50')
  })
  it('charges unknown: the TOTAL is before charges and no charges line shows', () => {
    const w = card({ state: 'LIVE', total_text: '₹1,393.50', total_after_text: null, after_charges_reason: 'rates_unavailable' })
    expect(w.find('[data-testid="pnl-charges-paid"]').exists()).toBe(false)
    expect(w.find('[data-testid="pnl-charges-close"]').exists()).toBe(false)
  })
})
