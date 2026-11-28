// ADR-330 (57): the builder page of a fully closed or settled trade shows its closed sentence, legs and result, the server's one plan line, and no Plan watch box and no way to add a leg.
// Real case 27 Nov: settled trade 173 showed a Plan watch box that read like an error and "Add a leg to start one". (setup copied from builder-completed-n48.test.js)
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
const FINAL = 'Plan: stop Rs 300, target Rs 800. Closed by your exit at 11:23.'
const DONE = { ...BOOK0, state: 'EXITED', closed_text: 'Closed: result Rs 2,207.49.', plan_final_text: FINAL, positions: BOOK0.positions.map((p) => ({ ...p, net_quantity: 0 })) }
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


const watchCalls = () => calls.filter((c) => c.url.includes('plan-watch'))

describe('ADR-330 (57): the builder page of a closed trade', () => {
  it('prints the server\'s closed sentence-line, the legs and the result, and the plan line as sent', async () => {
    answers['GET /strategies/63/plan-watch'] = never
    const w = await openBuilder()
    expect(t(w, 'closed-list').exists()).toBe(true)
    expect(t(w, 'closed-result').text()).toBe(BOOK.closed_text)
    expect(t(w, 'plan-final').text()).toBe(FINAL)
  })
  it('Lane FJ (UX-A06, owner review 28 Nov): the Plan watch box shows only the closed fact, never reads the plan watch, and offers no way to add a leg', async () => {
    answers['GET /strategies/63/plan-watch'] = never
    const w = await openBuilder()
    expect(t(w, 'plan-watch-closed').text()).toBe('This trade is closed; nothing is watched.')
    expect(t(w, 'plan-watch-loading').exists()).toBe(false)
    expect(t(w, 'plan-watch-plan').exists()).toBe(false)
    expect(watchCalls()).toEqual([])
    expect(t(w, 'add-edit').exists()).toBe(false)
    expect(t(w, 'no-legs-add').exists()).toBe(false)
    expect(w.text()).not.toContain('Add a leg to start one')
  })
  it('an open book still shows the Plan watch and no plan line', async () => {
    answers[PAPER] = { ...BOOK0, closed_text: null, plan_final_text: null }
    answers['GET /strategies/63/plan-watch'] = never
    const w = await openBuilder()
    expect(t(w, 'plan-final').exists()).toBe(false)
    expect(t(w, 'plan-watch').exists()).toBe(true)
  })
  it('a closed book whose plan line the server left out prints no plan line and no empty box', async () => {
    answers[PAPER] = { ...BOOK, plan_final_text: null }
    const w = await openBuilder()
    expect(t(w, 'plan-final').exists()).toBe(false)
    expect(t(w, 'closed-result').text()).toBe(BOOK.closed_text)
  })
})
