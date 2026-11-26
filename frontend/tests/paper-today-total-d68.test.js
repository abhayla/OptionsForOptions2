// GC-ICLIVE Part E, D-68 (ADR-320 point 6): the Positions header carries a "Today" total for the trades opened or closed today
// without scenario strategies, from the server's `today` block (the figure is the server's, never summed here). Every state:
// a value, paused (prices not live), nothing today, the last read failed (stale list), and an older reply with no block.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import REAL0 from './fixtures/paper-strategies.json'
import { closedFrom } from './_closedRows'
import { TRACKING_REFRESH_MS } from '@/lib/tracking'
const REAL = { ...REAL0, strategies: REAL0.strategies.map((s) => ({ ...s, closed: closedFrom(s.positions) })) }

let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url) => { const a = answers[`${method} ${url}`]; return a ? a() : Promise.reject({ message: 'no answer', parts: null, status: null }) }
  return { ...actual, default: { get: reply('GET'), post: reply('POST'), delete: reply('DELETE') } }
})
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'

const ok = (data) => () => Promise.resolve({ data })
const t = (w, id) => w.get(`[data-testid="${id}"]`)
const has = (w, id) => w.find(`[data-testid="${id}"]`).exists()
const TODAY = (over = {}) => ({ count: 2, empty_text: null, total: '70.05', total_text: '+70.05', total_after: '64.05', total_after_text: '+64.05',
  totals_reason: null, totals_reason_text: null, totals_as_of: null, after_charges_reason: null, after_charges_reason_text: null,
  charges_paid_text: 'Charges paid 4.00', charges_to_close_text: 'Estimated charges to close 2.00', ...over })
const reply = (today) => ({ ...JSON.parse(JSON.stringify(REAL)), today })

async function show() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } },
    { path: '/strategy/builder', component: { template: '<div/>' } }] })
  router.push('/')
  await router.isReady()
  const w = mount(PaperStrategies, { global: { plugins: [router] } })
  await flushPromises()
  return w
}
beforeEach(() => { answers = {}; vi.useFakeTimers() })
afterEach(() => vi.useRealTimers())

describe('D-68 the Today total in the header', () => {
  it('value: the label says Today and the figure is the server\'s after-charges text', async () => {
    answers['GET /paper/strategies'] = ok(reply(TODAY()))
    const w = await show()
    expect(t(w, 'totals-today-label').text()).toContain('Today')
    expect(t(w, 'totals-today').text()).toBe('+64.05')
    expect(has(w, 'totals-today-empty')).toBe(false)
  })
  it('paused: prices not live gives a dash and the server\'s reason, never a number', async () => {
    answers['GET /paper/strategies'] = ok(reply(TODAY({ total: null, total_text: null, total_after: null, total_after_text: null,
      totals_reason: 'prices_not_live', totals_reason_text: 'Paper P&L paused - prices not live', after_charges_reason: 'prices_not_live' })))
    const w = await show()
    expect(t(w, 'totals-today').text()).toBe('—')
    expect(t(w, 'totals-today-reason').text()).toContain('prices not live')
  })
  it('nothing today: the server\'s sentence replaces the figure', async () => {
    answers['GET /paper/strategies'] = ok(reply(TODAY({ count: 0, empty_text: 'No trades opened or closed today.', total_text: '+0.00', total_after_text: '+0.00' })))
    const w = await show()
    expect(t(w, 'totals-today-empty').text()).toBe('No trades opened or closed today.')
    expect(has(w, 'totals-today')).toBe(false)
  })
  it('read failed after a good read: the Today figure is paused like every other figure', async () => {
    answers['GET /paper/strategies'] = ok(reply(TODAY()))
    const w = await show()
    answers['GET /paper/strategies'] = () => Promise.reject({ message: 'down', parts: null, status: 503 })
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS + 50)
    await flushPromises()
    expect(t(w, 'totals-today').text()).toBe('—')
    expect(t(w, 'totals-today-reason').text()).toContain('prices not live')
  })
  it('a reply with no Today block (older server) shows no Today figure and no crash', async () => {
    answers['GET /paper/strategies'] = ok(reply(undefined))
    const w = await show()
    expect(has(w, 'totals-today')).toBe(false)
    expect(has(w, 'totals-total')).toBe(true)
  })
})
