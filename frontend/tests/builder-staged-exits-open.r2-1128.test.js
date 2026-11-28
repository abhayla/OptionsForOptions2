// Lane TB (R2, 28 Nov) I-74: a builder opened from an alert (the link the Alerts page builds: builderLinkOf(id) = /strategy/builder?strategy=<id>)
// on a strategy that has exits waiting (Drafts Mode) shows its legs, never an empty builder. Real book: tests/fixtures/paper-book-63.json
// (strategy 63 renumbered 86; four open legs 5572, 5587, 5585, 5574). "Staged exit" = a leg kept with fewer lots than the net position
// (stagedExitIds); a whole exit leaves no leg. Same harness as exit-all-staged-adr330-59.test.js.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import { netKeyOf, useBuilderHold } from '@/stores/builderHold'
import { builderLinkOf } from '@/lib/strategyLinks'
import { stagedExitIds } from '@/lib/paperDrafts'
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

const CONTRACTS = REAL.positions.map((p) => ({ contract_id: p.contract_id, exchange_segment: 'NSE_FO', exchange_token: p.contract_id,
  instrument_type: p.instrument, expiry: p.expiry, strike: p.strike, lot_size: 65, symbol: `NIFTY${p.strike}${p.instrument}` }))
const BOOK = { ...REAL, strategy_id: 86, name: '"IC"' }
const OPEN_IDS = BOOK.positions.filter((p) => p.net_quantity !== 0).map((p) => p.contract_id)
const S = (w) => w.vm.$.setupState
const rows = (w) => w.findAll('[data-testid="leg-row"]')
const mounted = []
async function builder(link) {
  calls.length = 0
  answers = {
    'GET /strategies': { strategies: [] },
    'POST /paper/strategies/86/orders': BOOK,
    'GET /paper/strategies/86': BOOK,
    'GET /catalogue/NIFTY/contracts?expiry=2026-11-03': { underlying: 'NIFTY', contracts: CONTRACTS },
    'POST /strategies/outcome': () => new Promise(() => {}),
    'POST /strategies/leg-edit': () => new Promise(() => {}),
  }
  const r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await r.push(link)
  await r.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [r], stubs: { PayoffChart: true } }, attachTo: document.body })
  mounted.push(w)
  await flushPromises()
  return w
}
beforeEach(() => { vi.useFakeTimers(); useBuilderHold().clear() })
afterEach(() => {
  vi.useRealTimers()
  while (mounted.length) mounted.pop().unmount()
  document.body.innerHTML = ''
  useBuilderHold().clear()
})

describe('I-74 a builder opened from an alert shows the legs when exits are waiting', () => {
  it('the alert link is the strategy link', () => {
    expect(builderLinkOf(86)).toEqual({ path: '/strategy/builder', query: { strategy: '86' } })
  })

  it('I-74: a fresh open from the alert link lists every open leg', async () => {
    const w = await builder('/strategy/builder?strategy=86')
    expect(S(w).legs).toHaveLength(OPEN_IDS.length)
    expect(rows(w)).toHaveLength(OPEN_IDS.length)
  })

  it('I-74: a partial exit waiting on one leg and a whole exit on another, held, then opened from the alert link: the kept legs show, the partial one is marked', async () => {
    const first = await builder('/strategy/builder?strategy=86')
    const net = S(first).paper.net
    const [a, b, ...rest] = net
    expect(a.lots).toBeGreaterThanOrEqual(1)
    // leg a: keep 0 of it (whole exit, no leg); leg b: stays; the others stay. To get a PARTIAL exit, hold b at one lot less when it has 2+.
    const staged = [...(b.lots > 1 ? [{ ...b, lots: b.lots - 1 }] : [b]), ...rest]
    S(first).setLegs(staged.map((l) => ({ ...l })))
    await flushPromises()
    const snapshot = { legs: S(first).legs, paperId: 86, netKey: netKeyOf(net), fills: [], openStrategy: null }
    first.unmount(); mounted.pop()
    useBuilderHold().hold(snapshot)
    expect(useBuilderHold().count).toBe(rest.length + 1)

    const w = await builder(`/strategy/builder?strategy=86`)
    expect(S(w).legs.length).toBe(rest.length + 1)
    expect(rows(w)).toHaveLength(rest.length + 1)
    expect(S(w).legs.some((l) => l.contract_id === a.contract_id)).toBe(false) // a's exit is still waiting, not undone
    if (b.lots > 1) expect(stagedExitIds(S(w).paper.net, S(w).legs)).toContain(b.contract_id)
  })

  it('I-74: every leg exit staged (no legs left), then the alert link: the hold keeps nothing and the book is read, so the open legs show, not an empty builder', async () => {
    useBuilderHold().hold({ legs: [], paperId: 86 })
    expect(useBuilderHold().held).toBeNull() // "no legs holds nothing"
    const w = await builder('/strategy/builder?strategy=86')
    expect(rows(w)).toHaveLength(OPEN_IDS.length)
    expect(w.find('[data-testid="opening-card"]').exists()).toBe(false)
  })
})
