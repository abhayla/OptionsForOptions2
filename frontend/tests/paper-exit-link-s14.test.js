// S-14 (ADR-330 (10), ADR-207): the Live card's Exit is a link to the Paper tab with `exit=<id>`; PaperStrategies opens its OWN
// exit confirm (the one door: usePaperExit gate + PaperConfirmDialog) for all open legs. Nothing is posted until the user confirms.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
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
  return { ...actual, default: { get: reply('GET'), post: reply('POST') } }
})

import { withPriceTexts } from './_priceTexts'
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'

const leg = (i, over = {}) => withPriceTexts({
  leg_index: i, instrument_id: `NSE_FO:${i + 1}`, action: i % 2 ? 'SELL' : 'BUY', instrument: i < 2 ? 'PE' : 'CE',
  strike: `${22300 + i * 100}.00`, expiry: '2026-11-03', quantity: 65, entry_price: '114.25', entry_at: '2026-10-28T05:03:09Z',
  current_price: '113.60', price_state: 'live', price_at: '2026-10-28T11:30:00+05:30', exit_price: null, exited_at: null, ...over,
})
const item = (over = {}) => withPriceTexts({
  strategy_id: 48, name: '"GCBP P3 IC"', underlying: 'NIFTY', started_at: '2026-10-28T05:03:10Z', state: 'LIVE',
  pause_reason: null, as_of: null, total: '71.50', booked: '0.00', unbooked: '71.50', legs: [leg(0), leg(1), leg(2), leg(3)], ...over,
})
const REAL_REPLY = { strategies: [item()], answered_at: '2026-10-28T06:00:00Z' }
const ok = (data) => () => Promise.resolve({ data })


async function showAt(path) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }, { path: '/positions/current-positions', component: { template: '<div/>' } }, { path: '/strategy/builder', component: { template: '<div/>' } }] })
  router.push(path)
  await router.isReady()
  const w = mount(PaperStrategies, { global: { plugins: [router] } })
  await flushPromises()
  return { w, router }
}
beforeEach(() => { calls.length = 0; answers = {}; vi.useFakeTimers() })
afterEach(() => vi.useRealTimers())
const dialog = (w) => w.findComponent(PaperConfirmDialog)

describe('S-14 exit link target on the Paper list', () => {
  it('?exit=48 opens the exit confirm for all open legs, titled with "paper", and posts nothing', async () => {
    answers['GET /tracking'] = ok(REAL_REPLY)
    const { w, router } = await showAt('/positions/current-positions?tab=paper&strategy=48&exit=48')
    expect(dialog(w).props('open')).toBe(true)
    expect(dialog(w).props('orders')).toHaveLength(4)
    expect(dialog(w).props('orders').every((o) => o.kind === 'exit')).toBe(true)
    expect(document.body.textContent + w.text()).toMatch(/Exit paper positions/)
    expect(calls.filter((c) => c[0] === 'POST')).toHaveLength(0)
    expect(router.currentRoute.value.query.exit).toBeUndefined() // not re-opened by the next refresh
  })
  it('no exit query: no dialog', async () => {
    answers['GET /tracking'] = ok(REAL_REPLY)
    const { w } = await showAt('/positions/current-positions?tab=paper&strategy=48')
    expect(dialog(w).props('open')).toBe(false)
  })
  it('exit query for a strategy not on the list: no dialog', async () => {
    answers['GET /tracking'] = ok(REAL_REPLY)
    const { w } = await showAt('/positions/current-positions?tab=paper&exit=99')
    expect(dialog(w).props('open')).toBe(false)
  })
  it('a failed read (gate blocked): no dialog from old prices', async () => {
    answers['GET /tracking'] = () => Promise.reject({ message: 'x', parts: null, status: 500 })
    const { w } = await showAt('/positions/current-positions?tab=paper&exit=48')
    expect(dialog(w).props('open')).toBe(false)
  })
})
