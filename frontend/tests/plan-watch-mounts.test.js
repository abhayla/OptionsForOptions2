// P10 Wave 2 (ADR-330 (13)): the Plan watch is mounted beside the live P&L on the builder (saved strategy with an id) and on each open
// Positions paper row (compact), with that strategy's id; the builder without a saved strategy mounts none.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'
import PlanWatch from '@/components/strategy/PlanWatch.vue'
import BOOK from '../../tests/fixtures/paper/strategy-63-roll.json'
import { legacy } from './_paperList'
import { withPriceTexts } from './_priceTexts'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push(`${method} ${url}`)
    const a = legacy(answers, method, url)
    if (a === undefined) return Promise.reject(Object.assign(new Error(`unmocked ${method} ${url}`), { parts: null, status: null }))
    return typeof a === 'function' ? a(body) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u, b) => respond('POST', u, b), put: (u, b) => respond('PUT', u, b) } }
})

const watchOf = (id) => ({
  strategy_id: id, as_of: '2026-11-26T05:10:00Z', as_of_text: 'As of 10:40:00 AM IST', plan_state: 'planned', no_plan_text: null, armed_heading: null,
  paused: null, lines: [{ key: 'T-07', kind: 'target', section: 'plan', label: 'Profit target', unit: 'pnl_rupees', fires_at: '1200.00', now: '350.00', distance_rs: '850.00', distance_pct: '70.83', state: 'watching', reason: null }],
})
const CATALOGUE = { underlying: 'NIFTY', contracts: BOOK.positions.map((p) => ({ contract_id: p.contract_id, exchange_segment: 'NSE_FO', exchange_token: p.contract_id,
  instrument_type: p.instrument, expiry: p.expiry, strike: p.strike, lot_size: 65, symbol: `NIFTY${p.strike}${p.instrument}` })) }
const never = () => new Promise(() => {})
const t = (w, id) => w.find(`[data-testid="${id}"]`)

afterEach(() => vi.useRealTimers())
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  calls.length = 0
})

describe('Plan watch mounts', () => {
  it('builder: a saved strategy (?strategy=63) shows one Plan watch with its id, reading its own plan-watch route', async () => {
    answers = {
      'GET /paper/strategies/63': BOOK, 'GET /strategies': { strategies: [] }, 'GET /strategies/63/plan-watch': watchOf(63),
      'GET /catalogue/NIFTY/contracts?expiry=2026-11-03': CATALOGUE,
      'POST /strategies/outcome': never, 'POST /strategies/leg-edit': never,
    }
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
    await router.push({ path: '/strategy/builder', query: { strategy: '63' } })
    await router.isReady()
    const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true } } })
    await flushPromises()
    const boxes = w.findAllComponents(PlanWatch)
    expect(boxes).toHaveLength(1)
    expect(boxes[0].props('strategyId')).toBe(63)
    expect(boxes[0].props('compact')).toBe(false)
    expect(calls).toContain('GET /strategies/63/plan-watch')
    expect(t(w, 'pw-now').text()).toBe('₹350.00')
  })

  it('builder: no saved strategy, no Plan watch and no read of the route', async () => {
    answers = { 'GET /strategies': { strategies: [] }, 'POST /strategies/outcome': never, 'POST /strategies/leg-edit': never }
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
    await router.push({ path: '/strategy/builder' })
    await router.isReady()
    const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true } } })
    await flushPromises()
    expect(w.findAllComponents(PlanWatch)).toHaveLength(0)
    expect(calls.some((c) => c.includes('plan-watch'))).toBe(false)
  })

  it('Positions paper row: each open strategy row gets a compact Plan watch with its own id', async () => {
    const leg = (i) => withPriceTexts({
      leg_index: i, instrument_id: `NSE_FO:${i + 1}`, action: 'SELL', instrument: 'PE', strike: `${22300 + i * 100}.00`, expiry: '2026-11-03',
      quantity: 65, entry_price: '114.25', entry_at: '2026-10-28T05:03:09Z', current_price: '113.60', price_state: 'live',
      price_at: '2026-10-28T11:30:00+05:30', exit_price: null, exited_at: null,
    })
    const item = (id) => withPriceTexts({ strategy_id: id, name: `"S${id}"`, underlying: 'NIFTY', started_at: '2026-10-28T05:03:10Z', state: 'LIVE', pause_reason: null, as_of: null, total: '71.50', booked: '0.00', unbooked: '71.50', legs: [leg(0), leg(1)] })
    answers = { 'GET /tracking': { strategies: [item(48), item(49)], answered_at: '2026-10-28T06:00:00Z' }, 'GET /strategies/48/plan-watch': watchOf(48), 'GET /strategies/49/plan-watch': watchOf(49) }
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: PaperStrategies }] })
    await router.push('/')
    await router.isReady()
    const w = mount(PaperStrategies, { global: { plugins: [router] } })
    await flushPromises()
    const boxes = w.findAllComponents(PlanWatch)
    expect(boxes.map((b) => b.props('strategyId'))).toEqual([48, 49])
    expect(boxes.every((b) => b.props('compact') === true)).toBe(true)
  })

  it('Lane Y item 2: 25 open rows make ONE batch request per 20 rows, never one per row, and one bad row blanks no other', async () => {
    const { resetPlanWatchQueueForTests } = await import('@/lib/planWatchQueue')
    resetPlanWatchQueueForTests()
    const leg = (i) => withPriceTexts({
      leg_index: i, instrument_id: `NSE_FO:${i + 1}`, action: 'SELL', instrument: 'PE', strike: `${22300 + i * 100}.00`, expiry: '2026-11-03',
      quantity: 65, entry_price: '114.25', entry_at: '2026-10-28T05:03:09Z', current_price: '113.60', price_state: 'live',
      price_at: '2026-10-28T11:30:00+05:30', exit_price: null, exited_at: null,
    })
    const item = (id) => withPriceTexts({ strategy_id: id, name: `"S${id}"`, underlying: 'NIFTY', started_at: '2026-10-28T05:03:10Z', state: 'LIVE', pause_reason: null, as_of: null, total: '71.50', booked: '0.00', unbooked: '71.50', legs: [leg(0), leg(1)] })
    const ids = Array.from({ length: 25 }, (_, i) => 100 + i)
    const okItem = (id) => ({ strategy_id: id, state: 'ok', watch: watchOf(id) })
    answers = { 'GET /tracking': { strategies: ids.map(item), answered_at: '2026-10-28T06:00:00Z' } }
    answers[`GET /plan-watch?strategy_ids=${ids.slice(0, 20).join(',')}`] = { items: ids.slice(0, 20).map((id) => (id === 103 ? { strategy_id: id, state: 'refused', status: 404, refusal: null } : okItem(id))) }
    answers[`GET /plan-watch?strategy_ids=${ids.slice(20).join(',')}`] = { items: ids.slice(20).map(okItem) }
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: PaperStrategies }] })
    await router.push('/')
    await router.isReady()
    const w = mount(PaperStrategies, { global: { plugins: [router] } })
    await flushPromises()
    expect(calls.filter((c) => c.includes('/plan-watch?strategy_ids=')).length).toBe(1) // the second batch waits its turn in the queue
    expect(calls.some((c) => /\/strategies\/\d+\/plan-watch/.test(c))).toBe(false) // no per-row request
    const boxes = w.findAllComponents(PlanWatch)
    expect(boxes).toHaveLength(25)
    expect(boxes[0].find('[data-testid="pw-now"]').text()).toBe('₹350.00') // a good row shows its figure
    expect(boxes[3].find('[data-testid="pw-now"]').exists()).toBe(false) // the bad row has none
  })
})
