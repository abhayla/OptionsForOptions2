// Lane FB2 item 3 (copy of the FB harness). Lane FB round 2, notes of the 27 Nov PC test: UX-AF1 (the closed-market banner time flips while the numbers update), UX-C3 (three loading
// lines at once), UX-B25 (whole-trade tiles keep the old book's figures while the builder is locked). The REAL page.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import { UPDATING_NUMBERS_TEXT } from '@/lib/sharedStateText'
import SummaryCards from '@/components/strategy/SummaryCards.vue'
import REAL from './fixtures/paper-book-63.json'
import { legacy } from './_paperList'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    const a = answers[`${method} ${url}`] ?? legacy(answers, method, url)
    if (a === undefined || a === null) return Promise.reject(new Error(`unmocked ${method} ${url}`))
    return typeof a === 'function' ? a(body) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u, b) => respond('POST', u, b), put: (u, b) => respond('PUT', u, b), patch: (u, b) => respond('PATCH', u, b) } }
})

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const S = (w) => w.vm.$.setupState
const CONTRACTS = REAL.positions.map((p) => ({ contract_id: p.contract_id, exchange_segment: 'NSE_FO', exchange_token: p.contract_id,
  instrument_type: p.instrument, expiry: p.expiry, strike: p.strike, lot_size: 65, symbol: `NIFTY${p.strike}${p.instrument}` }))
const BOOK = { ...REAL, strategy_id: 86, name: '"IC"' }
const OPEN_IDS = BOOK.positions.filter((p) => p.net_quantity !== 0).map((p) => p.contract_id)
const mounted = []

beforeEach(() => { vi.useFakeTimers() })
afterEach(() => { vi.useRealTimers(); while (mounted.length) mounted.pop().unmount(); document.body.innerHTML = '' })

async function page(query, extra = {}) {
  calls.length = 0
  answers = {
    'GET /strategies': { strategies: [] },
    'POST /paper/strategies/86/orders': () => Promise.reject({ status: 503, message: 'x', parts: null }),
    'GET /paper/strategies/86': BOOK,
    'GET /catalogue/NIFTY/contracts?expiry=2026-11-03': { underlying: 'NIFTY', contracts: CONTRACTS },
    'POST /strategies/outcome': () => new Promise(() => {}),
    'POST /strategies/leg-edit': () => new Promise(() => {}),
    ...extra,
  }
  const r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await r.push(`/strategy/builder${query}`)
  await r.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [r], stubs: { PayoffChart: true } }, attachTo: document.body })
  mounted.push(w)
  await flushPromises()
  return w
}


const LEFT = { profit: { label: '(after charges)', text: '+7,152', breakdown: null }, loss: { label: '(after charges)', text: '-5,848', breakdown: null }, recover: null, reason: null }
const cards = (over = {}) => mount(SummaryCards, { props: { left: LEFT, summary: { charges: '1.00' }, maxProfit: '+9,000', maxLoss: '-6,000', maxProfitExact: '9000', maxLossExact: '-6000', breakevens: ['22,000'], breakevensExact: ['22000'], ...over } })

describe('UX-B25: Profit left, Max profit and Loss left never show another leg set\'s numbers', () => {
  it('held: all four figures say "Updating the numbers..." and no old figure is in the card', () => {
    const w = cards({ holding: true })
    for (const id of ['profit-left', 'loss-left', 'max-profit', 'max-loss']) expect(t(w, id).text()).toBe(UPDATING_NUMBERS_TEXT)
    expect(w.text()).not.toContain('+7,152')
    expect(w.text()).not.toContain('-5,848')
    expect(w.text()).not.toContain('+9,000')
    expect(w.text()).not.toContain('-6,000')
  })
  it('not held: the figures show as before', () => {
    const w = cards()
    expect(t(w, 'profit-left').text()).toBe('+7,152')
    expect(t(w, 'loss-left').text()).toBe('-5,848')
    expect(t(w, 'max-profit').text()).toBe('+9,000')
    expect(t(w, 'max-loss').text()).toBe('-6,000')
  })
  it('on the page: an exit of unknown outcome holds the figures; the server deciding releases them', async () => {
    const w = await page('?strategy=86')
    expect(S(w).tilesHeld).toBe(false)
    S(w).exitPaper(OPEN_IDS[0], 1)
    await flushPromises()
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(S(w).tilesHeld).toBe(true)
    const after = { ...BOOK, positions: BOOK.positions.map((p) => (p.contract_id === OPEN_IDS[0] ? { ...p, net_quantity: 0 } : p)) }
    answers['GET /paper/strategies/86'] = after
    await vi.advanceTimersByTimeAsync(6000)
    await flushPromises()
    expect(S(w).tilesHeld).toBe(false)
  })
})

describe('UX-C3 (Open in Builder): the Plan watch line waits until the outcome is in', () => {
  it('a slow outcome with no numbers yet: the page\'s one loading line, no "Loading the rule check..." beside it', async () => {
    const w = await page('?strategy=86')
    expect(t(w, 'state-loading').exists()).toBe(true)
    expect(w.text()).toContain('Working out the outcome...')
    expect(w.text()).not.toContain('Loading the rule check...')
    expect(t(w, 'plan-watch-host').attributes('data-outcome-loading')).toBe('true') // the host hides the box's own loading line (style) until the outcome is in
  })
})

describe('UX-A12/A33 retest: a settled or completed trade never says "No draft strategy is open"', () => {
  it('completed book: the closed text, not the add-a-leg line', async () => {
    const done = { ...BOOK, state: 'settled', closed: [{ id: 'c1' }], positions: BOOK.positions.map((p) => ({ ...p, net_quantity: 0 })) }
    const w = await page('?strategy=86', { 'GET /paper/strategies/86': done })
    expect(w.text()).not.toContain('No draft strategy is open')
    expect(t(w, 'state-no-draft').exists()).toBe(false)
  })
})

describe('D-10 (Lane TC, 1366x768): "No fixed maximum" never spills out of its tile into Intrinsic value', () => {
  it('the four figure boxes may wrap (no nowrap), so a long server text stays inside block 1', () => {
    const w = cards({ left: { ...LEFT, loss: { ...LEFT.loss, text: 'No fixed maximum' } }, maxLoss: 'No fixed maximum' })
    for (const id of ['profit-left', 'loss-left']) {
      expect(t(w, id).classes()).not.toContain('whitespace-nowrap')
      expect(t(w, id).classes()).toContain('break-words')
    }
    for (const id of ['max-profit-pill', 'max-loss-pill']) {
      expect(t(w, id).classes()).not.toContain('whitespace-nowrap')
      expect(t(w, id).classes()).toContain('max-w-full')
    }
    expect(t(w, 'loss-left').text()).toBe('No fixed maximum')
  })
})
