// D-17 (ADR-322 point 2): the Time value line prints the server's "at live prices, as of HH:MM:SS"; no text, no label.
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import SummaryCards from '@/components/strategy/SummaryCards.vue'

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const base = { timeValue: '-3,439', timeValueExact: '-3439.00', intrinsicValue: '0', intrinsicValueExact: '0.00', valueLabel: 'value of the options, not P&L' }

describe('D-17 the time value names the prices it is on', () => {
  it('prints the server sentence beside the Time value', () => {
    const w = mount(SummaryCards, { props: { ...base, timeValueBasis: 'at live prices, as of 14:12:05' } })
    expect(t(w, 'value-basis').text()).toBe('at live prices, as of 14:12:05')
  })
  it('prints nothing when the reply sent no sentence or there is no time value', () => {
    expect(t(mount(SummaryCards, { props: base }), 'value-basis').exists()).toBe(false)
    expect(t(mount(SummaryCards, { props: { ...base, timeValue: null, timeValueBasis: 'at live prices, as of 14:12:05' } }), 'value-basis').exists()).toBe(false)
  })
})
