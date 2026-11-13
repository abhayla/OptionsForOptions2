// GC-ICFIX u123 + u125 (ADR-263, ADR-259, ADR-008, REQ-109 AC-5/AC-10): every total profit or loss of a practice trade is the
// server's figure AFTER charges, labelled "(after charges)"; when the server has none it is the before figure labelled
// "(before charges)" with the server's reason sentence; prices not live is the paused text and no number. Nothing is computed
// here. Real cases: strategy 141 closed -32.50 / 403.45 / -435.95; strategy 139 -159.25 / 352.40 / -511.65.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import REAL from './fixtures/paper-strategies.json'

let answers = {}
let answer = () => Promise.reject(new Error('unmocked'))
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url) => {
    const a = answers[`${method} ${url}`]
    if (a) return a()
    return method === 'GET' && url === '/strategies' ? answer(url) : Promise.reject({ message: 'no answer', parts: null, status: null })
  }
  return { ...actual, default: { get: reply('GET'), post: reply('POST'), delete: reply('DELETE') } }
})

import PaperStrategies from '@/components/strategy/PaperStrategies.vue'
import PaperBookPanel from '@/components/strategy/PaperBookPanel.vue'
import TrackingPanel from '@/components/strategy/TrackingPanel.vue'
import MyStrategiesPage from '@/pages/MyStrategiesPage.vue'
import { resetPaperAlerts } from '@/lib/paperAlerts'
import { withPriceTexts } from './_priceTexts'

const ok = (data) => () => Promise.resolve({ data })
const t = (w, id) => w.get(`[data-testid="${id}"]`)
const clone = () => JSON.parse(JSON.stringify(REAL))
const RATES = 'Charges and taxes are not included: the charge rates could not be read.'
const NOT_PRICED = 'Charges are not included: a leg has no price to charge on.'
const PAUSED = 'Paper P&L paused - prices not live'
const AFTER = { total_after: '-435.95', total_after_text: '-435.95', charges_paid: '403.45', charges_to_close: '0.00', charges_to_close_text: '₹0.00', after_charges_reason: null, after_charges_reason_text: null }
const NO_AFTER = (reason, text) => ({ total_after: null, total_after_text: null, charges_paid: null, charges_to_close: null, charges_to_close_text: null, after_charges_reason: reason, after_charges_reason_text: text })

beforeEach(() => { answers = {}; resetPaperAlerts(); vi.useFakeTimers() })
afterEach(() => vi.useRealTimers())

describe('u123 trade page book panel: Total P&L after charges', () => {
  const book = (over = {}) => ({ ...clone().strategies.find((s) => s.state === 'LIVE'), orders: [], total_text: '-32.50', ...over })
  const mountBook = (b) => mount(PaperBookPanel, { props: { book: b, net: [] } })

  it('A: the after figure with "(after charges)"', () => {
    const w = mountBook(book(AFTER))
    expect(t(w, 'book-total-label').text()).toBe('Total P&L (after charges)')
    expect(t(w, 'book-total').text()).toBe('-435.95')
    expect(w.find('[data-testid="book-after-reason"]').exists()).toBe(false)
  })
  it('B: no after figure (rates unavailable / not priced): the before figure, "(before charges)", the server sentence, never blank or 0', () => {
    for (const [code, sentence] of [['rates_unavailable', RATES], ['not_priced', NOT_PRICED]]) {
      const w = mountBook(book(NO_AFTER(code, sentence)))
      expect(t(w, 'book-total-label').text()).toBe('Total P&L (before charges)')
      expect(t(w, 'book-total').text()).toBe('-32.50')
      expect(t(w, 'book-after-reason').text()).toBe(sentence)
      expect(w.text()).not.toContain('(after charges)')
      expect(w.html()).not.toMatch(/rates_unavailable|not_priced/)
    }
  })
  it('C: prices not live: the paused text (REQ-109 AC-5), no number, no label claiming charges', () => {
    const w = mountBook(book({ ...NO_AFTER('prices_not_live', PAUSED), state: 'PAUSED', total: null, total_text: null, pause_reason: 'prices_not_live', pause_reason_text: PAUSED }))
    expect(t(w, 'book-total').text()).toBe('-')
    expect(t(w, 'book-after-reason').text()).toBe(PAUSED)
    expect(w.text()).not.toMatch(/\(after charges\)|\(before charges\)/)
  })
  it('D: a closed trade shows its final after-charges figure (strategy 141: -32.50 before, -435.95 after)', () => {
    const w = mountBook(book({ ...AFTER, state: 'EXITED' }))
    expect(t(w, 'book-total-label').text()).toBe('Total P&L (after charges)')
    expect(t(w, 'book-total').text()).toBe('-435.95')
    expect(w.text()).not.toContain('-32.50')
  })
  it('E: an older server (no new fields at all): the before figure under "(before charges)", never under "after"', () => {
    const w = mountBook(book())
    expect(t(w, 'book-total-label').text()).toBe('Total P&L (before charges)')
    expect(t(w, 'book-total').text()).toBe('-32.50')
    expect(w.text()).not.toContain('(after charges)')
  })
  it('a reply that sends both an after figure and a reason is not trusted as "after"', () => {
    const w = mountBook(book({ ...AFTER, after_charges_reason: 'rates_unavailable', after_charges_reason_text: RATES }))
    expect(t(w, 'book-total-label').text()).toBe('Total P&L (before charges)')
  })
})

describe('u123 practice strategies list: rows and totals', () => {
  async function show(compact = false) {
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: PaperStrategies }, { path: '/strategy/builder', component: { template: '<div/>' } }, { path: '/positions/:p', component: { template: '<div/>' } }] })
    router.push('/')
    await router.isReady()
    const w = mount(PaperStrategies, { props: { compact }, global: { plugins: [router] } })
    await flushPromises()
    return w
  }
  const live = (d) => d.strategies.find((s) => s.state === 'LIVE')

  it('A: each card and the totals strip show the after figure labelled', async () => {
    const d = clone()
    for (const x of [d.totals, ...d.strategies]) Object.assign(x, AFTER)
    answers['GET /paper/strategies'] = ok(d)
    const w = await show()
    expect(t(w, 'totals-total-label').text()).toBe('Total P&L (after charges)')
    expect(t(w, 'totals-total').text()).toBe('-435.95')
    const card = w.get(`[data-testid="paper-group"][data-strategy="${live(d).strategy_id}"]`)
    expect(card.get('[data-testid="paper-total-label"]').text()).toBe('Total P&L (after charges)')
    expect(card.get('[data-testid="paper-total"]').text()).toBe('-435.95')
  })
  it('B: one row has no after figure: the totals strip shows the before total, "(before charges)" and the reason, not a partial sum', async () => {
    const d = clone()
    Object.assign(d.totals, NO_AFTER('not_priced', NOT_PRICED))
    for (const s of d.strategies) Object.assign(s, AFTER)
    Object.assign(live(d), NO_AFTER('not_priced', NOT_PRICED))
    answers['GET /paper/strategies'] = ok(d)
    const w = await show()
    expect(t(w, 'totals-total-label').text()).toBe('Total P&L (before charges)')
    expect(t(w, 'totals-total').text()).toBe(d.totals.total_text)
    expect(t(w, 'totals-total-after-reason').text()).toBe(NOT_PRICED)
    const card = w.get(`[data-testid="paper-group"][data-strategy="${live(d).strategy_id}"]`)
    expect(card.get('[data-testid="paper-total-label"]').text()).toBe('Total P&L (before charges)')
    expect(card.get('[data-testid="paper-total-after-reason"]').text()).toBe(NOT_PRICED)
  })
  it('C: prices not live: the paused sentence, no number, in the totals strip', async () => {
    const d = clone()
    Object.assign(d.totals, { ...NO_AFTER('prices_not_live', PAUSED), total_text: null, total: null, totals_reason: 'prices_not_live', totals_reason_text: PAUSED })
    Object.assign(live(d), { ...NO_AFTER('prices_not_live', PAUSED), total_text: null, total: null, state: 'PAUSED', pause_reason: 'prices_not_live', pause_reason_text: PAUSED })
    answers['GET /paper/strategies'] = ok(d)
    const w = await show()
    expect(t(w, 'totals-total').text()).toBe('—')
    expect(t(w, 'totals-total-after-reason').text()).toBe(PAUSED)
    expect(t(w, 'totals-total-label').text()).toBe('Total P&L')
  })
  it('E: an older server: the before totals labelled "(before charges)"', async () => {
    answers['GET /paper/strategies'] = ok(clone())
    const w = await show()
    expect(t(w, 'totals-total-label').text()).toBe('Total P&L (before charges)')
    expect(w.text()).not.toContain('(after charges)')
  })
  it('compact list row: the after figure with its label', async () => {
    const d = clone()
    Object.assign(live(d), AFTER)
    answers['GET /paper/strategies'] = ok(d)
    const w = await show(true)
    const row = w.get(`[data-testid="paper-compact-row"][data-strategy="${live(d).strategy_id}"]`)
    expect(row.get('[data-testid="paper-total"]').text()).toBe('-435.95')
    expect(row.get('[data-testid="paper-total-label"]').text()).toBe('(after charges)')
  })
})

describe('u123 tracking box', () => {
  const leg = withPriceTexts([{ instrument_id: 'NSE_FO:44624', action: 'SELL', instrument: 'CE', strike: '22800.00', entry_price: '39.15', current_price: '45.15', price_state: 'live', expiry: '2026-11-03', quantity: 65, exit_price: null }])
  const body = (over = {}) => ({ strategy_id: 7, state: 'LIVE', paper_pnl: '-32.50', paper_pnl_text: '-32.50', as_of: null, legs: leg, detections: [], ...over })
  async function panel(b) {
    answers['GET /strategies/7/tracking'] = ok(b)
    answers['POST /strategies/7/tracking'] = ok(b)
    const w = mount(TrackingPanel, { props: { savedId: 7, legs: null } })
    await flushPromises()
    return w
  }
  it('A: the after figure, labelled', async () => {
    const w = await panel(body(AFTER))
    expect(t(w, 'paper-pnl').text()).toContain('-435.95')
    expect(t(w, 'paper-pnl').text()).toContain('(after charges)')
    expect(t(w, 'paper-pnl').text()).not.toContain('-32.50')
  })
  it('B: no after figure: the before figure, "(before charges)" and the server sentence', async () => {
    const w = await panel(body(NO_AFTER('rates_unavailable', RATES)))
    expect(t(w, 'paper-pnl').text()).toContain('-32.50')
    expect(t(w, 'paper-pnl').text()).toContain('(before charges)')
    expect(t(w, 'tracking-after-reason').text()).toBe(RATES)
  })
  it('C: paused: the paused text, no number', async () => {
    const w = await panel(body({ ...NO_AFTER('prices_not_live', PAUSED), state: 'PAUSED', paper_pnl: null, paper_pnl_text: null, as_of: '2026-11-13T09:30:00+05:30' }))
    expect(t(w, 'paper-pnl').text()).toContain('paused')
    expect(t(w, 'paper-pnl').text()).not.toMatch(/\(after charges\)|\(before charges\)|-32\.50/)
  })
  it('D: exited: the final after figure', async () => {
    const w = await panel(body({ ...AFTER, state: 'EXITED' }))
    expect(t(w, 'paper-pnl').text()).toContain('-435.95')
    expect(t(w, 'paper-pnl').text()).toContain('(after charges)')
  })
  it('E: an older server: "(before charges)" only', async () => {
    const w = await panel(body())
    expect(t(w, 'paper-pnl').text()).toContain('(before charges)')
    expect(t(w, 'paper-pnl').text()).not.toContain('(after charges)')
  })
})

describe('u125 Completed list row', () => {
  const row = (id, over = {}) => ({ id, underlying: 'NIFTY', status: 'closed', created_at: '2026-10-18T04:00:00Z', updated_at: '2026-10-18T04:00:00Z', ...over })
  async function open(...rows) {
    answer = () => Promise.resolve({ data: { strategies: rows } })
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/s', component: MyStrategiesPage, meta: { title: 'Completed Strategies', parent: 'Strategies', completedOnly: true } }, { path: '/strategy/builder', component: { template: '<div/>' } }] })
    await router.push('/s')
    await router.isReady()
    const w = mount(MyStrategiesPage, { global: { plugins: [router] } })
    await flushPromises()
    return w
  }
  it('D: "Final P&L -159.25 · Charges 352.40 · Net after charges -511.65" (strategy 139) from the server fields', async () => {
    const w = await open(row(139, { final_pnl_text: '-159.25', total_after: '-511.65', total_after_text: '-511.65', charges_paid: '352.40', after_charges_reason: null }))
    expect(t(w, 'row-completed').text()).toContain('Final P&L -159.25 · Charges 352.40 · Net after charges -511.65')
  })
  it('B: charges and net unavailable: "not available: <reason>", never 0', async () => {
    const w = await open(row(141, { final_pnl_text: '-32.50', total_after: null, total_after_text: null, charges_paid: null, after_charges_reason: 'rates_unavailable', after_charges_reason_text: RATES }))
    expect(t(w, 'row-charges').text()).toContain(`Charges not available: ${RATES}`)
    expect(t(w, 'row-net-after').text()).toContain(`Net after charges not available: ${RATES}`)
    expect(t(w, 'row-completed').text()).not.toMatch(/Charges 0|Net after charges 0/)
  })
  it('E: an older server without the fields: not available, never 0', async () => {
    const w = await open(row(9, { final_pnl_text: '+1,950.00', completed_reason_text: 'Not available: charge rates unreadable' }))
    expect(t(w, 'row-charges').text()).toContain('Charges not available')
    expect(t(w, 'row-net-after').text()).toContain('Net after charges not available')
  })
})
