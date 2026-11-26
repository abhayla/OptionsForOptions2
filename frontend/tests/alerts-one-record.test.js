// GC-ICFIX issue 8 (ADR-260, REQ-162 AC-1, ADR-207 (5)): the pop-up, the bell and Alerts > Active read ONE record.
// Two practice trades with one open alert each: the pop-up names the trade and the rule and opens THAT trade's offer;
// the bell count equals the rows listed in Alerts > Active (ADR-330 (4): both are the server's GET /alerts/active).
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

import AppHeader from '@/components/layout/AppHeader.vue'
import AlertsPage from '@/pages/AlertsPage.vue'
import { resetOpenRecords, resetActiveAlerts } from '@/lib/paperAlerts'
import { TRACKING_REFRESH_MS } from '@/lib/tracking'
import { openToast, toasts } from '@/composables/useToast'

const rec = (id, condition, outcome = 'open') => ({ id, rule_id: `R-${id}`, outcome, condition, can_act: outcome === 'open' })
const group = (strategy_id, strategy_name, ...records) => ({ group: `${strategy_id}-g`, strategy_id, strategy_name, label: 'Your rule was triggered', records })
const opp = (...groups) => () => Promise.resolve({ data: { groups } })
const active = (rows) => () => Promise.resolve({ data: { count: rows.length, alerts: rows } })
const item = (id, strategy_id, text) => ({ id, strategy_id, strategy_name: `"Trade ${strategy_id}"`, kind: 'adjustment_rule', text, fired_at_hm: '11:02', no_longer_true_since_hm: null, answers: [{ code: 'continue', label: 'Continue with the position' }] })

let r
async function mountAt(path, comp) {
  r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:p(.*)*', component: { template: '<div/>' } }] })
  r.push(path)
  await r.isReady()
  const w = mount(comp, { global: { plugins: [r] } })
  await flushPromises()
  return w
}
const tick = async () => { await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS); await flushPromises() }
const A = group(7, '"Trade A"', rec(1, 'Net delta above 40'))
const B = group(8, '"Trade B"', rec(2, 'Loss beyond 5000'))

beforeEach(() => {
  answers = {}
  resetActiveAlerts()
  resetOpenRecords()
  vi.useFakeTimers()
  toasts.splice(0)
})
afterEach(() => { vi.useRealTimers() })

describe('pop-up names the trade and the rule and opens that trade', () => {
  it('two trades, the second one raises a new alert: text names trade B and its rule; click opens trade B', async () => {
    answers['GET /alerts/active'] = active([])
    answers['GET /adjustment-opportunities'] = opp(A)
    await mountAt('/', AppHeader)
    answers['GET /adjustment-opportunities'] = opp(A, B)
    await tick()
    expect(toasts).toHaveLength(1)
    expect(toasts[0].message).toContain('Trade B')
    expect(toasts[0].message).toContain('Loss beyond 5000')
    expect(toasts[0].message).not.toContain('Trade A')
    openToast(toasts[0].id)
    await flushPromises()
    expect(r.currentRoute.value.query.adjust).toBe('8')
    expect(r.currentRoute.value.query.opp).toBe('2')
  })
})

describe('bell = rows of Alerts > Active, one server read', () => {
  it('two unanswered alerts on two trades: bell 2 and the list shows 2, each with its trade and rule', async () => {
    answers['GET /alerts/active'] = active([item(1, 7, 'Net delta above 40'), item(2, 8, 'Loss beyond 5000')])
    answers['GET /adjustment-opportunities'] = opp(A, B)
    const h = await mountAt('/', AppHeader)
    const page = await mountAt('/alerts/active', AlertsPage)
    const rows = page.findAll('[data-testid="alert-row"]')
    expect(h.get('[data-testid="alerts-bell-count"]').text()).toBe('2')
    expect(rows).toHaveLength(2)
    expect(rows[0].text()).toContain('Trade 7')
    expect(rows[0].text()).toContain('Net delta above 40')
    expect(rows[1].text()).toContain('Trade 8')
    expect(rows[1].text()).toContain('Loss beyond 5000')
  })
  it('no alerts: bell empty and the page says so; a failed read shows the could-not-load state, not a blank', async () => {
    answers['GET /alerts/active'] = active([])
    answers['GET /adjustment-opportunities'] = opp()
    const h = await mountAt('/', AppHeader)
    const page = await mountAt('/alerts/active', AlertsPage)
    expect(h.find('[data-testid="alerts-bell-count"]').exists()).toBe(false)
    expect(page.find('[data-testid="alerts-empty"]').exists()).toBe(true)
    resetActiveAlerts()
    resetOpenRecords()
    answers = {}
    const bad = await mountAt('/alerts/active', AlertsPage)
    expect(bad.find('[data-testid^="alerts-error"]').exists()).toBe(true)
  })
})
