// GC-ICFIX u124 screens (ADR-301, ADR-302, ADR-303, ADR-263, ADR-008, REQ-109 AC-5 / AC-9): Profit left / Loss left and
// Booked / Unbooked P&L of a practice trade are the server's AFTER-charges texts, labelled "(after charges)"; with no after
// figure the before figure is shown labelled "(before charges)" with the server's reason; prices not live is the paused
// text and no number. When the server sends `recover_text` one fixed line says so. Nothing is added up or capped here.
// Real values from the server's tests: open sold position booked_after -36.09, unbooked_after 1,274.05, total 1,237.96;
// losing position profit_left_after 9,685.91 beside Max profit 6,437.38, recover 3,248.53; condor at entry 2,764.83 / -3,735.17.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import REAL from './fixtures/paper-strategies.json'

let answers = {}
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
import { paperLeftOf, RECOVER_LINE_PREFIX, RECOVER_LINE_SUFFIX } from '@/lib/paperDrafts'
import { resetPaperAlerts } from '@/lib/paperAlerts'

const ok = (data) => () => Promise.resolve({ data })
const t = (w, id) => w.get(`[data-testid="${id}"]`)
const clone = () => JSON.parse(JSON.stringify(REAL))
const RATES = 'Charges and taxes are not included: the charge rates could not be read.'
const NOT_PRICED = 'Charges are not included: a leg has no price to charge on.'
const PAUSED = 'Paper P&L paused - prices not live'
const NO_AFTER = (reason, text) => ({ total_after: null, total_after_text: null, booked_after_text: null, unbooked_after_text: null, profit_left_after_text: null, loss_left_after_text: null, recover_text: null, after_charges_reason: reason, after_charges_reason_text: text })

beforeEach(() => { answers = {}; resetPaperAlerts(); vi.useFakeTimers() })
afterEach(() => vi.useRealTimers())

const LOSING = { profit_left_text: '+14,00.00', loss_left_text: '-5,00.00', profit_left_after_text: '+9,685.91', loss_left_after_text: '-1,111.11', recover_text: '+3,248.53', total_after_text: '-100.00', after_charges_reason: null }
const CONDOR = { profit_left_text: '+2,900.00', loss_left_text: '-3,600.00', profit_left_after_text: '+2,764.83', loss_left_after_text: '-3,735.17', recover_text: null, total_after_text: '-10.00', after_charges_reason: null }

describe('u124 Profit left / Loss left (the trade page summary)', () => {
  const card = (book, paused = null) => mount(SummaryCards, { props: { left: paperLeftOf(book, paused), maxProfit: '+6,437.38', maxLoss: '-1,000.00' } })

  it('A: the after texts as sent, labelled "(after charges)", not capped (9,685.91 beside Max profit 6,437.38)', () => {
    const w = card(LOSING)
    expect(t(w, 'profit-left').text()).toBe('+9,685.91')
    expect(t(w, 'loss-left').text()).toBe('-1,111.11')
    expect(t(w, 'profit-left-label').text()).toBe('Profit left (after charges)')
    expect(t(w, 'loss-left-label').text()).toBe('Loss left (after charges)')
    expect(t(w, 'max-profit').text()).toBe('+6,437.38')
  })
  it('B: recover_text present: the fixed ADR-302 line with the server amount', () => {
    const w = card(LOSING)
    expect(t(w, 'profit-left-recover').text()).toBe('includes Rs 3,248.53 needed to recover the current loss')
    expect(RECOVER_LINE_PREFIX + '3,248.53' + RECOVER_LINE_SUFFIX).toBe('includes Rs 3,248.53 needed to recover the current loss')
  })
  it('C: condor at entry (no recover): both figures, no recover line', () => {
    const w = card(CONDOR)
    expect(t(w, 'profit-left').text()).toBe('+2,764.83')
    expect(t(w, 'loss-left').text()).toBe('-3,735.17')
    expect(w.find('[data-testid="profit-left-recover"]').exists()).toBe(false)
  })
  it('D: no after figure with a reason: the before figure, "(before charges)", the reason sentence', () => {
    for (const [code, sentence] of [['rates_unavailable', RATES], ['not_priced', NOT_PRICED]]) {
      const w = card({ ...CONDOR, ...NO_AFTER(code, sentence) })
      expect(t(w, 'profit-left').text()).toBe('+2,900.00')
      expect(t(w, 'profit-left-label').text()).toBe('Profit left (before charges)')
      expect(t(w, 'loss-left-label').text()).toBe('Loss left (before charges)')
      expect(t(w, 'left-after-reason').text()).toBe(sentence)
      expect(w.text()).not.toContain('(after charges)')
    }
  })
  it('E: prices not live: the paused text, no number, no charges label', () => {
    const w = card({ ...CONDOR, ...NO_AFTER('prices_not_live', PAUSED) }, PAUSED)
    expect(t(w, 'profit-left').text()).toBe('-')
    expect(t(w, 'loss-left').text()).toBe('-')
    expect(t(w, 'left-after-reason').text()).toBe(PAUSED)
    expect(w.text()).not.toMatch(/\(after charges\)|\(before charges\)/)
  })
  it('F: an older reply without the new fields: "(before charges)", never "after"', () => {
    const w = card({ profit_left_text: '+2,132.00', loss_left_text: '-868.00' })
    expect(t(w, 'profit-left').text()).toBe('+2,132.00')
    expect(t(w, 'profit-left-label').text()).toBe('Profit left (before charges)')
    expect(w.text()).not.toContain('(after charges)')
  })
  it('G: a closed trade shows what the server sends; a real 0.00 is a figure, not a dash', () => {
    const w = card({ ...CONDOR, profit_left_after_text: '0.00', loss_left_after_text: '0.00', recover_text: null })
    expect(t(w, 'profit-left').text()).toBe('0.00')
    expect(t(w, 'loss-left').text()).toBe('0.00')
  })
  it('H: extremes_reason keeps the reason words and no figures', () => {
    const w = card({ ...CONDOR, extremes_reason_text: 'Not available: the book is empty' })
    expect(t(w, 'extremes-reason').text()).toBe('Not available: the book is empty')
    expect(w.find('[data-testid="profit-left"]').exists()).toBe(false)
  })
})

describe('u124 Booked / Unbooked P&L (practice list: card and totals strip)', () => {
  const OPEN = { total_after_text: '+1,237.96', booked_after_text: '-36.09', unbooked_after_text: '+1,274.05', after_charges_reason: null, after_charges_reason_text: null }
  async function show() {
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: PaperStrategies }, { path: '/strategy/builder', component: { template: '<div/>' } }, { path: '/positions/:p', component: { template: '<div/>' } }] })
    router.push('/')
    await router.isReady()
    const w = mount(PaperStrategies, { props: { compact: false }, global: { plugins: [router] } })
    await flushPromises()
    return w
  }
  const liveId = REAL.strategies.find((s) => s.state === 'LIVE').strategy_id // fixed before a test changes the state
  const live = (d) => d.strategies.find((s) => s.strategy_id === liveId)
  const cardOf = (w, d) => w.get(`[data-testid="paper-group"][data-strategy="${live(d).strategy_id}"]`)
  const labels = (c) => c.findAll('[data-testid="paper-figure-label"]').map((x) => x.text())

  it('A: the three shown texts are the server three texts, each labelled; the browser adds nothing', async () => {
    const d = clone()
    for (const x of [d.totals, live(d)]) Object.assign(x, OPEN)
    answers['GET /paper/strategies'] = ok(d)
    const w = await show()
    const c = cardOf(w, d)
    expect(c.get('[data-testid="paper-total"]').text()).toBe('+1,237.96')
    expect(c.get('[data-testid="paper-booked"]').text()).toBe('-36.09')
    expect(c.get('[data-testid="paper-unbooked"]').text()).toBe('+1,274.05')
    expect(labels(c)).toEqual(expect.arrayContaining(['Booked P&L (after charges)', 'Unbooked P&L (after charges)']))
    expect(t(w, 'totals-booked').text()).toBe('-36.09')
    expect(t(w, 'totals-unbooked-label').text()).toBe('Unbooked P&L (after charges)')
    expect(t(w, 'totals-booked-label').text()).toBe('Booked P&L (after charges)')
  })
  it('B: no after figure (rates_unavailable / not_priced): before figures, "(before charges)", the reason', async () => {
    for (const [code, sentence] of [['rates_unavailable', RATES], ['not_priced', NOT_PRICED]]) {
      const d = clone()
      for (const x of [d.totals, live(d)]) Object.assign(x, NO_AFTER(code, sentence))
      answers['GET /paper/strategies'] = ok(d)
      const w = await show()
      const c = cardOf(w, d)
      expect(c.get('[data-testid="paper-booked"]').text()).toBe(live(d).booked_text)
      expect(labels(c)).toEqual(expect.arrayContaining(['Booked P&L (before charges)', 'Unbooked P&L (before charges)']))
      expect(c.get('[data-testid="paper-booked-reason"]').text()).toBe(sentence)
      expect(c.get('[data-testid="paper-unbooked-reason"]').text()).toBe(sentence)
      expect(t(w, 'totals-booked-reason').text()).toBe(sentence)
    }
  })
  it('C: prices not live: the paused sentence, no number', async () => {
    const d = clone()
    Object.assign(live(d), { ...NO_AFTER('prices_not_live', PAUSED), state: 'PAUSED', pause_reason: 'prices_not_live', pause_reason_text: PAUSED, unbooked_text: null })
    answers['GET /paper/strategies'] = ok(d)
    const w = await show()
    const c = cardOf(w, d)
    expect(c.get('[data-testid="paper-unbooked"]').text()).toBe('—')
    expect(c.get('[data-testid="paper-booked"]').text()).toBe('—')
    expect(c.get('[data-testid="paper-unbooked-reason"]').text()).toContain(PAUSED)
  })
  it('D: an older reply without the new fields: "(before charges)"', async () => {
    answers['GET /paper/strategies'] = ok(clone())
    const w = await show()
    expect(t(w, 'totals-booked-label').text()).toBe('Booked P&L (before charges)')
    expect(w.text()).not.toContain('(after charges)')
  })
  it('E: a closed trade (strategy 141): booked -435.95 and a real Unbooked 0.00 are figures', async () => {
    const d = clone()
    Object.assign(live(d), { total_after_text: '-435.95', booked_after_text: '-435.95', unbooked_after_text: '0.00', after_charges_reason: null, after_charges_reason_text: null })
    answers['GET /paper/strategies'] = ok(d)
    const w = await show()
    const c = cardOf(w, d)
    expect(c.get('[data-testid="paper-booked"]').text()).toBe('-435.95')
    expect(c.get('[data-testid="paper-unbooked"]').text()).toBe('0.00')
  })
})
