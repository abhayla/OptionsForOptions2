// GC-ICFIX u507 (ISSUES.md 41, 43): the "Greeks at target" block prints the server's text figures under the server's basis
// sentence, and that sentence is the Greeks card's own column head ("Per position, 65 units"). The reply's fields are the
// server's (tests_app/test_target_greeks_basis.py); the block only prints them.
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import TargetBlock from '@/components/strategy/TargetBlock.vue'
import { greekModeHeading } from '@/lib/chartCard'
import { FIGURES } from '@/lib/figureDefinitions'

const NOTES_TOTAL = { delta: '1.4014', gamma: '-0.0144', theta: '264.6944', vega: '-116.6645' } // the user's 4-decimal case
const TEXT = { delta: '1.40', gamma: '-0.0144', theta: '264.69', vega: '-116.66' }
const target = (greeks) => ({ kind: 'estimate', pnl: { display: '272.35' }, greeks, limits: { min: '1', max: '2', step: '1' } })
const mountWith = (greeks) => mount(TargetBlock, { props: { target: target(greeks), pick: { level: '', dateIndex: 0 }, stopCount: 2 } })
const rowsOf = (units) => [{ isTotal: false, parts: { quantity: units } }, { isTotal: false, parts: { quantity: units } }]

describe('Greeks at target, basis and places', () => {
  it('prints the server text under the basis, not the raw 4-decimal figures', () => {
    const w = mountWith({ legs: [], total: NOTES_TOTAL, total_display: TEXT, basis_text: 'Per position, 65 units', unavailable: null })
    const text = w.find('[data-testid="target-greeks-total"]').text()
    expect(text).toContain('264.69')
    expect(text).not.toContain('264.6944')
    expect(w.find('[data-testid="target-greeks-basis"]').text()).toBe('Per position, 65 units')
  })

  it('the basis is the same sentence the Greeks card head prints, for one lot and for many', () => {
    for (const units of ['65', '130']) {
      const w = mountWith({ legs: [], total: NOTES_TOTAL, total_display: TEXT, basis_text: `Per position, ${units} units`, unavailable: null })
      expect(w.find('[data-testid="target-greeks-basis"]').text()).toBe(greekModeHeading(rowsOf(units), 'position'))
    }
  })

  it('the no-time-left sentence shows with no basis line', () => {
    const w = mountWith({ legs: [], total: null, total_display: null, basis_text: 'Per position', unavailable: 'no_time_left', unavailable_text: 'No Greeks at expiry: the options have no time left.' })
    expect(w.find('[data-testid="target-greeks-basis"]').exists()).toBe(false)
    expect(w.find('[data-testid="target-greeks-unavailable"]').text()).toContain('No Greeks at expiry')
  })

  it('Decay and Theta each carry a plain label that names the other', () => {
    expect(FIGURES.theta.text).toContain('one calendar day')
    expect(FIGURES.theta.text).toContain('Decay')
    expect(FIGURES.decay.text).toContain('Theta')
    expect(FIGURES.decay.text).toContain('next open')
  })
})
