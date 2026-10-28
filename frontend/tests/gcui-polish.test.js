// GC-UI step 7 follow-up POLISH (docs/process/ui-match-differences-2026-10-28.md rows D-A08, D-A20, D-A22, D-A29, D-C41,
// D-C54, D-7a, D-7c). jsdom measures no pixels: every row is asserted as structure. All texts are the server's, as before
// (ADR-008: no number is computed here). The drawer-header row (D-7b) is in leg-picker.test.js beside its spot tests.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url, body) => {
    calls.push([method, url, body])
    const a = answers[`${method} ${url}`]
    return a ? a() : Promise.reject({ message: 'no answer', parts: null, status: null })
  }
  return { ...actual, default: { get: reply('GET'), post: reply('POST'), put: reply('PUT'), patch: reply('PATCH') } }
})
import LegList from '@/components/strategy/LegList.vue'
import MoneySummary from '@/components/strategy/MoneySummary.vue'
import SummaryCards from '@/components/strategy/SummaryCards.vue'
import SaveDraftBar from '@/components/strategy/SaveDraftBar.vue'
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'
import StrategyPriceChart from '@/components/strategy/StrategyPriceChart.vue'
import CONDOR from './fixtures/outcome-money-condor.json'

const t = (w, id) => w.find(`[data-testid="${id}"]`)
beforeEach(() => {
  calls.length = 0
  answers = {}
})

const LEGS = [
  { id: 1, underlying: 'NIFTY', instrument_id: 'A', action: 'BUY', instrument: 'CE', instrument_type: 'CE', strike: '22600.00', expiry: '2026-11-03',
    days_to_expiry: 6, lots: 1, quantity: 65, planned_entry: '194.40', captured_at: '2026-10-28T11:29:37+05:30', included: true, hedge: false },
]

describe('D-A08: leg-list heads sit over their columns, with a "?" at the price head', () => {
  it('every head carries its own padding or alignment so "B/S" and "Expiry" never run together; the price head has the "?" icon', () => {
    const w = mount(LegList, { props: { legs: LEGS, hasReply: true, shapeName: 'X', ltpById: {} } })
    const cells = [...t(w, 'leg-table-head').element.children].slice(1, 7)
    for (const c of cells) expect(c.className).toMatch(/\b(px|pl)-\d/)
    expect(cells[0].className).toContain('text-center') // B/S over its tag
    expect(cells[1].className).toContain('pl-2') // Expiry starts where its box text starts
    const help = t(w, 'price-head').find('[data-testid="price-help"]')
    expect(help.exists()).toBe(true) // the "?" is there with no moved price too
    expect(help.find('svg').exists()).toBe(true)
    expect(help.attributes('data-icon')).toBe('question')
    expect(t(w, 'price-head').text()).toBe('Planned entry') // the words stay
    expect(t(w, 'price-moved-head').exists()).toBe(false)
  })
  it('a moved price marks the same "?" with the moved dot', () => {
    const w = mount(LegList, { props: { legs: LEGS, hasReply: true, shapeName: 'X', ltpById: { A: '236.35' } } })
    const head = t(w, 'price-head')
    expect(head.findAll('[data-testid="price-help"]')).toHaveLength(1)
    expect(head.find('[data-testid="price-help"] [data-testid="price-moved-head"]').exists()).toBe(true)
  })
})

describe('D-A20: net premium and Charges on ONE line, Charges with an icon', () => {
  const np = CONDOR.summary.net_premium
  it('one flex-nowrap line holds the net premium and Charges; per unit comes before the total; Charges has an icon', () => {
    const w = mount(MoneySummary, { props: { netPremium: np, charges: CONDOR.charges_breakdown } })
    const line = t(w, 'money-line')
    expect(line.exists()).toBe(true)
    expect(line.classes()).toEqual(expect.arrayContaining(['flex', 'items-center']))
    expect(line.classes().join(' ')).toContain('flex-nowrap')
    expect(line.find('[data-testid="net-premium"]').exists()).toBe(true)
    expect(line.find('[data-testid="charges-breakdown"]').exists()).toBe(true)
    const perUnit = t(w, 'net-premium-per-unit').element
    const total = t(w, 'net-premium-text').element
    expect(perUnit.compareDocumentPosition(total) & 4).toBeTruthy() // per unit first, then the total
    expect(t(w, 'charges-action').find('[data-testid="charges-icon"] svg').exists()).toBe(true)
    expect(t(w, 'charges-action').text()).toBe('Charges') // our words kept
  })
})

describe('D-A29: summary pills carry the percent inline at a small height', () => {
  const props = { maxProfit: '+4,631', maxLoss: '−1,869', fundsShare: { funds: 'F', read_at: '2026-10-28T09:49:05Z', max_profit_text: '9% of funds', max_loss_text: '4% of funds' } }
  it('the percent is inside the pill element, the pill never wraps and is a fixed small height', () => {
    const w = mount(SummaryCards, { props })
    for (const [pill, fig, pct] of [['max-profit-pill', 'max-profit', 'max-profit-percent'], ['max-loss-pill', 'max-loss', 'max-loss-percent']]) {
      const p = t(w, pill)
      expect(p.find(`[data-testid="${fig}"]`).exists()).toBe(true)
      expect(p.find(`[data-testid="${pct}"]`).exists()).toBe(true)
      const cls = p.classes().join(' ')
      expect(cls).toContain('flex-nowrap')
      expect(cls).toContain('whitespace-nowrap')
      expect(cls).toContain('h-6')
      expect(cls).not.toMatch(/(^| )flex-wrap( |$)/)
    }
    expect(t(w, 'max-profit-percent').text()).toBe('9% of funds')
  })
})

describe('D-A22: action row buttons of equal width', () => {
  it('Save has an equal basis (basis-0) so Add/Edit and Save match; "..." is a wider square', async () => {
    answers['GET /strategies'] = () => Promise.resolve({ data: { strategies: [] } })
    const w = mount(SaveDraftBar, { props: { legs: LEGS, rulesRef: '', current: null }, slots: { 'add-edit': '<button data-testid="add-edit" class="h-10 flex-1 basis-0">Add/Edit</button>' } })
    await flushPromises()
    expect(t(w, 'save-draft').classes()).toEqual(expect.arrayContaining(['flex-1', 'basis-0', 'h-10']))
    expect(t(w, 'more-menu').classes()).toEqual(expect.arrayContaining(['h-10', 'w-12']))
  })
})

describe('D-C41 / D-C54 / D-7a: the Paper tab', () => {
  const leg = (i) => ({ leg_index: i, instrument_id: `NSE_FO:${i}`, action: 'BUY', instrument: 'CE', strike: '22600.00', expiry: '2026-11-03', quantity: 65,
    entry_price: '114.25', current_price: '113.60', price_state: 'live', exit_price: null })
  const item = (id, over = {}) => ({ strategy_id: id, name: `"P ${id}"`, underlying: 'NIFTY', state: 'LIVE', pause_reason: null, as_of: null,
    total: '2808.00', booked: '0.00', unbooked: '2808.00', legs: [leg(0)], ...over })
  async function show(items, compact = false) {
    answers['GET /tracking'] = () => Promise.resolve({ data: { strategies: items, answered_at: '2026-10-28T06:00:00Z' } })
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }] })
    router.push('/')
    await router.isReady()
    const w = mount(PaperStrategies, { props: { compact }, global: { plugins: [router] } })
    await flushPromises()
    return w
  }
  it('D-C41: both the compact and the full list sit in a dashed frame with a "Paper mode" header strip and keep the not-real banner', async () => {
    for (const compact of [true, false]) {
      const w = await show([item(1)], compact)
      expect(t(w, 'paper-mode-header').text()).toBe('Paper mode')
      expect(t(w, 'paper-strategies').classes().join(' ')).toContain('border-dashed')
      expect(t(w, 'paper-banner').text()).toBe('Paper trades - not real money')
      w.unmount()
    }
  })
  it('D-C54: the compact list colours the total by the server sign', async () => {
    const w = await show([item(1, { total: '2808.00' }), item(2, { total: '-1894.75', unbooked: '-1894.75' })], true)
    const totals = w.findAll('[data-testid="paper-total"]')
    expect(totals[0].classes()).toContain('text-profit')
    expect(totals[1].classes()).toContain('text-loss')
  })
  it.each([
    ['LIVE', {}],
    ['PAUSED with a code', { state: 'PAUSED', total: null, unbooked: null, as_of: '2026-10-28T11:00:00+05:30', pause_reason: 'prices_not_live' }],
    ['PAUSED with another code', { state: 'PAUSED', total: null, unbooked: null, as_of: '2026-10-28T11:00:00+05:30', pause_reason: 'price_stale' }],
    ['NOT_CONNECTED', { state: 'NOT_CONNECTED', total: null, unbooked: null, pause_reason: 'prices_not_live' }],
    ['EXITED', { state: 'EXITED', total: '10.00', pause_reason: 'prices_not_live' }],
  ])('D-7a: %s prints no raw state code, in either list', async (_n, over) => {
    for (const compact of [true, false]) {
      const w = await show([item(1, over)], compact)
      expect(w.text()).not.toMatch(/prices_not_live|price_stale|[a-z]+_[a-z_]+/)
      expect(t(w, 'paper-pause-reason').exists()).toBe(false)
      w.unmount()
    }
  })
  it('D-7a: a paused item still says so in words', async () => {
    const w = await show([item(1, { state: 'PAUSED', total: null, unbooked: null, as_of: '2026-10-28T11:00:00+05:30', pause_reason: 'prices_not_live' })])
    expect(t(w, 'paper-state').text()).toContain('Paper P&L paused - prices not live')
  })
})

describe('D-7c: the Strategy Chart card keeps its height while loading', () => {
  it('the loading placeholder is a fixed-height (h-72, the plot height) block', async () => {
    answers['GET /strategies/7/price-history'] = () => new Promise(() => {})
    const w = mount(StrategyPriceChart, { props: { strategyId: 7, active: true } })
    await flushPromises()
    const el = t(w, 'price-chart-loading')
    expect(el.exists()).toBe(true)
    expect(el.classes()).toContain('h-72')
  })
})
