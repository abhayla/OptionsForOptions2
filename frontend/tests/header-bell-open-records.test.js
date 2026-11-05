// IC e2e stage B4 (design decision 10): the header bell = paper alerts unread + OPEN adjustment records, read on the same
// refresh tick; a toast when a new open record id shows up on a later poll (never on first load); click opens the compare.
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
import { resetPaperAlerts } from '@/lib/paperAlerts'
import { resetOpenRecords } from '@/lib/paperAlerts'
import { TRACKING_REFRESH_MS } from '@/lib/tracking'

const alertRow = (id) => ({ id, strategy_id: 48, trigger_id: id + 10, created_at: '2026-10-29T05:00:00Z', title: `t${id}`, body: `b${id}`, read: false })
const paper = (n) => () => Promise.resolve({ data: { alerts: Array.from({ length: n }, (_, i) => alertRow(i + 1)), unread: n } })
const rec = (id, outcome = 'open') => ({ id, outcome })
const opp = (...recs) => () => Promise.resolve({ data: { groups: [{ group: 'g', strategy_id: 7, records: recs }] } })
const OPEN3 = [rec(1), rec(2), rec(3)]

let confirmSpy
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
  resetPaperAlerts()
  resetOpenRecords()
  vi.useFakeTimers()
  confirmSpy = vi.fn(() => true)
  vi.stubGlobal('confirm', confirmSpy)
})
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

describe('bell counts paper unread + open records', () => {
  it('2 paper unread + 3 open records shows 5', async () => {
    answers['GET /paper/alerts'] = paper(2)
    answers['GET /adjustment-opportunities'] = opp(...OPEN3)
    const w = await header()
    expect(badge(w).text()).toBe('5')
  })
  it('a record that becomes non-open drops the count on the next tick', async () => {
    answers['GET /paper/alerts'] = paper(2)
    answers['GET /adjustment-opportunities'] = opp(...OPEN3)
    const w = await header()
    answers['GET /adjustment-opportunities'] = opp(rec(1), rec(2), rec(3, 'dismissed'))
    await tick()
    expect(badge(w).text()).toBe('4')
  })
  it('zero of both hides the badge', async () => {
    answers['GET /paper/alerts'] = paper(0)
    answers['GET /adjustment-opportunities'] = opp()
    const w = await header()
    expect(badge(w).exists()).toBe(false)
  })
  it('the opportunities endpoint failing keeps the paper count and raises no toast, tick after tick', async () => {
    answers['GET /paper/alerts'] = paper(2)
    const w = await header()
    await tick()
    await tick()
    expect(badge(w).text()).toBe('2')
    expect(confirmSpy).not.toHaveBeenCalled()
  })
  it('open records alone count when the paper read fails', async () => {
    answers['GET /adjustment-opportunities'] = opp(...OPEN3)
    const w = await header()
    expect(badge(w).text()).toBe('3')
  })
})

describe('toast on a new open record', () => {
  it('no toast on first load with 3 open records', async () => {
    answers['GET /paper/alerts'] = paper(0)
    answers['GET /adjustment-opportunities'] = opp(...OPEN3)
    await header()
    expect(confirmSpy).not.toHaveBeenCalled()
  })
  it('a new id on a later poll toasts once; the same id on the next poll does not toast again', async () => {
    answers['GET /paper/alerts'] = paper(0)
    answers['GET /adjustment-opportunities'] = opp(...OPEN3)
    await header()
    answers['GET /adjustment-opportunities'] = opp(...OPEN3, rec(4))
    await tick()
    expect(confirmSpy).toHaveBeenCalledTimes(1)
    await tick()
    expect(confirmSpy).toHaveBeenCalledTimes(1)
  })
  it('clicking the toast routes to the strategy compare with the open records', async () => {
    answers['GET /paper/alerts'] = paper(0)
    answers['GET /adjustment-opportunities'] = opp(rec(1))
    await header()
    answers['GET /adjustment-opportunities'] = opp(rec(1), rec(2))
    await tick()
    expect(r.currentRoute.value.fullPath).toContain('/strategy/builder?adjust=7')
    expect(r.currentRoute.value.query.opp).toBe('1,2')
  })
  it('a declined toast does not route', async () => {
    confirmSpy.mockReturnValue(false)
    answers['GET /paper/alerts'] = paper(0)
    answers['GET /adjustment-opportunities'] = opp(rec(1))
    await header()
    answers['GET /adjustment-opportunities'] = opp(rec(1), rec(2))
    await tick()
    expect(r.currentRoute.value.fullPath).toBe('/')
  })
})
