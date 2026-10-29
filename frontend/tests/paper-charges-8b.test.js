// GC-TP step 8b (REQ-109 AC-10; Sensibull Positions 050, Drafts Mode 278-279; findings R-14): the Charges figure beside the P&L.
// REAL is the reply of GET /paper/strategies captured from tests_app/test_paper_totals.py with step 8a's charge rates
// (tests/fixtures/paper-strategies.json): every Charges text expected below is that reply's own `charges_text`, as sent.
// The Drafts Mode book is one strategy of that same reply (the detail route builds the same figures), with no orders.
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

import PaperStrategies from '@/components/strategy/PaperStrategies.vue'
import PaperBookPanel from '@/components/strategy/PaperBookPanel.vue'
import { resetPaperAlerts } from '@/lib/paperAlerts'

const ok = (data) => () => Promise.resolve({ data })
const t = (w, id) => w.get(`[data-testid="${id}"]`)
const clone = () => JSON.parse(JSON.stringify(REAL))
const RATES_TEXT = 'Charges and taxes are not included: the charge rates could not be read.' // the server templates' words (tests/test_paper_reason_texts.py)
const PAUSED_TEXT = 'Paper P&L paused - prices not live'
const NO_IV_TEXT = 'no implied volatility for this leg'
const CODE = /rates_unavailable|not_priced|prices_not_live|no_iv|[a-z]+_[a-z_]+/

async function show() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: PaperStrategies }, { path: '/strategy/builder', component: { template: '<div/>' } }] })
  router.push('/')
  await router.isReady()
  const w = mount(PaperStrategies, { global: { plugins: [router] } })
  await flushPromises()
  return w
}

beforeEach(() => { answers = {}; resetPaperAlerts(); vi.useFakeTimers() })
afterEach(() => vi.useRealTimers())

describe('Charges beside the P&L on the Paper tab (the real reply)', () => {
  it('core: the strip and every card show the reply charges_text; the P&L texts are unchanged', async () => {
    answers['GET /paper/strategies'] = ok(REAL)
    const w = await show()
    expect(REAL.totals.charges_text).toBeTruthy()
    expect(t(w, 'totals-charges').text()).toBe(REAL.totals.charges_text)
    expect(t(w, 'totals-total').text()).toBe(REAL.totals.total_text)
    await t(w, 'show-closed').setValue(true) // the exited strategy 2 is listed too
    for (const s of REAL.strategies) {
      const card = w.get(`[data-testid="paper-group"][data-strategy="${s.strategy_id}"]`)
      expect(card.get('[data-testid="paper-charges"]').text()).toBe(s.charges_text)
      expect(card.get('[data-testid="paper-total"]').text()).toBe(s.total_text)
      expect(card.get('[data-testid="paper-booked"]').text()).toBe(s.booked_text)
      expect(card.get('[data-testid="paper-unbooked"]').text()).toBe(s.unbooked_text)
    }
  })

  it('charges absent with a reason: a dash, never 0, never the raw code; the strip too', async () => {
    const d = clone()
    for (const x of [d.totals, ...d.strategies]) Object.assign(x, { charges: null, charges_text: null, charges_reason: 'rates_unavailable', charges_reason_text: RATES_TEXT })
    answers['GET /paper/strategies'] = ok(d)
    const w = await show()
    expect(t(w, 'totals-charges').text()).toBe('—')
    for (const c of w.findAll('[data-testid="paper-charges"]')) expect(c.text()).toBe('—')
    expect(t(w, 'totals-charges-reason').text()).toBe(RATES_TEXT) // R-20: the reply's sentence beside the dash
    for (const c of w.findAll('[data-testid="paper-charges-reason"]')) expect(c.text()).toBe(RATES_TEXT)
    expect(w.html()).not.toMatch(/rates_unavailable|not_priced/)
    expect(t(w, 'totals-charges').text()).not.toMatch(/^0/)
  })

  it('totals_reason prices_not_live shows the paused sentence, not the code (R-14)', async () => {
    const d = clone()
    Object.assign(d.totals, { total_text: null, total: null, booked_text: null, unbooked_text: null, totals_reason: 'prices_not_live', totals_reason_text: PAUSED_TEXT, decay_text: null, decay: null, decay_reason: 'no_iv', decay_reason_text: NO_IV_TEXT })
    answers['GET /paper/strategies'] = ok(d)
    const w = await show()
    expect(t(w, 'totals-reason').text()).toBe(PAUSED_TEXT)
    expect(t(w, 'totals-decay-reason').text()).toBe(NO_IV_TEXT)
    expect(w.text()).not.toMatch(CODE)
  })
})

describe('Charges beside the P&L in Drafts Mode', () => {
  const book = (over = {}) => ({ ...clone().strategies.find((s) => s.state === 'LIVE'), orders: [], ...over })
  const mountBook = (b) => mount(PaperBookPanel, { props: { book: b, net: [] } })

  it('shows the book charges_text beside its total, as sent', () => {
    const b = book()
    const w = mountBook(b)
    expect(w.get('[data-testid="book-charges"]').text()).toBe(b.charges_text)
    expect(w.get('[data-testid="book-total"]').text()).toBe(b.total_text)
  })

  it('an absent charges shows a dash, never 0 and never the code', () => {
    const w = mountBook(book({ charges: null, charges_text: null, charges_reason: 'not_priced' }))
    expect(w.get('[data-testid="book-charges"]').text()).toBe('-')
    expect(w.text()).not.toMatch(/not_priced/)
  })
})
