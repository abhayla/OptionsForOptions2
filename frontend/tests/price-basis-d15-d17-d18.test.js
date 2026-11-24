// GC-ICLIVE-B D-15 / D-17 / D-18: every price-derived figure says which prices it uses; every panel that shows a leg's live
// price says when it was quoted. Real 2026-11-23 cases: C11 plan 23.85 (Get 1,550.25) vs fills 23.70 (Get 1,540.50); C1 plan
// 36.45 vs paper 35.35; C2 25300 PE 7.00 / 7.45 / 7.25 / 7.10 across four panels. The browser computes no money: every text
// below is a string the server sent.
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import MoneySummary from '@/components/strategy/MoneySummary.vue'
import SummaryCards from '@/components/strategy/SummaryCards.vue'
import LegList from '@/components/strategy/LegList.vue'
import PaperBookPanel from '@/components/strategy/PaperBookPanel.vue'
import { entryPriceFor } from '@/lib/tracking'
import { paperBasisFields, planPricesOf } from '@/lib/paperDrafts'

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const NET = { amount: '1540.50', amount_display: '1,541', side: 'get', per_unit: '23.70', per_unit_display: '23.70', text: 'Get ₹1,540.50', reason: null }

describe('D-15 the Get says which prices it uses; the plan stays visible as the plan', () => {
  it('prints the basis and the server plan line under the Get', () => {
    const w = mount(MoneySummary, { props: { netPremium: NET, basisText: 'At paper fill prices', planLine: 'Plan: Get ₹1,550.25 at plan prices' } })
    expect(t(w, 'money-basis').text()).toBe('At paper fill prices')
    expect(t(w, 'plan-line').text()).toBe('Plan: Get ₹1,550.25 at plan prices')
  })
  it('a reply with no basis text or plan line prints neither (an older reply, a plan not kept)', () => {
    const w = mount(MoneySummary, { props: { netPremium: NET } })
    expect(t(w, 'money-basis').exists()).toBe(false)
    expect(t(w, 'plan-line').exists()).toBe(false)
  })
  it('a paper trade asks for the fill basis and sends each leg its plan price (strings, no arithmetic)', () => {
    const plan = planPricesOf([{ instrument_id: 'NSE_FO:1', planned_entry: '23.85' }, { instrument_id: 'NSE_FO:2', planned_entry: '10.00' }])
    expect(plan).toEqual({ 'NSE_FO:1': '23.85', 'NSE_FO:2': '10.00' })
    const draft = { underlying: 'NIFTY', legs: [{ instrument_id: 'NSE_FO:1', planned_entry: '23.70' }, { instrument_id: 'NSE_FO:2', planned_entry: '10.05' }] }
    const sent = paperBasisFields({ plan }, draft)
    expect(sent.price_basis).toBe('paper_fills')
    expect(sent.legs.map((l) => [l.planned_entry, l.plan_entry])).toEqual([['23.70', '23.85'], ['10.05', '10.00']])
    expect(paperBasisFields(null, draft)).toEqual({}) // a plan: the default basis, nothing added
    expect(paperBasisFields({ plan: null }, draft).legs.every((l) => l.plan_entry === undefined)).toBe(true) // plan not kept
  })
  it('the same instrument twice has no single plan price: none is sent for it', () => {
    expect(planPricesOf([{ instrument_id: 'NSE_FO:1', planned_entry: '1.00' }, { instrument_id: 'NSE_FO:1', planned_entry: '2.00' }])).toEqual({})
  })
})

describe('D-15 (c) the Add to Paper price says when it differs from the plan', () => {
  it('live 35.35 against plan 36.45 shows "plan 36.45"; the same price shows nothing; no live price keeps the old note', () => {
    expect(entryPriceFor({ instrument_id: 'x', planned_entry: '36.45' }, { x: '35.35' })).toEqual({ price: '35.35', price_note: 'plan 36.45' })
    expect(entryPriceFor({ instrument_id: 'x', planned_entry: '36.45' }, { x: '36.45' })).toEqual({ price: '36.45', price_note: '' })
    expect(entryPriceFor({ instrument_id: 'x', planned_entry: '36.45' }, {}).price_note).toBe('planned price, no live quote')
  })
})

describe('D-17 the time value names the prices it is on', () => {
  it('prints the server basis beside the Time value', () => {
    const w = mount(SummaryCards, { props: { timeValue: '-3,439', timeValueExact: '-3439.00', intrinsicValue: '0', intrinsicValueExact: '0.00', priceBasis: 'At plan prices', valueLabel: 'value of the options, not P&L' } })
    expect(t(w, 'value-basis').text()).toBe('At plan prices')
  })
})

describe('D-18 each panel that shows a leg price says when it was quoted', () => {
  const leg = { id: 'a', instrument_id: 'NSE_FO:1', underlying: 'NIFTY', action: 'SELL', lots: 1, planned_entry: '7.00', captured_at: '2026-11-23T05:00:00Z', expiry: '2026-11-25', instrument_type: 'PE', strike: '25300.00' }
  it('the leg list: "Leg prices as of HH:MM:SS IST" from the outcome reply; none sent says so; no price shows no line', () => {
    const w = mount(LegList, { props: { legs: [leg], ltpById: { 'NSE_FO:1': '7.45' }, priceAt: '2026-11-23T05:31:02Z' } })
    expect(t(w, 'leg-prices-as-of').text()).toBe('Leg prices as of 11:01:02 IST')
    const none = mount(LegList, { props: { legs: [leg], ltpById: { 'NSE_FO:1': '7.45' }, priceAt: null } })
    expect(t(none, 'leg-prices-as-of').text()).toBe('Leg prices: time not given')
    expect(t(mount(LegList, { props: { legs: [leg] } }), 'leg-prices-as-of').exists()).toBe(false)
  })
  it('the paper book net table: the LTP carries its own quote time from price_at', () => {
    const p = { contract_id: 1, contract_text: 'NIFTY 25300 PE', net_quantity: -65, average_text: '7.00', ltp_text: '7.25', price_at: '2026-11-23T05:31:03Z', booked_text: '0', unbooked_text: '0', total_text: '0' }
    const book = { state: 'LIVE', positions: [p, { ...p, contract_id: 2, price_at: null }], orders: [] }
    const w = mount(PaperBookPanel, { props: { book, net: [] } })
    const stamps = w.findAll('[data-testid="net-ltp-at"]').map((n) => n.text())
    expect(stamps).toEqual(['11:01:03', 'time n/a'])
  })
})
