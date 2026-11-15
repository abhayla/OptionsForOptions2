// GC-ICFIX P3 u505 (user test note ISSUES.md:111 "#64 the Strike Controls and Save row jump up and down by 20-35 px while prices re-capture (grey
// 'captured 10:16:17' line appears under legs)"): the "captured HH:MM:SS" line's space is always reserved for a priced, not-typed leg,
// whether the line shows or not (a moved price hides it). jsdom measures no height: asserted as structure, a fixed-height slot.
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import LegList from '@/components/strategy/LegList.vue'

const L = () => [{ id: 1, underlying: 'NIFTY', instrument_id: 'A', action: 'BUY', instrument_type: 'CE', strike: '22600.00', expiry: '2026-11-03', days_to_expiry: 6, lots: 1, quantity: 65,
  planned_entry: '194.40', captured_at: '2026-10-28T11:29:37+05:30', included: true, hedge: false }]
const show = (props) => mount(LegList, { props: { legs: L(), hasReply: true, shapeName: 'X', ltpById: {}, priceTextById: {}, ...props } })
const slot = (w) => w.findAll('[data-testid="leg-caption-slot"]')

describe('u505: the captured line never changes the row height', () => {
  it('price not moved: the slot holds the caption line', () => {
    const w = show()
    expect(slot(w)).toHaveLength(1)
    expect(slot(w)[0].classes()).toContain('h-4')
    expect(w.findAll('[data-testid="leg-caption-line"]')).toHaveLength(1)
  })
  it('price moved (the line is hidden): the same fixed-height slot is still there, empty', () => {
    const w = show({ ltpById: { A: '236.35' }, priceTextById: { A: { ltp_display: '236.35', planned_entry_display: '194.40' } } })
    expect(w.findAll('[data-testid="leg-caption-line"]')).toHaveLength(0)
    expect(slot(w)).toHaveLength(1)
    expect(slot(w)[0].classes()).toContain('h-4')
  })
})
