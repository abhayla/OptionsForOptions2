// GC-TP step 7b (REQ-109 AC-8; ADR-207 (5)): the header bell's unread count and the Alerts page list come from GET /paper/alerts,
// text as the server sent it; opening the page marks them read with ONE POST /paper/alerts/read.
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
import { resetPaperAlerts } from '@/lib/paperAlerts'
import { TRACKING_REFRESH_MS } from '@/lib/tracking'

const alert = (id, over = {}) => ({ id, strategy_id: 48, trigger_id: id + 10, created_at: '2026-10-29T05:00:00Z',
  title: `Stop fired ${id}`, body: `Strategy 48 exited all legs, index crossed above 24500.00 (${id})`, read: false, ...over })
const TWO = { alerts: [alert(2, { created_at: '2026-10-29T06:30:15Z' }), alert(1)], unread: 2 }
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

beforeEach(() => { calls.length = 0; answers = {}; resetPaperAlerts(); vi.useFakeTimers() })
afterEach(() => vi.useRealTimers())

describe('header bell', () => {
  it('shows the unread count from GET /paper/alerts', async () => {
    answers['GET /paper/alerts'] = ok(TWO)
    const w = await header()
    expect(t(w, 'alerts-bell-count').text()).toBe('2')
  })
  it('is hidden at 0, and when the read fails or is unreadable', async () => {
    answers['GET /paper/alerts'] = ok({ alerts: [], unread: 0 })
    expect(has(await header(), 'alerts-bell-count')).toBe(false)
    resetPaperAlerts()
    answers['GET /paper/alerts'] = fail(null)
    expect(has(await header(), 'alerts-bell-count')).toBe(false)
    resetPaperAlerts()
    answers['GET /paper/alerts'] = ok({ nope: 1 })
    expect(has(await header(), 'alerts-bell-count')).toBe(false)
  })
  it('re-reads on the existing paper refresh tick and drops a stale count when the read then fails', async () => {
    answers['GET /paper/alerts'] = ok(TWO)
    const w = await header()
    answers['GET /paper/alerts'] = ok({ alerts: [], unread: 3 })
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    expect(t(w, 'alerts-bell-count').text()).toBe('3')
    answers['GET /paper/alerts'] = fail(null)
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    expect(has(w, 'alerts-bell-count')).toBe(false)
  })
})

describe('Alerts page', () => {
  it('shows the title once: an older body that opens with it loses that repeat', async () => {
    const one = { ...TWO.alerts[0], title: 'Paper strategy - X', body: 'Paper strategy - X: Conditional exit: NIFTY crossed below 22,845.00; exited 1 legs' }
    answers['GET /paper/alerts'] = ok({ alerts: [one], unread: 0 })
    const w = await page()
    expect(t(w, 'alert-title').text()).toBe('Paper strategy - X')
    expect(t(w, 'alert-body').text()).toBe('Conditional exit: NIFTY crossed below 22,845.00; exited 1 legs')
  })
  it('lists both rows newest first as sent, time in IST, and calls POST /paper/alerts/read once', async () => {
    answers['GET /paper/alerts'] = ok(TWO)
    answers['POST /paper/alerts/read'] = ok({ alerts: TWO.alerts.map((a) => ({ ...a, read: true })), unread: 0 })
    const w = await page()
    const rows = w.findAll('[data-testid="alert-row"]')
    expect(rows).toHaveLength(2)
    expect(rows[0].get('[data-testid="alert-time"]').text()).toBe('29 Oct 2026, 12:00:15 IST')
    expect(rows[0].get('[data-testid="alert-strategy"]').text()).toBe('Strategy 48')
    expect(rows[0].get('[data-testid="alert-title"]').text()).toBe('Stop fired 2')
    expect(rows[0].get('[data-testid="alert-body"]').text()).toBe('Strategy 48 exited all legs, index crossed above 24500.00 (2)')
    expect(rows[1].get('[data-testid="alert-title"]').text()).toBe('Stop fired 1')
    expect(has(w, 'alerts-empty')).toBe(false)
    expect(count('POST', '/paper/alerts/read')).toBe(1)
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS * 2)
    expect(count('POST', '/paper/alerts/read')).toBe(1)
  })
  it('empty: keeps the existing empty line and does not call read', async () => {
    answers['GET /paper/alerts'] = ok({ alerts: [], unread: 0 })
    const w = await page()
    expect(t(w, 'alerts-empty').text()).toBe('No alerts yet. Alerts start when strategy monitoring rules are added.')
    expect(count('POST', '/paper/alerts/read')).toBe(0)
  })
  it('a refused read shows the server reason and no rows; a failed mark-read keeps the rows', async () => {
    answers['GET /paper/alerts'] = fail({ what_happened: 'Alerts are paused.', impact: 'i', what_is_blocked: 'b', next_action: 'n' }, 409)
    const w = await page()
    expect(w.text()).toContain('Alerts are paused.')
    expect(has(w, 'alert-row')).toBe(false)
    resetPaperAlerts()
    answers['GET /paper/alerts'] = ok(TWO)
    answers['POST /paper/alerts/read'] = fail(null)
    const w2 = await page()
    expect(w2.findAll('[data-testid="alert-row"]')).toHaveLength(2)
  })
  it('History and Notification settings stay the honest empty lines and read nothing', async () => {
    answers['GET /paper/alerts'] = ok(TWO)
    const h = await page('/alerts/history')
    expect(h.text()).toContain('No alerts yet.')
    const n = await page('/alerts/notification-settings')
    expect(n.text()).toContain('No notification channels are set up yet.')
    expect(count('GET', '/paper/alerts')).toBe(0)
  })
})
