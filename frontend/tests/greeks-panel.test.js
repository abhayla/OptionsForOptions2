// W-127 (REQ-084 AC-8, AC-9): the Greeks panel shows the server's per-unit and per-position strings and the server's rupee
// sentences. The browser multiplies nothing: the switch only chooses which of the two server sets to show.
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import GreeksPanel from '@/components/strategy/GreeksPanel.vue'

const g = (delta, gamma, theta, vega) => ({ delta, gamma, theta, vega })
const GREEKS = {
  rows: [
    { instrument_id: 'NSE_FO:1', per_unit: g('0.5200', '0.0010', '-4.0000', '8.0000'), per_position: g('33.8000', '0.0650', '-260.0000', '520.0000') },
    { instrument_id: 'NSE_FO:2', per_unit: g('-0.3000', '0.0020', '5.0000', '-6.0000'), per_position: g('-19.5000', '0.1300', '325.0000', '-390.0000') },
  ],
  total_per_position: g('14.3000', '0.1950', '65.0000', '130.0000'),
  total_per_unit: g('0.2200', '0.0030', '1.0000', '2.0000'),
  examples: [
    { greek: 'delta', sentence: 'Delta 14.3000: if NIFTY rises 10 points, about Rs 143.00 (estimate).' },
    { greek: 'theta', sentence: 'Theta 65.0000: about Rs 65.00 over one day if nothing else changes (estimate).' },
  ],
}
const cells = (w, testid) => w.get(`[data-testid="${testid}"]`).findAll('td').map((c) => c.text())

describe('REQ-084 AC-8: per unit / per position', () => {
  it('AC-8: starts per position; rows and Total are the server strings', () => {
    const w = mount(GreeksPanel, { props: { greeks: GREEKS } })
    expect(cells(w, 'greeks-total')).toEqual(['Total', '14.3000', '0.1950', '65.0000', '130.0000'])
    expect(w.findAll('[data-testid="greeks-row"]')).toHaveLength(2)
    expect(w.findAll('[data-testid="greeks-row"]')[0].findAll('td')[1].text()).toBe('33.8000')
  })
  it('AC-8: the toggle shows the server\'s per unit set', async () => {
    const w = mount(GreeksPanel, { props: { greeks: GREEKS } })
    await w.get('[data-testid="greeks-per-unit"]').trigger('click')
    expect(w.findAll('[data-testid="greeks-row"]')[0].findAll('td')[1].text()).toBe('0.5200')
    expect(cells(w, 'greeks-total')).toEqual(['Total', '0.2200', '0.0030', '1.0000', '2.0000'])
  })
  it('AC-8 (red case): without a per unit total (different lot sizes) it says so and invents none', async () => {
    const w = mount(GreeksPanel, { props: { greeks: { ...GREEKS, total_per_unit: null } } })
    await w.get('[data-testid="greeks-per-unit"]').trigger('click')
    expect(w.get('[data-testid="greeks-no-unit-total"]').text()).toContain('different lot sizes')
    expect(cells(w, 'greeks-total').slice(1).join('')).toBe('')
  })
})

describe('REQ-084 AC-9: rupee examples', () => {
  it('AC-9: the examples are the server sentences, verbatim', () => {
    const w = mount(GreeksPanel, { props: { greeks: GREEKS } })
    expect(w.get('[data-testid="greeks-examples"]').findAll('li').map((l) => l.text())).toEqual(GREEKS.examples.map((e) => e.sentence))
  })
  it('AC-9: where Greeks are not defined the server reason is shown and no table', () => {
    const w = mount(GreeksPanel, { props: { greeks: null, reason: 'Greeks are not defined at the expiry close; choose an earlier time.' } })
    expect(w.get('[data-testid="greeks-reason"]').text()).toContain('not defined at the expiry close')
    expect(w.find('[data-testid="greeks-table"]').exists()).toBe(false)
  })
})
