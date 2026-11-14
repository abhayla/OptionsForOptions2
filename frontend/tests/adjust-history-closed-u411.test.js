// GC-ICFIX issue 21 (X-7, ADR-259, ADR-273): a Completed trade (every position flat) still shows its "Adjustment history" on the
// builder page, and the Compare link of a closed trade is not a dead end.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import AdjustCompare from '@/components/strategy/AdjustCompare.vue'
import BOOK from '../../tests/fixtures/paper/strategy-63-roll.json'

let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url) => {
    const a = answers[`${method} ${url}`]
    if (a === undefined) return Promise.reject(new Error(`unmocked ${method} ${url}`))
    return a instanceof Error ? Promise.reject(a) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u) => respond('POST', u), put: (u) => respond('PUT', u) } }
})

const never = () => new Promise(() => {})
const CLOSED = { ...BOOK, positions: BOOK.positions.map((p) => ({ ...p, net_quantity: 0 })) }

afterEach(() => vi.useRealTimers())
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  answers = { 'GET /paper/strategies/63': CLOSED, 'GET /strategies': { strategies: [] }, 'POST /strategies/outcome': never() }
})

describe('a Completed trade shows its adjustment history (X-7)', () => {
  it('?strategy=63 with no open leg mounts the history section', async () => {
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
    await router.push({ path: '/strategy/builder', query: { strategy: '63' } })
    await router.isReady()
    const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true } } })
    await flushPromises()
    expect(w.find('[data-testid="adjust-steps"]').exists()).toBe(true)
    expect(w.find('[data-testid="adjust-steps"]').text()).toContain('Adjustment history')
  })
})

describe('the Compare link of a closed trade is not a dead end', () => {
  it('a refused compare still offers the history', async () => {
    const refused = Object.assign(new Error('refused'), { parts: { what_happened: 'The page or action you asked for is not available here.' } })
    answers = { 'POST /strategies/141/adjustment-approaches': refused }
    const client = { post: () => Promise.reject(refused), get: () => Promise.reject(refused) }
    const w = mount(AdjustCompare, { props: { strategyId: '141', client } })
    await flushPromises()
    const link = w.get('[data-testid="adjust-steps-link"]')
    expect(link.attributes('href')).toBe('/strategy/builder?strategy=141')
    expect(link.text()).not.toBe('')
  })
})
