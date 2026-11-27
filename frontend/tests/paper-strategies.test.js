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
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'
import { readTrackingItem, readTracking, TRACKING_REFRESH_MS, NOT_CONNECTED_TEXT, PAPER_UNKNOWN_HOLD_MS } from '@/lib/tracking'

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
  it('D-05 r2: a failed refresh keeps the loaded list, an open Stops panel and its typed level, and shows an error banner', async () => {
    let fail = false
    answers['GET /tracking'] = () => (fail ? Promise.reject({ status: null, parts: null }) : Promise.resolve({ data: REAL_REPLY }))
    answers['GET /paper/strategies/48/triggers'] = ok({ triggers: [] })
    const w = await show()
    await t(w, 'stops-open-48').trigger('click')
    await flushPromises()
    await t(w, 'ce-above').setValue('29980')
    fail = true
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    expect(has(w, 'paper-error-what')).toBe(true)
    expect(has(w, 'paper-group')).toBe(true)
    expect(has(w, 'paper-stops')).toBe(true)
    expect(t(w, 'ce-above').element.value).toBe('29980')
    fail = false
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    expect(has(w, 'paper-error-what')).toBe(false)
    expect(t(w, 'ce-above').element.value).toBe('29980')
  })
  it('D-05 r3: a refresh failure after a good read shows NO figure, keeps cards, legs, the open Stops panel and its typed level', async () => {
    let fail = false
    answers['GET /tracking'] = () => (fail ? Promise.reject({ status: 503, parts: null }) : Promise.resolve({ data: REAL_REPLY }))
    answers['GET /paper/strategies/48/triggers'] = ok({ triggers: [] })
    const w = await show()
    expect(w.text()).toContain('113.60')
    expect(w.text()).toContain('71.50')
    await t(w, 'stops-open-48').trigger('click')
    await flushPromises()
    await t(w, 'ce-above').setValue('29980')
    fail = true
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    expect(w.text()).not.toContain('113.60')
    expect(w.text()).not.toContain('71.50')
    expect(t(w, 'paper-total').text()).toBe('—')
    expect(w.findAll('[data-testid="paper-ltp"]').every((c) => c.text().startsWith('—'))).toBe(true)
    expect(w.findAll('[data-testid="paper-leg-pnl"]').every((c) => c.text() === '—')).toBe(true)
    expect(t(w, 'paper-total-reason').text()).toBe('Paper P&L paused - prices not live')
    expect(has(w, 'paper-group')).toBe(true)
    expect(w.findAll('[data-testid="paper-leg"]')).toHaveLength(4)
    expect(has(w, 'paper-stops')).toBe(true)
    expect(t(w, 'ce-above').element.value).toBe('29980')
    expect(t(w, 'ce-save').attributes('disabled')).toBeUndefined()
    fail = false
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    expect(t(w, 'paper-total').text()).toBe('+71.50')
    expect(w.text()).toContain('113.60')
  })
  it('D-05 r3 (REQ-109 AC-5): Exit is disabled with the reason while the last refresh failed, and no order opens from the old price', async () => {
    let fail = false
    answers['GET /tracking'] = () => (fail ? Promise.reject({ status: 503, parts: null }) : Promise.resolve({ data: REAL_REPLY }))
    const w = await show()
    await t(w, 'select-leg-48-1').setValue(true)
    expect(t(w, 'exit-selected-48').attributes('disabled')).toBeUndefined()
    fail = true
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    expect(t(w, 'exit-selected-48').attributes('disabled')).toBeDefined()
    expect(t(w, 'paper-exit-reason').text()).toBe('Prices are not live; try again when they update')
    await t(w, 'exit-selected-48').trigger('click')
    await flushPromises()
    expect(w.findComponent(PaperConfirmDialog).props('open')).toBe(false)
    expect(calls.filter((c) => c[0] === 'POST')).toHaveLength(0)
    fail = false
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    expect(t(w, 'exit-selected-48').attributes('disabled')).toBeUndefined()
    expect(has(w, 'paper-exit-reason')).toBe(false)
  })
  it('a refresh failure after a good read keeps the list under an error banner; the next good read clears the banner', async () => {
    let fail = false
    answers['GET /tracking'] = () => (fail ? Promise.reject({ status: 503, parts: null }) : Promise.resolve({ data: REAL_REPLY }))
    const w = await show()
    fail = true
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    expect(has(w, 'paper-total')).toBe(true)
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
  it('R1-4 (hotfix 27 Nov, ADR-016..019, owner T1-02): a failed read keeps the open confirm, blocked with the reason; Cancel closes it and the exit error does not come back', async () => {
    let fail = false
    answers['GET /tracking'] = () => (fail ? Promise.reject({ status: 503, parts: null }) : Promise.resolve({ data: REAL_REPLY }))
    answers['POST /paper/strategies/48/orders'] = () => Promise.reject({ status: 409, parts: { what_happened: 'Prices are not live' } })
    const w = await show()
    await exitLeg(w, 0)
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(has(w, 'paper-error')).toBe(true)
    fail = true
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    expect(has(w, 'paper-confirm')).toBe(true)
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeDefined()
    await t(w, 'paper-cancel').trigger('click')
    fail = false
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    expect(has(w, 'paper-group')).toBe(true)
    expect(has(w, 'paper-confirm')).toBe(false)
    expect(has(w, 'paper-error')).toBe(false)
  })
  it('D-05 r5 (hotfix 27 Nov, ADR-016..019, owner T1-02): an unreadable 2xx refresh keeps the confirm open and blocked with the reason and the leg; confirming posts nothing; ticks are kept', async () => {
    let bad = false
    answers['GET /tracking'] = () => Promise.resolve({ data: bad ? { unreadable: true } : REAL_REPLY })
    answers['POST /paper/strategies/48/orders'] = ok({})
    const w = await show()
    await exitLeg(w, 0)
    const orders = w.findComponent(PaperConfirmDialog).props('orders')
    expect(w.findComponent(PaperConfirmDialog).props('open')).toBe(true)
    bad = true
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    expect(w.findComponent(PaperConfirmDialog).props('open')).toBe(true)
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeDefined()
    expect(t(w, 'paper-error').text()).toContain('22300')
    expect(t(w, 'paper-error').text()).toContain('Prices are not live; try again when they update')
    w.findComponent(PaperConfirmDialog).vm.$emit('confirm', orders)
    await flushPromises()
    expect(calls.filter((c) => c[0] === 'POST')).toHaveLength(0)
    expect(t(w, 'paper-error').text()).toContain('22300')
    expect(t(w, 'select-leg-48-1').element.checked).toBe(true)
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

describe('PaperStrategies: an Exit never ends with nothing done and nothing said (hotfix 27 Nov, ADR-016..019, ADR-328 (4), REQ-065, owner T1-02)', () => {
  const FOUR = { what_happened: 'Prices are not live.', impact: 'Nothing was exited.', what_is_blocked: 'This exit.', next_action: 'Try again when prices update.' }
  const NOT_LIVE = 'Prices are not live; try again when they update'
  const posts = () => calls.filter((c) => c[0] === 'POST')
  const err = (w) => t(w, 'paper-error').text()
  const confirmOff = (w) => t(w, 'paper-confirm-button').attributes('disabled') !== undefined
  it('a failed re-read with the dialog open: dialog stays, Confirm disabled, leg and the not-live sentence visible, nothing posted', async () => {
    let fail = false
    answers['GET /tracking'] = () => (fail ? Promise.reject({ status: 503, parts: null }) : Promise.resolve({ data: REAL_REPLY }))
    const w = await show()
    await exitLeg(w, 0)
    fail = true
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    expect(has(w, 'paper-confirm')).toBe(true)
    expect(confirmOff(w)).toBe(true)
    expect(err(w)).toContain('22300')
    expect(err(w)).toContain(NOT_LIVE)
    expect(posts()).toHaveLength(0)
  })
  it('reads flip fail / good / fail between Exit and Confirm: never silent, Confirm unlocks on the good read', async () => {
    let fail = false
    answers['GET /tracking'] = () => (fail ? Promise.reject({ status: 503, parts: null }) : Promise.resolve({ data: REAL_REPLY }))
    const w = await show()
    await exitLeg(w, 0)
    for (let i = 0; i < 3; i++) {
      fail = true
      await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
      expect(confirmOff(w)).toBe(true)
      expect(err(w)).toContain(NOT_LIVE)
      fail = false
      await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
      expect(confirmOff(w)).toBe(false)
      expect(has(w, 'paper-error')).toBe(false)
    }
    expect(posts()).toHaveLength(0)
  })
  it('Confirm while stale (the doExit stale branch) says so with the leg and posts nothing', async () => {
    let fail = false
    answers['GET /tracking'] = () => (fail ? Promise.reject({ status: 503, parts: null }) : Promise.resolve({ data: REAL_REPLY }))
    const w = await show()
    await exitLeg(w, 0)
    const orders = w.findComponent(PaperConfirmDialog).props('orders')
    fail = true
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    w.findComponent(PaperConfirmDialog).vm.$emit('confirm', orders)
    await flushPromises()
    expect(posts()).toHaveLength(0)
    expect(err(w)).toContain('22300')
    expect(err(w)).toContain(NOT_LIVE)
  })
  it('after the page heals the Exit button is enabled again with the ticks kept, and a button with nothing ticked says why', async () => {
    let fail = false
    answers['GET /tracking'] = () => (fail ? Promise.reject({ status: 503, parts: null }) : Promise.resolve({ data: REAL_REPLY }))
    const w = await show()
    expect(t(w, 'paper-exit-reason').text()).toBe('Tick a leg to exit.')
    await exitLeg(w, 0)
    fail = true
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    fail = false
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    await t(w, 'paper-cancel').trigger('click')
    expect(t(w, 'exit-selected-48').attributes('disabled')).toBeUndefined()
    expect(t(w, 'exit-selected-48').text()).toBe('Exit (1)')
  })
  it('settle: a group that becomes unreadable closes the dialog and leaves a note naming the leg', async () => {
    let reply = REAL_REPLY
    answers['GET /tracking'] = () => Promise.resolve({ data: reply })
    const w = await show()
    await exitLeg(w, 0)
    reply = list(item({ state: 'WEIRD' }))
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    expect(has(w, 'paper-confirm')).toBe(false)
    expect(t(w, 'paper-exit-link-note').text()).toContain('22300')
    expect(t(w, 'paper-exit-link-note').text()).toContain('This trade changed elsewhere. Reload to see the current legs.')
  })
  it('a 409 refusal shows all four parts and the leg', async () => {
    answers['GET /tracking'] = ok(REAL_REPLY)
    answers['POST /paper/strategies/48/orders'] = () => Promise.reject({ status: 409, parts: FOUR })
    const w = await show()
    await exitLeg(w, 0)
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    for (const p of Object.values(FOUR)) expect(err(w)).toContain(p)
    expect(err(w)).toContain('22300')
  })
  it.each([[{ status: 429, parts: null }], [{ superseded: true }], [{ status: 408, parts: null }]])('%j: outcome unknown, Orderbook link, Confirm not re-armed', async (rejection) => {
    answers['GET /tracking'] = ok(REAL_REPLY)
    answers['POST /paper/strategies/48/orders'] = () => Promise.reject(rejection)
    const w = await show()
    await exitLeg(w, 0)
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(has(w, 'paper-unknown')).toBe(true)
    expect(has(w, 'paper-open-orderbook')).toBe(true)
    expect(confirmOff(w)).toBe(true)
    expect(posts()).toHaveLength(1)
  })
  it('a refused Confirm with the rows unchanged unlocks after the next good read', async () => {
    answers['GET /tracking'] = ok(REAL_REPLY)
    answers['POST /paper/strategies/48/orders'] = () => Promise.reject({ status: 409, parts: FOUR })
    const w = await show()
    await exitLeg(w, 0)
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(confirmOff(w)).toBe(true)
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    expect(confirmOff(w)).toBe(false)
    expect(err(w)).toContain('22300')
  })
})

describe('PaperStrategies: an UNKNOWN outcome keeps that strategy\'s exit unresolved until a good re-read decides (Lane U round 1, ADR-016/017/019)', () => {
  const posts = () => calls.filter((c) => c[0] === 'POST')
  const confirmOff = (w) => t(w, 'paper-confirm-button').attributes('disabled') !== undefined
  const note = (w) => (has(w, 'paper-exit-link-note') ? t(w, 'paper-exit-link-note').text() : '')
  const NOT_STORED = 'The exit was not stored. You can try again.'
  const out0 = list(item({ legs: [leg(0, { exit_price: '120.00', exited_at: '2026-10-28T09:00:00Z', price_state: 'exited', current_price: null }), leg(1), leg(2), leg(3)] }))
  const hang = () => new Promise(() => {})
  it('A4: 503, hold passes, Cancel, Exit again: ONE post, Confirm never on, the unknown sentence is shown again (no good re-read yet)', async () => {
    let n = 0
    answers['GET /tracking'] = () => (n++ === 0 ? Promise.resolve({ data: REAL_REPLY }) : hang())
    answers['POST /paper/strategies/48/orders'] = () => Promise.reject({ status: 503, parts: null })
    const w = await show()
    await exitLeg(w, 0)
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(has(w, 'paper-unknown')).toBe(true)
    expect(confirmOff(w)).toBe(true)
    await vi.advanceTimersByTimeAsync(PAPER_UNKNOWN_HOLD_MS + 2 * TRACKING_REFRESH_MS)
    expect(has(w, 'paper-unknown')).toBe(true)
    expect(confirmOff(w)).toBe(true)
    await t(w, 'paper-confirm-button').trigger('click')
    await t(w, 'paper-cancel').trigger('click')
    await flushPromises()
    await exitLeg(w, 0)
    expect(has(w, 'paper-confirm')).toBe(true)
    expect(has(w, 'paper-unknown')).toBe(true)
    expect(confirmOff(w)).toBe(true)
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(posts()).toHaveLength(1)
  })
  it('a good re-read after the reply that shows the exit stored: the done note, the dialog is gone, no "changed elsewhere"', async () => {
    let reply = REAL_REPLY
    answers['GET /tracking'] = () => Promise.resolve({ data: reply })
    answers['POST /paper/strategies/48/orders'] = () => Promise.reject({ status: 503, parts: null })
    const w = await show()
    await exitLeg(w, 0)
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    reply = out0
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    expect(has(w, 'paper-confirm')).toBe(false)
    expect(note(w)).toContain('Exit placed on paper')
    expect(note(w)).toContain('22300')
    expect(note(w)).not.toMatch(/elsewhere|changed/i)
    expect(posts()).toHaveLength(1)
  })
  it('a good re-read after the reply that shows the legs unchanged: "not stored" sentence, then Confirm is on and a click posts again', async () => {
    answers['GET /tracking'] = ok(REAL_REPLY)
    answers['POST /paper/strategies/48/orders'] = () => Promise.reject({ status: 503, parts: null })
    const w = await show()
    await exitLeg(w, 0)
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(confirmOff(w)).toBe(true)
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    expect(has(w, 'paper-unknown')).toBe(false)
    expect(t(w, 'paper-error').text()).toContain(NOT_STORED)
    expect(confirmOff(w)).toBe(false)
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(posts()).toHaveLength(2)
  })
  it('a read that started BEFORE the reply cannot clear the unresolved state (it may predate the exit)', async () => {
    let n = 0
    let release
    answers['GET /tracking'] = () => (n++ === 1 ? new Promise((r) => { release = () => r({ data: REAL_REPLY }) }) : Promise.resolve({ data: REAL_REPLY }))
    answers['POST /paper/strategies/48/orders'] = () => Promise.reject({ status: 503, parts: null })
    const w = await show()
    await exitLeg(w, 0)
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS) // read #2 starts and hangs
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    release() // the old read lands after the reply, legs unchanged
    await flushPromises()
    expect(has(w, 'paper-unknown')).toBe(true)
    expect(confirmOff(w)).toBe(true)
  })
  it('A3: a re-read that shows the exit stored lands while the POST is in flight, then 503: not "changed elsewhere"; the next good read says done', async () => {
    let reply = REAL_REPLY
    answers['GET /tracking'] = () => Promise.resolve({ data: reply })
    let fail
    answers['POST /paper/strategies/48/orders'] = () => new Promise((_, rej) => { fail = () => rej({ status: 503, parts: null }) })
    const w = await show()
    await exitLeg(w, 0)
    await t(w, 'paper-confirm-button').trigger('click')
    reply = out0
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    expect(has(w, 'paper-confirm')).toBe(true)
    expect(note(w)).not.toMatch(/elsewhere|changed/i)
    fail()
    await flushPromises()
    expect(has(w, 'paper-unknown')).toBe(true)
    expect(confirmOff(w)).toBe(true)
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    expect(note(w)).toContain('Exit placed on paper')
    expect(note(w)).not.toMatch(/elsewhere|changed/i)
    expect(posts()).toHaveLength(1)
  })
  it('A3: the same re-read, then 201: the done note, never "changed elsewhere"', async () => {
    let reply = REAL_REPLY
    answers['GET /tracking'] = () => Promise.resolve({ data: reply })
    let done
    answers['POST /paper/strategies/48/orders'] = () => new Promise((r) => { done = () => r({ data: { strategy_id: 48, orders: [{ id: 901 }] } }) })
    const w = await show()
    await exitLeg(w, 0)
    await t(w, 'paper-confirm-button').trigger('click')
    reply = out0
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    done()
    await flushPromises()
    expect(note(w)).toContain('Exit placed on paper')
    expect(note(w)).not.toMatch(/elsewhere|changed/i)
  })
})

describe('PaperStrategies: the answer of Confirm always lands, and Confirm waits for the risk check (hotfix 27 Nov, T1-02 refined)', () => {
  const posts = () => calls.filter((c) => c[0] === 'POST')
  const note = (w) => t(w, 'paper-exit-link-note').text()
  it('201 while the next list read fails: "done" shows with the leg and the order number; the next good read drops the row', async () => {
    let reply = REAL_REPLY
    let fail = false
    answers['GET /tracking'] = () => (fail ? Promise.reject({ status: 503, parts: null }) : Promise.resolve({ data: reply }))
    answers['POST /paper/strategies/48/orders'] = ok({ strategy_id: 48, orders: [{ id: 901 }, { id: 902 }] })
    const w = await show()
    await exitLeg(w, 0)
    fail = true
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(posts()).toHaveLength(1)
    expect(has(w, 'paper-confirm')).toBe(false)
    expect(note(w)).toContain('22300')
    expect(note(w)).toContain('Exit placed on paper')
    expect(note(w)).toContain('902')
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS) // still failing: the done line stays
    expect(note(w)).toContain('Exit placed on paper')
    fail = false
    const out = (i) => leg(i, { exit_price: '120.00', exited_at: '2026-10-28T09:00:00Z', price_state: 'exited', current_price: null })
    reply = list(item({ legs: [out(0), leg(1), leg(2), leg(3)] }))
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    expect(has(w, 'select-leg-48-1')).toBe(false)
    expect(note(w)).toContain('Exit placed on paper')
  })
  it('201 with no order number in the reply still says done', async () => {
    answers['GET /tracking'] = ok(REAL_REPLY)
    answers['POST /paper/strategies/48/orders'] = ok({})
    const w = await show()
    await exitLeg(w, 0)
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(note(w)).toContain('22300')
    expect(note(w)).toContain('Exit placed on paper')
  })
  it('Confirm is disabled while the risk check runs, with its line shown, and enables when it answers', async () => {
    answers['GET /tracking'] = ok(REAL_REPLY)
    let answer
    answers['GET /paper/strategies/48/exit-risk'] = () => new Promise((r) => { answer = r })
    const w = await show()
    await exitLeg(w, 0)
    expect(t(w, 'paper-exit-checking').exists()).toBe(true)
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeDefined()
    await t(w, 'paper-confirm-button').trigger('click')
    expect(posts()).toHaveLength(0)
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS * 2) // slower than the quote window
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeDefined()
    answer({ data: { state: 'no' } })
    await flushPromises()
    expect(has(w, 'paper-exit-checking')).toBe(false)
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeUndefined()
  })
})

describe('lib/tracking readers', () => {
  it('readTracking reads EXITED with booked and unbooked', () => {
    const v = readTracking({ state: 'EXITED', paper_pnl: '55.00', paper_pnl_text: '+55.00', booked: '55.00', booked_text: '+55.00', unbooked: '0.00', unbooked_text: '0.00', legs: [], detections: [] })
    expect(v.kind).toBe('exited')
    expect(v.text).toBe('Paper P&L (not real): +55.00 (before charges) - exited')
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
