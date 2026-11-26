// GC-TP step 7b (REQ-109 AC-8; ADR-207 (5)), changed by ADR-330 (4): the header bell and the Alerts > Active list come from
// GET /alerts/active, text as the server sent it; opening the page writes nothing (no POST /paper/alerts/read).
// The bell is "unanswered actionable alerts", not "unread paper stops".
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

import AppHeader from '@/components/layout/AppHeader.vue'
import AlertsPage from '@/pages/AlertsPage.vue'
import { resetActiveAlerts } from '@/lib/paperAlerts'
import { TRACKING_REFRESH_MS } from '@/lib/tracking'

const alert = (id, over = {}) => ({ id, strategy_id: 48, strategy_name: null, kind: 'plan_loss_stop', text: `Loss stop reached (${id})`,
  fired_at: '2026-10-29T05:00:00Z', fired_line: 'Fired at 10:30', no_longer_true_since: null, no_longer_true_since_hm: null, answers: [{ code: 'continue', label: 'Continue with the position' }], ...over })
const TWO = { count: 2, alerts: [alert(2, { fired_line: 'Fired at 12:00' }), alert(1)] }
const ok = (data) => () => Promise.resolve({ data })
const fail = (parts, status = 500) => () => Promise.reject({ message: 'x', status, parts })
const t = (w, id) => w.get(`[data-testid="${id}"]`)
const has = (w, id) => w.find(`[data-testid="${id}"]`).exists()
const count = (m, u) => calls.filter((c) => c[0] === m && c[1] === u).length

async function router(path = '/') {
  const r = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/', component: { template: '<div/>' } },
    { path: '/alerts/active', meta: { title: 'Active' }, component: AlertsPage },
    { path: '/alerts/history', meta: { title: 'History' }, component: AlertsPage },
    { path: '/alerts/notification-settings', meta: { title: 'Notification settings' }, component: AlertsPage },
  ] })
  r.push(path)
  await r.isReady()
  return r
}
async function header() {
  const w = mount(AppHeader, { global: { plugins: [await router()] } })
  await flushPromises()
  return w
}
async function page(path = '/alerts/active') {
  const w = mount(AlertsPage, { global: { plugins: [await router(path)] } })
  await flushPromises()
  return w
}

beforeEach(() => { calls.length = 0; answers = {}; resetActiveAlerts(); vi.useFakeTimers() })
afterEach(() => vi.useRealTimers())

describe('header bell', () => {
  it('shows the count from GET /alerts/active', async () => {
    answers['GET /alerts/active'] = ok(TWO)
    const w = await header()
    expect(t(w, 'alerts-bell-count').text()).toBe('2')
  })
  it('is hidden at 0, and when the read fails or is unreadable', async () => {
    answers['GET /alerts/active'] = ok({ alerts: [], count: 0 })
    expect(has(await header(), 'alerts-bell-count')).toBe(false)
    resetActiveAlerts()
    answers['GET /alerts/active'] = fail(null)
    expect(has(await header(), 'alerts-bell-count')).toBe(false)
    resetActiveAlerts()
    answers['GET /alerts/active'] = ok({ nope: 1 })
    expect(has(await header(), 'alerts-bell-count')).toBe(false)
  })
  it('re-reads on the existing paper refresh tick and drops a stale count when the read then fails', async () => {
    answers['GET /alerts/active'] = ok(TWO)
    const w = await header()
    answers['GET /alerts/active'] = ok({ alerts: [], count: 3 })
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    expect(t(w, 'alerts-bell-count').text()).toBe('3')
    answers['GET /alerts/active'] = fail(null)
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    expect(has(w, 'alerts-bell-count')).toBe(false)
  })
  it('never reads /paper/alerts (an unread paper stop is not counted)', async () => {
    answers['GET /alerts/active'] = ok({ alerts: [], count: 0 })
    answers['GET /paper/alerts'] = ok({ alerts: [], unread: 5 })
    await header()
    expect(count('GET', '/paper/alerts')).toBe(0)
  })
})

describe('Alerts page', () => {
  it('lists both rows in the server order as sent, with Fired at HH:MM, and posts nothing', async () => {
    answers['GET /alerts/active'] = ok(TWO)
    const w = await page()
    const rows = w.findAll('[data-testid="alert-row"]')
    expect(rows).toHaveLength(2)
    expect(rows[0].get('[data-testid="alert-fired"]').text()).toBe('Fired at 12:00')
    expect(rows[0].get('[data-testid="alert-strategy"]').text()).toBe('Strategy 48')
    expect(rows[0].get('[data-testid="alert-text"]').text()).toBe('Loss stop reached (2)')
    expect(rows[1].get('[data-testid="alert-text"]').text()).toBe('Loss stop reached (1)')
    expect(has(w, 'alerts-empty')).toBe(false)
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS * 2)
    expect(calls.filter((c) => c[0] === 'POST')).toEqual([])
  })
  it('empty: keeps the existing empty line and writes nothing', async () => {
    answers['GET /alerts/active'] = ok({ alerts: [], count: 0 })
    const w = await page()
    expect(t(w, 'alerts-empty').text()).toBe('No alerts yet. Alerts start when strategy monitoring rules are added.')
    expect(calls.filter((c) => c[0] === 'POST')).toEqual([])
  })
  it('a refused read shows the server reason and no rows', async () => {
    answers['GET /alerts/active'] = fail({ what_happened: 'Alerts are paused.', impact: 'i', what_is_blocked: 'b', next_action: 'n' }, 409)
    const w = await page()
    expect(w.text()).toContain('Alerts are paused.')
    expect(has(w, 'alert-row')).toBe(false)
  })
  it('History (its own reads) and Notification settings (still the honest empty line) never read the Active list', async () => {
    answers['GET /alerts/active'] = ok(TWO)
    answers['GET /alerts/history'] = ok({ items: [] })
    answers['GET /paper/alerts/records'] = ok({ records: [] })
    const h = await page('/alerts/history')
    expect(h.text()).toContain('No stops or expiry settlements yet.')
    const n = await page('/alerts/notification-settings')
    expect(n.text()).toContain('No notification channels are set up yet.')
    expect(count('GET', '/alerts/active')).toBe(0)
  })
})
