// Lane TB (R2, 28 Nov) I-98: the Positions > Paper stop line names its leg with the one date rule ("1 Dec", never "2026-12-01"). Extends one-date-formatter-d57.test.js
// with the paper-stops.test.js harness; the legs expire 2026-12-01 (real shape: contract_text from the server carries the ISO date).
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

const leg = (i, over = {}) => withPriceTexts({
  leg_index: i, instrument_id: String(5000 + i), action: i % 2 ? 'SELL' : 'BUY', instrument: i < 2 ? 'PE' : 'CE',
  strike: `${22300 + i * 100}.00`, expiry: '2026-12-01', quantity: 65, entry_price: '114.25', entry_at: '2026-10-28T05:03:09Z',
  current_price: '113.60', price_state: 'live', price_at: '2026-10-28T11:30:00+05:30', exit_price: null, exited_at: null, ...over,
})
const item = withPriceTexts({
  strategy_id: 48, name: '"GCTP IC"', underlying: 'NIFTY', started_at: '2026-10-28T05:03:10Z', state: 'LIVE',
  pause_reason: null, as_of: null, total: '71.50', booked: '0.00', unbooked: '71.50', legs: [leg(0), leg(1)],
})
const trig = (id, over = {}) => ({ id, strategy_id: 48, kind: 'conditional_exit', direction: 'above', level: '24500.00',
  level_text: 'Index at or above 24,500.00', contract_id: null, contract_text: null, underlying: 'NIFTY', state: 'armed',
  created_at: '2026-10-29T05:00:00Z', fired_at: null, cancelled_at: null, ...over })
const ok = (data) => () => Promise.resolve({ data })
const t = (w, id) => w.get(`[data-testid="${id}"]`)
const TRIG = '/paper/strategies/48/triggers'

async function open(triggers = { triggers: [] }) {
  answers['GET /tracking'] = ok({ strategies: [item], answered_at: '2026-10-28T06:00:00Z' })
  answers[`GET ${TRIG}`] = ok(triggers)
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }, { path: '/strategy/builder', component: { template: '<div/>' } }] })
  router.push('/')
  await router.isReady()
  const w = mount(PaperStrategies, { global: { plugins: [router] } })
  await flushPromises()
  await t(w, 'stops-open-48').trigger('click')
  await flushPromises()
  return w
}

beforeEach(() => { calls.length = 0; answers = {} })

describe('I-98 the stop line date reads "1 Dec"', () => {
  it('I-98: an armed leg stop on a leg expiring 2026-12-01 names the leg with "1 Dec", never the ISO date', async () => {
    const w = await open({ triggers: [trig(7, { kind: 'leg_stop', contract_id: 5000, direction: 'above', level: '110.00', level_text: 'Above 110.00', contract_text: 'NIFTY 22300 PE 2026-12-01' })] })
    const row = w.get('[data-testid="trigger-row"]').text()
    expect(row).toContain('1 Dec')
    expect(row).not.toMatch(/2026-12-01/)
  })
  it('I-98: the same leg in the Stop form (its row label) and in the Positions list read "1 Dec"', async () => {
    const w = await open()
    expect(w.text()).toContain('1 Dec')
    expect(w.text()).not.toMatch(/\d{4}-\d{2}-\d{2}/)
  })
  // DEFECT (PaperStops.vue:279): when the stop's contract is not among the open legs the row falls back to the server's contract_text, which carries
  // the ISO date. it.fails = the body states the right behaviour and fails in the app today; change to `it` when the row formats the date.
  it.fails('I-98: a leg stop whose contract is not among the open legs (closed leg) still never prints the ISO date', async () => {
    const w = await open({ triggers: [trig(8, { kind: 'leg_stop', contract_id: 9999, contract_text: 'NIFTY 22300 PE 2026-12-01', level_text: 'Above 110.00' })] })
    expect(w.get('[data-testid="trigger-row"]').text()).not.toMatch(/2026-12-01/)
  })
})
