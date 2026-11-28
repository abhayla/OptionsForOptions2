// GC-ICFIX u127 (ADR-263, ADR-008, REQ-109 AC-10, ADR-259): the figure shown "(after charges)" opens, on one tap (or Enter / Space),
// a small breakdown of server texts: Before charges, Charges paid, Estimated charges to close, After charges. Nothing is computed
// here; a row whose server text is missing is left out; no after figure -> the before row and the reason sentence; prices not live
// and an older reply -> no tap target. Real values: strategy 141 closed -32.50 / 403.45 / 0.00 / -435.95; an open sold position
// +1,300.00 / 36.09 / 25.95 / +1,237.96.
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

import AfterChargesTap from '@/components/common/AfterChargesTap.vue'
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'
import PaperBookPanel from '@/components/strategy/PaperBookPanel.vue'
import SummaryCards from '@/components/strategy/SummaryCards.vue'
import TrackingPanel from '@/components/strategy/TrackingPanel.vue'
import MyStrategiesPage from '@/pages/MyStrategiesPage.vue'
import { afterFigure, BREAKDOWN_LABELS } from '@/lib/tracking'
import { paperLeftOf } from '@/lib/paperDrafts'
import { resetPaperAlerts } from '@/lib/paperAlerts'
import { withPriceTexts } from './_priceTexts'

const ok = (data) => () => Promise.resolve({ data })
const t = (w, id) => w.get(`[data-testid="${id}"]`)
const clone = () => JSON.parse(JSON.stringify(REAL))
const RATES = 'Charges and taxes are not included: the charge rates could not be read.'
const PAUSED = 'Paper P&L paused - prices not live'
const CLOSED = { total_after: '-435.95', total_after_text: '-435.95', charges_paid: '403.45', charges_to_close: '0.00', charges_to_close_text: '0.00', after_charges_reason: null, after_charges_reason_text: null }
const OPEN = { total_after: '1237.96', total_after_text: '+1,237.96', charges_paid: '36.09', charges_to_close: '25.95', charges_to_close_text: '25.95', after_charges_reason: null, after_charges_reason_text: null }
const NO_AFTER = (reason, text) => ({ total_after: null, total_after_text: null, booked_after_text: null, unbooked_after_text: null, profit_left_after_text: null, loss_left_after_text: null, charges_paid: null, charges_to_close: null, charges_to_close_text: null, after_charges_reason: reason, after_charges_reason_text: text })
const rowsOf = (f) => f.breakdown.rows.map((r) => `${r.label}: ${r.text}`)

beforeEach(() => { answers = {}; resetPaperAlerts(); vi.useFakeTimers() })
afterEach(() => vi.useRealTimers())

describe('u127 afterFigure breakdown (the one rule)', () => {
  it('fixed labels', () => {
    expect(BREAKDOWN_LABELS).toEqual({ before: 'Before charges', paid: 'Charges paid', close: 'Estimated charges to close', after: 'After charges' })
  })
  it('closed trade 141: four rows, to close 0.00 is a figure', () => {
    expect(rowsOf(afterFigure(CLOSED, '-32.50'))).toEqual(['Before charges: -32.50', 'Charges paid: 403.45', 'Estimated charges to close: 0.00', 'After charges: -435.95'])
  })
  it('open sold position: +1,300.00 / 36.09 / 25.95 / +1,237.96', () => {
    expect(rowsOf(afterFigure(OPEN, '+1,300.00'))).toEqual(['Before charges: +1,300.00', 'Charges paid: 36.09', 'Estimated charges to close: 25.95', 'After charges: +1,237.96'])
  })
  it('no after figure (rates_unavailable): the before row and the reason, no after row, no invented number', () => {
    const f = afterFigure(NO_AFTER('rates_unavailable', RATES), '-32.50')
    expect(rowsOf(f)).toEqual(['Before charges: -32.50'])
    expect(f.breakdown.reason).toBe(RATES)
  })
  it('prices not live and an older reply: nothing to open', () => {
    expect(afterFigure(NO_AFTER('prices_not_live', PAUSED), null, PAUSED).breakdown).toBeNull()
    expect(afterFigure({}, '-32.50').breakdown).toBeNull()
  })
  it('a row whose server text is missing is left out (not formatted here)', () => {
    expect(rowsOf(afterFigure({ ...OPEN, charges_to_close_text: null }, '+1,300.00'))).toEqual(['Before charges: +1,300.00', 'Charges paid: 36.09', 'After charges: +1,237.96'])
    expect(rowsOf(afterFigure({ ...OPEN, charges_paid: null }, '+1,300.00'))).toEqual(['Before charges: +1,300.00', 'Estimated charges to close: 25.95', 'After charges: +1,237.96'])
  })
  it('booked shows only Charges paid, unbooked only the estimate to close, a left figure neither', () => {
    const src = { ...OPEN, booked_after_text: '-36.09', unbooked_after_text: '+1,274.05', profit_left_after_text: '+9.00' }
    expect(rowsOf(afterFigure(src, '0.00', null, 'booked_after_text', ['paid']))).toEqual(['Before charges: 0.00', 'Charges paid: 36.09', 'After charges: -36.09'])
    expect(rowsOf(afterFigure(src, '+1,300.00', null, 'unbooked_after_text', ['close']))).toEqual(['Before charges: +1,300.00', 'Estimated charges to close: 25.95', 'After charges: +1,274.05'])
    expect(rowsOf(afterFigure(src, '+8.00', null, 'profit_left_after_text', []))).toEqual(['Before charges: +8.00', 'After charges: +9.00'])
  })
})

describe('u127 AfterChargesTap component', () => {
  const bd = () => afterFigure(CLOSED, '-32.50').breakdown
  const make = (breakdown) => mount(AfterChargesTap, { props: { breakdown }, slots: { default: '<span data-testid="fig">-435.95</span>' }, attachTo: document.body })
  it('closed until tapped; a tap opens the four rows; the figure stays visible; aria-expanded follows', async () => {
    const w = make(bd())
    expect(w.find('[data-testid="after-breakdown"]').exists()).toBe(false)
    expect(t(w, 'after-tap').attributes('aria-expanded')).toBe('false')
    await t(w, 'after-tap').trigger('click')
    expect(t(w, 'after-tap').attributes('aria-expanded')).toBe('true')
    expect(t(w, 'breakdown-before').text()).toBe('Before charges: -32.50')
    expect(t(w, 'breakdown-paid').text()).toBe('Charges paid: 403.45')
    expect(t(w, 'breakdown-close').text()).toBe('Estimated charges to close: 0.00')
    expect(t(w, 'breakdown-after').text()).toBe('After charges: -435.95')
    expect(t(w, 'fig').text()).toBe('-435.95')
    expect(t(w, 'after-breakdown').classes()).toContain('top-full') // opens below the figure, never over it
    w.unmount()
  })
  it('keyboard: focusable, Enter and Space open, Escape closes', async () => {
    const w = make(bd())
    expect(t(w, 'after-tap').attributes('tabindex')).toBe('0')
    await t(w, 'after-tap').trigger('keydown', { key: 'Enter' })
    expect(w.find('[data-testid="after-breakdown"]').exists()).toBe(true)
    await t(w, 'after-tap').trigger('keydown', { key: 'Escape' })
    expect(w.find('[data-testid="after-breakdown"]').exists()).toBe(false)
    await t(w, 'after-tap').trigger('keydown', { key: ' ' })
    expect(w.find('[data-testid="after-breakdown"]').exists()).toBe(true)
    w.unmount()
  })
  it('an outside click closes it', async () => {
    const w = make(bd())
    await t(w, 'after-tap').trigger('click')
    document.body.click()
    await flushPromises()
    expect(w.find('[data-testid="after-breakdown"]').exists()).toBe(false)
    w.unmount()
  })
  it('no after figure with a reason: the before row and the sentence, no after row', async () => {
    const w = make(afterFigure(NO_AFTER('rates_unavailable', RATES), '-32.50').breakdown)
    await t(w, 'after-tap').trigger('click')
    expect(t(w, 'breakdown-before').text()).toBe('Before charges: -32.50')
    expect(t(w, 'breakdown-reason').text()).toBe(RATES)
    expect(w.find('[data-testid="breakdown-after"]').exists()).toBe(false)
    w.unmount()
  })
  it('no breakdown (paused / older reply): the figure only, no tap target', () => {
    const w = make(null)
    expect(t(w, 'fig').text()).toBe('-435.95')
    expect(w.find('[data-testid="after-tap"]').exists()).toBe(false)
    w.unmount()
  })
})

describe('u127 each screen offers the breakdown', () => {
  const open = async (tap) => { await tap.trigger('click'); return tap.element.closest('[data-testid="after-tap"]') ? tap : tap }
  const tapAround = (root, figId) => root.find(`[data-testid="${figId}"] [data-testid="after-tap"]`) // the tap sits inside the figure's own element

  it('trade page book panel: closed 141 and the open sold position', async () => {
    const book = (over) => ({ ...clone().strategies.find((s) => s.state === 'LIVE'), orders: [], ...over })
    let w = mount(PaperBookPanel, { props: { book: book({ total_text: '-32.50', ...CLOSED, state: 'EXITED' }), net: [] } })
    await open(t(w, 'after-tap'))
    expect(w.findAll('[data-testid^="breakdown-"]').map((x) => x.text())).toEqual(['Before charges: -32.50', 'Charges paid: 403.45', 'Estimated charges to close: 0.00', 'After charges: -435.95'])
    w = mount(PaperBookPanel, { props: { book: book({ total_text: '+1,300.00', ...OPEN }), net: [] } })
    await open(t(w, 'after-tap'))
    expect(t(w, 'breakdown-paid').text()).toBe('Charges paid: 36.09')
    expect(t(w, 'breakdown-close').text()).toBe('Estimated charges to close: 25.95')
    expect(t(w, 'after-tap').text()).toBe('+1,237.96')
  })
  it('trade page book panel: no after figure -> before + reason; paused and older reply -> no tap', async () => {
    const book = (over) => ({ ...clone().strategies.find((s) => s.state === 'LIVE'), orders: [], total_text: '-32.50', ...over })
    let w = mount(PaperBookPanel, { props: { book: book(NO_AFTER('rates_unavailable', RATES)), net: [] } })
    await open(t(w, 'after-tap'))
    expect(t(w, 'breakdown-reason').text()).toBe(RATES)
    expect(w.find('[data-testid="breakdown-after"]').exists()).toBe(false)
    w = mount(PaperBookPanel, { props: { book: book({ ...NO_AFTER('prices_not_live', PAUSED), state: 'PAUSED', total_text: null, pause_reason: 'prices_not_live', pause_reason_text: PAUSED }), net: [] } })
    expect(w.find('[data-testid="after-tap"]').exists()).toBe(false)
    w = mount(PaperBookPanel, { props: { book: book(), net: [] } })
    expect(w.find('[data-testid="after-tap"]').exists()).toBe(false)
  })

  async function show(compact = false) {
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: PaperStrategies }, { path: '/strategy/builder', component: { template: '<div/>' } }, { path: '/positions/:p', component: { template: '<div/>' } }] })
    router.push('/')
    await router.isReady()
    const w = mount(PaperStrategies, { props: { compact }, global: { plugins: [router] } })
    await flushPromises()
    return w
  }
  it('practice list: card Total / Booked / Unbooked and the totals strip', async () => {
    const d = clone()
    const liveId = d.strategies.find((s) => s.state === 'LIVE').strategy_id
    const extra = { ...OPEN, booked_after_text: '-36.09', unbooked_after_text: '+1,274.05' }
    for (const x of [d.totals, ...d.strategies]) Object.assign(x, extra)
    answers['GET /paper/strategies'] = ok(d)
    const w = await show()
    const card = w.get(`[data-testid="paper-group"][data-strategy="${liveId}"]`)
    await tapAround(card, 'paper-total').trigger('click')
    expect(card.findAll('[data-testid^="breakdown-"]').map((x) => x.text())).toEqual(expect.arrayContaining(['Charges paid: 36.09', 'Estimated charges to close: 25.95', 'After charges: +1,237.96']))
    await tapAround(card, 'paper-booked').trigger('click')
    await tapAround(card, 'paper-unbooked').trigger('click')
    const texts = card.findAll('[data-testid^="breakdown-"]').map((x) => x.text())
    expect(texts).toContain('After charges: -36.09')
    expect(texts).toContain('After charges: +1,274.05')
    await tapAround(w, 'totals-total').trigger('click')
    expect(w.findAll('[data-testid^="breakdown-"]').length).toBeGreaterThan(texts.length)
  })
  it('practice list: no after figure -> reason in the breakdown; paused -> no tap on the total', async () => {
    const d = clone()
    const liveId = d.strategies.find((s) => s.state === 'LIVE').strategy_id
    for (const x of [d.totals, ...d.strategies]) Object.assign(x, NO_AFTER('rates_unavailable', RATES))
    answers['GET /paper/strategies'] = ok(d)
    let w = await show()
    let card = w.get(`[data-testid="paper-group"][data-strategy="${liveId}"]`)
    await tapAround(card, 'paper-total').trigger('click')
    expect(card.get('[data-testid="breakdown-reason"]').text()).toBe(RATES)
    const p = clone()
    Object.assign(p.strategies.find((s) => s.strategy_id === liveId), { ...NO_AFTER('prices_not_live', PAUSED), state: 'PAUSED', pause_reason: 'prices_not_live', pause_reason_text: PAUSED, total_text: null, total: null })
    answers['GET /paper/strategies'] = ok(p)
    w = await show()
    card = w.get(`[data-testid="paper-group"][data-strategy="${liveId}"]`)
    expect(tapAround(card, 'paper-total').exists()).toBe(false)
  })

  it('Profit left / Loss left: Max (after charges) and Total P&L so far (after charges), ADR-306', async () => {
    const w = mount(SummaryCards, { props: { left: paperLeftOf({ profit_left_text: '+2,900.00', loss_left_text: '-3,600.00', profit_left_after_text: '+3,006.26', loss_left_after_text: '-3,493.74', max_profit_text: '+2,764.83', total_after_text: '-241.43', after_charges_reason: null, charges_paid: '30.00' }), maxProfit: '+2,764.83', maxLoss: '-3,735.17' } })
    await tapAround(w, 'profit-left').trigger('click')
    expect(w.findAll('[data-testid^="breakdown-"]').map((x) => x.text())).toEqual(['Max profit (after charges): +2,764.83', 'Total P&L so far (after charges): -241.43'])
    expect(t(w, 'after-tap').text()).toBe('+3,006.26')
  })

  it('tracking box headline', async () => {
    const leg = withPriceTexts([{ instrument_id: 'NSE_FO:44624', action: 'SELL', instrument: 'CE', strike: '22800.00', entry_price: '39.15', current_price: '45.15', price_state: 'live', expiry: '2026-11-03', quantity: 65, exit_price: null }])
    const b = { strategy_id: 7, state: 'LIVE', paper_pnl: '-32.50', paper_pnl_text: '-32.50', as_of: null, legs: leg, detections: [], ...CLOSED }
    answers['GET /strategies/7/tracking'] = ok(b)
    answers['POST /strategies/7/tracking'] = ok(b)
    const w = mount(TrackingPanel, { props: { savedId: 7, legs: null } })
    await flushPromises()
    await t(w, 'after-tap').trigger('click')
    expect(t(w, 'breakdown-before').text()).toBe('Before charges: -32.50')
    expect(t(w, 'breakdown-after').text()).toBe('After charges: -435.95')
    expect(t(w, 'paper-pnl').text()).toContain('(after charges)')
  })

  it('Completed row: the server charges_paid_text is only the figure, so the row adds the word Charges (strategy 143)', async () => {
    const closed = { ...CLOSED, total_after: '-305.24', total_after_text: '-305.24', charges_paid: '279.24', charges_paid_text: '₹279.24' }
    answer = () => Promise.resolve({ data: { strategies: [{ id: 143, underlying: 'NIFTY', status: 'closed', status_word: 'Completed', created_at: '2026-10-18T04:00:00Z', updated_at: '2026-10-18T04:00:00Z', final_pnl_text: '-26.00', ...closed }] } })
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/s', component: MyStrategiesPage, meta: { title: 'Completed Strategies', parent: 'Strategies', completedOnly: true } }, { path: '/strategy/builder', component: { template: '<div/>' } }] })
    await router.push('/s')
    await router.isReady()
    const w = mount(MyStrategiesPage, { global: { plugins: [router] } })
    await flushPromises()
    expect(t(w, 'row-completed').text()).toContain('Final P&L -26.00 · Charges ₹279.24 · Net after charges -305.24')
  })

  it('Completed row: Net after charges opens the breakdown; the Charges figure stays its own number', async () => {
    answer = () => Promise.resolve({ data: { strategies: [{ id: 141, underlying: 'NIFTY', status: 'closed', status_word: 'Completed', created_at: '2026-10-18T04:00:00Z', updated_at: '2026-10-18T04:00:00Z', final_pnl_text: '-32.50', ...CLOSED }] } })
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/s', component: MyStrategiesPage, meta: { title: 'Completed Strategies', parent: 'Strategies', completedOnly: true } }, { path: '/strategy/builder', component: { template: '<div/>' } }] })
    await router.push('/s')
    await router.isReady()
    const w = mount(MyStrategiesPage, { global: { plugins: [router] } })
    await flushPromises()
    await t(w, 'after-tap').trigger('click')
    expect(w.findAll('[data-testid^="breakdown-"]').map((x) => x.text())).toEqual(['Before charges: -32.50', 'Charges paid: 403.45', 'Estimated charges to close: 0.00', 'After charges: -435.95'])
    expect(t(w, 'row-charges').text()).toBe('· Charges 403.45')
  })
})
