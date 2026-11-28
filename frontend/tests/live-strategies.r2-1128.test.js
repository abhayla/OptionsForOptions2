// Lane TB (R2, 28 Nov) I-94. Extends live-strategies.test.js: a Completed strategy (every leg closed) has no Exit and no Stops link on
// the Positions > Paper card, and no card at all on Live Strategies (ADR-259: Completed leaves Live Strategies). A Running card is the
// control: it does have both, so the absences are not vacuous. Harness of paper-stops.test.js.
// (base harness) GC-TP step 7b (REQ-109 AC-8; ADR-207 (5); screens 221-224): arming a Conditional exit or a leg Stop on a paper strategy,
// listing and cancelling its triggers. Levels are sent as typed strings; every figure shown is the server's text.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

const calls = []
let answers = {}
import { legacy } from './_paperList'
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url, body) => {
    calls.push([method, url, body])
    const a = legacy(answers, method, url)
    return a ? a() : Promise.reject({ message: 'no answer', parts: null, status: null })
  }
  return { ...actual, default: { get: reply('GET'), post: reply('POST'), delete: reply('DELETE') } }
})

import { withPriceTexts } from './_priceTexts'
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'
import LiveStrategiesPage from '@/pages/LiveStrategiesPage.vue'

const leg = (i, over = {}) => withPriceTexts({
  leg_index: i, instrument_id: String(5000 + i), action: i % 2 ? 'SELL' : 'BUY', instrument: i < 2 ? 'PE' : 'CE',
  strike: `${22300 + i * 100}.00`, expiry: '2026-11-03', quantity: 65, entry_price: '114.25', entry_at: '2026-10-28T05:03:09Z',
  current_price: '113.60', price_state: 'live', price_at: '2026-10-28T11:30:00+05:30', exit_price: null, exited_at: null, ...over,
})
const item = withPriceTexts({ status_word: 'Running',
  strategy_id: 48, name: '"GCTP IC"', underlying: 'NIFTY', started_at: '2026-10-28T05:03:10Z', state: 'LIVE',
  pause_reason: null, as_of: null, total: '71.50', booked: '0.00', unbooked: '71.50', legs: [leg(0), leg(1)],
})
const ok = (data) => () => Promise.resolve({ data })



const closedLeg = (i) => leg(i, { exit_price: '120.00', exited_at: '2026-10-29T09:00:00Z', current_price: null, price_state: null })
const done = { ...item, status_word: 'Completed', state: 'EXITED', legs: [closedLeg(0), closedLeg(1)] }
async function openList(strategies) {
  answers['GET /tracking'] = ok({ strategies, answered_at: '2026-10-29T10:00:00Z' })
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }, { path: '/strategy/builder', component: { template: '<div/>' } }] })
  router.push('/')
  await router.isReady()
  const w = mount(PaperStrategies, { global: { plugins: [router] } })
  await flushPromises()
  return w
}
beforeEach(() => { calls.length = 0; answers = {} })

describe('I-94 a Completed card has no Exit and no Stops link', () => {
  it('control: a Running paper card shows the Stops link and Exit', async () => {
    const w = await openList([item])
    expect(w.find('[data-testid="stops-open-48"]').exists()).toBe(true)
    expect(w.find('[data-testid="exit-selected-48"]').exists()).toBe(true)
  })
  it('I-94: a paper strategy with every leg closed shows no Stops link, no Exit button, no per-row Exit tick, and no stops panel', async () => {
    const w = await openList([done])
    await w.get('[data-testid="show-closed"]').setValue(true) // Completed cards are listed only with Show closed positions
    await flushPromises()
    expect(w.text()).toContain('GCTP IC') // the Completed card IS listed; it just has no Exit or Stops
    expect(w.find('[data-testid="stops-open-48"]').exists()).toBe(false)
    expect(w.find('[data-testid="exit-selected-48"]').exists()).toBe(false)
    expect(w.find('[data-testid="paper-stops"]').exists()).toBe(false)
    expect(w.findAll('button').map((b) => b.text()).filter((x) => /^(Exit|Stops?)\b/.test(x))).toEqual([])
  })
  it('I-94: with a Running and a Completed card side by side, only the Running one has the links', async () => {
    const w = await openList([item, { ...done, strategy_id: 49 }])
    await w.get('[data-testid="show-closed"]').setValue(true)
    await flushPromises()
    expect(w.findAll('[data-testid="paper-count"]')).toHaveLength(2)
    expect(w.find('[data-testid="stops-open-48"]').exists()).toBe(true)
    expect(w.find('[data-testid="stops-open-49"]').exists()).toBe(false)
    expect(w.find('[data-testid="exit-selected-49"]').exists()).toBe(false)
  })
})

describe('I-94 Live Strategies lists no Completed card', () => {
  it('I-94: a Completed strategy gets no card, so no Exit and no Stops link; the empty line points to Completed Strategies', async () => {
    answers['GET /strategies'] = ok({ strategies: [{ id: 5, underlying: 'NIFTY', status: 'closed', status_word: 'Completed', created_at: '2026-10-19T10:00:00+05:30', updated_at: '2026-10-19T10:00:00+05:30' }] })
    answers['GET /market/indices'] = () => Promise.reject(new Error('indices failed'))
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }, { path: '/strategies/completed-strategies', component: { template: '<div/>' } }] })
    router.push('/')
    await router.isReady()
    const w = mount(LiveStrategiesPage, { global: { plugins: [router] } })
    await flushPromises()
    expect(w.findAll('[data-testid="live-strategy-card"]')).toHaveLength(0)
    expect(w.text()).not.toMatch(/\bExit\b|\bStops\b/)
    expect(w.text()).toContain('Completed Strategies')
    w.unmount()
  })
})
