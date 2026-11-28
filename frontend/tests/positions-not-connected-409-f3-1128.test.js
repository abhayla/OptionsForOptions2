// Lane F3 I-207 (TG D-TG-3, screenshot c-sw2-positions-real.jpg): Positions with no broker session printed the raw 409 JSON
// `{ "error_class": "BROKER_AUTHENTICATION", ...}` twice. Now: ONE plain sentence, never the JSON, and a Retry.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url) => {
    const a = answers[`${method} ${url}`]
    const v = typeof a === 'function' ? a() : a
    return v ?? Promise.reject({ message: 'no answer', parts: null, status: null })
  }
  return { ...actual, default: { get: reply('GET'), post: reply('POST') } }
})
import PositionsPage from '@/pages/PositionsPage.vue'

const ok = (data) => () => Promise.resolve({ data })
const JSON_TEXT = '{ "error_class": "BROKER_AUTHENTICATION", "code": "BROKER_AUTHENTICATION_101" }'
const LINE = 'No broker is connected, so no real positions are shown.'
const mounted = []
async function page() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/p', component: PositionsPage, meta: { title: 'T', parent: 'Positions', view: 'current' } }] })
  router.push('/p'); await router.isReady()
  const w = mount(PositionsPage, { attachTo: document.body, global: { plugins: [router] } })
  await flushPromises(); mounted.push(w); return w
}
const count = (s, sub) => s.split(sub).length - 1
beforeEach(() => { answers = { 'GET /paper/strategies': ok({ strategies: [], totals: null, answered_at: null }), 'GET /features': ok({ order_path: 'on' }), 'GET /broker/status': ok({ account_connection: { state: 'disconnected' } }) } })
afterEach(() => { mounted.splice(0).forEach((w) => w.unmount()) })

describe('I-207 no broker session, 409 answer', () => {
  it('a refusal whose message is the raw JSON: one plain sentence, no error_class text, a Retry', async () => {
    const parts = { what_happened: JSON_TEXT, impact: JSON_TEXT, what_is_blocked: JSON_TEXT, next_action: JSON_TEXT }
    answers['GET /positions'] = () => Promise.reject({ status: 409, parts })
    const w = await page()
    const text = w.get('[data-testid="real-state"]').text() + w.get('[data-testid="positions-totals"]').text()
    expect(w.text()).not.toContain('error_class')
    expect(w.text()).not.toContain('BROKER_AUTHENTICATION')
    expect(count(w.text(), LINE)).toBe(1)
    expect(text).toContain(LINE)
    expect(w.find('[data-testid="positions-error-retry"]').exists()).toBe(true)
    expect(w.get('[data-testid="real-state"]').attributes('data-state')).toBe('not_connected')
  })
  it('a refusal with no readable message at all: the same one sentence', async () => {
    answers['GET /positions'] = () => Promise.reject({ status: 409, parts: null })
    const w = await page()
    expect(count(w.text(), LINE)).toBe(1)
    expect(w.find('[data-testid="positions-error-retry"]').exists()).toBe(true)
  })
  it('the server\'s own clean four-part message is kept (REQ-065) with a Retry, once', async () => {
    const parts = { what_happened: 'Connect your Zerodha account to continue.', impact: 'i', what_is_blocked: 'b', next_action: 'n' }
    answers['GET /positions'] = () => Promise.reject({ status: 409, parts })
    const w = await page()
    expect(count(w.text(), 'Connect your Zerodha account to continue.')).toBe(1)
    expect(w.find('[data-testid="positions-error-next"]').exists()).toBe(true)
    expect(w.find('[data-testid="positions-error-retry"]').exists()).toBe(true)
  })
  it('Retry reads again and a connected answer replaces the sentence', async () => {
    let n = 0
    answers['GET /positions'] = () => (++n === 1 ? Promise.reject({ status: 409, parts: null }) : Promise.resolve({ data: { read_at: '2026-11-28T03:34:07+05:30', real_pnl: null, strategies: [], has_outside: false, outside_lots: 0, blocked: false, blocked_strategy_ids: [], broker_connected: true } }))
    const w = await page()
    await w.get('[data-testid="positions-error-retry"]').trigger('click'); await flushPromises()
    expect(w.text()).not.toContain(LINE)
    expect(n).toBe(2)
  })
})
