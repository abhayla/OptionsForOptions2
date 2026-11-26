// IC e2e stage B4 (design decision 10), changed by ADR-330 (4): the header bell = the server's count of unanswered actionable alerts
// (GET /alerts/active); the OPEN adjustment records of GET /adjustment-opportunities are read on the same tick for the pop-up only
// and add nothing to the bell; a pop-up when a new open record id shows up on a later poll (never on first load); click opens the compare.
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
import { resetActiveAlerts, resetOpenRecords } from '@/lib/paperAlerts'
import { TRACKING_REFRESH_MS } from '@/lib/tracking'
import { dismissToast, openToast, toasts } from '@/composables/useToast'

const alertRow = (id) => ({ id, strategy_id: 48, kind: 'plan_loss_stop', text: `t${id}`, fired_at_hm: '11:02', answers: [] })
const paper = (n) => () => Promise.resolve({ data: { count: n, alerts: Array.from({ length: n }, (_, i) => alertRow(i + 1)) } })
const rec = (id, outcome = 'open') => ({ id, outcome })
const opp = (...recs) => () => Promise.resolve({ data: { groups: [{ group: 'g', strategy_id: 7, records: recs }] } })
const OPEN3 = [rec(1), rec(2), rec(3)]

let r
async function header() {
  r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }, { path: '/:p(.*)*', component: { template: '<div/>' } }] })
  r.push('/')
  await r.isReady()
  const w = mount(AppHeader, { global: { plugins: [r] } })
  await flushPromises()
  return w
}
const tick = async () => { await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS); await flushPromises() }
const badge = (w) => w.find('[data-testid="alerts-bell-count"]')

beforeEach(() => {
  answers = {}
  resetActiveAlerts()
  resetOpenRecords()
  vi.useFakeTimers()
  toasts.splice(0)
})
afterEach(() => { vi.useRealTimers() })

describe('bell counts the server count of unanswered alerts only', () => {
  it('2 unanswered alerts + 3 open adjustment records shows 2 (the records add nothing)', async () => {
    answers['GET /alerts/active'] = paper(2)
    answers['GET /adjustment-opportunities'] = opp(...OPEN3)
    const w = await header()
    expect(badge(w).text()).toBe('2')
  })
  it('a record that becomes non-open does not change the count; a new server count shows on the next tick', async () => {
    answers['GET /alerts/active'] = paper(2)
    answers['GET /adjustment-opportunities'] = opp(...OPEN3)
    const w = await header()
    answers['GET /adjustment-opportunities'] = opp(rec(1), rec(2), rec(3, 'dismissed'))
    await tick()
    expect(badge(w).text()).toBe('2')
    answers['GET /alerts/active'] = paper(1)
    await tick()
    expect(badge(w).text()).toBe('1')
  })
  it('zero hides the badge', async () => {
    answers['GET /alerts/active'] = paper(0)
    answers['GET /adjustment-opportunities'] = opp()
    const w = await header()
    expect(badge(w).exists()).toBe(false)
  })
  it('the opportunities endpoint failing keeps the alert count and raises no pop-up, tick after tick', async () => {
    answers['GET /alerts/active'] = paper(2)
    const w = await header()
    await tick()
    await tick()
    expect(badge(w).text()).toBe('2')
    expect(toasts).toHaveLength(0)
  })
  it('open records alone do not make a number when the alert read fails: no count', async () => {
    answers['GET /adjustment-opportunities'] = opp(...OPEN3)
    const w = await header()
    expect(badge(w).exists()).toBe(false)
  })
})

describe('toast on a new open record', () => {
  it('no toast on first load with 3 open records', async () => {
    answers['GET /alerts/active'] = paper(0)
    answers['GET /adjustment-opportunities'] = opp(...OPEN3)
    await header()
    expect(toasts).toHaveLength(0)
  })
  it('a new id on a later poll toasts once; the same id on the next poll does not toast again', async () => {
    answers['GET /alerts/active'] = paper(0)
    answers['GET /adjustment-opportunities'] = opp(...OPEN3)
    await header()
    answers['GET /adjustment-opportunities'] = opp(...OPEN3, rec(4))
    await tick()
    expect(toasts).toHaveLength(1)
    dismissToast(toasts[0].id)
    await tick()
    expect(toasts).toHaveLength(0)
  })
  it('clicking the toast routes to the strategy compare with the open records', async () => {
    answers['GET /alerts/active'] = paper(0)
    answers['GET /adjustment-opportunities'] = opp(rec(1))
    await header()
    answers['GET /adjustment-opportunities'] = opp(rec(1), rec(2))
    await tick()
    openToast(toasts[0].id)
    await flushPromises()
    expect(r.currentRoute.value.fullPath).toContain('/strategy/builder?adjust=7')
    expect(r.currentRoute.value.query.opp).toBe('1,2')
    expect(r.currentRoute.value.query.pick).toBeUndefined() // ADR-308 (4): the pop-up opens with every approach shown
  })
  it('a dismissed toast does not route', async () => {
    answers['GET /alerts/active'] = paper(0)
    answers['GET /adjustment-opportunities'] = opp(rec(1))
    await header()
    answers['GET /adjustment-opportunities'] = opp(rec(1), rec(2))
    await tick()
    dismissToast(toasts[0].id)
    await flushPromises()
    expect(r.currentRoute.value.fullPath).toBe('/')
  })
})
