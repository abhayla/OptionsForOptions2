// Lane FC2 (R2, 28 Nov) D-7, D-8, D-11 on the Positions / compact paper list (PaperStrategies.vue).
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import REAL from './fixtures/paper-strategies.json'

let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url) => {
    const a = answers[`${method} ${url}`]
    return a ? a() : Promise.reject({ message: 'no answer', parts: null, status: null })
  }
  return { ...actual, default: { get: reply('GET'), post: reply('POST'), delete: reply('DELETE') } }
})
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'
import { resetActiveAlerts } from '@/lib/paperAlerts'

const PAUSED = 'Paper P&L paused - prices not live'
const clone = () => JSON.parse(JSON.stringify(REAL))
async function show(props = {}) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: PaperStrategies }, { path: '/strategy/builder', component: { template: '<div/>' } }, { path: '/positions/:p(.*)*', component: { template: '<div/>' } }] })
  router.push('/')
  await router.isReady()
  const w = mount(PaperStrategies, { props, global: { plugins: [router] } })
  await flushPromises()
  return w
}
beforeEach(() => { answers = {}; resetActiveAlerts(); vi.useFakeTimers() })
afterEach(() => vi.useRealTimers())

describe('D-7 the underlying and the status word are apart', () => {
  it('"NIFTY" and "Running" are separated by a space in the card text', async () => {
    const d = clone()
    d.strategies.find((s) => s.state === 'LIVE').status_word = 'Running'
    answers['GET /paper/strategies'] = () => Promise.resolve({ data: d })
    const w = await show()
    const card = w.get('[data-testid="paper-group"][data-strategy="1"]')
    expect(card.text()).toContain('NIFTY Running')
    expect(card.text()).not.toContain('NIFTYRunning')
  })
})

describe('D-8 a closed row has no empty cell', () => {
  it('Unbooked and P&L of a closed leg show the dash (—), the booked figure stays', async () => {
    const d = clone()
    const s = d.strategies.find((x) => x.state === 'LIVE')
    s.closed = [{ contract_id: 901, contract_text: 'NIFTY 24200 CE 2026-12-08', instrument: 'CE', strike: '24200.00', expiry: '2026-12-08', quantity: 65, lots: 1, side: 'SELL', opened_at: '2026-11-26T04:00:00Z', average_entry_text: '98.00', average_exit_text: '90.00', booked_text: '+520.00', reason_text: null }]
    answers['GET /paper/strategies'] = () => Promise.resolve({ data: d })
    const w = await show()
    await w.get('[data-testid="show-closed"]').setValue(true)
    const row = w.get('[data-testid="paper-closed-leg"]')
    const cells = row.findAll('td').map((c) => c.text())
    expect(cells).toHaveLength(8)
    expect(cells[5]).toBe('+520.00')
    expect(cells[6]).toBe('—')
    expect(cells[7]).toBe('—')
    expect(cells.slice(1).every((c) => c !== '')).toBe(true)
  })
})

describe('D-11 the paused sentence is printed once under a paused compact row', () => {
  it('paused book with the server pause text and the state text: one sentence', async () => {
    const d = clone()
    const s = d.strategies.find((x) => x.state === 'LIVE')
    Object.assign(s, { state: 'PAUSED', total_text: null, total: null, pause_reason: 'prices_not_live', pause_reason_text: PAUSED, as_of: '2026-11-27T09:57:00Z' })
    answers['GET /paper/strategies'] = () => Promise.resolve({ data: d })
    const w = await show({ compact: true })
    const row = w.get(`[data-testid="paper-compact-row"][data-strategy="${s.strategy_id}"]`)
    expect(row.text().split(PAUSED).length - 1).toBe(1)
  })
})

// UX-A09 (ADR-330 (56)): the feed is paused and every open strategy was PAUSED: the page says it once, the tiles carry no sentence.
describe('UX-A09 one paused notice for the page', () => {
  const pausedList = (ids) => {
    const d = clone()
    for (const s of d.strategies.filter((x) => ids.includes(x.strategy_id))) {
      Object.assign(s, { state: 'PAUSED', total_text: null, total: null, unbooked_text: null, unbooked: null, pause_reason: 'prices_not_live', pause_reason_text: PAUSED, as_of: '2026-11-27T09:57:00Z' })
    }
    Object.assign(d.totals, { total_text: null, total: null, unbooked_text: null, unbooked: null, totals_reason: 'prices_not_live', totals_reason_text: PAUSED, totals_as_of: '2026-11-27T09:57:00Z' })
    return d
  }
  const count = (w) => w.text().split(PAUSED).length - 1
  it('two paused strategies: the sentence appears once on the page, as the page notice with its time', async () => {
    answers['GET /paper/strategies'] = () => Promise.resolve({ data: pausedList([1, 3]) })
    const w = await show()
    expect(count(w)).toBe(1)
    expect(w.get('[data-testid="paper-paused-notice"]').text()).toContain(PAUSED)
    expect(w.get('[data-testid="paper-paused-notice"]').text()).toContain('as of')
  })
  it('the page already shows its own notice (noticeUp): the list says nothing of its own', async () => {
    answers['GET /paper/strategies'] = () => Promise.resolve({ data: pausedList([1, 3]) })
    const w = await show({ noticeUp: true })
    expect(count(w)).toBe(0)
    expect(w.find('[data-testid="paper-paused-notice"]').exists()).toBe(false)
  })
  it('exactly one paused strategy: no page notice, that tile carries its line (unchanged)', async () => {
    answers['GET /paper/strategies'] = () => Promise.resolve({ data: pausedList([1]) })
    const w = await show()
    expect(w.find('[data-testid="paper-paused-notice"]').exists()).toBe(false)
    expect(w.get('[data-testid="paper-group"][data-strategy="1"]').text()).toContain(PAUSED)
  })
  it('the Paper total the list hands to the page carries no paused sentence of its own (the page notice speaks)', async () => {
    answers['GET /paper/strategies'] = () => Promise.resolve({ data: pausedList([1, 3]) })
    const w = await show()
    expect(w.emitted('summary').at(-1)[0].totalAfter.reason ?? null).toBe(null)
  })
  it('the list tells the page how many are affected', async () => {
    answers['GET /paper/strategies'] = () => Promise.resolve({ data: pausedList([1, 3]) })
    const w = await show()
    expect(w.emitted('summary').at(-1)[0].affected).toBe(2)
  })
})

import { priceNoticeUp } from '@/lib/priceState'
describe('priceNoticeUp follows PriceNotice', () => {
  it('closed: up; live: down; not live with 1 affected: down; with 2: up; unknown count: up', () => {
    expect(priceNoticeUp({ market_closed: true, last_price_at: '2026-11-27T10:00:00Z', state: 'LIVE' }, null)).toBe(true)
    expect(priceNoticeUp({ state: 'LIVE' }, null)).toBe(false)
    expect(priceNoticeUp({ state: 'STALE' }, 1)).toBe(false)
    expect(priceNoticeUp({ state: 'STALE' }, 2)).toBe(true)
    expect(priceNoticeUp({ state: 'STALE' }, null)).toBe(true)
    expect(priceNoticeUp(null, 3)).toBe(false)
  })
})
