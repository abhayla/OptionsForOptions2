// ADR-330 (3), (4), item P1 (frontend half): the bell number and Alerts > Active come from ONE server read (GET /alerts/active), so
// they cannot differ. Opening Active writes nothing. Answers are posted to /alerts/<id>/answer; Exit never exits by itself.
// Real case 25 Nov D-29: the bell showed 1 while Active listed 4.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

let answers = {}
let calls = []
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url, body) => {
    calls.push({ method, url, body })
    const a = answers[`${method} ${url}`]
    return a ? a() : Promise.reject({ message: 'no answer', parts: null, status: null })
  }
  return { ...actual, default: { get: reply('GET'), post: reply('POST') } }
})

import AppHeader from '@/components/layout/AppHeader.vue'
import AlertsPage from '@/pages/AlertsPage.vue'
import { bellCount, resetActiveAlerts, resetOpenRecords } from '@/lib/paperAlerts'
import { toasts } from '@/composables/useToast'

const row = (id, extra = {}) => ({
  id, strategy_id: 7, strategy_name: `"Trade ${id}"`, kind: 'plan_loss_stop', text: `Loss stop ${id} reached`,
  fired_at: '2026-11-25T05:32:20Z', fired_line: 'Fired at 11:02', no_longer_true_since: null, no_longer_true_line: null,
  answers: [{ code: 'exit', label: 'Exit the position' }, { code: 'continue', label: 'Continue with the position' }], ...extra,
})
const active = (n, extra) => ({ data: { count: n, alerts: Array.from({ length: n }, (_, i) => row(i + 1, extra)) } })

let r
async function mountAt(path, comp) {
  r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:p(.*)*', component: { template: '<div/>' } }] })
  r.push(path)
  await r.isReady()
  const w = mount(comp, { global: { plugins: [r] } })
  await flushPromises()
  return w
}
const ids = (w, id) => w.findAll(`[data-testid="${id}"]`)

beforeEach(() => {
  answers = {}
  calls = []
  resetActiveAlerts()
  resetOpenRecords()
  toasts.splice(0)
})
afterEach(() => { vi.useRealTimers() })

describe('bell equals Active rows', () => {
  it('bell equals Active rows: count 4 and 4 alerts, an unread paper alert of 1 does not change either', async () => {
    answers['GET /alerts/active'] = () => Promise.resolve(active(4))
    answers['GET /paper/alerts'] = () => Promise.resolve({ data: { unread: 1, alerts: [] } })
    answers['GET /adjustment-opportunities'] = () => Promise.resolve({ data: { groups: [] } })
    const h = await mountAt('/', AppHeader)
    expect(h.get('[data-testid="alerts-bell-count"]').text()).toBe('4')
    const page = await mountAt('/alerts/active', AlertsPage)
    expect(ids(page, 'alert-row')).toHaveLength(4)
    expect(bellCount()).toBe(4)
  })
  it.each([0, 1, 4])('bell printed == server count == Active rows (%i)', async (n) => {
    answers['GET /alerts/active'] = () => Promise.resolve(active(n))
    answers['GET /adjustment-opportunities'] = () => Promise.resolve({ data: { groups: [] } })
    const h = await mountAt('/', AppHeader)
    const page = await mountAt('/alerts/active', AlertsPage)
    const printed = h.find('[data-testid="alerts-bell-count"]')
    expect(printed.exists() ? printed.text() : '0').toBe(String(n))
    expect(ids(page, 'alert-row')).toHaveLength(n)
  })
  it('a failed read leaves no count and no rows', async () => {
    answers['GET /adjustment-opportunities'] = () => Promise.resolve({ data: { groups: [] } })
    const h = await mountAt('/', AppHeader)
    expect(h.find('[data-testid="alerts-bell-count"]').exists()).toBe(false)
    const page = await mountAt('/alerts/active', AlertsPage)
    expect(ids(page, 'alert-row')).toHaveLength(0)
    expect(bellCount()).toBe(0)
  })
  it('an answer that does not parse leaves no count and no rows', async () => {
    answers['GET /alerts/active'] = () => Promise.resolve({ data: { count: 'x', alerts: 'no' } })
    const page = await mountAt('/alerts/active', AlertsPage)
    expect(ids(page, 'alert-row')).toHaveLength(0)
    expect(bellCount()).toBe(0)
  })
})

describe('Active page', () => {
  it('opening Active posts nothing to /paper/alerts/read (and nothing at all)', async () => {
    answers['GET /alerts/active'] = () => Promise.resolve(active(2))
    await mountAt('/alerts/active', AlertsPage)
    expect(calls.filter((c) => c.method === 'POST')).toEqual([])
  })
  it('a row shows the strategy, the text, Fired at HH:MM, and "no longer true since HH:MM" when set', async () => {
    answers['GET /alerts/active'] = () => Promise.resolve({ data: { count: 2, alerts: [row(1), row(2, { no_longer_true_since: '2026-11-25T05:35:01Z', no_longer_true_line: 'no longer true since 11:05' })] } })
    const page = await mountAt('/alerts/active', AlertsPage)
    const [a, b] = ids(page, 'alert-row')
    expect(a.text()).toContain('Fired at 11:02')
    expect(a.text()).toContain('Loss stop 1 reached')
    expect(a.text()).not.toContain('no longer true')
    expect(b.text()).toContain('Fired at 11:02')
    expect(b.text()).toContain('no longer true since 11:05')
  })
  it('one button per server answer', async () => {
    answers['GET /alerts/active'] = () => Promise.resolve({ data: { count: 1, alerts: [row(1, { kind: 'side_closed', answers: [{ code: 'add_legs', label: 'Add legs' }, { code: 'confirm_new_shape', label: 'Confirm new shape' }] })] } })
    const page = await mountAt('/alerts/active', AlertsPage)
    expect(page.findAll('[data-testid^="alert-answer-"]').map((b) => b.text())).toEqual(['Add legs', 'Confirm new shape'])
  })
  it('Continue posts {"answer":"continue"} to /alerts/<id>/answer and re-reads Active', async () => {
    let list = active(2)
    answers['GET /alerts/active'] = () => Promise.resolve(list)
    answers['POST /alerts/1/answer'] = () => {
      list = { data: { count: 1, alerts: [row(2)] } }
      return Promise.resolve({ data: { id: 1 } })
    }
    const page = await mountAt('/alerts/active', AlertsPage)
    await page.get('[data-testid="alert-answer-continue"]').trigger('click')
    await flushPromises()
    expect(calls.find((c) => c.method === 'POST')).toEqual({ method: 'POST', url: '/alerts/1/answer', body: { answer: 'continue' } })
    expect(ids(page, 'alert-row')).toHaveLength(1)
    expect(bellCount()).toBe(1)
  })
  // W2-B: Exit no longer navigates; it opens the shared exit confirmation on this page (tests/alerts-exit-door-w2b.test.js)
  it('a 409 answer shows the server reason and keeps the row; Exit then stays on the page', async () => {
    answers['GET /alerts/active'] = () => Promise.resolve(active(1))
    const parts = { what_happened: 'This alert is already answered.', impact: 'It was answered elsewhere.', what_is_blocked: 'Nothing was changed.', next_action: 'Reload.' }
    answers['POST /alerts/1/answer'] = () => Promise.reject({ message: 'x', status: 409, parts })
    const page = await mountAt('/alerts/active', AlertsPage)
    await page.get('[data-testid="alert-answer-exit"]').trigger('click')
    await flushPromises()
    expect(ids(page, 'alert-row')).toHaveLength(1)
    expect(page.get('[data-testid="alert-answer-error"]').text()).toContain('This alert is already answered.')
    expect(r.currentRoute.value.path).toBe('/alerts/active')
  })
  it('a network failure of the answer shows a reason and keeps the row', async () => {
    answers['GET /alerts/active'] = () => Promise.resolve(active(1))
    answers['POST /alerts/1/answer'] = () => Promise.reject({ message: 'Network Error', parts: null, status: null })
    const page = await mountAt('/alerts/active', AlertsPage)
    await page.get('[data-testid="alert-answer-continue"]').trigger('click')
    await flushPromises()
    expect(ids(page, 'alert-row')).toHaveLength(1)
    expect(page.get('[data-testid="alert-answer-error"]').text().length).toBeGreaterThan(0)
  })
})

describe('History tab', () => {
  it('lists answered rows (label and time) with the stop and settlement records', async () => {
    answers['GET /alerts/answered'] = () => Promise.resolve({ data: { items: [{ id: 3, strategy_id: 7, strategy_name: '"Trade A"', kind: 'plan_loss_stop', text: 'Loss stop reached', fired_at: '2026-11-25T11:02:20+05:30', fired_line: 'Fired at 11:02', answer: 'continue', answer_label: 'Continue with the position', answered_at: '2026-11-25T11:09:00+05:30', closed_reason: null }] } })
    answers['GET /paper/alerts/records'] = () => Promise.resolve({ data: { records: [{ at: '2026-11-25T09:00:00Z', kind: 'stop', title: 'Stop fired', body: 'Leg stop reached', strategy_id: 7, strategy_name: '"Trade A"' }] } })
    const page = await mountAt('/alerts/history', AlertsPage)
    expect(ids(page, 'answered-row')).toHaveLength(1)
    expect(ids(page, 'answered-row')[0].text()).toContain('Continue with the position')
    expect(ids(page, 'answered-row')[0].text()).toContain('11:09')
    expect(ids(page, 'record-row')).toHaveLength(1)
  })
  it('shows a system-closed row as the server sentence alone, not the answer label (ADR-330 (3), 27 Nov 10:26)', async () => {
    answers['GET /alerts/answered'] = () => Promise.resolve({ data: { items: [{ id: 4, strategy_id: 7, strategy_name: '"Trade A"', kind: 'plan_loss_stop', text: 'Loss stop reached', fired_at: '2026-11-27T10:00:00+05:30', fired_line: 'Fired at 10:00', answer: 'closed_by_system', answer_label: 'Closed: the position ended', answered_at: '2026-11-27T10:23:00+05:30', closed_reason: 'Closed by system: the trade closed at 10:23' }] } })
    const page = await mountAt('/alerts/history', AlertsPage)
    const t = ids(page, 'answered-row')[0].text()
    expect(t).toContain('Closed by system: the trade closed at 10:23')
    expect(t).not.toContain('the position ended')
  })
})
