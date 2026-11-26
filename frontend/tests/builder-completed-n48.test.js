// N-48 (REQ-109 Completed, ADR-002): a fully closed paper book opens with no empty-legs block and no add-leg controls; the closed rows show.
// (setup copied from builder-drafts-mode.test.js) GC-TP step 3b1 (ADR-207 (2), REQ-109 AC-4 / AC-9; F-65, F-66; Sensibull Drafts Mode 274-279, Add to Drafts 166-173): the REAL
// StrategyBuilderPage on ?strategy=63 with the REAL strategy 63 book after its roll (tests/fixtures/paper/strategy-63-roll.json,
// measured live 2026-10-29). It opens as the NET position, every edit is a pending paper order from paperOrdersFor, nothing
// reaches the server before Confirm, and Save / Save As / Add to Paper are not offered.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import BOOK0 from '../../tests/fixtures/paper/strategy-63-roll.json'
import { closedFrom } from './_closedRows'
const DONE = { ...BOOK0, state: 'EXITED', closed_text: 'Closed: result Rs 2,207.49.', positions: BOOK0.positions.map((p) => ({ ...p, net_quantity: 0 })) }
const BOOK = { ...DONE, closed: closedFrom(DONE.positions) }

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    const a = answers[`${method} ${url}`]
    if (a === undefined) return Promise.reject(new Error(`unmocked ${method} ${url}`))
    return typeof a === 'function' ? a(body) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u, b) => respond('POST', u, b), put: (u, b) => respond('PUT', u, b) } }
})

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const PAPER = 'GET /paper/strategies/63'
const CATALOGUE = { underlying: 'NIFTY', contracts: BOOK.positions.map((p) => ({ contract_id: p.contract_id, exchange_segment: 'NSE_FO', exchange_token: p.contract_id,
  instrument_type: p.instrument, expiry: p.expiry, strike: p.strike, lot_size: 65, symbol: `NIFTY${p.strike}${p.instrument}` })) }
const never = () => new Promise(() => {}) // the numbers' requests stay out: this file is about the legs and the orders

// u126: the paper panel re-reads the book on a real interval; under load a slow run let one tick land inside a test and made
// "Confirm posts ... re-reads the book" count 3 reads instead of 2. Only the interval is faked, so this file's reads are its own.
afterEach(() => vi.useRealTimers())
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  calls.length = 0
  answers = {
    [PAPER]: BOOK,
    'GET /strategies': { strategies: [] },
    'GET /catalogue/NIFTY/contracts?expiry=2026-11-03': CATALOGUE,
    'POST /strategies/outcome': never,
    'POST /strategies/leg-edit': never,
  }
})

async function openBuilder(query = { strategy: '63' }) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await router.push({ path: '/strategy/builder', query })
  await router.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true } } })
  await flushPromises()
  return w
}

describe('N-48: a completed paper book has no empty-legs block', () => {
  it('shows the closed rows and no No legs yet, Add leg or Pick from Option Chain', async () => {
    const w = await openBuilder()
    expect(t(w, 'closed-list').exists()).toBe(true)
    expect(t(w, 'no-legs').exists()).toBe(false)
    expect(t(w, 'no-legs-add').exists()).toBe(false)
    expect(t(w, 'no-legs-chain').exists()).toBe(false)
    expect(t(w, 'add-edit').exists()).toBe(false)
    expect(w.text()).not.toContain('No legs yet')
    expect(t(w, 'closed-result').text()).toBe(BOOK.closed_text)
  })
})
