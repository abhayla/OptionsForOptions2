// S-06 (ADR-321 (3), owner case 25 Nov: Max Profit +3,619 = 3,877 - 258 charges, breakeven 25,490 before charges): a plan's summary
// card says which figures are before / after charges. One wording home: lib/targetBlock.js.
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import SummaryCards from '@/components/strategy/SummaryCards.vue'
import {
  OPEN_LEGS_ONLY_TEXT, OPEN_LEGS_ONLY_BEFORE_CHARGES_TEXT, PLAN_BASIS_AFTER_CHARGES_TEXT, PLAN_BASIS_BEFORE_CHARGES_TEXT,
} from '@/lib/targetBlock'

const AFTER = 'Max Profit and Max Loss are after charges estimated at entry prices; breakevens are before charges.'
const BEFORE = 'Max Profit, Max Loss and breakevens are before charges.'
const base = { maxProfit: '+3,619', maxLoss: '-6,131', breakevens: ['25,490'] }
const basis = (w) => w.find('[data-testid="summary-basis"]')

describe('S-06 plan summary basis line', () => {
  it('charges present: the after-charges sentence', () => {
    const w = mount(SummaryCards, { props: { ...base, summary: { charges: '258.00' } } })
    expect(basis(w).text()).toBe(AFTER)
  })
  it('charges null: the before-charges sentence', () => {
    const w = mount(SummaryCards, { props: { ...base, summary: { charges: null } } })
    expect(basis(w).text()).toBe(BEFORE)
  })
  it('no summary: no line', () => {
    expect(basis(mount(SummaryCards, { props: base })).exists()).toBe(false)
  })
  it('a paper book present (left set): the page line speaks, the card prints none', () => {
    const left = { profit: { label: '', text: '+1' }, loss: { label: '', text: '-1' } }
    const w = mount(SummaryCards, { props: { ...base, left, summary: { charges: '258.00' } } })
    expect(basis(w).exists()).toBe(false)
  })
  it('the open-legs texts are byte-identical to their old literals and derived from the two sentences', () => {
    expect(PLAN_BASIS_AFTER_CHARGES_TEXT).toBe(AFTER)
    expect(PLAN_BASIS_BEFORE_CHARGES_TEXT).toBe(BEFORE)
    expect(OPEN_LEGS_ONLY_TEXT).toBe('Open legs only: the booked P&L is not included. Max Profit and Max Loss are after charges estimated at entry prices; breakevens are before charges.')
    expect(OPEN_LEGS_ONLY_BEFORE_CHARGES_TEXT).toBe('Open legs only: the booked P&L is not included. Max Profit, Max Loss and breakevens are before charges.')
  })
})
