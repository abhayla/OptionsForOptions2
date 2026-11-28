// Lane FJ2 item 9 / T3-10 (FJ second PC list): Positions shows no Retry after a failed load. Real case: Positions with the paper list read failing
// (the server down): the Paper part printed the four-part message and no Retry (the Real part had one). One failed-load rule (ListLoadFailed) for every list.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import REAL0 from './fixtures/paper-strategies.json'

let answers = {}
const calls = []
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (m) => (url) => { calls.push(`${m} ${url}`); const a = answers[`${m} ${url}`]; return a ? a() : Promise.reject({ message: 'x', parts: null, status: 500 }) }
  return { ...actual, default: { get: reply('GET'), post: reply('POST') } }
})
import PositionsPage from '@/pages/PositionsPage.vue'
import AdjustmentOpportunitiesPage from '@/pages/AdjustmentOpportunitiesPage.vue'
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'

const ok = (data) => () => Promise.resolve({ data })
const t = (w, id) => w.find(`[data-testid="${id}"]`)
beforeEach(() => { answers = {}; calls.length = 0; vi.useFakeTimers() })
afterEach(() => { vi.useRealTimers(); document.body.innerHTML = '' })
const mk = async (C, path = '/p') => {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/p', component: C, meta: { title: 'T', parent: 'P', view: 'current' } }, { path: '/:x(.*)*', component: { template: '<div/>' } }] })
  router.push(path); await router.isReady()
  const w = mount(C, { attachTo: document.body, global: { plugins: [router] } }); await flushPromises(); return w
}

describe('FJ2-9 T3-10 a failed paper list read has a Retry that reads again', () => {
  it('first read fails: a Retry button; pressing it reads /paper/strategies again and the list comes', async () => {
    answers['GET /features'] = ok({ order_path: 'on' })
    const w = await mk(PaperStrategies)
    expect(t(w, 'paper-error-retry').exists()).toBe(true)
    const before = calls.filter((c) => c === 'GET /paper/strategies').length
    answers['GET /paper/strategies'] = ok(REAL0)
    await t(w, 'paper-error-retry').trigger('click')
    await flushPromises()
    expect(calls.filter((c) => c === 'GET /paper/strategies').length).toBe(before + 1)
    expect(t(w, 'paper-error-retry').exists()).toBe(false)
    expect(w.findAll('[data-testid="paper-group"]').length).toBeGreaterThan(0)
  })
  it('on the Positions page the Paper part carries the same Retry', async () => {
    const w = await mk(PositionsPage)
    expect(t(w, 'paper-error-retry').exists()).toBe(true)
  })
})

describe('FJ2-9 T3-10 Adjustment opportunities: the same Retry (pinned)', () => {
  it('a failed load (neutral and a server message): Retry; pressing it reads /adjustment-opportunities again', async () => {
    const w = await mk(AdjustmentOpportunitiesPage)
    expect(t(w, 'opp-error-retry').exists()).toBe(true)
    const before = calls.filter((c) => c === 'GET /adjustment-opportunities').length
    await t(w, 'opp-error-retry').trigger('click')
    await flushPromises()
    expect(calls.filter((c) => c === 'GET /adjustment-opportunities').length).toBe(before + 1)
    document.body.innerHTML = ''
    answers['GET /adjustment-opportunities'] = () => Promise.reject({ status: 409, parts: { what_happened: 'Connect your Zerodha account.', impact: 'i', what_is_blocked: 'b', next_action: 'n' } })
    const w2 = await mk(AdjustmentOpportunitiesPage)
    expect(t(w2, 'opp-error-retry').exists()).toBe(true)
  })
})
