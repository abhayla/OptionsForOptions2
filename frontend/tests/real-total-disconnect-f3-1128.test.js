// Lane F3 (28 Nov 2026) I-113 / TC walk AF-07 D-13: on an open Positions page the Real total kept its old figure 70 s after
// Zerodha disconnected. Fail closed: a read that says no broker is connected, or a last good read older than the 90 s rule,
// never leaves the old figure on the page. AF-07 itself stays PC ONLY.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url) => {
    calls.push(`${method} ${url}`)
    const a = answers[`${method} ${url}`]
    const v = typeof a === 'function' ? a() : a
    return v ?? Promise.reject({ message: 'no answer', parts: null, status: null })
  }
  return { ...actual, default: { get: reply('GET'), post: reply('POST') } }
})
import PositionsPage from '@/pages/PositionsPage.vue'

const REAL_PNL = { value: '650.00', pnl_text: '+650.00', state: 'stated', reason: null, source: 'Zerodha', read_at: '2026-11-28T03:34:07+05:30', caption: 'Zerodha, as at 03:34:07 IST', excludes_note: null }
const BODY = { read_at: '2026-11-28T03:34:07+05:30', real_pnl: REAL_PNL, pnl_text: '+650.00', strategies: [], has_outside: true, outside_lots: 1, blocked: false, blocked_strategy_ids: [], broker_connected: true }
// the server's disconnected answer, with a stale figure still riding in it (the worst shape)
const DISCONNECTED = { ...BODY, broker_connected: false }
const ok = (data) => () => Promise.resolve({ data })
const t = (w, id) => w.get(`[data-testid="${id}"]`)
const mounted = []
async function page() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/p', component: PositionsPage, meta: { title: 'T', parent: 'Positions', view: 'current' } }] })
  router.push('/p')
  await router.isReady()
  const w = mount(PositionsPage, { attachTo: document.body, global: { plugins: [router] } })
  await flushPromises()
  mounted.push(w)
  return w
}
const tick = async (ms) => { await vi.advanceTimersByTimeAsync(ms); await flushPromises() }
beforeEach(() => { calls.length = 0; answers = { 'GET /paper/strategies': ok({ strategies: [], totals: null, answered_at: null }), 'GET /features': ok({ order_path: 'on' }) }; vi.useFakeTimers() })
afterEach(() => { mounted.splice(0).forEach((w) => { try { w.unmount() } catch { /* left */ } }); vi.useRealTimers() })

describe('I-113 Real total after the broker disconnects', () => {
  it('a 200 read that says no broker is connected hides the old figure within one re-read (70 s case)', async () => {
    let n = 0
    answers['GET /positions'] = () => Promise.resolve({ data: ++n === 1 ? BODY : DISCONNECTED })
    const w = await page()
    expect(t(w, 'totals-real').text()).toBe('+650.00')
    await tick(70_000)
    expect(w.text()).not.toContain('+650.00')
    expect(t(w, 'real-state').attributes('data-state')).toBe('not_connected')
  })
  it('a re-read that hangs hides the figure with the old-figure sentence once the last good read is older than 90 s', async () => {
    let n = 0
    answers['GET /positions'] = () => (++n === 1 ? Promise.resolve({ data: BODY }) : new Promise(() => {}))
    const w = await page()
    await tick(70_000)
    expect(t(w, 'totals-real').text()).toBe('+650.00')
    await tick(30_000)
    expect(w.text()).not.toContain('+650.00')
    expect(w.text()).toContain('more than 90 seconds old')
  })
})
