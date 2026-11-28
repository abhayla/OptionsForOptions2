// Lane FC2 (R2, 28 Nov) order path: every exit request the paper list sends carries `client_request_id` (Lane FD2's routes: a repeat of
// the same key places nothing). One key per user action; the SAME key on a resend of that action (an exit whose outcome was unknown and is
// sent again with the same orders); a new key for any other action (the order was stored, the server refused it, or the orders changed).
// Spec basis: ADR-016..019 (no blind second order), ADR-330 (49).
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import REAL from './fixtures/paper-strategies.json'
import { newRequestKey, withRequestKey } from '@/lib/requestKey'

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

beforeEach(() => { calls.length = 0; resetActiveAlerts(); vi.useFakeTimers(); answers = { 'GET /paper/strategies': () => Promise.resolve({ data: clone() }) } })
afterEach(() => { mounted.splice(0).forEach((w) => { try { w.unmount() } catch { /* gone */ } }); vi.useRealTimers(); document.body.innerHTML = '' })

describe('requestKey', () => {
  it('keys differ per call; withRequestKey adds the key to a POST body and leaves other calls alone', async () => {
    expect(newRequestKey()).not.toBe(newRequestKey())
    expect(typeof newRequestKey()).toBe('string')
    const seen = []
    const client = { get: (u) => Promise.resolve(u), post: (u, b, c) => { seen.push([u, b, c]); return Promise.resolve({ data: 1 }) } }
    const k = withRequestKey(client, 'abc')
    await k.post('/x', { orders: [] }, { timeout: 5 })
    expect(seen[0]).toEqual(['/x', { orders: [], client_request_id: 'abc' }, { timeout: 5 }])
    expect(await k.get('/y')).toBe('/y')
  })
})

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
    await vi.advanceTimersByTimeAsync(6000) // the list re-reads (5 s); the legs are unchanged: the exit was not stored, Confirm may be on again
    await flushPromises()
    await exitLeg(w)
    expect(posts()).toHaveLength(2)
    expect(keys()[0]).toMatch(/\S{8,}/)
    expect(keys()[1]).toBe(keys()[0])
  })
})
