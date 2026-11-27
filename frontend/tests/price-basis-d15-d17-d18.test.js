// GC-ICLIVE-B D-15 / D-17 / D-18: every price-derived figure says which prices it uses; every panel that shows a leg's live
// price says when it was quoted. Real 2026-11-23 cases: C11 plan 23.85 (Get 1,550.25) vs fills 23.70 (Get 1,540.50); C1 plan
// 36.45 vs paper 35.35; C2 25300 PE 7.00 / 7.45 / 7.25 / 7.10 across four panels. The browser computes no money: every text
// below is a string the server sent.
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import MoneySummary from '@/components/strategy/MoneySummary.vue'
import LegList from '@/components/strategy/LegList.vue'
import PaperBookPanel from '@/components/strategy/PaperBookPanel.vue'
import { entryPriceFor } from '@/lib/tracking'

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const NET = { amount: '1540.50', amount_display: '1,541', side: 'get', per_unit: '23.70', per_unit_display: '23.70', text: 'Get ₹1,540.50', reason: null }

describe('D-15 the Get says which prices it uses; the plan stays visible as the plan', () => {
  it('prints the basis and the server plan line, as sent, under the Get (ADR-321 (8))', () => {
    const w = mount(MoneySummary, { props: { netPremium: NET, basisText: 'At paper fill prices', planLine: 'Plan: Get ₹1,550.25 at plan prices' } })
    expect(t(w, 'money-basis').text()).toBe('At paper fill prices')
    expect(t(w, 'plan-line').text()).toBe('Plan: Get ₹1,550.25 at plan prices')
  })
  it('a null plan line (after any exit, or a leg not a fill) prints nothing', () => {
    const w = mount(MoneySummary, { props: { netPremium: NET, basisText: 'At paper fill prices', planLine: null } })
    expect(t(w, 'money-basis').text()).toBe('At paper fill prices')
    expect(t(w, 'plan-line').exists()).toBe(false)
  })
  it('a reply with no basis text or plan line prints neither (an older reply, a plan not kept)', () => {
    const w = mount(MoneySummary, { props: { netPremium: NET } })
    expect(t(w, 'money-basis').exists()).toBe(false)
    expect(t(w, 'plan-line').exists()).toBe(false)
  })
})

describe('D-15 (c) the Add to Paper price says when it differs from the plan', () => {
  it('live 35.35 against plan 36.45 shows "plan 36.45"; the same price shows nothing; no live price keeps the old note', () => {
    expect(entryPriceFor({ instrument_id: 'x', planned_entry: '36.45' }, { x: '35.35' })).toEqual({ price: '35.35', price_note: 'plan 36.45' })
    expect(entryPriceFor({ instrument_id: 'x', planned_entry: '36.45' }, { x: '36.45' })).toEqual({ price: '36.45', price_note: '' })
    expect(entryPriceFor({ instrument_id: 'x', planned_entry: '36.45' }, {}).price_note).toBe('planned price, no live quote')
  })
})

describe('D-18 each panel that shows a leg price says when it was quoted', () => {
  it('the paper book net table: the LTP carries its own quote time from price_at', () => {
    const p = { contract_id: 1, contract_text: 'NIFTY 25300 PE', net_quantity: -65, average_text: '7.00', ltp_text: '7.25', price_at: '2026-11-23T05:31:03Z', booked_text: '0', unbooked_text: '0', total_text: '0' }
    const book = { state: 'LIVE', positions: [p, { ...p, contract_id: 2, price_at: null }], orders: [] }
    const w = mount(PaperBookPanel, { props: { book, net: [] } })
    const stamps = w.findAll('[data-testid="net-ltp-at"]').map((n) => n.text())
    expect(stamps).toEqual(['11:01:03', 'time n/a'])
  })
})

describe('D-18 (round 2) each leg shows its own quote time; the summary line is the OLDEST', () => {
  const leg = (n) => ({ id: `a${n}`, instrument_id: `NSE_FO:${n}`, underlying: 'NIFTY', action: 'SELL', lots: 1, planned_entry: '7.00', captured_at: '2026-11-23T05:00:00Z', expiry: '2026-11-25', instrument_type: 'PE', strike: '25300.00' })
  it('names the older of two leg quote times and each leg its own', () => {
    const w = mount(LegList, { props: { legs: [leg(1), leg(2)], ltpById: { 'NSE_FO:1': '7.45', 'NSE_FO:2': '7.10' }, quoteAtById: { 'NSE_FO:1': '2026-11-23T05:31:09Z', 'NSE_FO:2': '2026-11-23T05:31:02Z' }, oldestQuoteAt: '2026-11-23T05:31:02Z', priceAt: '2026-11-23T05:31:09Z' } })
    expect(t(w, 'leg-prices-as-of').text()).toBe('Oldest leg price as of 11:01:02 IST')
    expect(w.findAll('[data-testid="leg-quote-at"]').map((n) => n.text())).toEqual(['11:01:09', '11:01:02'])
  })
  it('prints the oldest time the server served, not one worked out from the strings it sorts', () => {
    const w = mount(LegList, { props: { legs: [leg(1), leg(2)], ltpById: { 'NSE_FO:1': '7.45', 'NSE_FO:2': '7.10' }, quoteAtById: { 'NSE_FO:1': '2026-11-23T05:31:09Z', 'NSE_FO:2': '2026-11-23T11:01:02+05:30' }, oldestQuoteAt: '2026-11-23T11:01:02+05:30' } })
    expect(t(w, 'leg-prices-as-of').text()).toBe('Oldest leg price as of 11:01:02 IST')
  })
  it('a leg with a price and no time says so, and the summary line does not borrow another time', () => {
    const w = mount(LegList, { props: { legs: [leg(1), leg(2)], ltpById: { 'NSE_FO:1': '7.45', 'NSE_FO:2': '7.10' }, quoteAtById: { 'NSE_FO:1': '2026-11-23T05:31:09Z' }, oldestQuoteAt: null, priceAt: '2026-11-23T05:31:09Z' } })
    expect(t(w, 'leg-prices-as-of').text()).toBe('Leg prices: time not given')
    expect(w.findAll('[data-testid="leg-quote-at"]').map((n) => n.text())).toEqual(['11:01:09', 'time n/a'])
  })
})
