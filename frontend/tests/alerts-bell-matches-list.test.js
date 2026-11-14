// GC-ICFIX P1 issue 8b (ADR-260, REQ-162 AC-1): the bell count is the number of items needing attention, and Alerts > Active
// lists exactly those on top; stops already read sit under "Earlier" and are never counted. The mark-read call SUCCEEDS here.
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
import { attentionItems, bellCount, resetOpenRecords, resetPaperAlerts } from '@/lib/paperAlerts'
import { TRACKING_REFRESH_MS } from '@/lib/tracking'
import { toasts } from '@/composables/useToast'

const rec = (id, condition) => ({ id, rule_id: `R-${id}`, outcome: 'open', condition, can_act: true })
const group = (strategy_id, strategy_name, ...records) => ({ group: `${strategy_id}-g`, strategy_id, strategy_name, label: 'Your rule was triggered', records })
const stop = (id, strategy_id, read = false) => ({ id, strategy_id, strategy_name: `"Trade ${strategy_id}"`, created_at: '2026-11-14T05:00:00Z', title: `Stop ${id}`, body: 'Stop reached', read })
const STOPS = [stop(1, 7, true), stop(2, 7), stop(3, 8)] // one read, two unread
const answerOf = (rows) => ({ data: { alerts: rows, unread: rows.filter((a) => !a.read).length } })

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
  resetPaperAlerts()
  resetOpenRecords()
  vi.useFakeTimers()
  toasts.splice(0)
})
afterEach(() => { vi.useRealTimers() })

describe('bell and Active agree before and after Active is opened', () => {
  it('before: bell 4 = 2 unread stops + 2 open records, attention list 4; after opening Active: bell 2, top list 2, read stops under Earlier', async () => {
    answers['GET /paper/alerts'] = () => Promise.resolve(answerOf(STOPS))
    answers['GET /adjustment-opportunities'] = () => Promise.resolve({ data: { groups: [group(7, '"Trade A"', rec(1, 'Net delta above 40')), group(8, '"Trade B"', rec(2, 'Loss beyond 5000'))] } })
    const h = await mountAt('/', AppHeader)
    expect(h.get('[data-testid="alerts-bell-count"]').text()).toBe('4')
    expect(attentionItems()).toHaveLength(4)
    // the server marks everything read on POST and answers with the same rows, all read
    answers['POST /paper/alerts/read'] = () => Promise.resolve(answerOf(STOPS.map((s) => ({ ...s, read: true }))))
    const page = await mountAt('/alerts/active', AlertsPage)
    expect(bellCount()).toBe(2)
    expect(attentionItems()).toHaveLength(2)
    expect(testid(page, 'open-record-row')).toHaveLength(2)
    expect(testid(page, 'alert-row')).toHaveLength(3) // the three stops, all read now, all under Earlier
    expect(page.get('[data-testid="alerts-earlier-heading"]').text()).toBe('Earlier')
    const top = page.get('[data-testid="alerts-attention"]')
    expect(top.findAll('[data-testid="open-record-row"], [data-testid="alert-row"]')).toHaveLength(2)
    expect(page.get('[data-testid="alerts-earlier"]').findAll('[data-testid="alert-row"]')).toHaveLength(3)
  })
  it('only read stops: bell 0, top list empty, the stop is under Earlier', async () => {
    answers['GET /paper/alerts'] = () => Promise.resolve(answerOf([stop(1, 7, true)]))
    answers['GET /adjustment-opportunities'] = () => Promise.resolve({ data: { groups: [] } })
    const page = await mountAt('/alerts/active', AlertsPage)
    expect(bellCount()).toBe(0)
    expect(testid(page, 'alert-row')).toHaveLength(1)
    expect(page.get('[data-testid="alerts-earlier-heading"]').text()).toBe('Earlier')
  })
})

describe('two open records on one trade', () => {
  it('the pop-up names both rules', async () => {
    answers['GET /paper/alerts'] = () => Promise.resolve(answerOf([]))
    answers['GET /adjustment-opportunities'] = () => Promise.resolve({ data: { groups: [] } })
    await mountAt('/', AppHeader)
    answers['GET /adjustment-opportunities'] = () => Promise.resolve({ data: { groups: [group(7, '"Trade A"', rec(1, 'Net delta above 40'), rec(2, 'Loss beyond 5000'))] } })
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    await flushPromises()
    expect(toasts).toHaveLength(1)
    expect(toasts[0].message).toContain('Net delta above 40')
    expect(toasts[0].message).toContain('Loss beyond 5000')
  })
})
