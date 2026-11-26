// W2-B (ADR-330 (3), (12); ADR-003, ADR-002): the Alerts page "Exit the position" stores the answer, then opens the ONE shared paper
// exit confirmation (PaperStrategies' door: usePaperExit gate + PaperConfirmDialog + addToPaper) for that alert's strategy, on the page.
// Nothing exits before the user confirms there. Real case 25 Nov: the alert on strategy 7 sent the user to the builder instead.
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
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'
import { resetActiveAlerts, resetOpenRecords } from '@/lib/paperAlerts'
import { withPriceTexts } from './_priceTexts'
import { toPaperList } from './_paperList'

const alertRow = (id, sid = 7) => ({
  id, strategy_id: sid, strategy_name: `"Trade ${id}"`, kind: 'plan_loss_stop', text: `Loss stop ${id} reached`,
  fired_at: '2026-11-25T05:32:20Z', fired_line: 'Fired at 11:02', no_longer_true_since: null, no_longer_true_line: null,
  answers: [{ code: 'exit', label: 'Exit the position' }, { code: 'continue', label: 'Continue with the position' }],
})
const leg = (i, over = {}) => withPriceTexts({
  leg_index: i, instrument_id: `NSE_FO:${i + 1}`, action: i % 2 ? 'SELL' : 'BUY', instrument: i < 2 ? 'PE' : 'CE',
  strike: `${22300 + i * 100}.00`, expiry: '2026-11-03', quantity: 65, entry_price: '114.25', entry_at: '2026-10-28T05:03:09Z',
  current_price: '113.60', price_state: 'live', price_at: '2026-10-28T11:30:00+05:30', exit_price: null, exited_at: null, ...over,
})
const strat = (over = {}) => withPriceTexts({
  strategy_id: 7, name: '"Trade 1"', underlying: 'NIFTY', started_at: '2026-10-28T05:03:10Z', state: 'LIVE',
  pause_reason: null, as_of: null, total: '71.50', booked: '0.00', unbooked: '71.50', legs: [leg(0), leg(1), leg(2), leg(3)], ...over,
})
const paperList = (...s) => () => Promise.resolve({ data: toPaperList({ strategies: s, answered_at: '2026-10-28T06:00:00Z' }) })

let r
async function mountPage() {
  r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:p(.*)*', component: { template: '<div/>' } }] })
  r.push('/alerts/active')
  await r.isReady()
  const w = mount(AlertsPage, { global: { plugins: [r] }, attachTo: document.body })
  await flushPromises()
  return w
}
const dialog = (w) => w.findComponent(PaperConfirmDialog)
const posts = () => calls.filter((c) => c.method === 'POST')
const exitPosts = () => posts().filter((c) => /\/paper\/strategies\/\d+\/orders/.test(c.url))
const clickExit = async (w) => { await w.get('[data-testid="alert-answer-exit"]').trigger('click'); await flushPromises() }

beforeEach(() => {
  answers = {}
  calls = []
  resetActiveAlerts()
  resetOpenRecords()
  answers['GET /alerts/active'] = () => Promise.resolve({ data: { count: 1, alerts: [alertRow(1)] } })
  answers['POST /alerts/1/answer'] = () => Promise.resolve({ data: { id: 1 } })
})
afterEach(() => { document.body.innerHTML = '' })

describe('W2-B Alerts Exit opens the shared exit confirmation', () => {
  it('core: stores the answer, opens the shared confirmation for strategy 7, posts no exit before Confirm, stays on Alerts', async () => {
    answers['GET /paper/strategies'] = paperList(strat())
    const w = await mountPage()
    await clickExit(w)
    expect(posts()[0]).toEqual({ method: 'POST', url: '/alerts/1/answer', body: { answer: 'exit' } }) // (a)
    expect(dialog(w).props('open')).toBe(true) // (b)
    expect(dialog(w).props('strategyId')).toBe(7)
    expect(dialog(w).props('orders')).toHaveLength(4)
    expect(dialog(w).props('orders').every((o) => o.kind === 'exit')).toBe(true)
    expect(exitPosts()).toHaveLength(0) // (c)
    expect(r.currentRoute.value.path).toBe('/alerts/active')
  })
  it('confirmed: ONE exit post to /paper/strategies/7/orders, then the dialog closes', async () => {
    answers['GET /paper/strategies'] = paperList(strat())
    answers['POST /paper/strategies/7/orders'] = () => Promise.resolve({ data: { stored: true } })
    const w = await mountPage()
    await clickExit(w)
    dialog(w).vm.$emit('confirm', dialog(w).props('orders'))
    await flushPromises()
    expect(exitPosts()).toHaveLength(1)
    expect(exitPosts()[0].url).toBe('/paper/strategies/7/orders')
    expect(w.findComponent(PaperConfirmDialog).exists()).toBe(false)
  })
  it('cancelled: nothing exited, the answer stays stored, the dialog is gone', async () => {
    answers['GET /paper/strategies'] = paperList(strat())
    const w = await mountPage()
    await clickExit(w)
    dialog(w).vm.$emit('cancel')
    await flushPromises()
    expect(exitPosts()).toHaveLength(0)
    expect(posts().filter((c) => c.url === '/alerts/1/answer')).toHaveLength(1)
    expect(w.findComponent(PaperConfirmDialog).exists()).toBe(false)
  })
  it('the answer call fails: says so, the exit door is not opened and no list is read', async () => {
    answers['GET /paper/strategies'] = paperList(strat())
    answers['POST /alerts/1/answer'] = () => Promise.reject({ message: 'Network Error', parts: null, status: null })
    const w = await mountPage()
    await clickExit(w)
    expect(w.get('[data-testid="alert-answer-error"]').text().length).toBeGreaterThan(0)
    expect(w.findComponent(PaperConfirmDialog).exists()).toBe(false)
    expect(calls.some((c) => c.url === '/paper/strategies')).toBe(false)
  })
  it('strategy already flat: the door\'s own note, no dialog, no exit post', async () => {
    answers['GET /paper/strategies'] = paperList(strat({ state: 'EXITED' }))
    const w = await mountPage()
    await clickExit(w)
    expect(w.get('[data-testid="paper-exit-link-note"]').text()).toBe('This strategy has no open paper legs to exit.')
    expect(dialog(w).props('open')).toBe(false)
    expect(exitPosts()).toHaveLength(0)
  })
  it('strategy not on the list: the same note', async () => {
    answers['GET /paper/strategies'] = paperList(strat({ strategy_id: 99 }))
    const w = await mountPage()
    await clickExit(w)
    expect(w.get('[data-testid="paper-exit-link-note"]').text()).toBe('This strategy has no open paper legs to exit.')
    expect(dialog(w).props('open')).toBe(false)
  })
  it('the paper read fails: no dialog from old prices, the door says the read failed', async () => {
    answers['GET /paper/strategies'] = () => Promise.reject({ message: 'x', parts: null, status: 500 })
    const w = await mountPage()
    await clickExit(w)
    expect(w.findComponent(PaperConfirmDialog).exists() && dialog(w).props('open')).toBeFalsy()
    expect(w.find('[data-testid^="paper-error"]').exists()).toBe(true)
    expect(exitPosts()).toHaveLength(0)
  })
  it('Continue opens no exit door and reads no paper list', async () => {
    answers['GET /paper/strategies'] = paperList(strat())
    const w = await mountPage()
    await w.get('[data-testid="alert-answer-continue"]').trigger('click')
    await flushPromises()
    expect(w.findComponent(PaperConfirmDialog).exists()).toBe(false)
    expect(calls.some((c) => c.url === '/paper/strategies')).toBe(false)
  })
})
