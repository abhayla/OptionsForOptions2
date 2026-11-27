// Lane FB round 2, notes of the 27 Nov PC test: UX-AF1 (the closed-market banner time flips while the numbers update), UX-C3 (three loading
// lines at once), UX-B25 (whole-trade tiles keep the old book's figures while the builder is locked). The REAL page.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import { closedBannerFor } from '@/lib/sharedStateText'
import LegList from '@/components/strategy/LegList.vue'
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

describe('UX-C3: one loading line, not three', () => {
  it('while each leg says it is being worked out, the legs card does not add "Updating the numbers..." on top', () => {
    const legs = [{ id: 1, underlying: 'NIFTY', instrument_id: 'NSE_FO:1', contract_id: 1, symbol: 'X', expiry: '2026-12-01', instrument_type: 'CE', strike: '1.00', lot_size: 65, action: 'SELL', lots: 1, planned_entry: '1.00', captured_at: '2026-11-27T10:00:00+05:30' }]
    const w = mount(LegList, { props: { legs, multiplierMax: 50, working: true, updating: true, oneLine: true } })
    expect(w.findAll('[data-testid="leg-working"]')).toHaveLength(1)
    expect(w.findAll('[data-testid="numbers-updating"]')).toHaveLength(0)
    const idle = mount(LegList, { props: { legs, multiplierMax: 50, working: true, updating: true } }) // old numbers kept (AC-4): the mark stays
    expect(idle.findAll('[data-testid="numbers-updating"]')).toHaveLength(1)
  })
  it('on the page, a slow outcome with no old numbers: no "Updating the numbers..." beside the working lines', async () => {
    const w = await page('')
    S(w).setLegs([{ id: 1, underlying: 'NIFTY', instrument_id: 'NSE_FO:1', contract_id: 1, symbol: 'X', expiry: '2026-12-01', instrument_type: 'CE', strike: '1.00', lot_size: 65, action: 'SELL', lots: 1, planned_entry: '1.00', captured_at: '2026-11-27T10:00:00+05:30' }])
    await flushPromises()
    expect(w.findAll('[data-testid="leg-working"]')).toHaveLength(1)
    expect(w.findAll('[data-testid="numbers-updating"]')).toHaveLength(0)
  })
})

describe('UX-AF1: the closed-market banner shows no time that is about to change', () => {
  const idx = { at: '2026-11-27T15:35:41+05:30', text: null } // the index's last tick
  const server = { at: '2026-11-27T15:35:41+05:30', text: 'Market closed. Prices are from 15:30:00 IST.' } // the server's close sentence
  it('first load, an answer is out: no time at all (the answer may replace it)', () => {
    expect(closedBannerFor(true, idx, null)).toEqual({ at: null, text: null })
  })
  it('an answer is out and an earlier one settled: the settled banner stays, never the index tick', () => {
    expect(closedBannerFor(true, idx, server)).toBe(server)
  })
  it('settled: the fresh banner is drawn; no market-closed state: no banner', () => {
    expect(closedBannerFor(false, server, null)).toBe(server)
    expect(closedBannerFor(true, null, server)).toBeNull()
    expect(closedBannerFor(false, null, null)).toBeNull()
  })
})

describe('UX-B25: whole-trade tiles never keep an older book\'s figures while the trade\'s outcome is unknown', () => {
  it('after an unknown exit the whole-trade tiles are off (the screen legs\' own outcome speaks) and come back when the server decides', async () => {
    const w = await page('?strategy=86')
    expect(S(w).paperLeft).not.toBeNull()
    S(w).exitPaper(OPEN_IDS[0], 1)
    await flushPromises()
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(S(w).exitBlocked).toBe(true)
    expect(S(w).paperLeft).toBeNull()
    expect(S(w).wholeTrade).toBe(false)
    const after = { ...BOOK, positions: BOOK.positions.map((p) => (p.contract_id === OPEN_IDS[0] ? { ...p, net_quantity: 0 } : p)) }
    answers['GET /paper/strategies/86'] = after
    await vi.advanceTimersByTimeAsync(6000)
    await flushPromises()
    expect(S(w).exitBlocked).toBe(false)
    expect(S(w).paperLeft).not.toBeNull()
  })
})
