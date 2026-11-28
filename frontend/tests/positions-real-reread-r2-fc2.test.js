// Lane FC2 (R2, 28 Nov) D-13: Positions re-reads the Real part on a timer and on connection loss; the figure goes when the read
// says not connected or when it is older than the server's 90 s stale rule; no timer once the page is left.
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
const BODY = { read_at: '2026-11-28T03:34:07+05:30', real_pnl: REAL_PNL, pnl_text: '+650.00', strategies: [], has_outside: true, outside_lots: 1, blocked: false, blocked_strategy_ids: [] }
const ok = (data) => () => Promise.resolve({ data })
const NOT_CONNECTED = 'Connect your Zerodha account to continue.'
const refused = () => Promise.reject({ status: 409, parts: { what_happened: NOT_CONNECTED, impact: 'i', what_is_blocked: 'b', next_action: 'n' } })
const t = (w, id) => w.get(`[data-testid="${id}"]`)
const mounted = []
const reads = () => calls.filter((c) => c === 'GET /positions').length

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
afterEach(() => { mounted.splice(0).forEach((w) => { try { w.unmount() } catch { /* already left */ } }); vi.useRealTimers() })

describe('D-13 Positions Real part stays fresh', () => {
  it('the session goes away: within the next re-read the figure is a dash and the reason is the not-connected message', async () => {
    let n = 0
    answers['GET /positions'] = () => (++n === 1 ? Promise.resolve({ data: BODY }) : refused())
    answers['GET /broker/status'] = ok({ account_connection: { state: 'disconnected' } })
    const w = await page()
    expect(t(w, 'totals-real').text()).toBe('+650.00')
    await tick(70_000)
    expect(t(w, 'totals-real').text()).not.toBe('+650.00')
    expect(t(w, 'real-state').attributes('data-state')).toBe('not_connected')
    expect(w.text()).toContain(NOT_CONNECTED)
  })
  it('a re-read that hangs: the figure is hidden once it is older than 90 s', async () => {
    let n = 0
    answers['GET /positions'] = () => (++n === 1 ? Promise.resolve({ data: BODY }) : new Promise(() => {}))
    const w = await page()
    await tick(60_000)
    expect(t(w, 'totals-real').text()).toBe('+650.00')
    await tick(40_000)
    expect(t(w, 'totals-real').text()).not.toBe('+650.00')
  })
  it('a good re-read replaces the figure', async () => {
    let n = 0
    answers['GET /positions'] = () => Promise.resolve({ data: ++n === 1 ? BODY : { ...BODY, real_pnl: { ...REAL_PNL, pnl_text: '+700.00' } } })
    const w = await page()
    await tick(35_000)
    expect(t(w, 'totals-real').text()).toBe('+700.00')
  })
  it('connection loss triggers a re-read at once', async () => {
    answers['GET /positions'] = ok(BODY)
    await page()
    const before = reads()
    window.dispatchEvent(new Event('offline'))
    await flushPromises()
    expect(reads()).toBe(before + 1)
  })
  it('no timer once the page is left', async () => {
    answers['GET /positions'] = ok(BODY)
    const w = await page()
    w.unmount()
    const before = reads()
    await tick(300_000)
    window.dispatchEvent(new Event('offline'))
    await flushPromises()
    expect(reads()).toBe(before)
  })
})
