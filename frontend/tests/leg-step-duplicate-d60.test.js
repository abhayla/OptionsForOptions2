// D-60 stage A5 (ADR-319, REQ-030 AC-11/AC-12; review finding 2): a move through /strategies/leg-edit (strike step, Shift, Width,
// Hedge) that lands a leg on a contract another leg holds with the SAME action asks through the one shared check
// (legDoor admitLegs): "<contract> is already in this strategy." with Increase quantity / Keep separate / Cancel. Real page,
// real recorded condor (outcome-condor.json: SELL 22800 CE 44624, BUY 23000 CE 44632, SELL 22400 PE 44604, BUY 22200 PE 44595).
// The fake server answers with the legs it landed; leg 0 (SELL 22800 CE) is stepped onto SELL 22400 PE (held, same action), onto
// BUY 23000 CE's id with SELL (held, OTHER action: no question) or onto a free contract (no question).
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const { withPriceTexts } = await import('./_priceTexts.js')
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    const a = answers[`${method} ${url}`]
    if (a === undefined && url.startsWith('/paper/strategies/')) return Promise.reject({ status: 404 })
    if (a === undefined && url === '/settings') return Promise.resolve({ data: settingsData() })
    if (a === undefined) return Promise.reject(new Error(`unmocked ${method} ${url}`))
    return typeof a === 'function' ? a(body) : Promise.resolve({ data: withPriceTexts(a) })
  }
  return { ...actual, default: { get: (url) => respond('GET', url), post: (url, body) => respond('POST', url, body) } }
})
import { settingsData } from './helpers/servedLots'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import { DUP_QUESTION } from '@/lib/legDoor'
import real from './fixtures/outcome-condor.json'

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const all = (w, id) => w.findAll(`[data-testid="${id}"]`)
const DRAFT = { underlying: 'NIFTY', legs: real.legs.map((l) => ({ instrument_id: l.instrument_id, action: l.action, lots: l.lots,
  planned_entry: l.planned_entry, captured_at: l.captured_at })) }
const replyLeg = (l, extra = {}) => ({ instrument_id: l.instrument_id, action: l.action, instrument: l.instrument, strike: l.strike,
  expiry: l.expiry, lots: l.lots, base_lots: l.lots, quantity: l.quantity, planned_entry: l.planned_entry, captured_at: l.captured_at,
  price_source: 'captured', included: true, hedge: false, block: null, ...extra })
const READ = { legs: real.legs.map((l) => replyLeg(l)), shape: 'iron_condor', shape_name: 'Short Iron Condor', outcome: real,
  controls: { shift: true, width: true, hedge: true }, shift_total: 0 }
const SELL_PE = real.legs[2] // 22400 PE, SELL, held

// the fake server: leg 0 lands on `onto` (a leg of the recorded condor, or a free contract); every other leg is as sent
const landing = (onto, over = {}) => (body) => Promise.resolve({ data: landedBody(onto, over, body) })
const landedBody = (onto, over, body) => ({
  seq: body.seq, shape: null, shape_name: null, outcome: null, controls: { shift: true, width: true, hedge: true }, shift_total: 50,
  legs: body.legs.map((sent, i) => (i === 0
    ? replyLeg(real.legs[0], { instrument_id: onto.instrument_id, instrument: onto.instrument, strike: onto.strike, ...over })
    : replyLeg(real.legs[i], { instrument_id: sent.instrument_id }))),
})
const FREE = { instrument_id: 'NSE_FO:44700', instrument: 'CE', strike: '22850' }

beforeEach(() => {
  calls.length = 0
  answers = {}
})
async function openPage() {
  answers['POST /strategies/outcome'] = real
  answers['POST /strategies/leg-edit'] = READ
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await router.push({ path: '/strategy/builder', query: { draft: JSON.stringify(DRAFT) } })
  await router.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true } } })
  await flushPromises()
  return w
}
const ids = (w) => w.vm.$.setupState.legs.map((l) => l.instrument_id)
const lotsOf = (w) => w.vm.$.setupState.legs.map((l) => l.lots)
const BEFORE = real.legs.map((l) => l.instrument_id)
const NAME = 'NIFTY 13 Oct 22400 PE'

describe('D-60 A5: a step onto a contract another leg holds with the same action asks', () => {
  it('Core: the strike step lands on the held SELL 22400 PE -> the question names it; nothing is applied before the answer', async () => {
    const w = await openPage()
    answers['POST /strategies/leg-edit'] = landing(SELL_PE)
    await all(w, 'strike-plus')[0].trigger('click')
    await flushPromises()
    expect(t(w, 'dup-question').text()).toBe(DUP_QUESTION(NAME))
    expect(t(w, 'dup-increase').exists() && t(w, 'dup-separate').exists() && t(w, 'dup-cancel').exists()).toBe(true)
    expect(ids(w)).toEqual(BEFORE) // the legs are still the ones before the step
  })

  it('a step onto a FREE contract does not ask and moves the leg', async () => {
    const w = await openPage()
    answers['POST /strategies/leg-edit'] = landing(FREE)
    await all(w, 'strike-plus')[0].trigger('click')
    await flushPromises()
    expect(t(w, 'dup-question').exists()).toBe(false)
    expect(ids(w)[0]).toBe(FREE.instrument_id)
  })

  it('a step onto a contract held with the OTHER action does not ask (two legs, REQ-030 AC-11)', async () => {
    const w = await openPage()
    answers['POST /strategies/leg-edit'] = landing(real.legs[1]) // BUY 23000 CE is held; the stepped leg is a SELL
    await all(w, 'strike-plus')[0].trigger('click')
    await flushPromises()
    expect(t(w, 'dup-question').exists()).toBe(false)
    expect(ids(w)[0]).toBe(real.legs[1].instrument_id)
  })

  it('Cancel keeps every leg exactly as before the step', async () => {
    const w = await openPage()
    answers['POST /strategies/leg-edit'] = landing(SELL_PE)
    await all(w, 'strike-plus')[0].trigger('click')
    await flushPromises()
    await t(w, 'dup-cancel').trigger('click')
    await flushPromises()
    expect(ids(w)).toEqual(BEFORE)
    expect(lotsOf(w)).toEqual([1, 1, 1, 1])
    expect(t(w, 'dup-question').exists()).toBe(false)
  })

  it('Keep separate applies the step: two rows on the contract, legs not merged', async () => {
    const w = await openPage()
    answers['POST /strategies/leg-edit'] = landing(SELL_PE)
    await all(w, 'strike-plus')[0].trigger('click')
    await flushPromises()
    await t(w, 'dup-separate').trigger('click')
    await flushPromises()
    expect(ids(w)).toEqual([SELL_PE.instrument_id, BEFORE[1], SELL_PE.instrument_id, BEFORE[3]])
    expect(lotsOf(w)).toEqual([1, 1, 1, 1])
    expect(t(w, 'dup-question').exists()).toBe(false)
  })

  it('Increase quantity adds the stepped leg\'s lots to the held row; the stepped row is gone (3 legs, lots 2)', async () => {
    const w = await openPage()
    answers['POST /strategies/leg-edit'] = landing(SELL_PE)
    await all(w, 'strike-plus')[0].trigger('click')
    await flushPromises()
    await t(w, 'dup-increase').trigger('click')
    await flushPromises()
    expect(ids(w)).toEqual([BEFORE[1], SELL_PE.instrument_id, BEFORE[3]])
    expect(lotsOf(w)).toEqual([1, 2, 1])
  })

  it('Increase past the served lots limit changes nothing and says why (the picker\'s sentence)', async () => {
    const w = await openPage()
    answers['POST /strategies/leg-edit'] = landing(SELL_PE, { lots: 10000 })
    await all(w, 'strike-plus')[0].trigger('click')
    await flushPromises()
    await t(w, 'dup-increase').trigger('click')
    await flushPromises()
    expect(ids(w)).toEqual(BEFORE)
    expect(t(w, 'edit-error').text()).toContain('Lots must be a whole number from 1 to')
  })

  it('Shift onto a held contract asks too (every relative control passes the same door)', async () => {
    const w = await openPage()
    answers['POST /strategies/leg-edit'] = landing(SELL_PE)
    await t(w, 'shift-plus').trigger('click')
    await flushPromises()
    expect(calls.filter((c) => c.body?.edit?.control === 'shift')).toHaveLength(1)
    expect(t(w, 'dup-question').text()).toBe(DUP_QUESTION(NAME))
    await t(w, 'dup-cancel').trigger('click')
    await flushPromises()
    expect(ids(w)).toEqual(BEFORE)
  })

  it('the question survives a parent refresh: the outcome re-read does not remove it', async () => {
    const w = await openPage()
    answers['POST /strategies/leg-edit'] = landing(SELL_PE)
    await all(w, 'strike-plus')[0].trigger('click')
    await flushPromises()
    await w.vm.$nextTick()
    expect(t(w, 'dup-question').exists()).toBe(true)
  })
})
