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

describe('FJ2-1b: no broker session (state NOT_CONNECTED), the server still words each reason "prices not live" (TG D-TG-5)', () => {
  for (const asOf of ['2026-11-06T06:10:00Z', null]) {
    it(`8 strategies not connected (as_of ${asOf}): once on the page`, async () => {
      answers['GET /paper/strategies'] = ok(eight(asOf, 'NOT_CONNECTED'))
      answers['GET /positions'] = () => Promise.reject({ status: 409, message: 'x', parts: null })
      answers['GET /features'] = ok({ order_path: 'on' })
      const w = await page()
      expect(w.text().split(PAUSED).length - 1).toBe(1)
      if (asOf) expect(w.text()).toContain(`${PAUSED}, as of`)
    })
  }
})

describe('FJ2-1: the paused sentence once, with its as-of time', () => {
  for (const asOf of ['2026-11-06T06:10:00Z', null]) {
    it(`8 paused strategies (as_of ${asOf}): the page prints the sentence exactly once`, async () => {
      answers['GET /paper/strategies'] = ok(eight(asOf))
      answers['GET /positions'] = () => Promise.reject({ status: 409, message: 'x', parts: null })
      answers['GET /features'] = ok({ order_path: 'on' })
      const w = await page()
      const n = w.text().split(PAUSED).length - 1
      expect(n).toBe(1)
      if (asOf) expect(w.text()).toContain(`${PAUSED}, as of`)
    })
  }
})
