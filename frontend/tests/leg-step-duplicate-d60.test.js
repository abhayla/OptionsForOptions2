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

// D-60 round 2 (review A5 findings 1-3): exactly one live question per move, moved legs checked against each other
describe('D-60 round 2: a newer move cancels the open question', () => {
  const step = (w) => w.vm.$.setupState.editLeg({ control: 'step', index: 0, direction: 1 })
  const track = (p) => { const s = { done: false }; p.then(() => { s.done = true }); return s }

  it('a second step onto a FREE contract closes the old question, settles the first edit and shows the second move', async () => {
    const w = await openPage()
    answers['POST /strategies/leg-edit'] = landing(SELL_PE)
    const first = track(step(w))
    await flushPromises()
    expect(all(w, 'dup-question')).toHaveLength(1)
    answers['POST /strategies/leg-edit'] = landing(FREE)
    const second = track(step(w))
    await flushPromises()
    expect(t(w, 'dup-question').exists()).toBe(false)
    expect(first.done).toBe(true) // no hang: the first edit's finally ran
    expect(second.done).toBe(true)
    expect(ids(w)[0]).toBe(FREE.instrument_id)
    expect(lotsOf(w)).toEqual([1, 1, 1, 1])
  })

  it('a second step onto a held contract leaves ONE question and answering it applies to the second move', async () => {
    const w = await openPage()
    answers['POST /strategies/leg-edit'] = landing(SELL_PE)
    const first = track(step(w))
    await flushPromises()
    answers['POST /strategies/leg-edit'] = landing(SELL_PE, { lots: 3 })
    const second = track(step(w))
    await flushPromises()
    expect(all(w, 'dup-question')).toHaveLength(1)
    expect(first.done).toBe(true)
    await t(w, 'dup-increase').trigger('click')
    await flushPromises()
    expect(second.done).toBe(true)
    expect(ids(w)).toEqual([BEFORE[1], SELL_PE.instrument_id, BEFORE[3]])
    expect(lotsOf(w)).toEqual([1, 4, 1]) // the second move's 3 lots, not the first move's 1
  })

  it('Width collapsing the two BUY wings onto one contract asks (moved against moved)', async () => {
    const w = await openPage()
    answers['POST /strategies/leg-edit'] = (body) => Promise.resolve({ data: {
      seq: body.seq, shape: null, shape_name: null, outcome: null, controls: { shift: true, width: true, hedge: true }, shift_total: 0,
      legs: real.legs.map((l, i) => replyLeg(l, i === 1 || i === 3 ? { instrument_id: FREE.instrument_id, instrument: 'CE', strike: '22850' } : {})),
    } })
    await t(w, 'width-minus').trigger('click')
    await flushPromises()
    expect(all(w, 'dup-question')).toHaveLength(1)
    await t(w, 'dup-cancel').trigger('click')
    await flushPromises()
    expect(ids(w)).toEqual(BEFORE)
  })

  it('Hedge keeps the leg count and order: moving one hedge leg to a free contract asks nothing (finding 3)', async () => {
    const w = await openPage()
    answers['POST /strategies/leg-edit'] = (body) => Promise.resolve({ data: {
      seq: body.seq, shape: null, shape_name: null, outcome: null, controls: { shift: true, width: true, hedge: true }, shift_total: 0,
      legs: real.legs.map((l, i) => replyLeg(l, i === 1 ? { instrument_id: FREE.instrument_id, hedge: true } : {})),
    } })
    await t(w, 'hedge-plus').trigger('click')
    await flushPromises()
    expect(t(w, 'dup-question').exists()).toBe(false)
    expect(ids(w)[1]).toBe(FREE.instrument_id)
    expect(ids(w).length).toBe(4)
  })
})

// D-60 round 3 (review A5 round 2, findings 1-3)
describe('D-60 round 3: net-zero step closes the question; Increase keeps base lots; legs changed under the dialog', () => {
  const step = (w, direction = 1) => w.vm.$.setupState.editLeg({ control: 'step', index: 0, direction })
  const track = (p) => { const s = { done: false }; p.then(() => { s.done = true }); return s }

  it('step onto a held contract, step back (+1 then -1 nets to zero): no question on screen, no hanging edit, legs as before', async () => {
    const w = await openPage()
    answers['POST /strategies/leg-edit'] = landing(SELL_PE)
    const first = track(step(w, 1))
    await flushPromises()
    expect(all(w, 'dup-question')).toHaveLength(1)
    const back = track(step(w, -1))
    await flushPromises()
    expect(t(w, 'dup-question').exists()).toBe(false)
    expect(first.done).toBe(true)
    expect(back.done).toBe(true)
    expect(ids(w)).toEqual(BEFORE)
    expect(lotsOf(w)).toEqual([1, 1, 1, 1])
  })

  it('step Increase then multiplier x1 keeps the total (base lots rise with lots)', async () => {
    const w = await openPage()
    answers['POST /strategies/leg-edit'] = landing(SELL_PE)
    await all(w, 'strike-plus')[0].trigger('click')
    await flushPromises()
    await t(w, 'dup-increase').trigger('click')
    await flushPromises()
    expect(lotsOf(w)).toEqual([1, 2, 1])
    expect(w.vm.$.setupState.legs.map((l) => l.base_lots)).toEqual([1, 2, 1])
    calls.length = 0
    answers['POST /strategies/leg-edit'] = (body) => Promise.resolve({ data: {
      seq: body.seq, shape: null, shape_name: null, outcome: null, controls: { shift: true, width: true, hedge: true }, shift_total: 0,
      legs: body.legs.map((l, i) => replyLeg(real.legs[i % 4], { instrument_id: l.instrument_id, action: l.action, lots: l.base_lots * 1, base_lots: l.base_lots })),
    } })
    await w.vm.$.setupState.editLeg({ control: 'multiplier', multiplier: 1 })
    await flushPromises()
    const sent = calls.find((c) => c.url === '/strategies/leg-edit')
    expect(sent.body.legs.map((l) => l.base_lots)).toEqual([1, 2, 1])
    expect(lotsOf(w)).toEqual([1, 2, 1])
  })

  it('legs changed while the question is open are not overwritten: the answer is treated as Cancel', async () => {
    const w = await openPage()
    answers['POST /strategies/leg-edit'] = landing(SELL_PE)
    const p = track(step(w, 1))
    await flushPromises()
    expect(all(w, 'dup-question')).toHaveLength(1)
    const changed = w.vm.$.setupState.legs.map((l, i) => (i === 3 ? { ...l, lots: 5, base_lots: 5 } : l))
    w.vm.$.setupState.legs = changed
    await t(w, 'dup-increase').trigger('click')
    await flushPromises()
    expect(p.done).toBe(true)
    expect(ids(w)).toEqual(BEFORE)
    expect(lotsOf(w)).toEqual([1, 1, 1, 5])
  })
})

describe('D-60 round 4: replacing the legs closes the open question; an equal-content refresh keeps the answer', () => {
  const step = (w, direction = 1) => w.vm.$.setupState.editLeg({ control: 'step', index: 0, direction })
  const track = (p) => { const s = { done: false }; p.then(() => { s.done = true }); return s }
  const openQuestion = async (w) => {
    answers['POST /strategies/leg-edit'] = landing(SELL_PE)
    const p = track(step(w, 1))
    await flushPromises()
    expect(all(w, 'dup-question')).toHaveLength(1)
    return p
  }

  it('route change to another strategy (new ?draft=) closes the question and settles the edit', async () => {
    const w = await openPage()
    const p = await openQuestion(w)
    answers['POST /strategies/leg-edit'] = READ // the shape read that follows the new legs
    const other = { underlying: 'NIFTY', legs: DRAFT.legs.slice(0, 2) }
    await w.vm.$router.push({ path: '/strategy/builder', query: { draft: JSON.stringify(other) } })
    await flushPromises()
    expect(t(w, 'dup-question').exists()).toBe(false)
    expect(p.done).toBe(true)
    expect(ids(w)).toEqual(BEFORE.slice(0, 2))
  })

  it('Undo closes the question and settles the edit', async () => {
    const w = await openPage()
    const p = await openQuestion(w)
    const s = w.vm.$.setupState
    answers['POST /strategies/leg-edit'] = READ // the shape read that follows the restored legs
    s.undoHeld = { legs: s.legs.map((l) => ({ ...l })), savedId: null, savedRevision: null, openStrategy: null }
    s.undoClear()
    await flushPromises()
    expect(t(w, 'dup-question').exists()).toBe(false)
    expect(p.done).toBe(true)
    expect(ids(w)).toEqual(BEFORE)
  })

  it('legs reassigned with equal content (a names reply) keep the answer: Increase still applies', async () => {
    const w = await openPage()
    const p = await openQuestion(w)
    const s = w.vm.$.setupState
    s.legs = s.legs.map((l) => ({ ...l, days_to_expiry: 7 })) // new objects, same ids / contract / action / lots
    await t(w, 'dup-increase').trigger('click')
    await flushPromises()
    expect(p.done).toBe(true)
    expect(lotsOf(w)).toEqual([1, 2, 1])
  })

  it('unmounting with the question open settles the pending edit', async () => {
    const w = await openPage()
    const p = await openQuestion(w)
    w.unmount()
    await flushPromises()
    expect(p.done).toBe(true)
  })
})
