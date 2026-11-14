// GC-ICFIX issue 8 (ADR-260, REQ-162 AC-1, ADR-207 (5)): the pop-up, the bell and Alerts > Active read ONE record.
// Two practice trades with one open alert each: the pop-up names the trade and the rule and opens THAT trade's offer;
// the bell count equals the open items listed in Alerts > Active.
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
import { resetOpenRecords, resetPaperAlerts } from '@/lib/paperAlerts'
import { TRACKING_REFRESH_MS } from '@/lib/tracking'
import { openToast, toasts } from '@/composables/useToast'

const rec = (id, condition, outcome = 'open') => ({ id, rule_id: `R-${id}`, outcome, condition, can_act: outcome === 'open' })
const group = (strategy_id, strategy_name, ...records) => ({ group: `${strategy_id}-g`, strategy_id, strategy_name, label: 'Your rule was triggered', records })
const opp = (...groups) => () => Promise.resolve({ data: { groups } })
const paper = (rows) => () => Promise.resolve({ data: { alerts: rows, unread: rows.filter((a) => !a.read).length } })
const stop = (id, strategy_id, read = false) => ({ id, strategy_id, strategy_name: `"Trade ${strategy_id}"`, created_at: '2026-11-14T05:00:00Z', title: 'Stop', body: 'Stop reached', read })

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
  resetPaperAlerts()
  resetOpenRecords()
  vi.useFakeTimers()
  toasts.splice(0)
})
afterEach(() => { vi.useRealTimers() })

describe('pop-up names the trade and the rule and opens that trade', () => {
  it('two trades, the second one raises a new alert: text names trade B and its rule; click opens trade B', async () => {
    answers['GET /paper/alerts'] = paper([])
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

describe('bell = open items of Alerts > Active, one record', () => {
  it('two open alerts on two trades + one unread stop: bell 3 and the list shows 3', async () => {
    answers['GET /paper/alerts'] = paper([stop(1, 7)])
    answers['GET /adjustment-opportunities'] = opp(A, B)
    const h = await mountAt('/', AppHeader)
    const page = await mountAt('/alerts/active', AlertsPage)
    const rows = page.findAll('[data-testid="alert-row"], [data-testid="open-record-row"]')
    expect(h.get('[data-testid="alerts-bell-count"]').text()).toBe('3')
    expect(rows).toHaveLength(3)
    const names = page.findAll('[data-testid="open-record-row"]').map((x) => x.text())
    expect(names[0]).toContain('Trade A')
    expect(names[0]).toContain('Net delta above 40')
    expect(names[1]).toContain('Trade B')
    expect(page.findAll('[data-testid="open-record-compare"]').map((x) => x.attributes('href')).join()).toContain('adjust=8')
  })
  it('a closed alert (trade closed) and a read alert are not counted or listed as open', async () => {
    answers['GET /paper/alerts'] = paper([stop(1, 7, true)])
    answers['GET /adjustment-opportunities'] = opp(group(7, '"Trade A"', rec(1, 'x', 'dismissed')), B)
    const h = await mountAt('/', AppHeader)
    const page = await mountAt('/alerts/active', AlertsPage)
    expect(h.get('[data-testid="alerts-bell-count"]').text()).toBe('1')
    expect(page.findAll('[data-testid="open-record-row"]')).toHaveLength(1)
  })
  it('no alerts: bell empty and the page says so; a failed read shows the could-not-load state, not a blank', async () => {
    answers['GET /paper/alerts'] = paper([])
    answers['GET /adjustment-opportunities'] = opp()
    const h = await mountAt('/', AppHeader)
    const page = await mountAt('/alerts/active', AlertsPage)
    expect(h.find('[data-testid="alerts-bell-count"]').exists()).toBe(false)
    expect(page.find('[data-testid="alerts-empty"]').exists()).toBe(true)
    resetPaperAlerts()
    resetOpenRecords()
    answers = {}
    const bad = await mountAt('/alerts/active', AlertsPage)
    expect(bad.find('[data-testid="alerts-error"], [data-testid="alerts-error-message"], [data-testid^="alerts-error"]').exists()).toBe(true)
  })
})
