// D-N13 / N-34 (owner Part D re-test, 26 Nov 2026): while ?strategy=N is being opened the left card is the existing loading line, not an
// empty "New Strategy" shell with Add/Edit, Save and Add to Paper. Spec basis: finding F-46, the N-13 fix (the `opening` flag).
// States: pending (loading line, no shell), answered (the trade's own card), read failed (opening ends: the shell and the error show).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
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
const all = (w, id) => w.findAll(`[data-testid="${id}"]`)
const CONTRACTS = REAL.positions.map((p) => ({ contract_id: p.contract_id, exchange_segment: 'NSE_FO', exchange_token: p.contract_id,
  instrument_type: p.instrument, expiry: p.expiry, strike: p.strike, lot_size: 65, symbol: `NIFTY${p.strike}${p.instrument}` }))
const BOOK = { ...REAL, strategy_id: 86, name: '"IC"' }
const mounted = []
async function builder(book, url = '/strategy/builder?strategy=86') {
  calls.length = 0
  answers = {
    'GET /strategies': { strategies: [] },
    'GET /paper/strategies/86': book ?? BOOK,
    'GET /catalogue/NIFTY/contracts?expiry=2026-11-03': { underlying: 'NIFTY', contracts: CONTRACTS },
    'POST /strategies/outcome': () => new Promise(() => {}),
    'POST /strategies/leg-edit': () => new Promise(() => {}),
  }
  const r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }, { path: '/positions/current-positions', component: { template: '<p />' } }] })
  await r.push(url)
  await r.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [r], stubs: { PayoffChart: true } }, attachTo: document.body })
  mounted.push(w)
  await flushPromises()
  return w
}

beforeEach(() => { vi.useFakeTimers() })
afterEach(() => { vi.useRealTimers(); while (mounted.length) mounted.pop().unmount(); document.body.innerHTML = '' })
const SHELL = ['add-edit', 'save-draft', 'add-to-paper']

describe('N-34: opening a strategy shows the loading line, not the empty shell', () => {
  it('book read pending: no "New Strategy", no Add/Edit, Save, Add to Paper; the loading line is on the left card', async () => {
    let release
    const w = await builder(() => new Promise((res) => { release = () => res({ data: BOOK }) }))
    expect(w.text()).not.toContain('New Strategy')
    expect(t(w, 'strategy-card-name').exists()).toBe(false)
    for (const id of SHELL) expect(t(w, id).isVisible(), id).toBe(false)
    expect(t(w, 'no-legs').exists()).toBe(false)
    expect(t(w, 'opening-card').text()).toBe('Working out the outcome...')
    release()
    await flushPromises()
    await flushPromises()
    expect(t(w, 'opening-card').exists()).toBe(false)
    expect(t(w, 'strategy-card-name').text()).toBe('IC')
    expect(t(w, 'add-edit').isVisible()).toBe(true)
    expect(all(w, 'leg-row').length).toBeGreaterThan(0)
  })

  it('read failed: opening ends, the error shows and the card is back', async () => {
    const w = await builder(() => Promise.reject({ status: 500 }))
    expect(t(w, 'opening-card').exists()).toBe(false)
    expect(t(w, 'open-error').exists()).toBe(true)
  })

  it('no ?strategy=: the plain new builder keeps its "New Strategy" card', async () => {
    const w = await builder(null, '/strategy/builder')
    expect(t(w, 'strategy-card-name').text()).toBe('New Strategy')
    expect(t(w, 'opening-card').exists()).toBe(false)
  })
})
