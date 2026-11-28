// P1 round 3 (ADR-330 (3), (4); REQ-170 AC-3; ADR-326 (5) / D-67): ONE announcement per actionable alert event (a new id, or the
// same id with a later escalated_at); never two pop-ups for one plan stop. Real case 25 Nov 2026: a plan loss stop showed the
// Active pop-up and the adjustment-opportunity pop-up on one tick.
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
import { resetActiveAlerts, resetOpenRecords } from '@/lib/paperAlerts'
import { TRACKING_REFRESH_MS } from '@/lib/tracking'
import { toasts } from '@/composables/useToast'

const row = (id, extra = {}) => ({
  id, strategy_id: 7, strategy_name: `"Trade ${id}"`, kind: 'plan_loss_stop', text: `Loss stop ${id} reached`,
  fired_at: '2026-11-25T05:32:20Z', fired_line: 'Fired at 11:02', no_longer_true_since: null, no_longer_true_line: null,
  escalated_at: null, worse_line: null, position_kind: 'paper', position_kind_text: null, answers: [{ code: 'exit', label: 'Exit the position' }, { code: 'continue', label: 'Continue' }], ...extra,
})
const active = (...rows) => () => Promise.resolve({ data: { count: rows.length, alerts: rows } })
const opp = (...recs) => () => Promise.resolve({ data: { groups: [{ group: 'g', strategy_id: 7, strategy_name: 'T', records: recs }] } })
const rec = (id, extra = {}) => ({ id, outcome: 'open', condition: `rule ${id}`, ...extra })

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

beforeEach(() => {
  answers = {}
  resetActiveAlerts()
  resetOpenRecords()
  vi.useFakeTimers()
  toasts.splice(0)
})
afterEach(() => { vi.useRealTimers() })

describe('M4: one pop-up for one plan stop', () => {
  it('a plan_loss_stop in /alerts/active AND as an open adjustment record on the same tick raises exactly one pop-up', async () => {
    answers['GET /alerts/active'] = active()
    answers['GET /adjustment-opportunities'] = opp()
    await mountAt('/', AppHeader)
    answers['GET /alerts/active'] = active(row(5))
    answers['GET /adjustment-opportunities'] = opp(rec(5))
    await tick()
    expect(toasts).toHaveLength(1)
    await tick()
    expect(toasts).toHaveLength(1)
  })
  it('a quiet record (popup_due false) holds the pop-up back; it raises once on the poll that finds it due', async () => {
    answers['GET /alerts/active'] = active()
    answers['GET /adjustment-opportunities'] = opp()
    await mountAt('/', AppHeader)
    answers['GET /alerts/active'] = active(row(5, { kind: 'adjustment_rule' }))
    answers['GET /adjustment-opportunities'] = opp(rec(5, { popup_due: false }))
    await tick()
    expect(toasts).toHaveLength(0)
    answers['GET /adjustment-opportunities'] = opp(rec(5, { popup_due: true }))
    await tick()
    expect(toasts).toHaveLength(1)
    await tick()
    expect(toasts).toHaveLength(1)
  })
})

describe('F3: a later escalation announces once more', () => {
  it('same id, later escalated_at: one more pop-up carrying the worse_line; the same pair again: none', async () => {
    answers['GET /alerts/active'] = active(row(5))
    answers['GET /adjustment-opportunities'] = opp(rec(5))
    await mountAt('/', AppHeader)
    expect(toasts).toHaveLength(0)
    const worse = { escalated_at: '2026-11-25T06:00:00Z', worse_line: 'Worse than when it fired: 16.2000 % (fired at 15.5750 %)' }
    answers['GET /alerts/active'] = active(row(5, worse))
    await tick()
    expect(toasts).toHaveLength(1)
    expect(JSON.stringify(toasts[0])).toContain('Worse than when it fired: 16.2000 %')
    toasts.splice(0)
    await tick()
    expect(toasts).toHaveLength(0)
    answers['GET /alerts/active'] = active(row(5, { ...worse, escalated_at: '2026-11-25T06:05:00Z' }))
    await tick()
    expect(toasts).toHaveLength(1)
  })
})

describe('M6: Alerts page', () => {
  it('a 409 refusal re-reads Active at once and Exit does not navigate', async () => {
    let list = active(row(1), row(2))
    answers['GET /alerts/active'] = () => list()
    answers['POST /alerts/1/answer'] = () => {
      list = active(row(2))
      return Promise.reject({ message: 'x', status: 409, parts: { what_happened: 'Already answered.', impact: 'i', what_is_blocked: 'b', next_action: 'n' } })
    }
    vi.useRealTimers()
    const page = await mountAt('/alerts/active', AlertsPage)
    await page.get('[data-testid="alert-answer-exit"]').trigger('click')
    await flushPromises()
    expect(page.findAll('[data-testid="alert-row"]')).toHaveLength(1)
    expect(r.currentRoute.value.path).toBe('/alerts/active')
  })
  it('an Active row and a History item show worse_line when present, and nothing when null', async () => {
    const w = 'Worse than when it fired: 16.2000 % (fired at 15.5750 %)'
    answers['GET /alerts/active'] = active(row(1, { worse_line: w, escalated_at: '2026-11-25T06:00:00Z' }), row(2))
    vi.useRealTimers()
    const page = await mountAt('/alerts/active', AlertsPage)
    const rows = page.findAll('[data-testid="alert-row"]')
    expect(rows[0].text()).toContain(w)
    expect(rows[1].find('[data-testid="alert-worse"]').exists()).toBe(false)
    answers['GET /alerts/answered'] = () => Promise.resolve({ data: { items: [{ id: 3, strategy_id: 7, strategy_name: '"T"', kind: 'plan_loss_stop', text: 'Loss', fired_line: 'Fired at 11:02', answer: 'continue', answer_label: 'Continue', answered_at: '2026-11-25T11:09:00+05:30', closed_reason: null, worse_line: w }] } })
    answers['GET /paper/alerts/records'] = () => Promise.resolve({ data: { records: [] } })
    const hist = await mountAt('/alerts/history', AlertsPage)
    expect(hist.get('[data-testid="answered-row"]').text()).toContain(w)
  })
})
