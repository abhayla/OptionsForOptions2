// Spec basis: ADR-330 point (73) (owner 28 Nov: real and paper same screens; a real action is only stored, nothing sent to Zerodha); ADR-016 to ADR-019; ADR-281.
// Lane R2: Alerts for a REAL position offer the same Exit answer as paper and carry the stored-not-sent line; unknown stays locked.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url) => (answers[`${method} ${url}`] ? answers[`${method} ${url}`]() : Promise.reject({ message: 'no answer', parts: null, status: null }))
  return { ...actual, default: { get: reply('GET'), post: reply('POST') } }
})
import AlertsPage from '@/pages/AlertsPage.vue'
import { resetActiveAlerts, resetOpenRecords } from '@/lib/paperAlerts'

const NOT_SENT = 'Not sent to Zerodha. Place it in Kite.'
const row = (id, extra = {}) => ({ id, strategy_id: 7, strategy_name: `"Trade ${id}"`, kind: 'plan_loss_stop', text: `Loss stop ${id} reached`, fired_at: '2026-11-25T05:32:20Z', fired_line: 'Fired at 11:02',
  no_longer_true_since: null, no_longer_true_line: null, position_kind: 'real', position_kind_text: null, answers: [{ code: 'exit', label: 'Exit the position' }, { code: 'continue', label: 'Continue with the position' }], ...extra })
async function open(path, rows) {
  answers['GET /alerts/active'] = () => Promise.resolve({ data: { count: rows.length, alerts: rows } })
  answers['GET /alerts/answered'] = () => Promise.resolve({ data: { alerts: [] } })
  answers['GET /paper/alerts/records'] = () => Promise.resolve({ data: { records: [] } })
  const r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:p(.*)*', component: { template: '<div/>' } }] })
  r.push(path)
  await r.isReady()
  const w = mount(AlertsPage, { global: { plugins: [r] } })
  await flushPromises()
  return w
}
beforeEach(() => { answers = {}; resetActiveAlerts(); resetOpenRecords() })

describe('R2 Alerts: a real position', () => {
  it('shows the Exit answer, the real row line and the not-sent note before the press', async () => {
    const w = await open('/alerts/active', [row(1)])
    expect(w.find('[data-testid="alert-answer-exit"]').exists()).toBe(true)
    expect(w.get('[data-testid="alert-position-kind-line"]').text()).toContain('Real position')
    expect(w.get('[data-testid="alert-not-sent-line"]').text()).toBe(NOT_SENT)
  })
  it('a stored action prints its record line with the time and price', async () => {
    const w = await open('/alerts/active', [row(2, { stored_not_sent: true, record: { action: 'stop_fired', stored_at: '2026-11-28T10:32:00+05:30', price: '99.00' } })])
    expect(w.get('[data-testid="alert-record-line"]').text()).toBe(`Stop reached 10:32:00 at 99.00. ${NOT_SENT}`)
  })
  it('unknown kind: no Exit answer, the line says why (fail closed); paper has no not-sent line', async () => {
    const w = await open('/alerts/active', [row(3, { position_kind: 'unknown' }), row(4, { position_kind: 'paper' })])
    const rows = w.findAll('[data-testid="alert-row"]')
    expect(rows[0].find('[data-testid="alert-answer-exit"]').exists()).toBe(false)
    expect(rows[0].get('[data-testid="alert-position-kind-line"]').text()).toContain('Cannot tell')
    expect(rows[1].find('[data-testid="alert-answer-exit"]').exists()).toBe(true)
    expect(rows[1].find('[data-testid="alert-not-sent-line"]').exists()).toBe(false)
  })
  it('the history record of a fired real stop carries the same line; a paper record does not', async () => {
    answers['GET /alerts/active'] = () => Promise.resolve({ data: { count: 0, alerts: [] } })
    answers['GET /alerts/answered'] = () => Promise.resolve({ data: { alerts: [] } })
    answers['GET /paper/alerts/records'] = () => Promise.resolve({ data: { records: [
      { kind: 'stop', title: 'Stop reached', at: '2026-11-28T05:00:00Z', strategy_id: 7, strategy_name: '"A"', body: 'Your stop was reached', stored_not_sent: true, record: { action: 'stop_fired', price: '99.00', stored_at: '2026-11-28T10:32:00+05:30' } },
      { kind: 'stop', title: 'Stop reached', at: '2026-11-28T05:01:00Z', strategy_id: 8, strategy_name: '"B"', body: 'Your stop was reached' }] } })
    const r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:p(.*)*', component: { template: '<div/>' } }] })
    r.push('/alerts/history')
    await r.isReady()
    const w = mount(AlertsPage, { global: { plugins: [r] } })
    await flushPromises()
    const recs = w.findAll('[data-testid="record-row"]')
    expect(recs[0].get('[data-testid="record-not-sent"]').text()).toContain(NOT_SENT)
    expect(recs[1].find('[data-testid="record-not-sent"]').exists()).toBe(false)
  })
})
