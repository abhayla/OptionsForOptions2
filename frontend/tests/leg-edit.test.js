// W-126 (REQ-076, REQ-077, REQ-078): the browser sends ONE edit and draws the server's reply; it moves no strike and prices
// nothing. The reply shape below is the REAL LegEditOut of backend/ofo_app/routes/leg_edit.py (a NIFTY iron condor of the
// 2026-10-06 instrument file after Shift +1; the strikes and entries are the hand-computed values of
// tests/strategy/test_leg_edit.py). Shift / Width / Hedge follow Sensibull screens 108-110 and bundle-findings 7.2.
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    const a = answers[`${method} ${url}`]
    if (a === undefined) return Promise.reject(new Error(`unmocked ${method} ${url}`))
    return typeof a === 'function' ? a(body) : a instanceof Error ? Promise.reject(a) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (url) => respond('GET', url), post: (url, body) => respond('POST', url, body) } }
})
import LegList from '@/components/strategy/LegList.vue'
import StrategyControls from '@/components/strategy/StrategyControls.vue'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import { REASONS, applyEditReply, buildEditRequest, multiplierValid, newestWins, priceShape, shiftText } from '@/lib/legEdit'
import { buildDraft } from '@/lib/legPicker'

const AT = '2026-10-06T09:20:00+05:30'
const page = (id, action, type, strike, price) => ({
  id, underlying: 'NIFTY', instrument_id: `NSE_FO:${id}`, action, lots: 1, planned_entry: price, captured_at: AT,
  instrument_type: type, strike, expiry: '2026-10-06',
})
const CONDOR = [
  page(1, 'BUY', 'PE', '22800.00', '42.50'), page(2, 'SELL', 'PE', '23000.00', '86.00'),
  page(3, 'SELL', 'CE', '23400.00', '91.50'), page(4, 'BUY', 'CE', '23600.00', '44.00'),
]
const replyLeg = (id, action, type, strike, price, extra = {}) => ({
  instrument_id: `NSE_FO:${id}`, action, instrument: type, strike, expiry: '2026-10-06', lots: 1, base_lots: 1, quantity: 65,
  planned_entry: price, captured_at: AT, price_source: 'captured', included: true, hedge: false, ...extra,
})
const SHIFTED = {
  legs: [replyLeg(11, 'BUY', 'PE', '22850.00', '45.00', { hedge: true }), replyLeg(12, 'SELL', 'PE', '23050.00', '90.00'),
    replyLeg(13, 'SELL', 'CE', '23450.00', '88.00'), replyLeg(14, 'BUY', 'CE', '23650.00', '41.00', { hedge: true })],
  shape: 'iron_condor', controls: { shift: true, width: true, hedge: true }, shift_total: 50,
  outcome: { state: 'NOT_CONNECTED', status_label: 'Draft — Live data not connected', legs: [], underlying: 'NIFTY' },
}
const NOOP = { ...SHIFTED, legs: SHIFTED.legs, shift_total: 0, outcome: null }

beforeEach(() => {
  calls.length = 0
  answers = {}
})
const t = (w, id) => w.find(`[data-testid="${id}"]`)
// Type into a box and commit it (a native change event), the way a user does; one event, no other.
const commit = async (w, id, text) => {
  t(w, id).element.value = text
  await t(w, id).trigger('input')
  await t(w, id).trigger('change')
}

describe('the request carries one edit and nothing computed (REQ-078 AC-6)', () => {
  it('AC-6: a Shift click sends only the control and its direction, plus the legs as they are', () => {
    const body = buildEditRequest('NIFTY', CONDOR, { control: 'shift', direction: 1, strike: '99999' }, 0)
    expect(body.edit).toEqual({ control: 'shift', direction: 1 })
    expect(body.legs.map((l) => Object.keys(l).sort())).toEqual(Array(4).fill(
      ['action', 'base_lots', 'captured_at', 'included', 'instrument_id', 'lots', 'planned_entry', 'typed']))
    expect(body.legs.map((l) => l.planned_entry)).toEqual(['42.50', '86.00', '91.50', '44.00'])
  })

  it('an edit missing its fields builds nothing (no guess)', () => {
    expect(buildEditRequest('NIFTY', CONDOR, { control: 'step', index: 0 })).toBeNull()
    expect(buildEditRequest('NIFTY', CONDOR, { control: 'nonsense' })).toBeNull()
    expect(buildEditRequest('NIFTY', CONDOR, { control: 'reset_prices' }).edit).toEqual({ control: 'reset_prices' })
  })

  it('AC-4 / REQ-076: the multiplier is a whole number 1 to 50; a typed price is digits with up to 2 decimals', () => {
    for (const ok of ['1', '9', '10', '49', '50']) expect(multiplierValid(ok)).toBe(true)
    for (const bad of ['0', '51', '1.5', '-1', '', 'x', '05']) expect(multiplierValid(bad)).toBe(false)
    expect(priceShape('81.35')).toBe(true)
    for (const bad of ['81.355', '-1', 'abc', '', '1e3']) expect(priceShape(bad)).toBe(false)
  })

  it('AC-3: the Shift total shows with its sign', () => {
    expect([shiftText(50), shiftText(-100), shiftText(0)]).toEqual(['+50', '-100', '0'])
  })
})

describe('the reply is drawn as sent (REQ-076 AC-3, REQ-077 AC-3/AC-9)', () => {
  it('AC-3: the page legs take the server strikes, entries, hedge marks and typed mark; unpriced stays null', () => {
    const next = applyEditReply(CONDOR, { ...SHIFTED, legs: [{ ...SHIFTED.legs[0], planned_entry: null, price_source: 'none', captured_at: null },
      { ...SHIFTED.legs[1], price_source: 'typed' }, ...SHIFTED.legs.slice(2)] })
    expect(next.map((l) => l.strike)).toEqual(['22850.00', '23050.00', '23450.00', '23650.00'])
    expect(next[0].planned_entry).toBeNull()
    expect(next[1].typed).toBe(true)
    expect(next[2].typed).toBe(false)
    expect(next[0].id).toBe(1) // the page's own fields are kept
  })

  it('REQ-076 AC-6: an unticked leg is never part of the draft sent to the outcome', () => {
    const legs = CONDOR.map((l, i) => (i === 3 ? { ...l, included: false } : l))
    expect(buildDraft(legs).legs.map((l) => l.instrument_id)).toEqual(['NSE_FO:1', 'NSE_FO:2', 'NSE_FO:3'])
  })

  it('late replies: only the newest request counts', () => {
    const seq = newestWins()
    const first = seq.start()
    const second = seq.start()
    expect(seq.isCurrent(first)).toBe(false)
    expect(seq.isCurrent(second)).toBe(true)
  })
})

describe('StrategyControls (Sensibull 108-110)', () => {
  it('AC-2: Width and Hedge are disabled with the requirement\'s reason when the shape does not allow them', () => {
    const w = mount(StrategyControls, { props: { controls: { shift: true, width: false, hedge: false, shiftTotal: 0 } } })
    expect(t(w, 'width-plus').attributes('disabled')).toBeDefined()
    expect(t(w, 'width-reason').text()).toBe(REASONS.width)
    expect(t(w, 'hedge-reason').text()).toBe(REASONS.hedge)
    expect(t(w, 'shift-plus').attributes('disabled')).toBeUndefined()
  })

  it('AC-3/AC-6: a click emits only the control and its direction; Shift shows the cumulative move', async () => {
    const w = mount(StrategyControls, { props: { controls: { shift: true, width: true, hedge: true, shiftTotal: 50 } } })
    expect(t(w, 'shift-total').text()).toBe('+50')
    await t(w, 'width-minus').trigger('click')
    await t(w, 'hedge-plus').trigger('click')
    expect(w.emitted('edit')).toEqual([[{ control: 'width', direction: -1 }], [{ control: 'hedge', direction: 1 }]])
  })

  it('REQ-076 AC-4: a multiplier out of 1..50 sends nothing and says why; Reset Prices emits its own edit', async () => {
    const w = mount(StrategyControls, { props: { controls: { shift: true, width: false, hedge: false, shiftTotal: 0 } } })
    await commit(w, 'multiplier', '51')
    expect(w.emitted('edit')).toBeUndefined()
    expect(t(w, 'multiplier-reason').exists()).toBe(true)
    await commit(w, 'multiplier', '3')
    await t(w, 'reset-prices').trigger('click')
    expect(w.emitted('edit')).toEqual([[{ control: 'multiplier', multiplier: 3 }], [{ control: 'reset_prices' }]])
  })
})

describe('LegList (Sensibull 011/012)', () => {
  const legs = [...CONDOR.slice(0, 1), { ...page(5, 'BUY', 'FUT', null, '23100.00'), strike: null }]

  it('REQ-076 AC-1: a futures leg has no stepper; an option leg steps down and up', async () => {
    const w = mount(LegList, { props: { legs, shape: null } })
    expect(w.findAll('[data-testid="strike-minus"]')).toHaveLength(1)
    await t(w, 'strike-plus').trigger('click')
    expect(w.emitted('edit')).toEqual([[{ control: 'step', index: 0, direction: 1 }]])
  })

  it('REQ-076 AC-6/AC-8: the tick emits an include edit; the shape name is shown as a label only', async () => {
    const w = mount(LegList, { props: { legs: CONDOR, shape: 'Iron Condor' } })
    expect(t(w, 'leg-list-header').text()).toContain('4 selected')
    expect(t(w, 'shape-label').text()).toContain('Iron Condor')
    await w.findAll('[data-testid="leg-tick"]')[3].setValue(false)
    expect(w.emitted('edit')).toEqual([[{ control: 'include', index: 3, included: false }]])
  })

  it('REQ-077 AC-1/AC-9: a typed price emits a price edit; a malformed one is not sent; the typed mark shows', async () => {
    const w = mount(LegList, { props: { legs: [{ ...CONDOR[0], typed: true }], shape: null } })
    expect(t(w, 'typed-marker').exists()).toBe(true)
    await commit(w, 'leg-price-0', '81.355')
    expect(w.emitted('edit')).toBeUndefined()
    expect(t(w, 'price-shape').exists()).toBe(true)
    await commit(w, 'leg-price-0', '81.35')
    expect(w.emitted('edit')).toEqual([[{ control: 'price', index: 0, price: '81.35' }]])
  })

  it('REQ-077 AC-9: an unpriced leg says so and shows no price', () => {
    const w = mount(LegList, { props: { legs: [{ ...CONDOR[0], planned_entry: null }], shape: null } })
    expect(t(w, 'leg-unpriced').exists()).toBe(true)
    expect(t(w, 'leg-price-0').element.value).toBe('')
  })
})

describe('the Builder page sends the edit and draws the reply', () => {
  async function open() {
    const draft = JSON.stringify({ underlying: 'NIFTY', legs: CONDOR.map((l) => ({
      instrument_id: l.instrument_id, action: l.action, lots: 1, planned_entry: l.planned_entry, captured_at: AT })) })
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
    await router.push({ path: '/strategy/builder', query: { draft } })
    await router.isReady()
    const w = mount(StrategyBuilderPage, { global: { plugins: [router] } })
    await flushPromises()
    return w
  }

  it('AC-3/AC-6: Shift +1 posts {control, direction} and the strikes on screen are the server\'s', async () => {
    answers['POST /strategies/outcome'] = SHIFTED.outcome
    answers['POST /strategies/leg-edit'] = (body) => Promise.resolve({ data: body.edit.control === 'shift' ? SHIFTED : NOOP })
    const w = await open()
    await t(w, 'shift-plus').trigger('click')
    await flushPromises()
    const post = calls.filter((c) => c.url === '/strategies/leg-edit').at(-1)
    expect(post.body.edit).toEqual({ control: 'shift', direction: 1 })
    expect(w.findAll('[data-testid="leg-strike"]').map((s) => s.text())).toEqual(['22850.00', '23050.00', '23450.00', '23650.00'])
    expect(t(w, 'shift-total').text()).toBe('+50')
  })

  it('AC-6: a refused edit shows the server\'s text and leaves the legs as they were', async () => {
    const parts = { what_happened: 'No leg changed.', impact: 'b', what_is_blocked: 'c', next_action: 'd' }
    answers['POST /strategies/outcome'] = SHIFTED.outcome
    answers['POST /strategies/leg-edit'] = (body) => (body.edit.control === 'shift'
      ? Promise.reject(Object.assign(new Error('x'), { parts, status: 422 })) : Promise.resolve({ data: NOOP }))
    const w = await open()
    await t(w, 'shift-plus').trigger('click')
    await flushPromises()
    expect(t(w, 'edit-error').exists()).toBe(true)
    expect(w.findAll('[data-testid="leg-strike"]').map((s) => s.text())).toEqual(['', '', '', '']) // unchanged: the draft link carried no strikes
  })

  it('late replies: two quick edits, the older answer arrives last and is not drawn', async () => {
    answers['POST /strategies/outcome'] = SHIFTED.outcome
    const release = []
    answers['POST /strategies/leg-edit'] = (body) => {
      if (body.edit.control === 'multiplier') return Promise.resolve({ data: NOOP })
      return new Promise((res) => release.push(() => res({ data: body.edit.direction === 1 ? SHIFTED : { ...SHIFTED, legs: SHIFTED.legs.map((l) => ({ ...l, strike: '1.00' })) } })))
    }
    const w = await open()
    await t(w, 'shift-plus').trigger('click')
    await t(w, 'shift-minus').trigger('click')
    release[1]() // the newer (Shift -1) answers first
    await flushPromises()
    release[0]() // the older (Shift +1) answers last
    await flushPromises()
    expect(w.findAll('[data-testid="leg-strike"]').map((s) => s.text())).toEqual(['1.00', '1.00', '1.00', '1.00'])
  })
})
