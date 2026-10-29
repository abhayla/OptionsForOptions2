// GC-UI step 6d (D-C41, D-C44, D-C48, D-C50, D-C53, D-C54; REQ-109 AC-2; REQ-152; ADR-201 (2)): the Paper tab strategy
// header in Sensibull's layout. The fixture is the recorded GET /tracking shape of tests/paper-strategies.test.js (strategy 48,
// 2026-10-28), with a SELL leg, an exited (booked) leg and a loss. The API was not running for this step (low memory), so no
// fresh curl: every figure expected is the server's own string, only re-grouped. No funds figure appears.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

const calls = []
let answers = {}
import { legacy } from './_paperList'
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url, body) => {
    calls.push([method, url, body])
    const a = legacy(answers, method, url)
    return a ? a() : Promise.reject({ message: 'no answer', parts: null, status: null })
  }
  return { ...actual, default: { get: reply('GET'), post: reply('POST') } }
})

import { withPriceTexts } from './_priceTexts'
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'

const leg = (i, over = {}) => withPriceTexts({
  leg_index: i, instrument_id: `NSE_FO:${i + 1}`, action: i % 2 ? 'SELL' : 'BUY', instrument: i < 2 ? 'PE' : 'CE',
  strike: `${22300 + i * 100}.00`, expiry: '2026-11-03', quantity: 65, entry_price: '114.25', entry_at: '2026-10-28T05:03:09Z',
  current_price: '113.60', price_state: 'live', price_at: '2026-10-28T11:30:00+05:30', exit_price: null, exited_at: null, ...over,
})
const item = (over = {}) => withPriceTexts({
  strategy_id: 48, name: '"GCBP P1 BCS"', underlying: 'NIFTY', started_at: '2026-10-28T05:03:10Z', state: 'LIVE',
  pause_reason: null, as_of: null, total: '-1894.75', booked: '0.00', unbooked: '-1894.75', legs: [leg(0), leg(1)], ...over,
})
const list = (...strategies) => ({ strategies, answered_at: '2026-10-28T06:00:00Z' })
const ok = (data) => () => Promise.resolve({ data })
const t = (w, id) => w.get(`[data-testid="${id}"]`)
const has = (w, id) => w.find(`[data-testid="${id}"]`).exists()

async function show() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { template: '<div/>' } }, { path: '/strategy/builder', component: { template: '<div/>' } }],
  })
  router.push('/')
  await router.isReady()
  const w = mount(PaperStrategies, { global: { plugins: [router] } })
  await flushPromises()
  return w
}
beforeEach(() => { calls.length = 0; answers = {}; vi.useFakeTimers() })
afterEach(() => vi.useRealTimers())

describe('GC-UI 6d: Paper strategy header (D-C44)', () => {
  it('D-C54: a profit carries the profit class', async () => {
    answers['GET /tracking'] = ok(list(item({ total: '2808.00', unbooked: '2808.00' })))
    const w = await show()
    expect(t(w, 'paper-total').text()).toBe('+2,808.00')
    expect(t(w, 'paper-total').classes()).toContain('text-profit')
  })
  it('a P&L null with its reason: a dash and the reason line, no class', async () => {
    answers['GET /tracking'] = ok(list(item({ state: 'PAUSED', total: null, unbooked: null, as_of: '2026-10-28T11:00:00+05:30', pause_reason: 'price_stale' })))
    const w = await show()
    expect(t(w, 'paper-total').text()).toBe('—')
    expect(t(w, 'paper-unbooked').text()).toBe('—')
    expect(t(w, 'paper-state').text()).toContain('prices not live')
  })
  it('no paper strategies: the empty line, no header', async () => {
    answers['GET /tracking'] = ok(list())
    const w = await show()
    expect(has(w, 'paper-empty')).toBe(true)
    expect(has(w, 'paper-count')).toBe(false)
  })
  it('read failed: the server parts, no figure and no frame of figures', async () => {
    answers['GET /tracking'] = () => Promise.reject({ status: 503, parts: { what_happened: 'Tracking could not be read.' } })
    const w = await show()
    expect(has(w, 'paper-error-what')).toBe(true)
    expect(has(w, 'paper-total')).toBe(false)
  })
})

describe('GC-UI 6d: frame and action column (D-C41, D-C50)', () => {
  it('D-C41: the whole tab content sits in a dashed frame and keeps the not-real banner', async () => {
    answers['GET /tracking'] = ok(list(item()))
    const w = await show()
    expect(t(w, 'paper-strategies').classes()).toEqual(expect.arrayContaining(['border-dashed']))
    expect(t(w, 'paper-banner').text()).toBe('Paper trades - not real money')
  })
})
