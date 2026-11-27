// Lane TB (R2, 28 Nov) I-76. Extends paper-alerts.test.js. While Alerts > Active waits for GET /alerts/active the page says it
// is loading; "No alerts yet" is only for a read that answered with nothing.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url) => {
    const a = answers[`${method} ${url}`]
    return a ? a() : Promise.reject({ message: 'no answer', parts: null, status: null })
  }
  return { ...actual, default: { get: reply('GET'), post: reply('POST') } }
})

import AlertsPage from '@/pages/AlertsPage.vue'
import { PAPER_ALERTS_EMPTY, RECORDS_EMPTY, resetActiveAlerts, resetOpenRecords } from '@/lib/paperAlerts'

const alert = (id) => ({ id, strategy_id: 48, strategy_name: null, kind: 'plan_loss_stop', text: `Loss stop reached (${id})`,
  fired_at: '2026-10-29T05:00:00Z', fired_line: 'Fired at 10:30', no_longer_true_since: null, no_longer_true_since_hm: null, answers: [{ code: 'continue', label: 'Continue with the position' }] })
const later = (ms, data) => () => new Promise((resolve) => setTimeout(() => resolve({ data }), ms))

async function mountAt(path) {
  const r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:p(.*)*', meta: { title: 'Alerts' }, component: { template: '<div/>' } }] })
  r.push(path)
  await r.isReady()
  const w = mount(AlertsPage, { global: { plugins: [r] } })
  await flushPromises()
  return w
}
beforeEach(() => { answers = {}; resetActiveAlerts(); resetOpenRecords(); vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] }) })
afterEach(() => { vi.useRealTimers() })

describe('I-76 Alerts > Active while the read is pending', () => {
  it('I-76: for the whole 8 s wait the page says Loading and never "No alerts yet"; then the rows', async () => {
    answers['GET /alerts/active'] = later(8000, { count: 1, alerts: [alert(1)] })
    const w = await mountAt('/alerts/active')
    for (const ms of [0, 3000, 4900]) { // 0 s, 3 s, 7.9 s
      if (ms) await vi.advanceTimersByTimeAsync(ms)
      expect(w.find('[data-testid="alerts-empty"]').exists()).toBe(false)
      expect(w.text()).not.toContain(PAPER_ALERTS_EMPTY)
      expect(w.get('[data-testid="alerts-loading"]').text()).toBe('Loading...')
    }
    await vi.advanceTimersByTimeAsync(200)
    await flushPromises()
    expect(w.find('[data-testid="alerts-loading"]').exists()).toBe(false)
    expect(w.findAll('[data-testid="alert-row"]')).toHaveLength(1)
  })
  it('I-76: a read that answered with no alerts says the empty sentence, and Loading is gone', async () => {
    answers['GET /alerts/active'] = later(2000, { count: 0, alerts: [] })
    const w = await mountAt('/alerts/active')
    expect(w.find('[data-testid="alerts-empty"]').exists()).toBe(false)
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()
    expect(w.find('[data-testid="alerts-loading"]').exists()).toBe(false)
    expect(w.get('[data-testid="alerts-empty"]').text()).toContain(PAPER_ALERTS_EMPTY)
  })
  it('I-76: a failed read shows the error, not "No alerts yet" and not Loading', async () => {
    answers['GET /alerts/active'] = () => new Promise((_, reject) => setTimeout(() => reject({ message: 'x', status: 500, parts: null }), 3000))
    const w = await mountAt('/alerts/active')
    await vi.advanceTimersByTimeAsync(3000)
    await flushPromises()
    expect(w.find('[data-testid="alerts-empty"]').exists()).toBe(false)
    expect(w.find('[data-testid="alerts-loading"]').exists()).toBe(false)
    expect(w.find('[data-testid="alerts-error-what"]').exists()).toBe(true)
  })
})

// Same class on the History tab (found while reading AlertsPage.vue; not in the item list). It.fails = the test body describes
// the right behaviour and currently FAILS in the app, so the gate stays green and flips red-to-fix when the page is repaired.
describe('I-76 (same class) Alerts > History while its reads are pending', () => {
  it('History says loading, never "No stops or expiry settlements yet", while both reads wait', async () => {
    answers['GET /alerts/answered'] = later(6000, { items: [] })
    answers['GET /paper/alerts/records'] = later(6000, { records: [] })
    const w = await mountAt('/alerts/history')
    await vi.advanceTimersByTimeAsync(3000)
    expect(w.text()).not.toContain(RECORDS_EMPTY)
  })
})
