// P7 page flow (ADR-330 (2)(b), (33); ADR-002, ADR-003): a side_closed row on Alerts > Active offers the server's two answers.
// "Add the legs again" stores add_legs then opens the builder of that strategy (the builder cannot be told a side: it shows the
// strategy and the server's notice). "Confirm the new shape" first shows the server's sentence naming the shape that remains;
// Confirm stores confirm_new_shape, Cancel stores nothing and the row stays asking. Real case 25 Nov: strategy 7, call side exited.
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

import AlertsPage from '@/pages/AlertsPage.vue'
import { activeAlerts, resetActiveAlerts, resetOpenRecords } from '@/lib/paperAlerts'

const CONFIRM = 'The call side of this trade is closed. Add the legs again, or confirm the new shape: this strategy will change from its entry shape to Bull Put Spread.'
const sideClosed = (over = {}) => ({
  id: 5, strategy_id: 7, strategy_name: '"Trade 7"', kind: 'side_closed',
  text: CONFIRM,
  fired_at: '2026-11-25T05:32:20Z', fired_line: 'Fired at 11:02', no_longer_true_since: null, no_longer_true_line: null,
  escalated_at: null, worse_line: null,
  answers: [{ code: 'add_legs', label: 'Add the legs again' }, { code: 'confirm_new_shape', label: 'Confirm the new shape' }], ...over,
})
const other = () => ({
  id: 1, strategy_id: 7, strategy_name: '"Trade 7"', kind: 'plan_loss_stop', text: 'Loss stop reached', fired_at: '2026-11-25T05:32:20Z',
  fired_line: 'Fired at 11:02', no_longer_true_since: null, no_longer_true_line: null, escalated_at: null, worse_line: null,
  answers: [{ code: 'exit', label: 'Exit the position' }, { code: 'continue', label: 'Continue with the position' }],
})
const list = (...a) => () => Promise.resolve({ data: { count: a.length, alerts: a } })

let r
async function mountPage() {
  r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:p(.*)*', component: { template: '<div/>' } }] })
  r.push('/alerts/active')
  await r.isReady()
  const w = mount(AlertsPage, { global: { plugins: [r] }, attachTo: document.body })
  await flushPromises()
  return w
}
const posts = () => calls.filter((c) => c.method === 'POST')
const click = async (w, id) => { await w.get(`[data-testid="${id}"]`).trigger('click'); await flushPromises() }
const parts = (m) => ({ what_happened: m, impact: '', what_is_blocked: '', next_action: '' })

beforeEach(() => {
  answers = {}
  calls = []
  resetActiveAlerts()
  resetOpenRecords()
  answers['GET /alerts/active'] = list(sideClosed())
  answers['POST /alerts/5/answer'] = () => Promise.resolve({ data: { id: 5 } })
})
afterEach(() => { document.body.innerHTML = '' })

describe('P7 side_closed answers on Alerts > Active', () => {
  it('core: Add the legs stores add_legs, then opens the builder of strategy 7', async () => {
    const w = await mountPage()
    await click(w, 'alert-answer-add_legs')
    expect(posts()).toEqual([{ method: 'POST', url: '/alerts/5/answer', body: { answer: 'add_legs' } }])
    expect(r.currentRoute.value.path).toBe('/strategy/builder')
    expect(r.currentRoute.value.query.strategy).toBe('7')
  })
  it('add legs: the answer call fails -> the reason shows, nothing navigates', async () => {
    answers['POST /alerts/5/answer'] = () => Promise.reject({ message: 'x', parts: parts('The answer was not saved.'), status: 500 })
    const w = await mountPage()
    await click(w, 'alert-answer-add_legs')
    expect(w.get('[data-testid="alert-answer-error"]').text()).toContain('The answer was not saved.')
    expect(r.currentRoute.value.path).toBe('/alerts/active')
  })
  it('add legs: a 409 shows the server text, re-reads Active, nothing navigates', async () => {
    answers['POST /alerts/5/answer'] = () => Promise.reject({ message: 'x', parts: parts('Already answered.'), status: 409 })
    answers['GET /alerts/active'] = list(sideClosed())
    const w = await mountPage()
    const reads = calls.filter((c) => c.url === '/alerts/active').length
    await click(w, 'alert-answer-add_legs')
    expect(w.get('[data-testid="alert-answer-error"]').text()).toContain('Already answered.')
    expect(calls.filter((c) => c.url === '/alerts/active').length).toBe(reads + 1)
    expect(r.currentRoute.value.path).toBe('/alerts/active')
  })
  it('confirm new shape: shows the server sentence first and stores nothing yet', async () => {
    const w = await mountPage()
    await click(w, 'alert-answer-confirm_new_shape')
    expect(w.get('[data-testid="side-closed-confirm"]').text()).toContain(CONFIRM)
    expect(posts()).toHaveLength(0)
  })
  it('confirm new shape: Confirm stores confirm_new_shape and stays on Alerts', async () => {
    const w = await mountPage()
    await click(w, 'alert-answer-confirm_new_shape')
    await click(w, 'side-closed-confirm-yes')
    expect(posts()).toEqual([{ method: 'POST', url: '/alerts/5/answer', body: { answer: 'confirm_new_shape' } }])
    expect(r.currentRoute.value.path).toBe('/alerts/active')
    expect(w.find('[data-testid="side-closed-confirm"]').exists()).toBe(false)
  })
  it('confirm new shape: Cancel stores nothing, the row stays asking with both answers', async () => {
    const w = await mountPage()
    await click(w, 'alert-answer-confirm_new_shape')
    await click(w, 'side-closed-confirm-no')
    expect(posts()).toHaveLength(0)
    expect(w.find('[data-testid="side-closed-confirm"]').exists()).toBe(false)
    expect(w.find('[data-testid="alert-answer-add_legs"]').exists() && w.find('[data-testid="alert-answer-confirm_new_shape"]').exists()).toBe(true)
    expect(activeAlerts.alerts).toHaveLength(1)
  })
  it('confirm new shape: the server sent no text -> nothing is stored (fail closed), the neutral reason shows', async () => {
    answers['GET /alerts/active'] = list(sideClosed({ text: '' }))
    const w = await mountPage()
    await click(w, 'alert-answer-confirm_new_shape')
    expect(posts()).toHaveLength(0)
    expect(w.find('[data-testid="side-closed-confirm"]').exists()).toBe(false)
    expect(w.find('[data-testid="alert-answer-error"]').exists()).toBe(true)
  })
  it('confirm new shape: the store call fails after Confirm -> the reason shows and the row stays', async () => {
    answers['POST /alerts/5/answer'] = () => Promise.reject({ message: 'x', parts: parts('The answer was not saved.'), status: 500 })
    const w = await mountPage()
    await click(w, 'alert-answer-confirm_new_shape')
    await click(w, 'side-closed-confirm-yes')
    expect(w.get('[data-testid="alert-answer-error"]').text()).toContain('The answer was not saved.')
    expect(w.findAll('[data-testid="alert-row"]')).toHaveLength(1)
  })
  it('another kind is unchanged: Continue posts at once, no confirmation, no navigation', async () => {
    answers['GET /alerts/active'] = list(other())
    answers['POST /alerts/1/answer'] = () => Promise.resolve({ data: { id: 1 } })
    const w = await mountPage()
    await click(w, 'alert-answer-continue')
    expect(posts()).toEqual([{ method: 'POST', url: '/alerts/1/answer', body: { answer: 'continue' } }])
    expect(w.find('[data-testid="side-closed-confirm"]').exists()).toBe(false)
    expect(r.currentRoute.value.path).toBe('/alerts/active')
  })
})
