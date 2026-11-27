// S-06 page wiring (ADR-330 (17), ADR-321 (3)): the builder page passes the plan summary to SummaryCards, so an UNPLACED plan's
// summary says "Max Profit and Max Loss are after charges ...; breakevens are before charges." (one wording home: lib/targetBlock.js).
// Placed paper book: the page's own tiles-basis line wins and the sentence is not printed twice. Both max figures "Not available"
// (mixed expiry sends charges): the line must not claim "after charges" over them.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

const calls = []
let outcome = () => Promise.reject(new Error('no outcome answer set'))
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    if (method === 'POST' && url === '/strategies/outcome') return outcome(body)
    const a = answers[`${method} ${url}`]
    return a === undefined ? Promise.reject(new Error(`unmocked ${method} ${url}`)) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (url) => respond('GET', url), post: (url, body) => respond('POST', url, body) } }
})
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import SummaryCards from '@/components/strategy/SummaryCards.vue'
import { PLAN_BASIS_AFTER_CHARGES_TEXT, PLAN_BASIS_BEFORE_CHARGES_TEXT, OPEN_LEGS_ONLY_TEXT } from '@/lib/targetBlock'
import on from './fixtures/outcome-target-booked-on.json'
import plain from './fixtures/outcome-target-plain.json'
import BOOK from '../../tests/fixtures/paper/strategy-63-roll.json'

const AFTER = 'Max Profit and Max Loss are after charges estimated at entry prices; breakevens are before charges.'
let answers = {}
const t = (w, id) => w.find(`[data-testid="${id}"]`)
const DRAFT = { underlying: 'NIFTY', legs: on.legs.map((l) => ({ instrument_id: l.instrument_id, action: l.action, lots: l.lots, planned_entry: l.planned_entry, captured_at: l.captured_at })) }
const withSummary = (extra) => () => Promise.resolve({ data: { ...plain, summary: { ...plain.summary, ...extra } } })

beforeEach(() => {
  calls.length = 0
  answers = {}
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
})
afterEach(() => vi.useRealTimers())

async function openPlan() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await router.push({ path: '/strategy/builder', query: { draft: JSON.stringify(DRAFT) } })
  await router.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true } } })
  await flushPromises()
  return w
}
async function openBook() {
  const catalogue = { underlying: 'NIFTY', contracts: BOOK.positions.map((p) => ({ contract_id: p.contract_id, exchange_segment: 'NSE_FO', exchange_token: p.contract_id,
    instrument_type: p.instrument, expiry: p.expiry, strike: p.strike, lot_size: 65, symbol: `NIFTY${p.strike}${p.instrument}` })) }
  answers = { 'GET /paper/strategies/63': BOOK, 'GET /strategies': { strategies: [] }, 'GET /catalogue/NIFTY/contracts?expiry=2026-11-03': catalogue }
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await router.push({ path: '/strategy/builder', query: { strategy: '63' } })
  await router.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true } } })
  await flushPromises()
  return w
}
const count = (text, sentence) => text.split(sentence).length - 1

describe('S-06 page wiring', () => {
  it('an unplaced plan with charges: the page prints the exact after-charges sentence once', async () => {
    outcome = withSummary({ charges: '258.00' })
    const w = await openPlan()
    expect(t(w, 'summary-basis').text()).toBe(AFTER)
    expect(count(w.text(), AFTER)).toBe(1)
  })
  it('an unplaced plan with no charges: the before-charges sentence, never "after charges"', async () => {
    outcome = withSummary({ charges: null })
    const w = await openPlan()
    expect(t(w, 'summary-basis').text()).toBe(PLAN_BASIS_BEFORE_CHARGES_TEXT)
    expect(w.text()).not.toContain('after charges estimated')
  })
  it('a placed paper book: the page tiles-basis line speaks and the sentence is not doubled', async () => {
    outcome = withSummary({ charges: '80.00' })
    const w = await openBook()
    await t(w, 'add-booked-switch').setValue(false)
    await vi.advanceTimersByTimeAsync(250)
    await flushPromises()
    expect(t(w, 'tiles-basis').text()).toBe(OPEN_LEGS_ONLY_TEXT)
    expect(t(w, 'summary-basis').exists()).toBe(false)
    expect(count(w.text(), AFTER)).toBe(1)
  })
})

describe('S-06 mixed-expiry quirk: charges sent, both max figures not available', () => {
  const props = { maxProfit: 'Not available', maxLoss: 'Not available', breakevens: [] }
  it('both figures not available: no "after charges" line', () => {
    const w = mount(SummaryCards, { props: { ...props, summary: { charges: '258.00' } } })
    expect(t(w, 'summary-basis').exists()).toBe(false)
    expect(w.text()).not.toContain('after charges')
  })
  it('one figure available: the line stays', () => {
    const w = mount(SummaryCards, { props: { ...props, maxProfit: '+3,619', summary: { charges: '258.00' } } })
    expect(t(w, 'summary-basis').text()).toBe(PLAN_BASIS_AFTER_CHARGES_TEXT)
  })
})
