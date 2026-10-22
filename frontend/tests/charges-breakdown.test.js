// W-127 (ADR-167): the round-trip charges appear once, by component, as the server sent them; no browser arithmetic.
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ChargesBreakdown from '@/components/strategy/ChargesBreakdown.vue'

const B = { brokerage: '160.00', stt: '29.70', exchange_transaction: '14.07', gst: '31.34', stamp: '0.59', sebi: '0.04', total: '235.75' }

describe('ADR-167: one charges breakdown', () => {
  it('shows each component and the total exactly as sent', () => {
    const w = mount(ChargesBreakdown, { props: { breakdown: B } })
    for (const [key, value] of Object.entries(B)) {
      if (key === 'total') continue
      expect(w.get(`[data-testid="charges-${key}"] dd`).text()).toBe(value)
    }
    expect(w.get('[data-testid="charges-total"]').text()).toBe('Total 235.75')
  })
  it('says the curves are before these charges', () => {
    const w = mount(ChargesBreakdown, { props: { breakdown: B } })
    expect(w.text()).toContain('before these charges')
  })
})
