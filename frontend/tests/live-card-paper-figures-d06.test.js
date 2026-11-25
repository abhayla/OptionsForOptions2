// D-06 (ADR-008 one engine; GC-ICLIVE-B): the Live Strategies card of a PAPER trade shows the paper reply's figures (the same
// fields the builder tiles read), not the open-legs-only outcome. Real case: C1 155 (closed short 25400 PE booked +643.50, then
// the adjusted condor): builder +2,380.32 / -4,119.68, BE 25,457 / 25,693; the card showed +1,985 / -4,515, BE 25,466 / 25,684.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { echoSeq } from './helpers/echoSeq'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

let bookAnswer
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const get = (url) => {
    if (url === '/strategies') return Promise.resolve({ data: { strategies: [{ id: 155, underlying: 'NIFTY', status: 'draft', status_word: 'Running', has_order: true, created_at: '2026-11-23T10:00:00+05:30', updated_at: '2026-11-23T10:00:00+05:30' }] } })
    if (/^\/paper\/strategies\/155$/.test(url)) return typeof bookAnswer === 'function' ? bookAnswer() : Promise.resolve({ data: bookAnswer })
    if (/^\/catalogue\/NIFTY\/contracts/.test(url)) {
      return Promise.resolve({ data: { contracts: [...Array(40).keys()].map((i) => ({ contract_id: i + 1, exchange_segment: 'NSE_FO', exchange_token: 1001 + i,
        instrument_type: 'PE', expiry: '2026-11-25', strike: '25400.00', lot_size: 65, symbol: `NIFTY${i + 1}` })) } })
    }
    return Promise.reject(new Error(`unmocked get ${url}`))
  }
  return { ...actual, default: { get, post: () => Promise.resolve({ data: {} }) } }
})
import LiveStrategiesPage from '@/pages/LiveStrategiesPage.vue'

class FakeSocket {
  static all = []
  constructor(url) { this.url = url; this.sent = []; this.readyState = 0; FakeSocket.all.push(this) }
  send(t) { this.sent.push(t) }
  close() { this.readyState = 3 }
  serverOpen() { this.readyState = 1; this.onopen?.() }
  serverPush(obj) { this.onmessage?.({ data: JSON.stringify(echoSeq(this, obj)) }) }
}

const book = (over = {}) => ({
  strategy_id: 155, underlying: 'NIFTY', answered_at: '2026-11-23T11:18:00+05:30', state: 'LIVE', as_of: null,
  orders: [{ id: 1 }, { id: 2 }],
  positions: [{ contract_id: 5, net_quantity: -65, average: '88.50', expiry: '2026-11-25', price_at: '2026-11-23T11:18:00+05:30' },
    { contract_id: 6, net_quantity: 0, average: '90.00', expiry: '2026-11-25' }],
  max_profit_text: '+2,380.32', max_loss_text: '−4,119.68', max_profit: '2380.32', max_loss: '-4119.68',
  breakevens: ['25457.00', '25693.00'], breakevens_display: ['25,457 (−0.4%)', '25,693 (+0.5%)'], breakevens_reason: null,
  extremes_reason_text: null, total_after_text: '+3.50', total_text: '+9.00', after_charges_reason: null,
  extremes_charges_text: 'Maximum profit and maximum loss include about Rs 61.00 of charges and taxes.',
  breakevens_basis_text: 'Breakevens include the booked P&L and about Rs 61.00 of charges and taxes.', ...over,
})
// what the outcome socket sends: the OPEN legs only, no booked +643.50
const outcome = () => ({ state: 'COMPUTED', underlying: 'NIFTY', status_label: null, reason: null, output_label: null,
  spot_level: '25575.00', spot_at: '2026-11-23T11:18:00+05:30', answered_at: '2026-11-23T11:18:01+05:30',
  summary: { max_profit: '1985.00', max_loss: '-4515.00', max_profit_display: '+1,985', max_loss_display: '−4,515',
    breakevens_display: ['25,466 (−0.4%)', '25,684 (+0.4%)'] },
  legs: [{ instrument_id: 'NSE_FO:1005', symbol: 'NIFTY5', action: 'SELL', ltp: '39.15', health: 'available', label: null }] })

const mounted = []
async function mountCard() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }, { path: '/strategy/builder', component: { template: '<div/>' } }, { path: '/positions/adjustment-opportunities', component: { template: '<div/>' } }] })
  router.push('/')
  await router.isReady()
  const w = mount(LiveStrategiesPage, { global: { plugins: [router] } })
  mounted.push(w)
  await flushPromises()
  FakeSocket.all.forEach((s) => s.serverOpen())
  FakeSocket.all[0].serverPush(outcome())
  await flushPromises()
  return w.get('[data-strategy-id="155"]')
}

beforeEach(() => {
  FakeSocket.all = []
  bookAnswer = book()
  vi.useRealTimers()
  vi.spyOn(Math, 'random').mockReturnValue(0)
  global.WebSocket = FakeSocket
})
afterEach(() => { while (mounted.length) mounted.pop().unmount(); vi.restoreAllMocks() })

describe('D-06: the card of a paper trade reads the paper reply', () => {
  it('core: C1 155 card max profit / max loss / breakevens are the book reply texts, not the open-legs outcome', async () => {
    const c = await mountCard()
    expect(c.get('[data-testid="live-max-profit"]').text()).toBe('+2,380.32')
    expect(c.get('[data-testid="live-max-loss"]').text()).toBe('−4,119.68')
    expect(c.get('[data-testid="live-breakevens"]').text()).toBe('Breakeven: 25,457 (−0.4%), 25,693 (+0.5%)')
  })
  it('labels the basis: booked P&L and charges', async () => {
    const c = await mountCard()
    const lines = c.findAll('[data-testid="live-figures-basis"]').map((x) => x.text())
    expect(lines).toEqual(['Maximum profit and maximum loss include about Rs 61.00 of charges and taxes.',
      'Breakevens include the booked P&L and about Rs 61.00 of charges and taxes.'])
    expect(c.get('[data-testid="live-total"]').text()).toContain('+3.50 (after charges)') // D-07: the one after-charges total, labelled
  })
  it('no maximum from the book (multi-expiry): dash and the server reason, not the outcome figure', async () => {
    bookAnswer = book({ max_profit_text: null, max_loss_text: null, max_profit: null, max_loss: null, extremes_reason_text: 'Legs on more than one expiry.',
      breakevens: null, breakevens_display: null, breakevens_reason_text: 'Legs on more than one expiry.' })
    const c = await mountCard()
    expect(c.get('[data-testid="live-max-profit"]').text()).toBe('-')
    expect(c.get('[data-testid="live-figures-reason"]').text()).toBe('Legs on more than one expiry.')
  })
})
