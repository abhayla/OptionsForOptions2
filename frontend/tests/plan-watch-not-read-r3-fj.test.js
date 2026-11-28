// Lane FJ r3 (28 Nov 2026), PC W-03 tail: a plan-watch row the batch answers "not_read" is not an answer: it is RE-ASKED in the next batch and shown
// "Updating the numbers..." (never "not available"); the rows that did come back are untouched. After the re-asks run out the plain not-read line shows.
// Spec basis: ADR-330 (13), (64); REQ-049; REQ-119 AC-4 (the one "updating" wording).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'
import PlanWatch from '@/components/strategy/PlanWatch.vue'
import { legacy } from './_paperList'
import { withPriceTexts } from './_priceTexts'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push(`${method} ${url}`)
    const a = legacy(answers, method, url)
    if (a === undefined) return Promise.reject(Object.assign(new Error(`unmocked ${method} ${url}`), { parts: null, status: null }))
    return typeof a === 'function' ? a(body) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u, b) => respond('POST', u, b), put: (u, b) => respond('PUT', u, b) } }
})

const watchOf = (id) => ({
  strategy_id: id, as_of: '2026-11-26T05:10:00Z', as_of_text: 'As of 10:40:00 AM IST', plan_state: 'planned', no_plan_text: null, armed_heading: null,
  paused: null, lines: [{ key: 'T-07', kind: 'target', section: 'plan', label: 'Profit target', unit: 'pnl_rupees', fires_at: '1200.00', now: '350.00', distance_rs: '850.00', distance_pct: '70.83', state: 'watching', reason: null }],
})

import { resetPlanWatchQueueForTests, PLAN_WATCH_COMPACT_PAGE_GAP_MS } from '@/lib/planWatchQueue'
import { PLAN_WATCH_NOT_READ } from '@/lib/planWatchBatch'

const FAKE = ['setInterval', 'clearInterval', 'setTimeout', 'clearTimeout', 'Date']
afterEach(() => vi.useRealTimers())
beforeEach(() => { vi.useFakeTimers({ toFake: FAKE }); resetPlanWatchQueueForTests(); calls.length = 0 })
const leg = (i) => withPriceTexts({
  leg_index: i, instrument_id: `NSE_FO:${i + 1}`, action: 'SELL', instrument: 'PE', strike: `${22300 + i * 100}.00`, expiry: '2026-11-03',
  quantity: 65, entry_price: '114.25', entry_at: '2026-10-28T05:03:09Z', current_price: '113.60', price_state: 'live',
  price_at: '2026-10-28T11:30:00+05:30', exit_price: null, exited_at: null,
})
const item = (id) => withPriceTexts({ strategy_id: id, name: `"S${id}"`, underlying: 'NIFTY', started_at: '2026-10-28T05:03:10Z', state: 'LIVE', pause_reason: null, as_of: null, total: '71.50', booked: '0.00', unbooked: '71.50', legs: [leg(0), leg(1)] })
const okItem = (id) => ({ strategy_id: id, state: 'ok', watch: watchOf(id) })
async function open(first, retry) {
  answers = { 'GET /tracking': { strategies: [item(48), item(49)], answered_at: '2026-10-28T06:00:00Z' }, 'GET /plan-watch?strategy_ids=48,49': first, 'GET /plan-watch?strategy_ids=49': retry }
  let n = 0
  const firstThen = answers['GET /plan-watch?strategy_ids=48,49']
  answers['GET /plan-watch?strategy_ids=48,49'] = () => { n += 1; return Promise.resolve({ data: n === 1 ? firstThen : { items: [okItem(48), ...retry.items] } }) }
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: PaperStrategies }] })
  await router.push('/')
  await router.isReady()
  const w = mount(PaperStrategies, { global: { plugins: [router] } })
  await flushPromises()
  return w
}
const boxOf = (w, id) => w.findAllComponents(PlanWatch).find((b) => b.props('strategyId') === id)

describe('plan watch rows answered not_read', () => {
  it('only part of the rows not_read: the good row shows its figure, the not_read row says "Updating the numbers..." and is re-asked alone in the next batch', async () => {
    const w = await open({ items: [okItem(48), { strategy_id: 49, state: 'not_read' }] }, { items: [okItem(49)] })
    expect(boxOf(w, 48).find('[data-testid="pw-now"]').text()).toBe('₹350.00')
    expect(boxOf(w, 49).text()).toContain('Updating the numbers...')
    expect(boxOf(w, 49).text()).not.toContain('not available')
    expect(boxOf(w, 49).text()).not.toContain(PLAN_WATCH_NOT_READ)
    await vi.advanceTimersByTimeAsync(PLAN_WATCH_COMPACT_PAGE_GAP_MS + 1000)
    await flushPromises()
    expect(calls.filter((c) => c.includes('/plan-watch?strategy_ids=')).length).toBeGreaterThan(1) // the next batch asks the not_read row again
    expect(boxOf(w, 49).find('[data-testid="pw-now"]').text()).toBe('₹350.00')
    expect(boxOf(w, 48).find('[data-testid="pw-now"]').text()).toBe('₹350.00') // the row that came back is untouched
  })
  it('a row that stays not_read keeps being asked by every batch and never reads "not available"', async () => {
    const nr = { items: [{ strategy_id: 49, state: 'not_read' }] }
    const w = await open({ items: [okItem(48), { strategy_id: 49, state: 'not_read' }] }, nr)
    for (let i = 0; i < 6; i += 1) { await vi.advanceTimersByTimeAsync(PLAN_WATCH_COMPACT_PAGE_GAP_MS + 1000); await flushPromises() }
    expect(boxOf(w, 49).text()).toContain('Updating the numbers...') // a poll batch keeps asking; the row is never shown as "not available"
    expect(boxOf(w, 49).text()).not.toContain('not available')
  })
})
