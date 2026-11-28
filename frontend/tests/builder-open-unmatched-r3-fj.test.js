// Lane FJ (TF finding, RESULTS-lane-td D-TD-3): ?strategy=1 said "paper position could not be read" although every request answered
// 200: the catalogue answered with no contract of the book. "Could not be read" is for a read that failed; an answer that does not
// match the book is its own state with its own sentence. (setup as tests/builder-completed-n48.test.js)
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import BOOK0 from '../../tests/fixtures/paper/strategy-63-roll.json'

const BOOK = { ...BOOK0, strategy_id: 1 }
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url) => {
    const a = answers[`${method} ${url}`]
    if (a === undefined) return Promise.reject(new Error(`unmocked ${method} ${url}`))
    if (a instanceof Error || a?.failed) return Promise.reject({ message: 'x', status: a.status ?? null })
    return Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u) => respond('POST', u), put: (u) => respond('PUT', u) } }
})
const UNMATCHED = "This strategy's paper position was read, but its contracts are not in the catalogue for today, so it is not shown."
const t = (w, id) => w.find(`[data-testid="${id}"]`)
const CAT = 'GET /catalogue/NIFTY/contracts?expiry=2026-11-03'
afterEach(() => vi.useRealTimers())
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  answers = { 'GET /paper/strategies/1': BOOK, 'GET /strategies': { strategies: [] } }
})
async function openBuilder() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await router.push({ path: '/strategy/builder', query: { strategy: '1' } })
  await router.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true } } })
  await flushPromises()
  return w
}

describe('?strategy=1: "could not be read" only when a read failed', () => {
  it('catalogue answered with no contracts (answered, not matched): its own sentence, not "could not be read"', async () => {
    answers[CAT] = { underlying: 'NIFTY', contracts: [] }
    const w = await openBuilder()
    expect(t(w, 'open-error-what').text()).toBe(UNMATCHED)
    expect(t(w, 'open-error').text()).not.toContain('could not be read')
    expect(t(w, 'open-error').text()).not.toContain('could not get an answer')
  })
  it('catalogue request failed: "could not be read" stays', async () => {
    answers[CAT] = { failed: true, status: 500 }
    const w = await openBuilder()
    expect(t(w, 'open-error').text()).toContain('could not be read')
  })
  it('catalogue answered a body with no contracts list (unreadable answer): "could not be read" stays', async () => {
    answers[CAT] = { underlying: 'NIFTY' }
    const w = await openBuilder()
    expect(t(w, 'open-error').text()).toContain('could not be read')
  })
})
