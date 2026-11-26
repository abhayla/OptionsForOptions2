// GC-ICFIX P1 issue 8b (ADR-260, REQ-162 AC-1), changed by ADR-330 (4): "bell = unanswered actionable alerts". The bell count is the
// server's count of GET /alerts/active, and Alerts > Active lists exactly those rows. Open adjustment records and read/unread
// paper stops add nothing; opening Active changes neither the bell nor the list.
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
import { bellCount, resetActiveAlerts, resetOpenRecords } from '@/lib/paperAlerts'
import { TRACKING_REFRESH_MS } from '@/lib/tracking'
import { toasts } from '@/composables/useToast'

const rec = (id, condition) => ({ id, rule_id: `R-${id}`, outcome: 'open', condition, can_act: true })
const group = (strategy_id, strategy_name, ...records) => ({ group: `${strategy_id}-g`, strategy_id, strategy_name, label: 'Your rule was triggered', records })
const row = (id, strategy_id) => ({ id, strategy_id, strategy_name: `"Trade ${strategy_id}"`, kind: 'plan_loss_stop', text: `Loss stop ${id}`, fired_line: 'Fired at 11:02', answers: [{ code: 'continue', label: 'Continue with the position' }] })
const ACTIVE = { count: 2, alerts: [row(1, 7), row(2, 8)] }

let r
async function mountAt(path, comp) {
  r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:p(.*)*', component: { template: '<div/>' } }] })
  r.push(path)
  await r.isReady()
  const w = mount(comp, { global: { plugins: [r] } })
  await flushPromises()
  return w
}
const testid = (w, id) => w.findAll(`[data-testid="${id}"]`)

beforeEach(() => {
  answers = {}
  resetActiveAlerts()
  resetOpenRecords()
  vi.useFakeTimers()
  toasts.splice(0)
})
afterEach(() => { vi.useRealTimers() })

describe('bell and Active agree before and after Active is opened', () => {
  it('bell 2 = Active 2 rows, with 2 open adjustment records and 1 unread paper stop adding nothing; opening Active changes neither', async () => {
    answers['GET /alerts/active'] = () => Promise.resolve({ data: ACTIVE })
    answers['GET /paper/alerts'] = () => Promise.resolve({ data: { unread: 1, alerts: [] } })
    answers['GET /adjustment-opportunities'] = () => Promise.resolve({ data: { groups: [group(7, '"Trade A"', rec(1, 'Net delta above 40')), group(8, '"Trade B"', rec(2, 'Loss beyond 5000'))] } })
    const h = await mountAt('/', AppHeader)
    expect(h.get('[data-testid="alerts-bell-count"]').text()).toBe('2')
    const page = await mountAt('/alerts/active', AlertsPage)
    expect(bellCount()).toBe(2)
    expect(testid(page, 'alert-row')).toHaveLength(2)
    expect(h.get('[data-testid="alerts-bell-count"]').text()).toBe('2')
  })
  it('an answered alert leaves both at once: the next server read says 1, the bell and the list say 1', async () => {
    answers['GET /alerts/active'] = () => Promise.resolve({ data: ACTIVE })
    answers['GET /adjustment-opportunities'] = () => Promise.resolve({ data: { groups: [] } })
    const h = await mountAt('/', AppHeader)
    answers['GET /alerts/active'] = () => Promise.resolve({ data: { count: 1, alerts: [row(2, 8)] } })
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    await flushPromises()
    const page = await mountAt('/alerts/active', AlertsPage)
    expect(h.get('[data-testid="alerts-bell-count"]').text()).toBe('1')
    expect(testid(page, 'alert-row')).toHaveLength(1)
  })
})

describe('two open records on one trade', () => {
  it('the pop-up names both rules', async () => {
    answers['GET /alerts/active'] = () => Promise.resolve({ data: { count: 0, alerts: [] } })
    answers['GET /adjustment-opportunities'] = () => Promise.resolve({ data: { groups: [] } })
    await mountAt('/', AppHeader)
    // P1 r3: announced from /alerts/active (kind adjustment_rule), still one pop-up per trade naming both rules
    const rule = (id, text) => ({ ...row(id, 7), kind: 'adjustment_rule', text })
    answers['GET /alerts/active'] = () => Promise.resolve({ data: { count: 2, alerts: [rule(1, 'Net delta above 40'), rule(2, 'Loss beyond 5000')] } })
    answers['GET /adjustment-opportunities'] = () => Promise.resolve({ data: { groups: [group(7, '"Trade A"', rec(1, 'Net delta above 40'), rec(2, 'Loss beyond 5000'))] } })
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    await flushPromises()
    expect(toasts).toHaveLength(1)
    expect(toasts[0].message).toContain('Net delta above 40')
    expect(toasts[0].message).toContain('Loss beyond 5000')
  })
})
