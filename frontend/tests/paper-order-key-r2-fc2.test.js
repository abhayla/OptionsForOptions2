// Lane FC2 (R2, 28 Nov) order path: every exit request the paper list sends carries `client_request_id` (Lane FD2's routes: a repeat of
// the same key places nothing). One key per user action; the SAME key on a resend of that action (an exit whose outcome was unknown and is
// sent again with the same orders); a new key for any other action (the order was stored, the server refused it, or the orders changed).
// Spec basis: ADR-016..019 (no blind second order), ADR-330 (49).
// Lane FJ (R3, item 1d): moved to the ONE key rule: the key is the dialog's (a UUID made at each Confirm press); lib/unknownLocks.js orderKeyFor keeps it for the same orders
// while their record is open. The older FC2 helpers (newRequestKey, withRequestKey, useRequestKeys) are gone.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import REAL from './fixtures/paper-strategies.json'
import { dropOrderKey, orderKeyFor, resetExitLocks } from '@/lib/unknownLocks'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    const a = answers[`${method} ${url}`]
    if (a === undefined && method === 'GET' && url === '/market/exit-state') return Promise.resolve({ data: { closed: false, sentence: null, next_open_at: null } })
    if (a === undefined) return Promise.reject({ message: 'no answer', parts: null, status: null })
    return typeof a === 'function' ? a(body) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u, b) => respond('POST', u, b), delete: (u) => respond('DELETE', u) } }
})
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'
import { resetActiveAlerts } from '@/lib/paperAlerts'

const URL = '/paper/strategies/1/orders'
const clone = () => JSON.parse(JSON.stringify(REAL))
const posts = () => calls.filter((c) => c.method === 'POST' && c.url === URL)
const keys = () => posts().map((c) => c.body.client_request_id)
const mounted = []
async function show() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: PaperStrategies }, { path: '/strategy/builder', component: { template: '<div/>' } }] })
  router.push('/')
  await router.isReady()
  const w = mount(PaperStrategies, { global: { plugins: [router] }, attachTo: document.body })
  mounted.push(w)
  await flushPromises()
  return w
}
const btn = (w, id) => w.get(`[data-testid="${id}"]`)
async function exitLeg(w) {
  const box = btn(w, 'select-leg-1-776')
  if (!box.element.checked) await box.setValue(true)
  await btn(w, 'exit-selected-1').trigger('click')
  await flushPromises()
  await btn(w, 'paper-confirm-button').trigger('click')
  await flushPromises()
}
const REFUSED = () => Promise.reject({ message: 'x', status: 422, parts: { what_happened: 'Enter a price in steps of 0.05.', impact: 'i', what_is_blocked: 'b', next_action: 'n' } })
const UNKNOWN = () => Promise.reject({ message: 'x', status: 503, parts: null })

beforeEach(() => { resetExitLocks(); calls.length = 0; resetActiveAlerts(); vi.useFakeTimers(); answers = { 'GET /paper/strategies': () => Promise.resolve({ data: clone() }) } })
afterEach(() => { mounted.splice(0).forEach((w) => { try { w.unmount() } catch { /* gone */ } }); vi.useRealTimers(); document.body.innerHTML = '' })

describe('the exit request carries client_request_id', () => {
  it('one exit: the body has the key and the orders as before', async () => {
    answers[`POST ${URL}`] = () => Promise.resolve({ data: { orders: [{ id: 9 }] } })
    const w = await show()
    await exitLeg(w)
    expect(posts()).toHaveLength(1)
    expect(posts()[0].body.client_request_id).toMatch(/\S{8,}/)
    expect(Array.isArray(posts()[0].body.orders)).toBe(true)
  })
  it('a REFUSED exit is a definite answer: the next attempt is a new action with a new key', async () => {
    answers[`POST ${URL}`] = REFUSED
    const w = await show()
    await exitLeg(w)
    await exitLeg(w)
    expect(posts()).toHaveLength(2)
    expect(keys()[0]).not.toBe(keys()[1])
  })
  it('a STORED exit ends the action: the next exit of the same leg gets a new key', async () => {
    answers[`POST ${URL}`] = () => Promise.resolve({ data: { orders: [{ id: 9 }] } })
    const w = await show()
    await exitLeg(w)
    await exitLeg(w)
    expect(posts()).toHaveLength(2)
    expect(keys()[0]).not.toBe(keys()[1])
  })
  it('an exit whose outcome was UNKNOWN, sent again with the same orders after a re-read shows nothing stored: the SAME key', async () => {
    answers[`POST ${URL}`] = UNKNOWN
    const w = await show()
    await exitLeg(w)
    expect(posts()).toHaveLength(1)
    await vi.advanceTimersByTimeAsync(140000) // the list re-reads every 5 s; the first read SENT more than 130 s after the client gave up shows the legs unchanged: not stored, Confirm may be on again
    await flushPromises()
    await exitLeg(w)
    expect(posts()).toHaveLength(2)
    expect(keys()[0]).toMatch(/\S{8,}/)
    expect(keys()[1]).toBe(keys()[0])
  })
})

describe('key rules (Opus review F1, F2, F5), on the one rule', () => {
  it('the same orders get the held key while their record is open; other orders, or a decided action, get the dialog\'s new key', () => {
    const a = orderKeyFor(1, 'A', 'k1')
    expect(a).toBe('k1')
    expect(orderKeyFor(1, 'A', 'k2')).toBe('k1') // record still open (no definite answer yet): the same key
    expect(orderKeyFor(1, 'B', 'k3')).toBe('k3') // other orders: a new action, the dialog's key
    dropOrderKey(1) // a definite answer (stored or refused)
    expect(orderKeyFor(1, 'B', 'k4')).toBe('k4')
  })
  it('F2: the key survives the screen being mounted again (it is kept in the browser, not in the page)', () => {
    expect(orderKeyFor(7, 'A', 'k1')).toBe('k1')
    expect(orderKeyFor(7, 'A', 'k9')).toBe('k1')
  })
  it('F1: an unknown outcome that a re-read settled as placed does not lend its key to the next, identical exit', async () => {
    let n = 0
    answers[`POST ${URL}`] = () => (++n === 1 ? UNKNOWN() : Promise.resolve({ data: { orders: [{ id: 9 }] } }))
    const w = await show()
    await exitLeg(w)
    const d = clone()
    d.strategies.find((x) => x.strategy_id === 1).positions.find((p) => p.contract_id === 776).net_quantity = 0 // the re-read shows the leg gone: stored
    answers['GET /paper/strategies'] = () => Promise.resolve({ data: d })
    await vi.advanceTimersByTimeAsync(6000)
    await flushPromises()
    answers['GET /paper/strategies'] = () => Promise.resolve({ data: clone() }) // the leg is back (a later position), the same exit again
    await vi.advanceTimersByTimeAsync(6000)
    await flushPromises()
    await exitLeg(w)
    expect(posts()).toHaveLength(2)
    expect(keys()[1]).not.toBe(keys()[0])
  })
})
