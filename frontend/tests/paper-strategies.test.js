// GC-BP step 6 (ADR-201 (2); REQ-109 AC-2/AC-3/AC-4): the shared Paper strategies list. REAL_REPLY is GET /tracking as
// answered live on 2026-10-28 11:3x IST for strategy 48 (the other three legs are the same shape). Every figure expected
// below is the server's own string, only re-grouped: the browser sums nothing.
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
import { readTrackingItem, readTracking, TRACKING_REFRESH_MS, UNREADABLE_TEXT, NOT_CONNECTED_TEXT } from '@/lib/tracking'

const leg = (i, over = {}) => ({
  leg_index: i, instrument_id: `NSE_FO:${i + 1}`, action: i % 2 ? 'SELL' : 'BUY', instrument: i < 2 ? 'PE' : 'CE',
  strike: `${22300 + i * 100}.00`, expiry: '2026-11-03', quantity: 65, entry_price: '114.25', entry_at: '2026-10-28T05:03:09Z',
  current_price: '113.60', price_state: 'live', price_at: '2026-10-28T11:30:00+05:30', exit_price: null, exited_at: null, ...over,
})
const item = (over = {}) => ({
  strategy_id: 48, name: '"GCBP P3 IC"', underlying: 'NIFTY', started_at: '2026-10-28T05:03:10Z', state: 'LIVE',
  pause_reason: null, as_of: null, total: '71.50', booked: '0.00', unbooked: '71.50', legs: [leg(0), leg(1), leg(2), leg(3)], ...over,
})
const REAL_REPLY = { strategies: [item()], answered_at: '2026-10-28T06:00:00Z' }
const list = (...strategies) => ({ strategies, answered_at: '2026-10-28T06:00:00Z' })
const ok = (data) => () => Promise.resolve({ data })
const t = (w, id) => w.get(`[data-testid="${id}"]`)
const has = (w, id) => w.find(`[data-testid="${id}"]`).exists()
const gets = () => calls.filter((c) => c[0] === 'GET' && c[1] === '/tracking').length

// GC-UI 6d D-C50: a leg is exited by ticking it and pressing Exit (n) in the action column
async function exitLeg(w, i) {
  await t(w, `select-leg-48-${i}`).setValue(true)
  await t(w, 'exit-selected-48').trigger('click')
}
async function exitAll(w) {
  for (const b of w.findAll('input[type="checkbox"]')) await b.setValue(true)
  await t(w, 'exit-selected-48').trigger('click')
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
  it('core: shows GCBP P3 IC (quotes stripped), 4 legs and the total +71.50, labelled paper', async () => {
    answers['GET /tracking'] = ok(REAL_REPLY)
    const w = await show()
    expect(t(w, 'paper-banner').text()).toBe('Paper trades - not real money')
    expect(t(w, 'paper-group-name').text()).toBe('GCBP P3 IC')
    expect(w.findAll('[data-testid="paper-leg"]')).toHaveLength(4)
    expect(t(w, 'paper-total').text()).toBe('+71.50')
    expect(t(w, 'paper-booked').text()).toBe('0.00') // D-C53: a true zero has no sign
    expect(t(w, 'paper-unbooked').text()).toBe('+71.50')
    expect(t(w, 'paper-group').text()).toContain('Paper')
    expect(t(w, 'paper-open-builder').attributes('href')).toBe('/strategy/builder?strategy=48')
    const first = w.findAll('[data-testid="paper-leg"]')[0].text()
    expect(first).toContain('B 3 Nov 22300 PE')
    expect(first).toContain('3 Nov')
    expect(first).toContain('22300')
    expect(first).toContain('114.25')
    expect(t(w, 'paper-group').findAll('th').map((h) => h.text())).toContain('Paper entry') // D-B51
    expect(t(w, 'paper-group').findAll('th').map((h) => h.text())).not.toContain('Entry')
    expect(first).toContain('113.60')
  })
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
    expect(totals).toEqual(['+71.50', '-20.00'])
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
    expect(t(w, 'paper-empty').text()).toBe('No paper strategies yet. Save a strategy in the builder, then press Start tracking.')
  })
  it('paused: the paused line with the time and the reason, no total', async () => {
    answers['GET /tracking'] = ok(list(item({ state: 'PAUSED', total: null, unbooked: null, as_of: '2026-10-28T11:00:00+05:30', pause_reason: 'price_stale' })))
    const w = await show()
    expect(t(w, 'paper-state').text()).toContain('prices not live, as of 28 Oct 2026, 11:00:00 IST')
    expect(t(w, 'paper-pause-reason').text()).toBe('price_stale')
    expect(t(w, 'paper-total').text()).toBe('—')
    expect(t(w, 'paper-unbooked').text()).toBe('—')
  })
  it('not connected', async () => {
    answers['GET /tracking'] = ok(list(item({ state: 'NOT_CONNECTED', total: null, unbooked: null })))
    const w = await show()
    expect(t(w, 'paper-state').text()).toBe(NOT_CONNECTED_TEXT)
    expect(t(w, 'paper-total').text()).toBe('—')
  })
  it('exited: Exited line, exit prices, no Exit buttons', async () => {
    const out = (i) => leg(i, { exit_price: '120.00', exited_at: '2026-10-28T09:00:00Z', price_state: 'exited', current_price: null })
    answers['GET /tracking'] = ok(list(item({ state: 'EXITED', total: '55.00', booked: '55.00', unbooked: '0.00', legs: [out(0), out(1)] })))
    const w = await show()
    expect(t(w, 'paper-state').text()).toBe('Exited')
    expect(w.findAll('[data-testid="paper-leg"]')[0].text()).toContain('Exited at 120.00')
    expect(t(w, 'paper-booked').text()).toBe('+55.00')
    expect(w.findAll('button')).toHaveLength(0)
  })
  it('one unreadable item among good ones: shown as unreadable with no figure, the others stay', async () => {
    answers['GET /tracking'] = ok(list(item(), item({ strategy_id: 50, name: 'Bad', total: 'oops' })))
    const w = await show()
    const groups = w.findAll('[data-testid="paper-group"]')
    expect(groups).toHaveLength(2)
    expect(groups[1].text()).toContain(UNREADABLE_TEXT)
    expect(groups[1].find('[data-testid="paper-total"]').exists()).toBe(false)
    expect(groups[0].get('[data-testid="paper-total"]').text()).toBe('+71.50')
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
  it('per leg: Exit opens an inline confirm naming the leg and "no order is sent"; confirm posts that leg and re-reads', async () => {
    let state = item()
    answers['GET /tracking'] = () => Promise.resolve({ data: list(state) })
    answers['POST /strategies/48/tracking/exit'] = () => {
      state = item({ total: '80.00', unbooked: '30.00', booked: '50.00' })
      return Promise.resolve({ data: {} })
    }
    const w = await show()
    await exitLeg(w, 2)
    expect(t(w, 'exit-confirm-text').text()).toContain('Paper exit - no order is sent')
    expect(t(w, 'exit-confirm-text').text()).toContain('22500')
    expect(calls.some((c) => c[0] === 'POST')).toBe(false)
    await t(w, 'exit-confirm').trigger('click')
    await flushPromises()
    const post = calls.find((c) => c[0] === 'POST')
    expect(post[1]).toBe('/strategies/48/tracking/exit')
    expect(post[2]).toEqual({ legs: [2] })
    expect(has(w, 'exit-confirm')).toBe(false)
    expect(t(w, 'paper-booked').text()).toBe('+50.00')
  })
  it('Exit all posts every open leg only', async () => {
    const legs = [leg(0), leg(1, { exit_price: '1.00', exited_at: '2026-10-28T09:00:00Z', price_state: 'exited' }), leg(2)]
    answers['GET /tracking'] = ok(list(item({ legs })))
    answers['POST /strategies/48/tracking/exit'] = ok({})
    const w = await show()
    expect(has(w, 'select-leg-48-1')).toBe(false)
    await exitAll(w)
    await t(w, 'exit-confirm').trigger('click')
    await flushPromises()
    expect(calls.find((c) => c[0] === 'POST')[2]).toEqual({ legs: [0, 2] })
  })
  it('cancel posts nothing', async () => {
    answers['GET /tracking'] = ok(REAL_REPLY)
    const w = await show()
    await exitAll(w)
    await t(w, 'exit-cancel').trigger('click')
    expect(has(w, 'exit-confirm')).toBe(false)
    expect(calls.some((c) => c[0] === 'POST')).toBe(false)
  })
  it('refused: the catalogue message shows by that group and the figures do not change', async () => {
    answers['GET /tracking'] = ok(REAL_REPLY)
    answers['POST /strategies/48/tracking/exit'] = () => Promise.reject({ status: 409, parts: { what_happened: 'Prices are not live; try again when they update' } })
    const w = await show()
    await exitLeg(w, 0)
    await t(w, 'exit-confirm').trigger('click')
    await flushPromises()
    expect(t(w, 'paper-exit-error').text()).toBe('Prices are not live; try again when they update')
    expect(t(w, 'paper-total').text()).toBe('+71.50')
    expect(w.findAll('[data-testid="paper-leg"]')).toHaveLength(4)
  })
  it('while an exit is in flight every Exit button is disabled', async () => {
    answers['GET /tracking'] = ok(REAL_REPLY)
    answers['POST /strategies/48/tracking/exit'] = () => new Promise(() => {})
    const w = await show()
    await exitLeg(w, 0)
    await t(w, 'exit-confirm').trigger('click')
    await flushPromises()
    expect(t(w, 'exit-selected-48').attributes('disabled')).toBeDefined()
    expect(t(w, 'exit-confirm').attributes('disabled')).toBeDefined()
    await exitLeg(w, 1)
    expect(calls.filter((c) => c[0] === 'POST')).toHaveLength(1)
  })
})

describe('PaperStrategies: review 1 minors (GC-BP step 8)', () => {
  it('R1-5: each per-leg Exit button is named by its leg', async () => {
    answers['GET /tracking'] = ok(REAL_REPLY)
    const w = await show()
    expect(t(w, 'select-leg-48-0').attributes('aria-label')).toBe('Select Buy 22300 PE 3 Nov')
    expect(t(w, 'select-leg-48-1').attributes('aria-label')).toBe('Select Sell 22400 PE 3 Nov')
  })
  it('R1-4: a read that changes the list drops an open confirm whose leg is no longer open', async () => {
    let reply = REAL_REPLY
    answers['GET /tracking'] = () => Promise.resolve({ data: reply })
    const w = await show()
    await exitLeg(w, 0)
    expect(has(w, 'exit-confirm')).toBe(true)
    const out = (i) => leg(i, { exit_price: '120.00', exited_at: '2026-10-28T09:00:00Z', price_state: 'exited', current_price: null })
    reply = list(item({ legs: [out(0), leg(1), leg(2), leg(3)] }))
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    expect(has(w, 'exit-confirm')).toBe(false)
  })
  it('R1-4: a failed read drops the confirm and the exit error; they do not come back with the next good read', async () => {
    let fail = false
    answers['GET /tracking'] = () => (fail ? Promise.reject({ status: 503, parts: null }) : Promise.resolve({ data: REAL_REPLY }))
    answers['POST /strategies/48/tracking/exit'] = () => Promise.reject({ status: 409, parts: { what_happened: 'Prices are not live' } })
    const w = await show()
    await exitLeg(w, 0)
    await t(w, 'exit-confirm').trigger('click')
    await flushPromises()
    expect(has(w, 'paper-exit-error')).toBe(true)
    await exitLeg(w, 1)
    fail = true
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    fail = false
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    expect(has(w, 'paper-group')).toBe(true)
    expect(has(w, 'exit-confirm')).toBe(false)
    expect(has(w, 'paper-exit-error')).toBe(false)
  })
  it('R1-4: Cancel clears that group\'s exit error', async () => {
    answers['GET /tracking'] = ok(REAL_REPLY)
    answers['POST /strategies/48/tracking/exit'] = () => Promise.reject({ status: 409, parts: { what_happened: 'Prices are not live' } })
    const w = await show()
    await exitLeg(w, 0)
    await t(w, 'exit-confirm').trigger('click')
    await flushPromises()
    await exitLeg(w, 1)
    await t(w, 'exit-cancel').trigger('click')
    expect(has(w, 'paper-exit-error')).toBe(false)
  })
})

describe('lib/tracking readers', () => {
  it('readTracking reads EXITED with booked and unbooked', () => {
    const v = readTracking({ state: 'EXITED', paper_pnl: '55.00', booked: '55.00', unbooked: '0.00', legs: [], detections: [] })
    expect(v.kind).toBe('exited')
    expect(v.text).toBe('Paper P&L (not real): +55.00 - exited')
    expect(v.figure).toBe('+55.00')
    expect(v.booked).toBe('+55.00')
    expect(v.unbooked).toBe('+0.00')
  })
  it('readTrackingItem fails closed on a state or money string it cannot read', () => {
    expect(readTrackingItem(item()).readable).toBe(true)
    expect(readTrackingItem(item({ state: 'WEIRD' })).readable).toBe(false)
    expect(readTrackingItem(item({ booked: '1' })).readable).toBe(false)
    expect(readTrackingItem(item({ total: null })).readable).toBe(false)
    expect(readTrackingItem(null).readable).toBe(false)
  })
})
