// GC-ICFIX issues 3 and 4, last screen leftovers (ADR-306, ADR-302, ADR-303, ADR-263, ADR-008, REQ-109 AC-5): every profit figure of
// the trade page and the practice list says its basis and its breakdown rows are server texts that explain it.
//  1. Profit left / Loss left open "Max profit (after charges)" + "Total P&L so far (after charges)" (the figure IS their difference).
//  2. The practice list's totals strip opens a "Charges paid" row (the totals' charges_paid_text).
//  3. extremes_charges_text shows under Max Profit / Max Loss; the after-charges forms are labelled "(after charges)".
//  4. The P&L table's per-row P&L column says "(before charges)" once; the TOTAL row's percent is a dash (no server percent).
// Real values: losing sold put (all after charges) Total -3,314.09, Max profit 6,437.38, Profit left 9,751.47, recover 3,314.09;
// iron condor at entry Total -241.43, Max profit 2,764.83, Profit left 3,006.26, Max loss -3,735.17, Loss left -3,493.74.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import REAL from './fixtures/paper-strategies.json'
import condor from './fixtures/outcome-condor.json'

let answers = {}
vi.mock('chart.js/auto', () => ({ default: class { constructor() {} destroy() {} } }))
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url) => {
    const a = answers[`${method} ${url}`]
    return a ? a() : Promise.reject({ message: 'no answer', parts: null, status: null })
  }
  return { ...actual, default: { get: reply('GET'), post: reply('POST'), delete: reply('DELETE') } }
})

import SummaryCards from '@/components/strategy/SummaryCards.vue'
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'
import ChartCard from '@/components/strategy/ChartCard.vue'
import { paperLeftOf } from '@/lib/paperDrafts'
import { sharedTotal } from '@/lib/tracking'
import { resetPaperAlerts } from '@/lib/paperAlerts'

const ok = (data) => () => Promise.resolve({ data })
const t = (w, id) => w.get(`[data-testid="${id}"]`)
const clone = () => JSON.parse(JSON.stringify(REAL))
const RATES = 'Charges and taxes are not included: the charge rates could not be read.'
const PAUSED = 'Paper P&L paused - prices not live'
const NO_AFTER = (reason, text) => ({ total_after_text: null, booked_after_text: null, unbooked_after_text: null, profit_left_after_text: null, loss_left_after_text: null, recover_text: null, charges_paid_text: null, after_charges_reason: reason, after_charges_reason_text: text })
const LOSING = { profit_left_text: '+1,400.00', loss_left_text: '-500.00', profit_left_after_text: '9,751.47', loss_left_after_text: '-1,111.11', recover_text: '+3,314.09', total_after_text: '-3,314.09', max_profit_text: '6,437.38', max_loss_text: '-1,000.00', after_charges_reason: null }
const CONDOR = { profit_left_text: '+2,900.00', loss_left_text: '-3,600.00', profit_left_after_text: '3,006.26', loss_left_after_text: '-3,493.74', recover_text: null, total_after_text: '-241.43', max_profit_text: '2,764.83', max_loss_text: '-3,735.17', after_charges_reason: null }
const WITH = 'Maximum profit and maximum loss include about Rs 235.17 of charges and taxes.'
const BEFORE = 'Maximum profit and maximum loss are before charges and taxes: the charges could not be priced.'

beforeEach(() => { answers = {}; resetPaperAlerts(); vi.useFakeTimers() })
afterEach(() => vi.useRealTimers())

const card = (book, extra = {}) => mount(SummaryCards, { props: { left: paperLeftOf(book), maxProfit: book.max_profit_text ?? '-', maxLoss: book.max_loss_text ?? '-', ...extra } })
const rows = (w) => w.findAll('[data-testid^="breakdown-"]').map((x) => x.text())
const tap = (w, id) => w.find(`[data-testid="${id}"] [data-testid="after-tap"]`)

describe('item 1: Profit left / Loss left breakdown is Max (after charges) and Total so far (after charges)', () => {
  it('losing sold put: Profit left rows are Max profit and Total P&L so far, no before / after rows', async () => {
    const w = card({ ...LOSING, extremes_charges: '235.17' })
    await tap(w, 'profit-left').trigger('click')
    expect(rows(w)).toEqual(['Max profit (after charges): 6,437.38', 'Total P&L so far (after charges): -3,314.09'])
    expect(t(w, 'profit-left-recover').text()).toBe('includes Rs 3,314.09 needed to recover the current loss')
  })
  it('iron condor at entry: both figures, Loss left rows use Max loss', async () => {
    const w = card(CONDOR)
    await tap(w, 'profit-left').trigger('click')
    expect(rows(w)).toEqual(['Max profit (after charges): 2,764.83', 'Total P&L so far (after charges): -241.43'])
    await tap(w, 'loss-left').trigger('click')
    expect(rows(w)).toContain('Max loss (after charges): -3,735.17')
    expect(rows(w).filter((r) => r.startsWith('Total P&L so far'))).toHaveLength(2)
    expect(w.text()).not.toMatch(/Before charges|After charges:/)
  })
  it('a row whose server text is missing is left out and no tap opens a half sum', () => {
    const w = card({ ...CONDOR, max_profit_text: null })
    expect(w.find('[data-testid="profit-left"] [data-testid="after-tap"]').exists()).toBe(false)
    expect(t(w, 'profit-left').text()).toBe('3,006.26')
  })
  it('rates_unavailable: the reason sentence, no rows that pretend to add up', () => {
    const w = card({ ...CONDOR, ...NO_AFTER('rates_unavailable', RATES) })
    expect(t(w, 'left-after-reason').text()).toBe(RATES)
    expect(w.find('[data-testid="after-tap"]').exists()).toBe(false)
  })
  it('prices not live: no number, no breakdown; older reply without new fields: no tap target', () => {
    const w = mount(SummaryCards, { props: { left: paperLeftOf({ ...CONDOR, ...NO_AFTER('prices_not_live', PAUSED) }, PAUSED), maxProfit: '-', maxLoss: '-' } })
    expect(t(w, 'profit-left').text()).toBe('-')
    expect(w.find('[data-testid="after-tap"]').exists()).toBe(false)
    const old = card({ profit_left_text: '+2,132.00', loss_left_text: '-868.00' })
    expect(old.find('[data-testid="after-tap"]').exists()).toBe(false)
  })
  it('closed trade: 0.00 and 0.00 are figures, their rows are the server texts as sent', async () => {
    const w = card({ ...CONDOR, profit_left_after_text: '0.00', loss_left_after_text: '0.00', max_profit_text: '0.00', max_loss_text: '0.00', total_after_text: '0.00' })
    expect(t(w, 'profit-left').text()).toBe('0.00')
    await tap(w, 'profit-left').trigger('click')
    expect(rows(w)).toEqual(['Max profit (after charges): 0.00', 'Total P&L so far (after charges): 0.00'])
  })
})

describe('item 2: practice list totals strip opens Charges paid', () => {
  async function show(mutate) {
    const d = clone()
    mutate(d)
    answers['GET /paper/strategies'] = ok(d)
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: PaperStrategies }, { path: '/strategy/builder', component: { template: '<div/>' } }, { path: '/positions/:p', component: { template: '<div/>' } }] })
    router.push('/')
    await router.isReady()
    const w = mount(PaperStrategies, { global: { plugins: [router] } })
    await flushPromises()
    return w
  }
  const OPEN = { total_after_text: '-241.43', charges_paid: '1403.45', charges_paid_text: '1,403.45', charges_to_close_text: '25.95', after_charges_reason: null, after_charges_reason_text: null }
  it('Total P&L tap shows "Charges paid: 1,403.45"; the Charges figure opens the same row', async () => {
    const w = await show((d) => Object.assign(d.totals, OPEN))
    await tap(w, 'totals-total').trigger('click')
    expect(rows(w)).toContain('Charges paid: 1,403.45')
    const c = tap(w, 'totals-charges')
    expect(c.exists()).toBe(true)
    await c.trigger('click')
    expect(w.get('[data-testid="totals-charges"] [data-testid="breakdown-paid"]').text()).toBe('Charges paid: 1,403.45')
  })
  it('older reply without charges_paid_text: no Charges paid row, no empty tap target on Charges', async () => {
    const w = await show((d) => Object.assign(d.totals, { ...OPEN, charges_paid: null, charges_paid_text: null }))
    await tap(w, 'totals-total').trigger('click')
    expect(rows(w).some((r) => r.startsWith('Charges paid'))).toBe(false)
    expect(tap(w, 'totals-charges').exists()).toBe(false)
  })
})

describe('item 3: extremes_charges_text under Max Profit / Max Loss; after-charges forms are labelled', () => {
  it('charges inside: the sentence is shown and Max Profit / Max Loss say "(after charges)"', () => {
    const w = card({ ...CONDOR, extremes_charges: '235.17', extremes_charges_text: WITH })
    expect(t(w, 'extremes-charges-text').text()).toBe(WITH)
    expect(t(w, 'max-profit-basis').text()).toBe('(after charges)')
    expect(t(w, 'max-loss-basis').text()).toBe('(after charges)')
  })
  it('rates unavailable: the server sentence is shown, no "(after charges)" label', () => {
    const w = card({ ...CONDOR, ...NO_AFTER('rates_unavailable', RATES), extremes_charges: null, extremes_charges_text: BEFORE })
    expect(t(w, 'extremes-charges-text').text()).toBe(BEFORE)
    expect(w.find('[data-testid="max-profit-basis"]').exists()).toBe(false)
  })
  it('older reply / closed trade (no sentence): nothing extra shown', () => {
    for (const over of [{}, { extremes_charges: null, extremes_charges_text: null }]) {
      const w = card({ ...CONDOR, ...over })
      expect(w.find('[data-testid="extremes-charges-text"]').exists()).toBe(false)
      expect(w.find('[data-testid="max-profit-basis"]').exists()).toBe(false)
    }
  })
  it('prices not live: the sentence is not shown beside paused figures', () => {
    const w = mount(SummaryCards, { props: { left: paperLeftOf({ ...CONDOR, ...NO_AFTER('prices_not_live', PAUSED), extremes_charges_text: WITH, extremes_charges: '1.00' }, PAUSED), maxProfit: '-', maxLoss: '-' } })
    expect(w.find('[data-testid="max-profit-basis"]').exists()).toBe(false)
  })
})

describe('item 4: the P&L table', () => {
  const shared = (over = {}) => sharedTotal({ strategy_id: 138, state: 'LIVE', answered_at: '2026-11-13T04:01:00Z', total_text: '-100.00', total_after_text: '-241.43', after_charges_reason: null, ...over })
  const mountCard = (paperTotal) => mount(ChartCard, { props: { points: condor.payoff.points, spot: condor.spot_level, table: condor.table, legs: condor.legs, paperTotal } })
  const heads = (w) => w.findAll('[data-testid="compact-head"]').map((x) => x.text())
  const totalRow = (w) => w.findAll('[data-testid="compact-row"]').find((r) => r.text().startsWith('Total'))
  const cell = (r, f) => r.get(`[data-field="${f}"]`).text()
  it('paper: ONE "(before charges)" label for the per-row P&L cells; TOTAL keeps "(after charges)" and a dash percent', () => {
    const w = mountCard(shared())
    expect(heads(w).filter((h) => h.includes('(before charges)'))).toEqual(['P&L (before charges)'])
    expect(w.findAll('[data-testid="compact-cell"]').filter((c) => c.text().includes('(before charges)'))).toHaveLength(0)
    const r = totalRow(w)
    expect(cell(r, 'unrealized_pnl')).toBe('-241.43 (after charges)')
    expect(cell(r, 'pnl_percent')).toBe('—')
  })
  it('paper, prices not live: no number and a dash percent', () => {
    const r = totalRow(mountCard(shared({ state: 'PAUSED', total_after_text: null, total_text: null, after_charges_reason: 'prices_not_live' })))
    expect(cell(r, 'unrealized_pnl')).toBe('—')
    expect(cell(r, 'pnl_percent')).toBe('—')
  })
  it('paper, rates unavailable: the before figure says so and the percent is a dash', () => {
    const r = totalRow(mountCard(shared({ total_after_text: null, after_charges_reason: 'rates_unavailable' })))
    expect(cell(r, 'unrealized_pnl')).toBe('-100.00 (before charges)')
    expect(cell(r, 'pnl_percent')).toBe('—')
  })
  it('closed trade: 0.00 total, dash percent', () => {
    const r = totalRow(mountCard(shared({ total_after_text: '0.00', total_text: '0.00' })))
    expect(cell(r, 'unrealized_pnl')).toBe('0.00 (after charges)')
    expect(cell(r, 'pnl_percent')).toBe('—')
  })
  it('not a paper trade (no shared total): the header and the percent are unchanged', () => {
    const w = mountCard(null)
    expect(heads(w)).toEqual(['Planned entry', 'LTP', 'P&L', 'P&L %'])
    expect(cell(totalRow(w), 'pnl_percent')).not.toBe('—')
  })
})
