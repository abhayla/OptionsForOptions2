// Lane FJ2 item 3 (28 Nov 2026). Real case: Lane TG, c-sw2-positions-real.jpg: Positions with no broker session printed the raw 409 body
// { "error_class": "BROKER_AUTHENTICATION", "code": "BROKER_AUTHENTICATION_102", ... } twice in the Real P&L card.
// Wanted: one plain "not connected" sentence; never the JSON.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import REAL0 from './fixtures/paper-strategies.json'

const BODY = { error_class: 'BROKER_AUTHENTICATION', code: 'BROKER_AUTHENTICATION_102', what_happened: "Connect your Zerodha account to continue. We'll use your Zerodha account to verify availability, check margin and prepare/execute your strategy.", impact: 'Orders cannot be sent to Zerodha.', what_is_blocked: 'Execution of this strategy.', next_action: 'Connect your Zerodha account from the account page.', external_text: null }
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url) => {
    const a = answers[`${method} ${url}`]
    return a ? a() : Promise.reject(actual.mapError({ response: { status: 404, data: {} } }))
  }
  return { ...actual, default: { get: reply('GET'), post: reply('POST') } }
})
import { mapError } from '@/services/api'
import PositionsPage from '@/pages/PositionsPage.vue'

const ok = (data) => () => Promise.resolve({ data })
async function page() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/p', component: PositionsPage, meta: { title: 'T', parent: 'Positions', view: 'current' } }, { path: '/positions/current-positions', component: { template: '<div/>' } }, { path: '/strategy/builder', component: { template: '<div/>' } }] })
  router.push('/p?tab=real')
  await router.isReady()
  const w = mount(PositionsPage, { attachTo: document.body, global: { plugins: [router] } })
  await flushPromises()
  return w
}
beforeEach(() => { answers = {}; vi.useFakeTimers() })
afterEach(() => { vi.useRealTimers(); document.body.innerHTML = '' })

describe('FJ2-3 no broker session: never the raw JSON', () => {
  it('409 body with the catalogue parts plus error_class / code / external_text', async () => {
    answers['GET /positions'] = () => Promise.reject(mapError({ response: { status: 409, data: BODY } }))
    answers['GET /broker/status'] = ok({ connected: false })
    answers['GET /paper/strategies'] = ok(REAL0)
    answers['GET /features'] = ok({ order_path: 'on' })
    const w = await page()
    const text = w.text()
    expect(text).not.toContain('error_class')
    expect(text).not.toContain('BROKER_AUTHENTICATION')
    expect(text).not.toContain('{')
    expect(text.split(BODY.what_happened).length - 1).toBe(1) // the refusal's own message once (section), not again in the totals card
  })
  it('the server puts the stringified 409 into real_pnl.reason / caption (a 200): a plain sentence, once', async () => {
    const json = JSON.stringify(BODY, null, 1)
    answers['GET /positions'] = ok({ read_at: '2026-11-27T10:00:00+05:30', real_pnl: { value: null, pnl_text: null, state: 'not_connected', reason: json, source: 'Zerodha', read_at: '2026-11-27T10:00:00+05:30', caption: json, excludes_note: null }, pnl_text: null, strategies: [], has_outside: false, outside_lots: 0, blocked: false, blocked_strategy_ids: [], broker_connected: false })
    answers['GET /paper/strategies'] = ok(REAL0)
    answers['GET /features'] = ok({ order_path: 'on' })
    const w = await page()
    expect(w.text()).not.toContain('error_class')
    expect(w.text()).not.toContain('{')
    expect(w.text().split('No broker is connected, so no real positions are shown.').length - 1).toBe(1)
  })
})
