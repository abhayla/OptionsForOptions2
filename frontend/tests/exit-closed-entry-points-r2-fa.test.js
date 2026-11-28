// Lane FA r2, #874 (ADR-330 (60), ADR-212): with the market closed the Exit dialog opens from BOTH entry points (Positions and Alerts), lists the
// legs it would close, shows the server's one sentence and has Confirm greyed; nothing is posted. Expected text is written here.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

let answers = {}
let calls = []
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url, body) => {
    calls.push({ method, url, body })
    const a = answers[`${method} ${url}`]
    return a ? a() : Promise.reject({ message: 'no answer', parts: null, status: null })
  }
  return { ...actual, default: { get: reply('GET'), post: reply('POST'), delete: reply('DELETE') } }
})
import AlertsPage from '@/pages/AlertsPage.vue'
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'
import { resetActiveAlerts, resetOpenRecords } from '@/lib/paperAlerts'
import { withPriceTexts } from './_priceTexts'
import { toPaperList } from './_paperList'

const SENTENCE = 'The market is closed. Exits can be placed from 09:15 on Monday 30 Nov.'
let legState = 'closed' // r3 FJ: with the market closed no leg is live; the open-market test sets 'live'
const leg = (i) => withPriceTexts({
  leg_index: i, instrument_id: `NSE_FO:${i + 1}`, action: i % 2 ? 'SELL' : 'BUY', instrument: i < 2 ? 'PE' : 'CE',
  strike: `${22300 + i * 100}.00`, expiry: '2026-12-01', quantity: 65, entry_price: '114.25', entry_at: '2026-10-28T05:03:09Z',
  current_price: '113.60', price_state: legState, price_at: '2026-10-28T11:30:00+05:30', exit_price: null, exited_at: null,
})
const strat = () => withPriceTexts({ strategy_id: 7, name: '"Trade 1"', underlying: 'NIFTY', started_at: '2026-10-28T05:03:10Z', state: 'LIVE',
  pause_reason: null, as_of: null, total: '71.50', booked: '0.00', unbooked: '71.50', legs: [leg(0), leg(1), leg(2), leg(3)] })
const list = () => Promise.resolve({ data: toPaperList({ strategies: [strat()], answered_at: '2026-10-28T06:00:00Z' }) })
const alertRow = { id: 1, strategy_id: 7, strategy_name: '"Trade 1"', kind: 'plan_loss_stop', text: 'Loss stop 1 reached', fired_at: '2026-11-25T05:32:20Z',
  fired_line: 'Fired at 11:02', no_longer_true_since: null, no_longer_true_line: null, position_kind: 'paper', position_kind_text: null,
  answers: [{ code: 'exit', label: 'Exit the position' }, { code: 'continue', label: 'Continue with the position' }] }
const t = (w, id) => w.get(`[data-testid="${id}"]`)
const orderPosts = () => calls.filter((c) => c.method === 'POST' && /\/orders$/.test(c.url))
const mounted = []
const CATCH_ALL = [{ path: '/:rest(.*)', component: { template: '<div/>' } }]

beforeEach(() => {
  legState = 'closed'
  calls = []
  resetActiveAlerts()
  resetOpenRecords()
  answers = {
    'GET /paper/strategies': list,
    'GET /market/exit-state': () => Promise.resolve({ data: { closed: true, sentence: SENTENCE, next_open_at: '2026-11-30T09:15:00+05:30' } }),
    'GET /alerts/active': () => Promise.resolve({ data: { count: 1, alerts: [alertRow] } }),
    'POST /alerts/1/answer': () => Promise.resolve({ data: { id: 1 } }),
    'GET /paper/strategies/7/triggers': () => Promise.resolve({ data: { triggers: [] } }),
  }
})
afterEach(() => { while (mounted.length) mounted.pop().unmount(); document.body.innerHTML = '' })

async function positions() {
  const r = createRouter({ history: createMemoryHistory(), routes: CATCH_ALL })
  r.push('/')
  await r.isReady()
  const w = mount(PaperStrategies, { global: { plugins: [r] }, attachTo: document.body })
  mounted.push(w)
  await flushPromises()
  await t(w, 'select-leg-7-1').setValue(true)
  await t(w, 'exit-selected-7').trigger('click')
  await flushPromises()
  return w
}

describe('closed market: the Exit dialog from both entry points', () => {
  it('Alerts "Exit the position": the dialog lists the 4 legs, shows the sentence, Confirm is greyed, nothing is posted', async () => {
    const r = createRouter({ history: createMemoryHistory(), routes: CATCH_ALL })
    r.push('/alerts/active')
    await r.isReady()
    const w = mount(AlertsPage, { global: { plugins: [r] }, attachTo: document.body })
    mounted.push(w)
    await flushPromises()
    await t(w, 'alert-answer-exit').trigger('click')
    await flushPromises()
    expect(w.findAll('[data-testid="paper-order"]')).toHaveLength(4)
    expect(t(w, 'paper-market-closed').text()).toBe(SENTENCE)
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeDefined()
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(orderPosts()).toHaveLength(0)
  })
  it('Positions Exit (ticked leg): same dialog, same sentence, Confirm greyed, nothing is posted', async () => {
    const w = await positions()
    expect(w.findAll('[data-testid="paper-order"]')).toHaveLength(1)
    expect(t(w, 'paper-market-closed').text()).toBe(SENTENCE)
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeDefined()
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(orderPosts()).toHaveLength(0)
  })
  it('the same Positions Exit with the market OPEN: Confirm is enabled (the test above is not vacuous)', async () => {
    legState = 'live'
    answers['GET /market/exit-state'] = () => Promise.resolve({ data: { closed: false, sentence: null, next_open_at: null } })
    const w = await positions()
    expect(w.find('[data-testid="paper-market-closed"]').exists()).toBe(false)
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeUndefined()
  })
})
