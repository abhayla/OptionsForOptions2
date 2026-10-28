// GC-UI step 6d (D-C41, D-C44, D-C48, D-C50, D-C53, D-C54; REQ-109 AC-2; REQ-152; ADR-201 (2)): the Paper tab strategy
// header in Sensibull's layout. The fixture is the recorded GET /tracking shape of tests/paper-strategies.test.js (strategy 48,
// 2026-10-28), with a SELL leg, an exited (booked) leg and a loss. The API was not running for this step (low memory), so no
// fresh curl: every figure expected is the server's own string, only re-grouped. No funds figure appears.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url, body) => {
    calls.push([method, url, body])
    const a = answers[`${method} ${url}`]
    return a ? a() : Promise.reject({ message: 'no answer', parts: null, status: null })
  }
  return { ...actual, default: { get: reply('GET'), post: reply('POST') } }
})

import PaperStrategies from '@/components/strategy/PaperStrategies.vue'

const leg = (i, over = {}) => ({
  leg_index: i, instrument_id: `NSE_FO:${i + 1}`, action: i % 2 ? 'SELL' : 'BUY', instrument: i < 2 ? 'PE' : 'CE',
  strike: `${22300 + i * 100}.00`, expiry: '2026-11-03', quantity: 65, entry_price: '114.25', entry_at: '2026-10-28T05:03:09Z',
  current_price: '113.60', price_state: 'live', price_at: '2026-10-28T11:30:00+05:30', exit_price: null, exited_at: null, ...over,
})
const item = (over = {}) => ({
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
  it('core: three labelled columns with the server texts, "2 of 2 positions", a SELL leg signed from the server side, the loss class', async () => {
    answers['GET /tracking'] = ok(list(item()))
    const w = await show()
    const cols = w.findAll('[data-testid="paper-figure-label"]').map((x) => x.text())
    expect(cols).toEqual(['Total P&L', 'Unbooked P&L', 'Booked P&L'])
    expect(t(w, 'paper-total').text()).toBe('-1,894.75')
    expect(t(w, 'paper-unbooked').text()).toBe('-1,894.75')
    expect(t(w, 'paper-booked').text()).toBe('0.00') // D-C53: a true zero has no sign
    expect(t(w, 'paper-count').text()).toBe('2 of 2 positions')
    const legs = w.findAll('[data-testid="paper-leg"]')
    expect(t(w, 'paper-group').findAll('th').map((h) => h.text())).toEqual(expect.arrayContaining(['Instrument', 'Qty', 'Paper entry']))
    expect(legs[0].get('[data-testid="paper-instrument"]').text()).toBe('B 3 Nov 22300 PE')
    expect(legs[0].get('[data-testid="paper-qty"]').text()).toBe('65')
    expect(legs[1].get('[data-testid="paper-instrument"]').text()).toBe('S 3 Nov 22400 PE')
    expect(legs[1].get('[data-testid="paper-qty"]').text()).toBe('-65')
    expect(t(w, 'paper-total').classes()).toContain('text-loss')
    expect(t(w, 'paper-booked').classes()).not.toContain('text-loss')
    expect(t(w, 'paper-booked').classes()).not.toContain('text-profit')
  })
  it('D-C54: a profit carries the profit class', async () => {
    answers['GET /tracking'] = ok(list(item({ total: '2808.00', unbooked: '2808.00' })))
    const w = await show()
    expect(t(w, 'paper-total').text()).toBe('+2,808.00')
    expect(t(w, 'paper-total').classes()).toContain('text-profit')
  })
  it('a strategy with an exited (booked) leg: "1 of 2 positions", booked figure, exit price, no tick box on the exited leg', async () => {
    const out = leg(1, { exit_price: '120.00', exited_at: '2026-10-28T09:00:00Z', price_state: 'exited', current_price: null })
    answers['GET /tracking'] = ok(list(item({ total: '-20.00', booked: '-20.00', unbooked: '0.00', legs: [leg(0), out] })))
    const w = await show()
    expect(t(w, 'paper-count').text()).toBe('1 of 2 positions')
    expect(t(w, 'paper-booked').text()).toBe('-20.00')
    expect(t(w, 'paper-booked').classes()).toContain('text-loss')
    expect(t(w, 'paper-unbooked').text()).toBe('0.00')
    const legs = w.findAll('[data-testid="paper-leg"]')
    expect(legs[1].text()).toContain('Exited at 120.00')
    expect(legs[1].find('input[type="checkbox"]').exists()).toBe(false)
  })
  it('a P&L null with its reason: a dash and the reason line, no class', async () => {
    answers['GET /tracking'] = ok(list(item({ state: 'PAUSED', total: null, unbooked: null, as_of: '2026-10-28T11:00:00+05:30', pause_reason: 'price_stale' })))
    const w = await show()
    expect(t(w, 'paper-total').text()).toBe('—')
    expect(t(w, 'paper-unbooked').text()).toBe('—')
    expect(t(w, 'paper-state').text()).toContain('prices not live')
  })
  it('a FUT leg: "B 3 Nov FUT" with no strike', async () => {
    answers['GET /tracking'] = ok(list(item({ legs: [leg(0, { instrument: 'FUT', strike: null })] })))
    const w = await show()
    expect(t(w, 'paper-instrument').text()).toBe('B 3 Nov FUT')
    expect(t(w, 'paper-count').text()).toBe('1 of 1 positions')
  })
  it('a calendar strategy: the two expiries show in the Instrument cells', async () => {
    answers['GET /tracking'] = ok(list(item({ legs: [leg(0, { expiry: '2026-11-03' }), leg(1, { expiry: '2026-11-10' })] })))
    const w = await show()
    const cells = w.findAll('[data-testid="paper-instrument"]').map((c) => c.text())
    expect(cells).toEqual(['B 3 Nov 22300 PE', 'S 10 Nov 22400 PE'])
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
  it('D-C50: the action column has Open in Builder and Exit (n) following the ticks; no Add Orders, no Convert', async () => {
    answers['GET /tracking'] = ok(list(item()))
    const w = await show()
    const actions = t(w, 'paper-actions')
    expect(actions.get('[data-testid="paper-open-builder"]').attributes('href')).toBe('/strategy/builder?strategy=48')
    expect(t(w, 'exit-selected-48').text()).toBe('Exit (0)')
    expect(t(w, 'exit-selected-48').attributes('disabled')).toBeDefined()
    await t(w, 'select-leg-48-0').setValue(true)
    expect(t(w, 'exit-selected-48').text()).toBe('Exit (1)')
    await t(w, 'select-leg-48-1').setValue(true)
    expect(t(w, 'exit-selected-48').text()).toBe('Exit (2)')
    expect(w.text()).not.toMatch(/Add Orders|Convert To Real/i)
  })
  it('Exit (n) keeps the inline paper confirm and posts the ticked legs to the paper route only', async () => {
    answers['GET /tracking'] = ok(list(item()))
    answers['POST /strategies/48/tracking/exit'] = ok({})
    const w = await show()
    await t(w, 'select-leg-48-1').setValue(true)
    await t(w, 'exit-selected-48').trigger('click')
    expect(t(w, 'exit-confirm-text').text()).toContain('Paper exit - no order is sent')
    expect(t(w, 'exit-confirm-text').text()).toContain('22400')
    expect(calls.some((c) => c[0] === 'POST')).toBe(false)
    await t(w, 'exit-confirm').trigger('click')
    await flushPromises()
    const posts = calls.filter((c) => c[0] === 'POST')
    expect(posts).toHaveLength(1)
    expect(posts[0][1]).toBe('/strategies/48/tracking/exit')
    expect(posts[0][2]).toEqual({ legs: [1] })
  })
})
