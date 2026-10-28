// G-065 attack 6 (REQ-148 AC-4/AC-6, ADR-143): legs on more than one expiry have no single maximum. The summary keys are
// those the backend sends for a mixed-expiry condor (tests_app/test_outcome_route.py, the G-065 tests): max_loss and
// max_profit null, not unlimited, no breakevens, the ADR-143 line as what_can_i_lose.
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import SummaryCards from '@/components/strategy/SummaryCards.vue'
import { maxLine, MAX_NOT_AVAILABLE } from '@/lib/displayFormat'

const WORST = "Worst case: the loss for this strategy can't be estimated."
const MIXED = {
  max_loss: null, max_profit: null, max_loss_unlimited: false, max_profit_unlimited: false, breakevens: [],
  what_can_i_lose: WORST,
  what_can_i_make: 'The most this strategy can make can\'t be estimated: its legs are on more than one expiry.',
}
const t = (w, id) => w.find(`[data-testid="${id}"]`)

describe('REQ-148 AC-4: no single maximum reads Not available with the ADR-143 line', () => {
  it('Max Loss and Max Profit read "Not available", the lose line is the ADR-143 line, no NaN, "-" or "0"', async () => {
    const w = mount(SummaryCards, { props: {
      maxProfit: maxLine(MIXED, 'profit'), maxLoss: maxLine(MIXED, 'loss'), breakevens: MIXED.breakevens,
      whatCanILose: MIXED.what_can_i_lose, whatCanIMake: MIXED.what_can_i_make,
    } })
    for (const id of ['max-loss', 'max-profit']) {
      expect(t(w, id).text()).toBe(MAX_NOT_AVAILABLE)
      expect(t(w, id).text()).not.toMatch(/^(-|0|NaN)$/)
    }
    // GC-UI step 3b (REQ-034 AC-7, ADR-204): the ADR-143 line is the first line of the Max Loss "?", verbatim
    const hint = w.find('[data-testid="figure-hint"][data-figure="max_loss"]')
    await hint.find('[data-testid="figure-hint-mark"]').trigger('click')
    expect(hint.findAll('[data-testid="figure-hint-line"]').map((l) => l.text())).toEqual([WORST])
    expect(w.text()).not.toMatch(/NaN/)
  })

  it('no summary still reads "-"; Unlimited still wins; a sent figure is printed as sent', () => {
    expect(maxLine(null, 'loss')).toBe('-')
    expect(maxLine({ max_loss: null, max_loss_unlimited: true }, 'loss')).toBe('Unlimited')
    expect(maxLine({ max_loss: '3334.50', max_loss_unlimited: false }, 'loss')).toBe('3334.50')
  })
})
