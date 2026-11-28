// Lane FJ (R3) item 3, the builder half. Real cases: UX-A06 (a settled trade's Plan watch), the Plan watch "Loading the rule check..." under the page's
// own "Working out the outcome..." (hidden by a CSS rule), a real trade's exits read from the paper route (ADR-330 (58)), UX-A02 (what a leg costs now).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import TrackingPanel from '@/components/strategy/TrackingPanel.vue'
import PlanWatch from '@/components/strategy/PlanWatch.vue'
import PaperStops from '@/components/strategy/PaperStops.vue'
import BOOK0 from '../../tests/fixtures/paper/strategy-63-roll.json'
import CONDOR from './fixtures/outcome-money-condor.json'
import { closedFrom } from './_closedRows'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    const a = answers[`${method} ${url}`]
    if (a === undefined) return Promise.reject(Object.assign(new Error(`unmocked ${method} ${url}`), { parts: null, status: null }))
    return typeof a === 'function' ? a(body) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u, b) => respond('POST', u, b), put: (u, b) => respond('PUT', u, b) } }
})
class FakeSocket { constructor(url) { this.url = url; this.readyState = 0 } send() {} close() {} }

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const never = () => new Promise(() => {})
const DONE = { ...BOOK0, state: 'EXITED', positions: BOOK0.positions.map((p) => ({ ...p, net_quantity: 0 })) }
const CLOSED_BOOK = { ...DONE, closed: closedFrom(DONE.positions) }
const catalogueOf = (book) => ({ underlying: 'NIFTY', contracts: book.positions.map((p) => ({ contract_id: p.contract_id, exchange_segment: 'NSE_FO', exchange_token: p.contract_id,
  instrument_type: p.instrument, expiry: p.expiry, strike: p.strike, lot_size: 65, symbol: `NIFTY${p.strike}${p.instrument}` })) })
const tokenOf = (l) => Number(l.instrument_id.split(':')[1])
const savedOf = (statusWord) => ({ id: 90, revision: 2, name: '"IC"', status_word: statusWord, definition: { underlying: 'NIFTY', legs: CONDOR.legs.map((l) => ({
  contract_id: tokenOf(l), contract_state: 'live', exchange_segment: 'NSE_FO', exchange_token: tokenOf(l), instrument: l.instrument, strike: l.strike, expiry: l.expiry,
  action: l.action, quantity: l.quantity, planned_entry: l.planned_entry, captured_at: l.captured_at, entry_source: 'captured' })) } })
const CONDOR_CATALOGUE = { underlying: 'NIFTY', contracts: CONDOR.legs.map((l) => ({ contract_id: tokenOf(l), exchange_segment: 'NSE_FO', exchange_token: tokenOf(l),
  instrument_type: l.instrument, expiry: l.expiry, strike: l.strike, lot_size: l.lot_size, symbol: l.symbol })) }
const mounted = []
beforeEach(() => { setActivePinia(createPinia()); vi.stubGlobal('WebSocket', FakeSocket); vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] }); calls.length = 0; answers = {} })
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); while (mounted.length) mounted.pop().unmount() })
async function open(id, query = {}) {
  const r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await r.push({ path: '/strategy/builder', query: { strategy: String(id), ...query } })
  await r.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [r], stubs: { PayoffChart: true } } })
  mounted.push(w)
  await flushPromises()
  return w
}

describe('ADR-330 (58): a real trade reads its exits from the real route', () => {
  const realTrade = (statusWord, over = {}) => {
    answers = { 'GET /strategies': { strategies: [] }, 'GET /paper/strategies/90': () => Promise.reject({ status: 404, parts: null }), 'GET /strategies/90': savedOf(statusWord),
      'GET /catalogue/NIFTY/contracts?expiry=2026-10-13': CONDOR_CATALOGUE, 'POST /strategies/outcome': CONDOR, 'POST /strategies/leg-edit': never,
      'GET /strategies/90/tracking': { strategy_id: 90, state: 'LIVE', paper_pnl: '195.00', paper_pnl_text: '+195.00', as_of: null, legs: [], detections: [] }, 'GET /strategies/90/adjustment-check': () => Promise.reject({ status: 404, parts: null }),
      'GET /strategies/90/plan-watch': never, 'GET /paper/strategies/90/triggers': { triggers: [] }, 'GET /real/strategies/90/triggers': { triggers: [] }, ...over }
  }
  it('a running strategy with no paper book is a real trade: TrackingPanel gets tradeMode real and the real route is read', async () => {
    realTrade('Running')
    const w = await open(90)
    expect(w.findComponent(TrackingPanel).props('tradeMode')).toBe('real')
    expect(calls.some((c) => c.url === '/real/strategies/90/triggers')).toBe(true)
    expect(calls.some((c) => c.url === '/paper/strategies/90/triggers')).toBe(false)
  })
  it('the "cannot be read here yet" line stays only when the real read fails', async () => {
    realTrade('Running', { 'GET /real/strategies/90/triggers': () => Promise.reject({ status: 500, parts: null }) })
    const w = await open(90)
    expect(t(w, 'plan-entry-exits-real-unreadable').text()).toBe('Exits of a real-mode trade cannot be read here yet.')
  })
  it('a plain draft (status Draft) stays paper mode and reads the paper route', async () => {
    realTrade('Draft')
    const w = await open(90)
    expect(w.findComponent(TrackingPanel).props('tradeMode')).toBe('paper')
    expect(calls.some((c) => c.url === '/real/strategies/90/triggers')).toBe(false)
  })
  it('status word missing or unknown: paper mode (fail closed to the existing behaviour)', async () => {
    realTrade(undefined)
    const w = await open(90)
    expect(w.findComponent(TrackingPanel).props('tradeMode')).toBe('paper')
  })
})

describe('UX-A06: a settled trade shows the closed sentence in the Plan watch box', () => {
  it('the box is there with the closed fact and nothing is read', async () => {
    answers = { 'GET /paper/strategies/63': CLOSED_BOOK, 'GET /strategies': { strategies: [] }, 'GET /catalogue/NIFTY/contracts?expiry=2026-11-03': catalogueOf(CLOSED_BOOK),
      'POST /strategies/outcome': never, 'POST /strategies/leg-edit': never, 'GET /strategies/63/plan-watch': never }
    const w = await open(63)
    expect(w.findComponent(PlanWatch).props('closed')).toBe(true)
    expect(t(w, 'plan-watch').exists()).toBe(false) // F2 (W-29 step 57, ADR-330 (57)): a closed trade has no Plan watch box
    expect(calls.some((c) => c.url.includes('plan-watch'))).toBe(false)
  })
})

describe('Lane FB: the box says nothing of loading while the page works out the outcome', () => {
  it('the page passes outcomeLoading; no loading line is rendered, and no CSS rule is needed', async () => {
    answers = { 'GET /paper/strategies/63': BOOK0, 'GET /strategies': { strategies: [] }, 'GET /catalogue/NIFTY/contracts?expiry=2026-11-03': catalogueOf(BOOK0),
      'POST /strategies/outcome': never, 'POST /strategies/leg-edit': never, 'GET /strategies/63/plan-watch': never }
    const w = await open(63)
    expect(w.findComponent(PlanWatch).props('outcomeLoading')).toBe(true)
    expect(t(w, 'plan-watch-loading').exists()).toBe(false)
  })
})

describe('UX-A02: the stop offer after a move carries each new leg\'s price text', () => {
  it('stopOffer.legs hold ltpText from the book (null when the leg is not live)', async () => {
    answers = { 'GET /paper/strategies/63': BOOK0, 'GET /strategies': { strategies: [] }, 'GET /catalogue/NIFTY/contracts?expiry=2026-11-03': catalogueOf(BOOK0),
      'POST /strategies/outcome': never, 'POST /strategies/leg-edit': never, 'GET /strategies/63/plan-watch': never, 'GET /paper/strategies/63/triggers': { triggers: [{ id: 5, kind: 'leg_stop', state: 'cancelled' }] } }
    const w = await open(63)
    const S = w.vm.$.setupState
    const openPos = BOOK0.positions.filter((p) => p.net_quantity !== 0)
    await S.offerAfterMove({ id: 63, stops: [{ id: 5, kind: 'leg_stop', state: 'armed' }], net: [] })
    await flushPromises()
    const legs = S.stopOffer?.legs
    expect(legs?.length).toBe(openPos.length)
    for (const l of legs) {
      const p = openPos.find((x) => x.contract_id === l.index)
      expect(l.ltpText).toBe(p.price_state === 'live' ? p.ltp_text : null)
    }
    expect(legs.some((l) => typeof l.ltpText === 'string')).toBe(true)
  })
})
