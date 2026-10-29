// GC-BP step 6 (ADR-201 (2); REQ-109 AC-2/AC-3/AC-4): the shared Paper strategies list. REAL_REPLY is GET /tracking as
// answered live on 2026-10-28 11:3x IST for strategy 48 (the other three legs are the same shape). Every figure expected
// below is the server's own string, only re-grouped: the browser sums nothing.
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
import { readTrackingItem, readTracking, TRACKING_REFRESH_MS, NOT_CONNECTED_TEXT } from '@/lib/tracking'

const leg = (i, over = {}) => withPriceTexts({
  leg_index: i, instrument_id: `NSE_FO:${i + 1}`, action: i % 2 ? 'SELL' : 'BUY', instrument: i < 2 ? 'PE' : 'CE',
  strike: `${22300 + i * 100}.00`, expiry: '2026-11-03', quantity: 65, entry_price: '114.25', entry_at: '2026-10-28T05:03:09Z',
  current_price: '113.60', price_state: 'live', price_at: '2026-10-28T11:30:00+05:30', exit_price: null, exited_at: null, ...over,
})
const item = (over = {}) => withPriceTexts({
  strategy_id: 48, name: '"GCBP P3 IC"', underlying: 'NIFTY', started_at: '2026-10-28T05:03:10Z', state: 'LIVE',
  pause_reason: null, as_of: null, total: '71.50', booked: '0.00', unbooked: '71.50', legs: [leg(0), leg(1), leg(2), leg(3)], ...over,
})
const REAL_REPLY = { strategies: [item()], answered_at: '2026-10-28T06:00:00Z' }
const list = (...strategies) => ({ strategies, answered_at: '2026-10-28T06:00:00Z' })
const ok = (data) => () => Promise.resolve({ data })
const t = (w, id) => w.get(`[data-testid="${id}"]`)
const has = (w, id) => w.find(`[data-testid="${id}"]`).exists()
const gets = () => calls.filter((c) => c[0] === 'GET' && c[1] === '/paper/strategies').length

// GC-UI 6d D-C50: a leg is exited by ticking it and pressing Exit (n) in the action column
async function exitLeg(w, i) {
  await t(w, `select-leg-48-${i + 1}`).setValue(true)
  await t(w, 'exit-selected-48').trigger('click')
  await flushPromises()
}
async function exitAll(w) {
  for (const b of w.findAll('input[type="checkbox"]')) await b.setValue(true)
  await t(w, 'exit-selected-48').trigger('click')
  await flushPromises()
}

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

describe('PaperStrategies: the real reply', () => {
  it('REQ-109 AC-3: nothing links to /execute and there is no Execute button', async () => {
    answers['GET /tracking'] = ok(REAL_REPLY)
    const w = await show()
    expect(w.findAll('a').filter((a) => (a.attributes('href') || '').includes('/execute'))).toHaveLength(0)
    expect(w.text()).not.toMatch(/execute/i)
  })
  it('ADR-008: shows the server totals of two strategies and no sum of them', async () => {
    answers['GET /tracking'] = ok(list(item(), item({ strategy_id: 49, name: 'Second', total: '-20.00', booked: '-20.00', unbooked: '0.00' })))
    const w = await show()
    const totals = w.findAll('[data-testid="paper-total"]').map((x) => x.text())
    expect(totals).toEqual(['+71.50', '−20.00'])
    expect(w.text()).not.toContain('51.50')
  })
})

describe('PaperStrategies: answer states', () => {
  it('loading', async () => {
    answers['GET /tracking'] = () => new Promise(() => {})
    const w = await show()
    expect(has(w, 'paper-loading')).toBe(true)
    expect(has(w, 'paper-group')).toBe(false)
  })
  it('empty list', async () => {
    answers['GET /tracking'] = ok(list())
    const w = await show()
    expect(t(w, 'paper-empty').text()).toBe('No paper strategies yet. Build a strategy, then press Add to Paper.')
  })
  it('not connected', async () => {
    answers['GET /tracking'] = ok(list(item({ state: 'NOT_CONNECTED', total: null, unbooked: null })))
    const w = await show()
    expect(t(w, 'paper-state').text()).toBe(NOT_CONNECTED_TEXT)
    expect(t(w, 'paper-total').text()).toBe('—')
  })
  it('the list read fails: the server parts and no figures', async () => {
    answers['GET /tracking'] = () => Promise.reject({ status: 503, parts: { what_happened: 'Tracking could not be read.', impact: 'i', what_is_blocked: 'b', next_action: 'n' } })
    const w = await show()
    expect(t(w, 'paper-error-what').text()).toBe('Tracking could not be read.')
    expect(has(w, 'paper-group')).toBe(false)
    expect(has(w, 'paper-total')).toBe(false)
  })
  it('a refresh failure after a good read shows no figures; the next good read restores them', async () => {
    let fail = false
    answers['GET /tracking'] = () => (fail ? Promise.reject({ status: 503, parts: null }) : Promise.resolve({ data: REAL_REPLY }))
    const w = await show()
    fail = true
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    expect(has(w, 'paper-total')).toBe(false)
    expect(has(w, 'paper-error-what')).toBe(true)
    fail = false
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    expect(t(w, 'paper-total').text()).toBe('+71.50')
    expect(has(w, 'paper-error-what')).toBe(false)
  })
  it('re-reads every TRACKING_REFRESH_MS and stops after unmount', async () => {
    answers['GET /tracking'] = ok(REAL_REPLY)
    const w = await show()
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    expect(gets()).toBe(2)
    w.unmount()
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS * 3)
    expect(gets()).toBe(2)
  })
  it('a read still in flight is never doubled by the next tick', async () => {
    answers['GET /tracking'] = () => new Promise(() => {})
    await show()
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS * 3)
    expect(gets()).toBe(1)
  })
})

describe('PaperStrategies: Paper exit', () => {
  it('cancel posts nothing', async () => {
    answers['GET /tracking'] = ok(REAL_REPLY)
    const w = await show()
    await exitAll(w)
    await t(w, 'paper-cancel').trigger('click')
    expect(has(w, 'paper-confirm')).toBe(false)
    expect(calls.some((c) => c[0] === 'POST')).toBe(false)
  })
})

describe('PaperStrategies: review 1 minors (GC-BP step 8)', () => {
  it('R1-4: a read that changes the list drops an open confirm whose leg is no longer open', async () => {
    let reply = REAL_REPLY
    answers['GET /tracking'] = () => Promise.resolve({ data: reply })
    const w = await show()
    await exitLeg(w, 0)
    expect(has(w, 'paper-confirm')).toBe(true)
    const out = (i) => leg(i, { exit_price: '120.00', exited_at: '2026-10-28T09:00:00Z', price_state: 'exited', current_price: null })
    reply = list(item({ legs: [out(0), leg(1), leg(2), leg(3)] }))
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    expect(has(w, 'paper-confirm')).toBe(false)
  })
  it('R1-4: a failed read drops the confirm and the exit error; they do not come back with the next good read', async () => {
    let fail = false
    answers['GET /tracking'] = () => (fail ? Promise.reject({ status: 503, parts: null }) : Promise.resolve({ data: REAL_REPLY }))
    answers['POST /paper/strategies/48/orders'] = () => Promise.reject({ status: 409, parts: { what_happened: 'Prices are not live' } })
    const w = await show()
    await exitLeg(w, 0)
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(has(w, 'paper-error')).toBe(true)
    await exitLeg(w, 1)
    fail = true
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    fail = false
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    expect(has(w, 'paper-group')).toBe(true)
    expect(has(w, 'paper-confirm')).toBe(false)
    expect(has(w, 'paper-error')).toBe(false)
  })
  it('R1-4: Cancel clears that group\'s exit error', async () => {
    answers['GET /tracking'] = ok(REAL_REPLY)
    answers['POST /paper/strategies/48/orders'] = () => Promise.reject({ status: 409, parts: { what_happened: 'Prices are not live' } })
    const w = await show()
    await exitLeg(w, 0)
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    await exitLeg(w, 1)
    await t(w, 'paper-cancel').trigger('click')
    expect(has(w, 'paper-error')).toBe(false)
  })
})

describe('lib/tracking readers', () => {
  it('readTracking reads EXITED with booked and unbooked', () => {
    const v = readTracking({ state: 'EXITED', paper_pnl: '55.00', paper_pnl_text: '+55.00', booked: '55.00', booked_text: '+55.00', unbooked: '0.00', unbooked_text: '0.00', legs: [], detections: [] })
    expect(v.kind).toBe('exited')
    expect(v.text).toBe('Paper P&L (not real): +55.00 - exited')
    expect(v.figure).toBe('+55.00')
    expect(v.booked).toBe('+55.00')
    expect(v.unbooked).toBe('0.00')
  })
  it('readTrackingItem fails closed on a state or money string it cannot read', () => {
    expect(readTrackingItem(item()).readable).toBe(true)
    expect(readTrackingItem(item({ state: 'WEIRD' })).readable).toBe(false)
    expect(readTrackingItem(item({ booked: '1' })).readable).toBe(false)
    expect(readTrackingItem(item({ total: null })).readable).toBe(false)
    expect(readTrackingItem(null).readable).toBe(false)
  })
})
