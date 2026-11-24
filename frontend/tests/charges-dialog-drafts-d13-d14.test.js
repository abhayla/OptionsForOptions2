// D-13 / D-14 round 2 (ADR-306 (1)-(6), ADR-320 (2), ADR-008): in Drafts Mode the Charges dialog shows the charges the Max Profit pill
// carries (the paper book's paid + the estimated cost to close at the live price, the server's fields as sent), never the plan's round
// trip at planned prices. On a plan the round trip stays and "Max Profit and Max Loss are after them" stays true there.
// C2-shaped book of tests_app/test_charges_basis_d13_d14.py: paid 97.35, cost to close 94.90, inside Max Profit 192.25.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

let outcome
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    if (method === 'POST' && url === '/strategies/outcome') return Promise.resolve({ data: outcome })
    const a = answers[`${method} ${url}`]
    return a === undefined ? Promise.reject(new Error(`unmocked ${method} ${url}`)) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (url) => respond('GET', url), post: (url, body) => respond('POST', url, body) } }
})
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import plain from './fixtures/outcome-target-plain.json'
import CONDOR from './fixtures/outcome-money-condor.json'
import BOOK from '../../tests/fixtures/paper/strategy-63-roll.json'

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const ROUND_TRIP = CONDOR.charges_breakdown
const C2 = {
  charges: '97.35', charges_text: 'Rs 97.35', charges_paid: '97.35', charges_paid_text: 'Rs 97.35',
  charges_to_close: '94.90', charges_to_close_text: 'Rs 94.90', extremes_charges: '192.25',
  extremes_charges_text: 'Maximum profit and maximum loss include about Rs 192.25 of charges and taxes.',
}
const SENTENCE = 'Max Profit and Max Loss are after them'

beforeEach(() => { outcome = { ...plain, charges_breakdown: ROUND_TRIP } })
afterEach(() => vi.useRealTimers())

async function open(query, book) {
  const catalogue = { underlying: 'NIFTY', contracts: BOOK.positions.map((p) => ({ contract_id: p.contract_id, exchange_segment: 'NSE_FO', exchange_token: p.contract_id,
    instrument_type: p.instrument, expiry: p.expiry, strike: p.strike, lot_size: 65, symbol: `NIFTY${p.strike}${p.instrument}` })) }
  answers = { 'GET /paper/strategies/63': book, 'GET /strategies': { strategies: [] }, 'GET /catalogue/NIFTY/contracts?expiry=2026-11-03': catalogue }
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await router.push({ path: '/strategy/builder', query })
  await router.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true } } })
  await flushPromises()
  return w
}

describe('Charges dialog in Drafts Mode', () => {
  it('shows paid + cost to close = the charges inside Max Profit, never the planned-price round trip', async () => {
    const w = await open({ strategy: '63' }, { ...BOOK, ...C2 })
    await t(w, 'charges-action').trigger('click')
    await flushPromises()
    const panel = t(w, 'charges-panel').text()
    expect(panel).toContain('Rs 97.35')
    expect(panel).toContain('Rs 94.90')
    expect(t(w, 'charges-total').text()).toBe('Total Rs 192.25')
    expect(panel).not.toContain(ROUND_TRIP.total)
    expect(panel).toContain(SENTENCE)
  })

  it('a book with no cost-to-close figure (prices not live): the sentence is not shown beside a figure that is not inside them', async () => {
    const w = await open({ strategy: '63' }, { ...BOOK, ...C2, charges_to_close: null, charges_to_close_text: null, extremes_charges: null, extremes_charges_text: null })
    await t(w, 'charges-action').trigger('click')
    await flushPromises()
    expect(t(w, 'charges-panel').text()).not.toContain(SENTENCE)
    expect(t(w, 'charges-panel').text()).not.toContain(ROUND_TRIP.total)
  })

  it('a plan keeps the round trip, and the sentence is true there', async () => {
    const draft = { underlying: 'NIFTY', legs: plain.legs.map((l) => ({ instrument_id: l.instrument_id, action: l.action, lots: l.lots, planned_entry: l.planned_entry, captured_at: l.captured_at })) }
    const w = await open({ draft: JSON.stringify(draft) }, BOOK)
    await t(w, 'charges-action').trigger('click')
    await flushPromises()
    expect(t(w, 'charges-total').text()).toBe(`Total Rs ${ROUND_TRIP.total}`)
    expect(t(w, 'charges-panel').text()).toContain(SENTENCE)
  })
})

// finding 3: a paused book (`extremes: null` before) shows Max Profit before charges; the server's sentence says so beside it
import SummaryCards from '@/components/strategy/SummaryCards.vue'
import { paperLeftOf } from '@/lib/paperDrafts'

const BEFORE = 'Maximum profit and maximum loss are before charges and taxes: the charges could not be priced.'

describe('paused book: the basis sentence stays beside Max Profit', () => {
  it('Drafts Mode tiles: the server sentence is shown', () => {
    const book = { ...BOOK, state: 'PAUSED', after_charges_reason: 'prices_not_live', after_charges_reason_text: 'Prices are not live.',
      max_profit_text: '+484.25', extremes_charges: null, extremes_charges_text: BEFORE }
    const w = mount(SummaryCards, { props: { left: paperLeftOf(book), maxProfit: '+484.25', maxLoss: '-6,015.75' } })
    expect(t(w, 'extremes-charges-text').text()).toBe(BEFORE)
    expect(w.find('[data-testid="max-profit-basis"]').exists()).toBe(false)
  })
})
