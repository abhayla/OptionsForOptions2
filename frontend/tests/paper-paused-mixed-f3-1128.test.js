// Lane F3 item 6 (I-209, TG D-TG-5): Positions > Paper with 8 strategies in a MIX of states printed the paused sentence 8 times (19 with
// repeats). Real case: 3 PAUSED (as_of), 3 NOT_CONNECTED (no broker session), 2 stored closes (LIVE with as_of). The sentence once at the top.
// Lane FJ2 item 1 (28 Nov 2026). Real case: Lane TG, Positions > Paper with 8 paused strategies printed
// "Paper P&L paused - prices not live" 8 times (twice per running card), with no date and time in the market-closed state.
// T1-20: Home lacks the as-of part. Wanted: the sentence ONCE on the page, with its as-of time.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import REAL0 from './fixtures/paper-strategies.json'

let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url) => {
    const a = answers[`${method} ${url}`]
    return a ? a() : Promise.reject({ message: 'no answer', parts: null, status: null })
  }
  return { ...actual, default: { get: reply('GET'), post: reply('POST') } }
})
import PositionsPage from '@/pages/PositionsPage.vue'

const PAUSED = 'Paper P&L paused - prices not live'
const ok = (data) => () => Promise.resolve({ data })
const eight = (asOf, state = 'PAUSED') => {
  const d = JSON.parse(JSON.stringify(REAL0))
  const live = d.strategies.find((s) => s.state === 'LIVE')
  d.strategies = Array.from({ length: 8 }, (_, i) => ({
    ...JSON.parse(JSON.stringify(live)), strategy_id: 100 + i, name: `S${i}`, state, total_text: null, total: null, unbooked_text: null, unbooked: null,
    pause_reason: 'prices_not_live', pause_reason_text: PAUSED, as_of: asOf,
    positions: live.positions.map((p) => ({ ...p, price_state: p.net_quantity ? 'stale' : null, ltp: null, ltp_text: null })),
  }))
  Object.assign(d.totals, { total_text: null, total: null, unbooked_text: null, unbooked: null, totals_reason: 'prices_not_live', totals_reason_text: PAUSED, totals_as_of: asOf, after_charges_reason: 'prices_not_live' })
  return d
}
async function page() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/p', component: PositionsPage, meta: { title: 'T', parent: 'Positions', view: 'current' } }, { path: '/positions/current-positions', component: { template: '<div/>' } }, { path: '/strategy/builder', component: { template: '<div/>' } }] })
  router.push('/p')
  await router.isReady()
  const w = mount(PositionsPage, { attachTo: document.body, global: { plugins: [router] } })
  await flushPromises()
  return w
}
beforeEach(() => { answers = {}; vi.useFakeTimers() })
afterEach(() => { vi.useRealTimers(); document.body.innerHTML = '' })


const mixed = (asOf) => {
  const d = eight(asOf)
  const states = ['PAUSED', 'PAUSED', 'PAUSED', 'NOT_CONNECTED', 'NOT_CONNECTED', 'NOT_CONNECTED', 'LIVE', 'LIVE']
  d.strategies.forEach((s, i) => {
    s.state = states[i]
    if (s.state === 'LIVE') Object.assign(s, { total_text: '+100.00', total: '100.00', pause_reason: null, pause_reason_text: null, as_of: asOf })
    if (s.state === 'NOT_CONNECTED') Object.assign(s, { as_of: null })
  })
  return d
}
describe('F3-6: mixed states, the sentence once', () => {
  for (const asOf of ['2026-11-06T06:10:00Z', null]) {
    it(`3 paused + 3 not connected + 2 stored closes (as_of ${asOf}): the paused sentence once; the stored closes say their time`, async () => {
      answers['GET /paper/strategies'] = ok(mixed(asOf))
      answers['GET /positions'] = () => Promise.resolve({ data: { read_at: '2026-11-06T06:10:00Z', real_pnl: null, strategies: [], has_outside: false, outside_lots: 0, blocked: false, blocked_strategy_ids: [], broker_connected: false } })
      answers['GET /features'] = ok({ order_path: 'on' })
      const w = await page()
      expect(w.text().split(PAUSED).length - 1).toBe(1)
      expect(w.text().split('Paper P&L paused').length - 1).toBeLessThanOrEqual(1) // neither wording repeats
      if (asOf) { expect(w.text()).toContain(`${PAUSED}, as of`); expect(w.findAll('[data-testid="paper-state"]').filter((n) => n.text().startsWith('As of')).length).toBe(2) }
    })
  }
})
