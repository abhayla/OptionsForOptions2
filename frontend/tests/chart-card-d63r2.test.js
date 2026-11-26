// D-63 round 2 (ADR-207 (2), ADR-306 (5)): on a two-expiry paper trade the Greeks tab Total says it is summed across the
// expiries and the P&L Table TOTAL stays plain "Total" (rupee columns); the P&L Table lists the paper reply's closed rows
// beside its TOTAL, which includes their booked P&L (real case C9 164: total +199.02 includes booked closed legs).
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import real from './fixtures/outcome-condor.json'

vi.mock('chart.js/auto', () => ({ default: class { constructor() {} destroy() {} } }))
import ChartCard from '@/components/strategy/ChartCard.vue'

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const twoExpiries = real.legs.map((l, i) => (i === 0 ? { ...l, expiry: '2026-12-29' } : l))
const closed = [{ contract_id: 7, contract_text: 'NIFTY 25400 PE 2026-11-24', side: 'SELL', quantity: 150, lots: 2, average_entry_text: '₹120.00', average_exit_text: '₹115.71', booked_text: '₹643.50', opened_at: '2026-11-23T04:00:00Z' }]
const card = (extra = {}) => mount(ChartCard, { attachTo: document.body, props: { points: real.payoff.points, spot: real.spot_level, table: real.table, legs: twoExpiries, ...extra } })

describe('D-63 round 2: Total labels', () => {
  it('the summed-across note is on the Greeks tab Total, not on the P&L Table TOTAL', () => {
    const w = card()
    expect(t(w, 'panel-greeks').get('[data-testid="greeks-total-label"]').text()).toBe('Total (summed across 2 expiries)')
    expect(t(w, 'panel-pnl').find('[data-row="TOTAL"]').text()).not.toContain('summed')
    expect(t(w, 'panel-pnl').find('[data-row="TOTAL"]').text()).toContain('Total')
  })
})

describe('D-63 round 2: P&L Table closed rows', () => {
  it('lists each closed leg of the paper reply with entry, exit and booked, before charges', () => {
    const w = card({ closed })
    const rows = t(w, 'panel-pnl').findAll('[data-testid="pnl-closed-row"]')
    expect(rows).toHaveLength(1)
    expect(rows[0].get('[data-testid="pnl-closed-entry"]').text()).toBe('₹120.00')
    expect(rows[0].get('[data-testid="pnl-closed-exit"]').text()).toBe('₹115.71')
    expect(rows[0].get('[data-testid="pnl-closed-booked"]').text()).toBe('₹643.50')
    expect(t(w, 'pnl-closed-basis').text()).toContain('before charges')
  })
  it('shows no closed section when the reply has none', () => {
    expect(card({ closed: [] }).find('[data-testid="pnl-closed-list"]').exists()).toBe(false)
  })
})
