// W-068 / REQ-035 AC-8: the Builder adds and edits legs only from contracts the catalogue API offers, and the picked
// legs reach the outcome API as the draft it already prices.
// The mocked API answers are the REAL shapes of backend/ofo_app/routes/catalogue.py (exchange_segment and exchange_token
// apart, strike a string or null for FUT, lot_size an int) and routes/planned_entry.py (planned_entry string + captured_at
// + source, or null + reason_code). Tokens and symbols are the recorded NIFTY 13-Oct-2026 contracts of the outcome fixture
// (44595/44604/44624/44632) and the instruments slice (FUT 48704). No price here is computed or defaulted by the page.
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises, enableAutoUnmount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    const key = `${method} ${url}`
    const a = answers[key]
    if (a === undefined) return Promise.reject(new Error(`unmocked ${key}`))
    return typeof a === 'function' ? a(body) : a instanceof Error ? Promise.reject(a) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (url) => respond('GET', url), post: (url, body) => respond('POST', url, body) } }
})
import LegPicker from '@/components/strategy/LegPicker.vue'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import { NOT_CONNECTED_LABEL, REPRICE_PROMPT, lotsValid, instrumentId, buildDraft } from '@/lib/legPicker'

const AT = '2026-10-08T09:20:09+05:30'
const c = (token, type, strike, symbol, expiry = '2026-10-13') => ({
  exchange_segment: 'NSE_FO', exchange_token: token, instrument_type: type, expiry, strike, lot_size: 65, symbol,
})
const NIFTY_13 = {
  underlying: 'NIFTY',
  contracts: [
    c(44595, 'PE', '22200.00', 'NIFTY26O1322200PE'),
    c(44604, 'PE', '22400.00', 'NIFTY26O1322400PE'),
    c(44624, 'CE', '22800.00', 'NIFTY26O1322800CE'),
    c(44632, 'CE', '23000.00', 'NIFTY26O1323000CE'),
  ],
}
const NIFTY_27 = { underlying: 'NIFTY', contracts: [c(48704, 'FUT', null, 'NIFTY26OCTFUT', '2026-10-27')] }
const entry = (token, price) => ({
  exchange_segment: 'NSE_FO', exchange_token: token, planned_entry: price, captured_at: price ? AT : null,
  source: price ? 'ltp' : null, reason_code: price ? null : 'not_connected',
})
const OUTCOME_NOT_CONNECTED = { state: 'NOT_CONNECTED', status_label: NOT_CONNECTED_LABEL, legs: [], underlying: 'NIFTY' }

// #582 item 2: every mounted picker starts its 5 s refresh (PICKER_REFRESH_MS). Left mounted on real timers, the pickers
// of earlier tests kept polling into `calls` once this file ran past 5 s under the full-suite load (49 reads in one
// 5.6 s window, measured 2026-10-27), so a later test saw requests it never made. Two guarantees, for every test here:
// each wrapper is unmounted after its test (its interval cleared), and setInterval is fake, so a picker's refresh runs
// only when a test advances the clock. A test that needs every timer fake still calls vi.useFakeTimers() itself.
enableAutoUnmount(afterEach)
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
})
afterEach(() => {
  vi.useRealTimers()
})

beforeEach(() => {
  calls.length = 0
  answers = {
    'GET /catalogue/NIFTY/expiries': { underlying: 'NIFTY', expiries: ['2026-10-13', '2026-10-27'] },
    'GET /catalogue/SENSEX/expiries': { underlying: 'SENSEX', expiries: ['2026-10-15'] },
    'GET /catalogue/NIFTY/contracts?expiry=2026-10-13': NIFTY_13,
    'GET /catalogue/NIFTY/contracts?expiry=2026-10-27': NIFTY_27,
  }
})

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const options = (w, id) => t(w, id).findAll('option').map((o) => o.element.value).filter(Boolean)

function mountPicker(initial = []) {
  const w = mount(LegPicker, {
    props: { legs: initial, 'onUpdate:legs': (v) => w.setProps({ legs: v }) },
  })
  return w
}

async function pick(w, { expiry = '2026-10-13', type, strike, action = 'SELL', lots = '1' }) {
  await t(w, 'pick-expiry').setValue(expiry)
  await flushPromises()
  await t(w, 'pick-type').setValue(type)
  if (strike) await t(w, 'pick-strike').setValue(strike)
  await t(w, 'pick-action').setValue(action)
  await t(w, 'pick-lots').setValue(lots)
}

describe('only offered contracts are selectable', () => {
  it('offers the underlyings, then the expiries and strikes the API sent, in the API order', async () => {
    const w = mountPicker()
    await flushPromises()
    expect(options(w, 'pick-underlying')).toEqual(['NIFTY', 'SENSEX'])
    expect(options(w, 'pick-expiry')).toEqual(['2026-10-13', '2026-10-27'])
    expect(calls.filter((x) => x.url.startsWith('/catalogue/')).map((x) => x.url)).toEqual(['/catalogue/NIFTY/expiries', '/catalogue/NIFTY/contracts?expiry=2026-10-13']) // G-070: opens on the nearest expiry
    await t(w, 'pick-expiry').setValue('2026-10-13')
    await flushPromises()
    expect(calls.filter((x) => x.url.startsWith('/catalogue/')).at(-1).url).toBe('/catalogue/NIFTY/contracts?expiry=2026-10-13') // the picker's own strikes read follows it
    expect(options(w, 'pick-type')).toEqual(['CE', 'PE'])
    await t(w, 'pick-type').setValue('PE')
    expect(options(w, 'pick-strike')).toEqual(['22200.00', '22400.00'])
    await t(w, 'pick-type').setValue('CE')
    expect(options(w, 'pick-strike')).toEqual(['22800.00', '23000.00'])
  })

  it('changing the underlying asks the API again and clears the expiry, so an old contract cannot be added', async () => {
    const w = mountPicker()
    await flushPromises()
    await t(w, 'pick-expiry').setValue('2026-10-13')
    await flushPromises()
    await t(w, 'pick-underlying').setValue('SENSEX')
    await flushPromises()
    expect(options(w, 'pick-expiry')).toEqual(['2026-10-15'])
    expect(t(w, 'pick-expiry').element.value).toBe('2026-10-15') // G-070: the new underlying's nearest expiry
    expect(options(w, 'pick-type')).toEqual([])
    expect(t(w, 'add-leg').attributes('disabled')).toBeDefined()
  })

  it('an expiry with no contracts offers nothing and cannot be added', async () => {
    answers['GET /catalogue/NIFTY/contracts?expiry=2026-10-13'] = { underlying: 'NIFTY', contracts: [] }
    const w = mountPicker()
    await flushPromises()
    await t(w, 'pick-expiry').setValue('2026-10-13')
    await flushPromises()
    expect(options(w, 'pick-type')).toEqual([])
    expect(t(w, 'add-leg').attributes('disabled')).toBeDefined()
  })

  it('a catalogue failure shows the four-part message and offers nothing', async () => {
    const parts = { what_happened: 'a', impact: 'b', what_is_blocked: 'c', next_action: 'd' }
    answers['GET /catalogue/NIFTY/expiries'] = Object.assign(new Error('x'), { parts, status: 422 })
    const w = mountPicker()
    await flushPromises()
    expect(t(w, 'picker-error').text()).toContain('a')
    expect(t(w, 'error-what').exists()).toBe(false) // the page's own error block keeps those ids
    expect(options(w, 'pick-expiry')).toEqual([])
  })
})

describe('FUT has no strike', () => {
  it('a FUT is added without a strike and is sent to the planned-entry API by its joined id', async () => {
    answers['POST /strategies/planned-entry'] = { entries: [entry(48704, '24750.50')] }
    const w = mountPicker()
    await flushPromises()
    await pick(w, { expiry: '2026-10-27', type: 'FUT', action: 'BUY' })
    expect(t(w, 'pick-strike').exists()).toBe(false)
    await t(w, 'add-leg').trigger('click')
    await flushPromises()
    const post = calls.find((x) => x.method === 'POST')
    expect(post.body).toEqual({ underlying: 'NIFTY', instrument_ids: ['NSE_FO:48704'] })
    const legs = w.props('legs')
    expect(legs).toHaveLength(1)
    expect(legs[0]).toMatchObject({ instrument_id: 'NSE_FO:48704', instrument_type: 'FUT', strike: null, action: 'BUY', lots: 1, planned_entry: '24750.50', captured_at: AT })
  })
})

describe('lots validation', () => {
  it('accepts whole numbers 1 to 10000 only', () => {
    for (const ok of ['1', '7', '10', '9999', '10000']) expect(lotsValid(ok)).toBe(true)
    for (const bad of ['', '0', '-1', '1.5', '10001', '01', ' 1', '1e2', 'abc', null, undefined]) expect(lotsValid(bad)).toBe(false)
  })

  it('the Add button stays disabled for bad lots and nothing is sent', async () => {
    const w = mountPicker()
    await flushPromises()
    await pick(w, { type: 'CE', strike: '22800.00', lots: '0' })
    expect(t(w, 'add-leg').attributes('disabled')).toBeDefined()
    expect(t(w, 'lots-error').exists()).toBe(true)
    await t(w, 'pick-lots').setValue('10001')
    expect(t(w, 'add-leg').attributes('disabled')).toBeDefined()
    await t(w, 'pick-lots').setValue('3')
    expect(t(w, 'add-leg').attributes('disabled')).toBeUndefined()
    expect(calls.some((x) => x.method === 'POST')).toBe(false)
  })
})

describe('planned entry: captured when the leg is added, never invented', () => {
  it('a priced leg keeps the API strings exactly and the id is segment:token', async () => {
    answers['POST /strategies/planned-entry'] = { entries: [entry(44624, '104.65')] }
    const w = mountPicker()
    await flushPromises()
    await pick(w, { type: 'CE', strike: '22800.00', lots: '2' })
    await t(w, 'add-leg').trigger('click')
    await flushPromises()
    const [leg] = w.props('legs')
    expect(leg).toMatchObject({ underlying: 'NIFTY', instrument_id: instrumentId('NSE_FO', 44624), symbol: 'NIFTY26O1322800CE', expiry: '2026-10-13', instrument_type: 'CE', strike: '22800.00', action: 'SELL', lots: 2, planned_entry: '104.65', captured_at: AT })
    expect(w.findAll('[data-testid="leg-row"]')).toHaveLength(1)
    expect(w.text()).toContain('104.65')
    expect(t(w, 'leg-unpriced').exists()).toBe(false)
  })

  it('a leg with no live price is added with NO planned entry and shows the not-connected wording', async () => {
    answers['POST /strategies/planned-entry'] = { entries: [entry(44624, null)] }
    const w = mountPicker()
    await flushPromises()
    await pick(w, { type: 'CE', strike: '22800.00' })
    await t(w, 'add-leg').trigger('click')
    await flushPromises()
    const [leg] = w.props('legs')
    expect(leg.planned_entry).toBeNull()
    expect(leg.captured_at).toBeNull()
    expect(t(w, 'leg-unpriced').text()).toBe(NOT_CONNECTED_LABEL)
  })

  it('a failed planned-entry call also leaves the leg without a price (no default, no zero)', async () => {
    answers['POST /strategies/planned-entry'] = Object.assign(new Error('down'), { status: 500 })
    const w = mountPicker()
    await flushPromises()
    await pick(w, { type: 'CE', strike: '22800.00' })
    await t(w, 'add-leg').trigger('click')
    await flushPromises()
    const [leg] = w.props('legs')
    expect(leg.planned_entry).toBeNull()
    expect(t(w, 'leg-unpriced').exists()).toBe(true)
  })
})

describe('edit and remove', () => {
  async function withOneLeg() {
    answers['POST /strategies/planned-entry'] = (body) => Promise.resolve({ data: { entries: body.instrument_ids.map((i) => entry(Number(i.split(':')[1]), '100.00')) } })
    const w = mountPicker()
    await flushPromises()
    await pick(w, { type: 'CE', strike: '22800.00' })
    await t(w, 'add-leg').trigger('click')
    await flushPromises()
    return w
  }

  it('Edit re-fills the form from the API; changing only buy/sell and lots keeps the captured entry', async () => {
    const w = await withOneLeg()
    const posts = () => calls.filter((x) => x.method === 'POST').length
    expect(posts()).toBe(1)
    await t(w, 'edit-leg').trigger('click')
    await flushPromises()
    expect(t(w, 'pick-expiry').element.value).toBe('2026-10-13')
    expect(t(w, 'pick-type').element.value).toBe('CE')
    expect(t(w, 'pick-strike').element.value).toBe('22800.00')
    await t(w, 'pick-action').setValue('BUY')
    await t(w, 'pick-lots').setValue('4')
    await t(w, 'add-leg').trigger('click')
    await flushPromises()
    const legs = w.props('legs')
    expect(legs).toHaveLength(1)
    expect(legs[0]).toMatchObject({ action: 'BUY', lots: 4, planned_entry: '100.00', captured_at: AT })
    expect(posts()).toBe(1)
  })

  it('Edit to another strike picks it from the API list and captures a new entry for the new contract', async () => {
    const w = await withOneLeg()
    await t(w, 'edit-leg').trigger('click')
    await flushPromises()
    expect(options(w, 'pick-strike')).toEqual(['22800.00', '23000.00'])
    await t(w, 'pick-strike').setValue('23000.00')
    await t(w, 'add-leg').trigger('click')
    await flushPromises()
    const legs = w.props('legs')
    expect(legs).toHaveLength(1)
    expect(legs[0]).toMatchObject({ instrument_id: 'NSE_FO:44632', strike: '23000.00' })
    expect(calls.at(-1).body).toEqual({ underlying: 'NIFTY', instrument_ids: ['NSE_FO:44632'] })
  })

  it('Remove drops the leg', async () => {
    const w = await withOneLeg()
    await t(w, 'remove-leg').trigger('click')
    expect(w.props('legs')).toEqual([])
    expect(w.findAll('[data-testid="leg-row"]')).toHaveLength(0)
  })

  it('the underlying is locked while legs exist, so a draft never mixes underlyings', async () => {
    const w = await withOneLeg()
    expect(t(w, 'pick-underlying').attributes('disabled')).toBeDefined()
  })

  it('the underlying stays locked while editing the only leg, so its NIFTY contract cannot be saved as SENSEX', async () => {
    const w = await withOneLeg()
    await t(w, 'edit-leg').trigger('click')
    await flushPromises()
    expect(t(w, 'pick-underlying').attributes('disabled')).toBeDefined()
    expect(t(w, 'pick-underlying').element.value).toBe('NIFTY')
    await t(w, 'add-leg').trigger('click')
    await flushPromises()
    expect(w.props('legs')[0]).toMatchObject({ underlying: 'NIFTY', instrument_id: 'NSE_FO:44624' })
  })
})

describe('a late async reply never overwrites newer user state', () => {
  it('a leg is saved from what was picked at the click; picks made while the entry is being captured survive', async () => {
    let release
    answers['POST /strategies/planned-entry'] = () => new Promise((res) => { release = () => res({ data: { entries: [entry(44624, '104.65')] } }) })
    const w = mountPicker()
    await flushPromises()
    await pick(w, { type: 'CE', strike: '22800.00', action: 'SELL', lots: '1' })
    await t(w, 'add-leg').trigger('click')
    await flushPromises()
    // while the capture is pending the user picks the next leg
    await t(w, 'pick-type').setValue('PE')
    await t(w, 'pick-strike').setValue('22400.00')
    await t(w, 'pick-action').setValue('BUY')
    await t(w, 'pick-lots').setValue('3')
    release()
    await flushPromises()
    const [leg] = w.props('legs')
    expect(w.props('legs')).toHaveLength(1)
    expect(leg).toMatchObject({ instrument_id: instrumentId('NSE_FO', 44624), action: 'SELL', lots: 1, instrument_type: 'CE', planned_entry: '104.65' })
    expect(t(w, 'pick-type').element.value).toBe('PE')
    expect(t(w, 'pick-strike').element.value).toBe('22400.00')
    expect(t(w, 'pick-action').element.value).toBe('BUY')
    expect(t(w, 'pick-lots').element.value).toBe('3')
  })

  it('the Builder ignores an outcome answer that arrives after every leg was removed', async () => {
    let release
    answers['POST /strategies/planned-entry'] = { entries: [entry(44624, '104.65')] }
    answers['POST /strategies/outcome'] = () => new Promise((res) => { release = () => res({ data: OUTCOME_NOT_CONNECTED }) })
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
    await router.push({ path: '/strategy/builder' })
    await router.isReady()
    const w = mount(StrategyBuilderPage, { global: { plugins: [router] } })
    await flushPromises()
    await pick(w, { type: 'CE', strike: '22800.00' })
    await t(w, 'add-leg').trigger('click')
    await flushPromises()
    expect(t(w, 'strategy-builder').attributes('data-state')).toBe('loading')
    await t(w, 'remove-leg').trigger('click')
    await flushPromises()
    expect(t(w, 'strategy-builder').attributes('data-state')).toBe('no-draft')
    release()
    await flushPromises()
    expect(t(w, 'strategy-builder').attributes('data-state')).toBe('no-draft')
  })
})

// CI #581 (leg-picker.spec.ts:48, desktop-1280): four legs added one after another ended with three for 5 s. The trace shows the 4th
// planned-entry request queued behind a 5.2 s outcome reply on the replay API: late, not lost. This pins the product half: legs
// added in quick sequence, each capture answering while the previous add's outcome and shape read are still in flight, and those
// stale replies (a 3-leg shape read among them) landing AFTER the next leg: every leg is kept.
describe('legs added quickly in sequence are all kept', () => {
  it('four adds, each capture answering before the previous outcome and shape read, end with four legs', async () => {
    const held = [] // every outcome / leg-edit reply, released only at the end, oldest LAST
    const captures = []
    const ALL = [entry(44595, '41.10'), entry(44604, '55.20'), entry(44624, '104.65'), entry(44632, '61.30')]
    answers['POST /strategies/planned-entry'] = () => new Promise((res) => captures.push(() => res({ data: { entries: ALL } })))
    answers['POST /strategies/outcome'] = () => new Promise((res) => held.push(() => res({ data: OUTCOME_NOT_CONNECTED })))
    answers['POST /strategies/leg-edit'] = (body) => new Promise((res) => held.push(() => res({ data: {
      seq: body.seq, shape_name: null, // a shape read for the legs it was SENT with: applied late, it would drop the newer legs
      legs: body.legs.map((l) => ({ ...l, instrument_id: l.instrument_id, action: l.action, lots: l.lots, included: true })),
    } })))
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
    await router.push({ path: '/strategy/builder' })
    await router.isReady()
    const w = mount(StrategyBuilderPage, { global: { plugins: [router] } })
    await flushPromises()
    const legsAdded = [['CE', '22800.00', 'SELL'], ['CE', '23000.00', 'BUY'], ['PE', '22400.00', 'SELL'], ['PE', '22200.00', 'BUY']]
    for (const [i, [type, strike, action]] of legsAdded.entries()) {
      if (t(w, 'add-edit').exists() && t(w, 'add-edit').attributes('aria-expanded') !== 'true') await t(w, 'add-edit').trigger('click')
      await pick(w, { type, strike, action })
      await t(w, 'add-leg').trigger('click')
      await flushPromises()
      captures.shift()() // this leg's capture answers while every earlier outcome / shape read is still unanswered
      await flushPromises()
      expect(w.findAll('[data-testid="leg-row"]')).toHaveLength(i + 1)
    }
    // the race is real: a shape read went out after the 2nd, 3rd and 4th adds, and an outcome after every add
    expect(calls.filter((c) => c.url === '/strategies/leg-edit').map((c) => c.body.legs.length)).toEqual([2, 3, 4])
    expect(calls.filter((c) => c.url === '/strategies/outcome').length).toBeGreaterThanOrEqual(4)
    while (held.length) held.pop()() // the stale replies land newest first, the oldest last
    await flushPromises()
    const rows = w.findAll('[data-testid="leg-row"]')
    expect(rows).toHaveLength(4)
    expect(rows.map((r) => r.attributes('data-instrument-id'))).toEqual([44624, 44632, 44604, 44595].map((k) => instrumentId('NSE_FO', k)))
  })
})

describe('buildDraft: the body the outcome API takes', () => {
  const priced = { underlying: 'NIFTY', instrument_id: 'NSE_FO:44624', action: 'SELL', lots: 2, planned_entry: '104.65', captured_at: AT, symbol: 'x' }
  const unpriced = { ...priced, instrument_id: 'NSE_FO:44632', planned_entry: null, captured_at: null }
  it('sends every leg, with exactly the five fields its leg model has', () => {
    expect(buildDraft([priced])).toEqual({
      underlying: 'NIFTY',
      legs: [{ instrument_id: 'NSE_FO:44624', action: 'SELL', lots: 2, planned_entry: '104.65', captured_at: AT }],
    })
  })
  it('REQ-077 AC-9: an included leg without an entry next to a priced one sends no draft', () => {
    expect(buildDraft([priced, unpriced])).toBeNull()
    expect(buildDraft([unpriced, priced])).toBeNull()
    expect(buildDraft([priced, { ...unpriced, included: true }])).toBeNull()
    expect(buildDraft([priced, { ...unpriced, captured_at: AT }])).toBeNull()
    expect(buildDraft([priced, { ...unpriced, planned_entry: '1.00' }])).toBeNull()
  })
  it('W-148: an unticked unpriced leg is left out and the priced rest is sent', () => {
    expect(buildDraft([priced, { ...unpriced, included: false }])).toEqual({
      underlying: 'NIFTY',
      legs: [{ instrument_id: 'NSE_FO:44624', action: 'SELL', lots: 2, planned_entry: '104.65', captured_at: AT }],
    })
  })
  it('issue #500: a leg that is not live still wins', () => {
    expect(buildDraft([priced, { ...priced, not_live: true }])).toBeNull()
  })
  it('is null when no leg has a planned entry', () => {
    expect(buildDraft([unpriced])).toBeNull()
    expect(buildDraft([])).toBeNull()
  })
})

describe('the Builder page', () => {
  async function open(query = {}) {
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
    await router.push({ path: '/strategy/builder', query })
    await router.isReady()
    const w = mount(StrategyBuilderPage, { global: { plugins: [router] } })
    await flushPromises()
    return w
  }

  it('with no draft it shows the picker and the no-draft state, and calls no outcome API', async () => {
    const w = await open()
    expect(t(w, 'strategy-builder').attributes('data-state')).toBe('no-draft')
    expect(t(w, 'leg-picker').exists()).toBe(true)
    expect(calls.some((x) => x.url === '/strategies/outcome')).toBe(false)
  })

  it('picked legs are sent to the outcome API as the draft it prices', async () => {
    answers['POST /strategies/planned-entry'] = { entries: [entry(44624, '104.65')] }
    answers['POST /strategies/outcome'] = OUTCOME_NOT_CONNECTED
    const w = await open()
    await pick(w, { type: 'CE', strike: '22800.00', lots: '2' })
    await t(w, 'add-leg').trigger('click')
    await flushPromises()
    const out = calls.filter((x) => x.url === '/strategies/outcome')
    expect(out).toHaveLength(1)
    expect(out[0].body).toEqual({
      underlying: 'NIFTY',
      legs: [{ instrument_id: 'NSE_FO:44624', action: 'SELL', lots: 2, planned_entry: '104.65', captured_at: AT }],
      fallback: false,
      seq: 2, // REQ-119: rises with every call; the mount's empty-draft call (no request) took 1
    })
    expect(t(w, 'strategy-builder').attributes('data-state')).toBe('not-connected')
    expect(t(w, 'status-label').text()).toBe(NOT_CONNECTED_LABEL)
  })

  it('only unpriced legs: no outcome call, the not-connected wording, no numbers', async () => {
    answers['POST /strategies/planned-entry'] = { entries: [entry(44624, null)] }
    const w = await open()
    await pick(w, { type: 'CE', strike: '22800.00' })
    await t(w, 'add-leg').trigger('click')
    await flushPromises()
    expect(calls.some((x) => x.url === '/strategies/outcome')).toBe(false)
    expect(t(w, 'strategy-builder').attributes('data-state')).toBe('unpriced')
    expect(t(w, 'state-unpriced').text()).toContain(NOT_CONNECTED_LABEL)
    for (const id of ['strategy-table', 'payoff-chart', 'summary-cards']) expect(t(w, id).exists()).toBe(false)
  })

  it('removing the last leg returns to the no-draft state', async () => {
    answers['POST /strategies/planned-entry'] = { entries: [entry(44624, null)] }
    const w = await open()
    await pick(w, { type: 'CE', strike: '22800.00' })
    await t(w, 'add-leg').trigger('click')
    await flushPromises()
    await t(w, 'remove-leg').trigger('click')
    await flushPromises()
    expect(t(w, 'strategy-builder').attributes('data-state')).toBe('no-draft')
  })

  it('the existing ?draft= path still works: its legs are sent unchanged and listed on the one leg list', async () => {
    answers['POST /strategies/outcome'] = OUTCOME_NOT_CONNECTED
    const draft = {
      underlying: 'NIFTY',
      legs: [
        { instrument_id: 'NSE_FO:44624', action: 'SELL', lots: 1, planned_entry: '100.00', captured_at: AT },
        { instrument_id: 'NSE_FO:44632', action: 'BUY', lots: 1, planned_entry: '100.00', captured_at: AT },
      ],
    }
    const w = await open({ draft: JSON.stringify(draft) })
    const out = calls.filter((x) => x.url === '/strategies/outcome')
    expect(out).toHaveLength(1)
    expect(out[0].body).toEqual({ ...draft, fallback: false, seq: 1 })
    expect(w.findAll('[data-testid="leg-row"]')).toHaveLength(2) // the one list is LegList's
    expect(w.findAll('[data-testid="leg-list"]')).toHaveLength(0) // the picker draws no list of its own on the Builder
    expect(t(w, 'strategy-builder').attributes('data-state')).toBe('not-connected')
  })

  it('ADR-086 item 1 (W-073): the not-connected answer names each known contract in draft-legs, never the fixed unavailable wording, never the instrument id', async () => {
    const draftLegs = [
      { instrument_id: 'NSE_FO:44624', action: 'SELL', lots: 1, planned_entry: '100.00', captured_at: AT },
      { instrument_id: 'NSE_FO:44632', action: 'BUY', lots: 1, planned_entry: '100.00', captured_at: AT },
    ]
    // the server's not-live answer names each leg's contract (underlying, expiry, type, strike), as it does for the page
    const known = [['CE', '22800.00'], ['CE', '23000.00']]
    answers['POST /strategies/outcome'] = {
      ...OUTCOME_NOT_CONNECTED,
      legs: draftLegs.map((l, i) => ({ ...l, underlying: 'NIFTY', expiry: '2026-10-13', instrument_type: known[i][0], strike: known[i][1] })),
    }
    const w = await open({ draft: JSON.stringify({ underlying: 'NIFTY', legs: draftLegs }) })
    expect(t(w, 'strategy-builder').attributes('data-state')).toBe('not-connected')
    const text = t(w, 'draft-legs').text()
    expect(text).toContain('NIFTY')
    expect(w.findAll('[data-testid="draft-legs"] [data-testid="leg-name"]')).toHaveLength(2)
    expect(text).not.toContain('Contract details not available')
    for (const l of draftLegs) expect(text).not.toContain(l.instrument_id)
  })

  it('when the outcome call and the catalogue call both fail the page shows exactly one error-what', async () => {
    const parts = { what_happened: 'outcome down', impact: 'b', what_is_blocked: 'c', next_action: 'd' }
    answers['GET /catalogue/NIFTY/expiries'] = Object.assign(new Error('x'), { parts: { ...parts, what_happened: 'catalogue down' } })
    answers['POST /strategies/outcome'] = Object.assign(new Error('x'), { parts })
    const draft = { underlying: 'NIFTY', legs: [{ instrument_id: 'NSE_FO:44624', action: 'SELL', lots: 1, planned_entry: '100.00', captured_at: AT }] }
    const w = await open({ draft: JSON.stringify(draft) })
    expect(w.findAll('[data-testid="error-what"]')).toHaveLength(1)
    expect(t(w, 'error-what').text()).toBe('outcome down')
    expect(t(w, 'picker-error').text()).toContain('catalogue down') // the picker failure is still visible
  })

  it('a malformed ?draft= is ignored like before (no-draft)', async () => {
    const w = await open({ draft: '{not json' })
    expect(t(w, 'strategy-builder').attributes('data-state')).toBe('no-draft')
  })
})

// W-071 round 4: a reopened leg's template branches, and the reprice prompt for a draft saved without planned entries.
describe('leg row branches: unpriced label follows planned_entry, capture time shows only with it', () => {
  const base = { id: 1, underlying: 'NIFTY', instrument_id: 'NSE_FO:44624', contract_id: 1, symbol: 'NIFTY26O1322800CE', expiry: '2026-10-13', instrument_type: 'CE', strike: '22800.00', lot_size: 65, action: 'SELL', lots: 1 }
  it('both: entry and capture time, no unpriced label, no prompt', () => {
    const w = mountPicker([{ ...base, planned_entry: '104.65', captured_at: AT, reason_code: null }])
    expect(t(w, 'leg-entry').exists()).toBe(true)
    expect(t(w, 'leg-captured').exists()).toBe(true)
    expect(t(w, 'leg-unpriced').exists()).toBe(false)
    expect(t(w, 'leg-reprice-prompt').exists()).toBe(false)
  })
  it('capture time without an entry shows neither the time nor a price', () => {
    const w = mountPicker([{ ...base, planned_entry: null, captured_at: AT, reason_code: 'no_live_price' }])
    expect(t(w, 'leg-entry').exists()).toBe(false)
    expect(t(w, 'leg-captured').exists()).toBe(false)
    expect(t(w, 'leg-unpriced').text()).toBe(NOT_CONNECTED_LABEL)
    expect(t(w, 'leg-reprice-prompt').exists()).toBe(false)
  })
  it('entry without a capture time shows the unpriced label nowhere', () => {
    const w = mountPicker([{ ...base, planned_entry: '104.65', captured_at: null, reason_code: null }])
    expect(t(w, 'leg-entry').exists()).toBe(true)
    expect(t(w, 'leg-captured').exists()).toBe(false)
    expect(t(w, 'leg-unpriced').exists()).toBe(false)
  })
  it('neither: unpriced label, no capture time', () => {
    const w = mountPicker([{ ...base, planned_entry: null, captured_at: null, reason_code: 'no_live_price' }])
    expect(t(w, 'leg-unpriced').exists()).toBe(true)
    expect(t(w, 'leg-captured').exists()).toBe(false)
  })
})

describe('a draft reopened without planned entries asks for a reprice', () => {
  const legs = [{ id: 1, underlying: 'NIFTY', instrument_id: 'NSE_FO:44624', contract_id: 1, symbol: 'NIFTY26O1322800CE', expiry: '2026-10-13', instrument_type: 'CE', strike: '22800.00', lot_size: 65, action: 'SELL', lots: 1, planned_entry: null, captured_at: null, reason_code: 'needs_reprice' }]
  it('shows the prompt, captures nothing on load, and captures only after Reprice then Save leg', async () => {
    answers['POST /strategies/planned-entry'] = { entries: [entry(44624, '104.65')] }
    const w = mountPicker(legs)
    await flushPromises()
    expect(REPRICE_PROMPT).toBe('This leg was saved without a planned entry. Reprice it to see its numbers.')
    expect(t(w, 'leg-reprice-prompt').text()).toBe('This leg was saved without a planned entry. Reprice it to see its numbers.')
    expect(calls.some((x) => x.method === 'POST')).toBe(false)
    await t(w, 'reprice-leg').trigger('click')
    await flushPromises()
    await t(w, 'add-leg').trigger('click')
    await flushPromises()
    expect(calls.filter((x) => x.method === 'POST')).toHaveLength(1)
    const [leg] = w.props('legs')
    expect(leg).toMatchObject({ planned_entry: '104.65', captured_at: AT, reason_code: null })
    expect(t(w, 'leg-reprice-prompt').exists()).toBe(false)
  })
})

// #583 I-12: a FUTURES leg saved without a planned entry goes through the same Reprice -> Save leg capture as an option.
describe('a futures leg without a planned entry captures on Reprice then Save leg', () => {
  const legs = [{ id: 1, underlying: 'NIFTY', instrument_id: 'NSE_FO:48704', contract_id: 3, symbol: 'NIFTY26OCTFUT', expiry: '2026-10-27', instrument_type: 'FUT', strike: null, lot_size: 65, action: 'BUY', lots: 1, planned_entry: null, captured_at: null, reason_code: 'needs_reprice' }]
  it('sends the planned-entry request for the future and stores its LTP', async () => {
    answers['POST /strategies/planned-entry'] = { entries: [entry(48704, '22800.00')] }
    const w = mountPicker(legs)
    await flushPromises()
    expect(t(w, 'leg-reprice-prompt').exists()).toBe(true)
    await t(w, 'reprice-leg').trigger('click')
    await flushPromises()
    await t(w, 'add-leg').trigger('click')
    await flushPromises()
    const posts = calls.filter((x) => x.method === 'POST')
    expect(posts).toHaveLength(1)
    expect(posts[0].body).toEqual({ underlying: 'NIFTY', instrument_ids: ['NSE_FO:48704'] })
    expect(w.props('legs')[0]).toMatchObject({ planned_entry: '22800.00', captured_at: AT, reason_code: null, instrument_type: 'FUT' })
  })
})

// ---- W-147 / REQ-080: the Strikes and Futures tabs, multi-select Done, the Lots/Quantity setting. ----
// The strikes answer is the shape of backend/ofo_app/routes/leg_picker.py StrikesOut, built from the SAME recorded NIFTY
// 2026-10-08 09:20:09 IST values as tests_app/test_leg_picker_routes.py: spot 22,533.25, grid 22450..22600 step 50 (ATM 22550),
// tokens 44000 + 2 x index (CE) and +1 (PE), lot size 65, only 22500 CE (151.30, OI 3218475) and 22550 PE (145.10,
// OI 4022200) priced; IV/delta are the independent hand figures of that file (11.34 %, 0.5730 and 13.65 %, -0.4920).
const GRID = ['22450.00', '22500.00', '22550.00', '22600.00']
const tok = (i, side) => 44000 + 2 * i + (side === 'pe' ? 1 : 0)
const cell = (i, side, extra = {}, lot = 65) => ({
  instrument_id: `NSE_FO:${tok(i, side)}`, lot_size: lot, ltp: null, oi: null, iv_percent: null, delta: null,
  health: 'unavailable', at: null, ...extra,
})
const PRICED = {
  1: { ce: { ltp: '151.30', oi: 3218475, iv_percent: '11.34', delta: '0.5730', health: 'available', at: AT } },
  2: { pe: { ltp: '145.10', oi: 4022200, iv_percent: '13.65', delta: '-0.4920', health: 'available', at: AT } },
}
const strikesAnswer = (over = {}) => ({
  state: 'LIVE', reason: 'SOME_PRICES_MISSING', underlying: 'NIFTY', expiry: '2026-10-13', width: 10, spot: '22533.25',
  spot_at: AT, centre: 'LIVE_SPOT', atm_strike: '22550.00', answered_at: AT, market_closed: false,
  rows: GRID.map((strike, i) => ({
    strike, is_atm: strike === '22550.00', ce: cell(i, 'ce', PRICED[i]?.ce), pe: cell(i, 'pe', PRICED[i]?.pe),
  })),
  ...over,
})
const catalogue13 = {
  underlying: 'NIFTY',
  contracts: GRID.flatMap((strike, i) => ['ce', 'pe'].map((side) => ({
    contract_id: tok(i, side), exchange_segment: 'NSE_FO', exchange_token: tok(i, side), instrument_type: side.toUpperCase(),
    expiry: '2026-10-13', strike, lot_size: 65, symbol: `NIFTY26OCT${strike}${side.toUpperCase()}`,
  }))),
}
const STRIKES_URL = (w = 10, u = 'NIFTY', e = '2026-10-13') => `GET /leg-picker/strikes?underlying=${u}&expiry=${e}&width=${w}`
const entryFor = (prices) => (body) => Promise.resolve({
  data: {
    entries: body.instrument_ids.map((id) => {
      const token = Number(id.split(':')[1])
      return entry(token, prices[token] ?? null)
    }),
    answered_at: AT,
  },
})
const rowOf = (w, strike) => w.find(`[data-testid="strike-row"][data-strike="${strike}"]`)
const sideOf = (w, strike, side) => rowOf(w, strike).find(`[data-testid="cell-${side}"]`)

async function openStrikes(w, expiry = '2026-10-13') {
  await t(w, 'pick-expiry').setValue(expiry)
  await flushPromises()
}

describe('REQ-080 strikes tab (W-147)', () => {
  beforeEach(() => {
    answers['GET /catalogue/NIFTY/contracts?expiry=2026-10-13'] = catalogue13
    answers[STRIKES_URL()] = strikesAnswer()
    answers['POST /strategies/planned-entry'] = entryFor({ 44002: '151.30', 44005: '145.10' })
  })

  it('AC-1/AC-2/AC-3 core: ATM row highlighted, a null price shows "-" with the server reason, two selected cells then Done emit two legs', async () => {
    const w = mountPicker()
    await flushPromises()
    await openStrikes(w)
    expect(t(w, 'tab-strikes').attributes('aria-selected')).toBe('true')
    expect(t(w, 'tab-futures').exists()).toBe(true)
    expect(w.findAll('[data-testid="strike-row"]').map((r) => r.attributes('data-strike'))).toEqual(GRID)
    expect(w.findAll('[data-testid="strike-row"]').map((r) => r.attributes('data-atm'))).toEqual(['false', 'false', 'true', 'false'])
    expect(rowOf(w, '22550.00').classes()).toContain('bg-accent-soft')
    expect(rowOf(w, '22550.00').find('[data-testid="atm-mark"]').exists()).toBe(true)
    expect(rowOf(w, '22450.00').find('[data-testid="atm-mark"]').exists()).toBe(false)
    // priced cell: the server's strings, nothing computed
    const ce = sideOf(w, '22500.00', 'ce')
    expect([ce.find('[data-testid="cell-ltp"]').text(), ce.find('[data-testid="cell-oi"]').text(), ce.find('[data-testid="cell-iv"]').text(), ce.find('[data-testid="cell-delta"]').text()])
      .toEqual(['151.30', '3218475', '11.34', '0.5730'])
    // unpriced cell: '-' in every figure, and the reason sits above the list
    const none = sideOf(w, '22450.00', 'ce')
    expect(['cell-ltp', 'cell-oi', 'cell-iv', 'cell-delta'].map((id) => none.find(`[data-testid="${id}"]`).text())).toEqual(['-', '-', '-', '-'])
    expect(t(w, 'strikes-reason').text()).toBe('Some strikes have no live price right now; they show a dash.')
    expect(t(w, 'strikes-reason').element.compareDocumentPosition(rowOf(w, '22450.00').element) & 4).toBeTruthy() // the list follows the reason
    // select two contracts (22500 CE sell, 22550 PE buy), Done adds both
    await sideOf(w, '22500.00', 'ce').find('[data-testid="cell-sell"]').trigger('click')
    await sideOf(w, '22550.00', 'pe').find('[data-testid="cell-buy"]').trigger('click')
    await t(w, 'picker-done').trigger('click')
    await flushPromises()
    const added = w.props('legs')
    expect(added.map((l) => [l.instrument_id, l.action, l.lots, l.planned_entry, l.captured_at, l.contract_id, l.strike, l.instrument_type]))
      .toEqual([['NSE_FO:44002', 'SELL', 1, '151.30', AT, 44002, '22500.00', 'CE'], ['NSE_FO:44005', 'BUY', 1, '145.10', AT, 44005, '22550.00', 'PE']])
    expect(calls.filter((x) => x.method === 'POST').map((x) => x.url)).toEqual(['/strategies/planned-entry', '/strategies/planned-entry'])
    expect(w.findAll('[data-testid="leg-row"]')).toHaveLength(2)
    expect(t(w, 'picker-done').attributes('disabled')).toBeDefined() // the selection is cleared
  })

  it('AC-1: widths 10/20/30/40, default 10; choosing one re-reads with it and clears the selection', async () => {
    answers[STRIKES_URL(20)] = strikesAnswer({ width: 20 })
    const w = mountPicker()
    await flushPromises()
    await openStrikes(w)
    expect(options(w, 'pick-width')).toEqual(['10', '20', '30', '40'])
    expect(t(w, 'pick-width').element.value).toBe('10')
    await sideOf(w, '22500.00', 'ce').find('[data-testid="cell-buy"]').trigger('click')
    await t(w, 'pick-width').setValue('20')
    await flushPromises()
    expect(calls.at(-1).url).toBe('/leg-picker/strikes?underlying=NIFTY&expiry=2026-10-13&width=20')
    expect(t(w, 'picker-done').text()).toBe('Done')
  })

  it('attack 1: a leg picked on a strike with no price is still added and shows the reprice prompt', async () => {
    answers['POST /strategies/planned-entry'] = entryFor({})
    const w = mountPicker()
    await flushPromises()
    await openStrikes(w)
    await sideOf(w, '22450.00', 'ce').find('[data-testid="cell-sell"]').trigger('click')
    await sideOf(w, '22500.00', 'ce').find('[data-testid="cell-sell"]').trigger('click')
    await t(w, 'picker-done').trigger('click')
    await flushPromises()
    expect(w.props('legs').map((l) => [l.planned_entry, l.captured_at, l.reason_code])).toEqual([[null, null, 'needs_reprice'], [null, null, 'needs_reprice']])
    expect(w.findAll('[data-testid="leg-reprice-prompt"]')).toHaveLength(2)
    expect(t(w, 'leg-reprice-prompt').text()).toBe(REPRICE_PROMPT)
    // the other strike is still shown priced by the server
    expect(sideOf(w, '22500.00', 'ce').find('[data-testid="cell-ltp"]').text()).toBe('151.30')
  })

  it('attack 2: no live spot says how the list is centred (last known spot with its time, or the middle strike)', async () => {
    answers[STRIKES_URL()] = strikesAnswer({ state: 'NOT_LIVE', reason: 'FEED_STALE', centre: 'LAST_KNOWN_SPOT', atm_strike: '22550.00' })
    let w = mountPicker()
    await flushPromises()
    await openStrikes(w)
    expect(t(w, 'strikes-reason').text()).toBe('The live feed is not fresh, so no prices are shown as current.')
    expect(t(w, 'strikes-centre').text()).toBe('Centred on the last known index price 22533.25, as of 8 Oct 2026, 09:20:09 IST.')
    answers[STRIKES_URL()] = strikesAnswer({
      state: 'NOT_LIVE', reason: 'SPOT_MISSING', centre: 'MIDDLE_STRIKE', spot: null, spot_at: null, atm_strike: null,
      rows: GRID.map((strike, i) => ({ strike, is_atm: false, ce: cell(i, 'ce'), pe: cell(i, 'pe') })),
    })
    w = mountPicker()
    await flushPromises()
    await openStrikes(w)
    expect(t(w, 'strikes-centre').text()).toBe('ATM unknown - no live price. The list is centred on the middle listed strike.')
    expect(w.findAll('[data-testid="strike-row"][data-atm="true"]')).toHaveLength(0)
    expect(w.findAll('[data-testid="cell-ltp"]').every((e) => e.text() === '-')).toBe(true)
  })

  it('AC-5/ADR-015: a failed read leaves no old list, an unknown reason code reads as "not given"', async () => {
    answers[STRIKES_URL()] = new Error('down')
    const w = mountPicker()
    await flushPromises()
    await openStrikes(w)
    expect(t(w, 'strikes-error').exists()).toBe(true)
    expect(w.findAll('[data-testid="strike-row"]')).toHaveLength(0)
    expect(t(w, 'picker-error').exists()).toBe(false)
    answers[STRIKES_URL()] = strikesAnswer({ reason: 'SOMETHING_NEW' })
    const w2 = mountPicker()
    await flushPromises()
    await openStrikes(w2)
    expect(t(w2, 'strikes-reason').text()).toBe('The reason was not given.')
  })

  it('AC-4 attack 3: quantity mode on SENSEX lists multiples of the SENSEX lot size from the server data, not NIFTY\'s', async () => {
    const SENSEX_LOT = 20 // the lot size this fixture's server answer carries; the page must show the server's, never a typed 65
    answers['GET /catalogue/SENSEX/contracts?expiry=2026-10-15'] = {
      underlying: 'SENSEX',
      contracts: [{ contract_id: 7001, exchange_segment: 'BSE_FO', exchange_token: 7001, instrument_type: 'CE', expiry: '2026-10-15', strike: '82000.00', lot_size: SENSEX_LOT, symbol: 'SENSEX26O1582000CE' }],
    }
    const sx = cell(0, 'ce', {}, SENSEX_LOT)
    sx.instrument_id = 'BSE_FO:7001'
    answers[STRIKES_URL(10, 'SENSEX', '2026-10-15')] = strikesAnswer({
      underlying: 'SENSEX', expiry: '2026-10-15', spot: null, centre: 'MIDDLE_STRIKE', state: 'NOT_LIVE', reason: 'SPOT_MISSING', atm_strike: null,
      rows: [{ strike: '82000.00', is_atm: false, ce: sx, pe: null }],
    })
    answers['POST /strategies/planned-entry'] = { entries: [], answered_at: AT }
    const w = mountPicker()
    await flushPromises()
    await t(w, 'pick-underlying').setValue('SENSEX')
    await flushPromises()
    await openStrikes(w, '2026-10-15')
    const lotsSelect = () => rowOf(w, '82000.00').find('[data-testid="cell-lots"]')
    expect(lotsSelect().findAll('option').map((o) => o.text())).toEqual(['1', '2', '3', '4', '5', '6', '7', '8', '9', '10']) // lots mode
    await t(w, 'pick-lots-mode').setValue('quantity')
    expect(lotsSelect().findAll('option').map((o) => o.text())).toEqual(['20', '40', '60', '80', '100', '120', '140', '160', '180', '200'])
    expect(lotsSelect().text()).not.toContain('65')
    await lotsSelect().setValue('3') // the option "60" = 3 lots
    await rowOf(w, '82000.00').find('[data-testid="cell-buy"]').trigger('click')
    await t(w, 'picker-done').trigger('click')
    await flushPromises()
    expect(w.props('legs').map((l) => [l.instrument_id, l.lots, l.lot_size])).toEqual([['BSE_FO:7001', 3, 20]])
  })

  it('AC-4: quantity mode with no usable lot size offers no selector and no Buy/Sell (fail closed)', async () => {
    const bad = strikesAnswer()
    bad.rows[1].ce.lot_size = null
    answers[STRIKES_URL()] = bad
    const w = mountPicker()
    await flushPromises()
    await openStrikes(w)
    await t(w, 'pick-lots-mode').setValue('quantity')
    expect(sideOf(w, '22500.00', 'ce').find('[data-testid="cell-buy"]').exists()).toBe(false)
    expect(sideOf(w, '22550.00', 'pe').find('[data-testid="cell-buy"]').exists()).toBe(true)
  })

  it('Done refuses (adds nothing) when a selected contract is not in the catalogue answer', async () => {
    answers['GET /catalogue/NIFTY/contracts?expiry=2026-10-13'] = { underlying: 'NIFTY', contracts: catalogue13.contracts.slice(0, 2) }
    const w = mountPicker()
    await flushPromises()
    await openStrikes(w)
    await sideOf(w, '22550.00', 'pe').find('[data-testid="cell-buy"]').trigger('click')
    await t(w, 'picker-done').trigger('click')
    await flushPromises()
    expect(w.props('legs')).toEqual([])
    expect(t(w, 'done-error').exists()).toBe(true)
    expect(calls.filter((x) => x.method === 'POST')).toHaveLength(0)
  })

  it('AC-3 attack 4: a selected strike the refresh re-centred out of the rows stays in the selection list and Done adds it', async () => {
    vi.useFakeTimers()
    try {
      const w = mountPicker()
      await flushPromises()
      await openStrikes(w)
      await sideOf(w, '22500.00', 'ce').find('[data-testid="cell-sell"]').trigger('click')
      expect(w.findAll('[data-testid="selection-row"]').map((r) => [r.attributes('data-instrument-id'), r.attributes('data-action'), r.attributes('data-lots')]))
        .toEqual([['NSE_FO:44002', 'SELL', '1']])
      // the 5 s refresh answers a window centred elsewhere: 22500 is no longer in the rows
      const moved = strikesAnswer()
      moved.rows = moved.rows.filter((r) => r.strike !== '22500.00')
      answers[STRIKES_URL()] = moved
      await vi.advanceTimersByTimeAsync(5000)
      expect(rowOf(w, '22500.00').exists()).toBe(false)
      const row = t(w, 'selection-row')
      expect(row.text()).toContain('NIFTY 13 Oct 22500 CE') // the contract, as the legs list names it
      expect([t(w, 'selection-side').text(), t(w, 'selection-lots').text()]).toEqual(['SELL', '1 lot'])
      // the selection list sits above Done
      expect(t(w, 'selection-list').element.compareDocumentPosition(t(w, 'picker-done').element) & 4).toBeTruthy()
      await t(w, 'picker-done').trigger('click')
      await vi.advanceTimersByTimeAsync(0)
      expect(w.props('legs').map((l) => [l.instrument_id, l.action, l.lots, l.planned_entry])).toEqual([['NSE_FO:44002', 'SELL', 1, '151.30']])
      expect(w.findAll('[data-testid="selection-row"]')).toHaveLength(0)
    } finally {
      vi.useRealTimers()
    }
  })

  it('AC-3: removing a contract from the selection list means Done no longer adds it; the other is added', async () => {
    const w = mountPicker()
    await flushPromises()
    await openStrikes(w)
    await sideOf(w, '22500.00', 'ce').find('[data-testid="cell-sell"]').trigger('click')
    await sideOf(w, '22500.00', 'ce').find('[data-testid="cell-lots"]').setValue('3')
    await sideOf(w, '22550.00', 'pe').find('[data-testid="cell-buy"]').trigger('click')
    await sideOf(w, '22550.00', 'pe').find('[data-testid="cell-lots"]').setValue('2')
    expect(w.findAll('[data-testid="selection-row"]').map((r) => r.find('[data-testid="selection-lots"]').text())).toEqual(['3 lot', '2 lot'])
    await w.find('[data-testid="selection-row"][data-instrument-id="NSE_FO:44002"] [data-testid="selection-remove"]').trigger('click')
    // a removed contract forgets its lots: selecting it again starts at 1
    await sideOf(w, '22500.00', 'ce').find('[data-testid="cell-sell"]').trigger('click')
    expect(w.find('[data-testid="selection-row"][data-instrument-id="NSE_FO:44002"]').attributes('data-lots')).toBe('1')
    await w.find('[data-testid="selection-row"][data-instrument-id="NSE_FO:44002"] [data-testid="selection-remove"]').trigger('click')
    expect(w.findAll('[data-testid="selection-row"]').map((r) => r.attributes('data-instrument-id'))).toEqual(['NSE_FO:44005'])
    expect(sideOf(w, '22500.00', 'ce').find('[data-testid="cell-sell"]').attributes('aria-pressed')).toBe('false')
    await t(w, 'picker-done').trigger('click')
    await flushPromises()
    expect(w.props('legs').map((l) => [l.instrument_id, l.action, l.lots])).toEqual([['NSE_FO:44005', 'BUY', 2]])
    expect(calls.filter((x) => x.method === 'POST').map((x) => x.body.instrument_ids)).toEqual([['NSE_FO:44005']])
  })

  it('AC-3: removing the only selection leaves Done disabled and sending nothing', async () => {
    const w = mountPicker()
    await flushPromises()
    await openStrikes(w)
    await sideOf(w, '22500.00', 'ce').find('[data-testid="cell-sell"]').trigger('click')
    await t(w, 'selection-remove').trigger('click')
    expect(t(w, 'selection-list').exists()).toBe(false)
    await t(w, 'picker-done').trigger('click')
    await flushPromises()
    expect(w.props('legs')).toEqual([])
    expect(calls.filter((x) => x.method === 'POST')).toHaveLength(0)
  })

  it('AC-3 (RD-129) core: three picked strikes show "3 selected" in a footer with Clear All and Done; Clear All empties it; Done adds all three', async () => {
    const pickThree = async (w) => {
      await sideOf(w, '22450.00', 'ce').find('[data-testid="cell-buy"]').trigger('click')
      await sideOf(w, '22500.00', 'ce').find('[data-testid="cell-sell"]').trigger('click')
      await sideOf(w, '22550.00', 'pe').find('[data-testid="cell-buy"]').trigger('click')
    }
    const w = mountPicker()
    await flushPromises()
    await openStrikes(w)
    expect(t(w, 'picker-count').text()).toBe('0 selected')
    expect(t(w, 'picker-clear-all').attributes('disabled')).toBeDefined()
    await pickThree(w)
    const footer = t(w, 'picker-footer')
    expect(t(w, 'picker-count').text()).toBe('3 selected')
    expect(footer.find('[data-testid="picker-clear-all"]').text()).toBe('Clear All')
    expect(footer.find('[data-testid="picker-done"]').text()).toBe('Done')
    // Clear All: no selection row, no pressed Buy/Sell, Done disabled, nothing sent
    await t(w, 'picker-clear-all').trigger('click')
    expect(t(w, 'picker-count').text()).toBe('0 selected')
    expect(w.findAll('[data-testid="selection-row"]')).toHaveLength(0)
    expect(w.findAll('[aria-pressed="true"]')).toHaveLength(0)
    expect(t(w, 'picker-done').attributes('disabled')).toBeDefined()
    expect(calls.filter((x) => x.method === 'POST')).toHaveLength(0)
    // a cleared cell forgets its lots, and Done adds all three at once
    await pickThree(w)
    expect(t(w, 'picker-count').text()).toBe('3 selected')
    await t(w, 'picker-done').trigger('click')
    await flushPromises()
    expect(w.props('legs').map((l) => [l.instrument_id, l.action])).toEqual([['NSE_FO:44000', 'BUY'], ['NSE_FO:44002', 'SELL'], ['NSE_FO:44005', 'BUY']])
    expect(w.emitted('update:legs')).toHaveLength(1)
    expect(t(w, 'picker-count').text()).toBe('0 selected')
  })

  it('AC-3 attack 6: Done with nothing selected adds nothing and sends no request', async () => {
    const w = mountPicker()
    await flushPromises()
    await openStrikes(w)
    expect(t(w, 'picker-done').attributes('disabled')).toBeDefined()
    expect(t(w, 'selection-list').exists()).toBe(false)
    const before = calls.length
    await t(w, 'picker-done').trigger('click')
    await flushPromises()
    expect(w.props('legs')).toEqual([])
    expect(calls.slice(before)).toEqual([])
    await w.vm.done() // the function itself, not only the disabled button, refuses an empty selection
    expect(w.emitted('update:legs')).toBeUndefined()
    expect(calls.slice(before)).toEqual([])
    // the clock moved explicitly past one refresh: the only request is that refresh's read, never a POST from Done
    await vi.advanceTimersByTimeAsync(5000)
    expect(calls.slice(before).map((x) => `${x.method} ${x.url}`)).toEqual([STRIKES_URL()])
    expect(w.emitted('update:legs')).toBeUndefined()
  })

  // standing item (d): the reply states for an expiry switch; each one leaves the NEW expiry's list (or its error) on screen
  async function switchWithOldPending() {
    let releaseOld
    answers[STRIKES_URL()] = () => new Promise((res) => { releaseOld = () => res({ data: strikesAnswer() }) })
    const w = mountPicker()
    await flushPromises()
    await openStrikes(w) // the 13 Oct read is now in flight
    await openStrikes(w, '2026-10-27')
    return { w, releaseOld }
  }
  const at27 = () => strikesAnswer({ expiry: '2026-10-27', rows: [{ strike: '23000.00', is_atm: true, ce: null, pe: null }] })

  it('an expiry switch: the new expiry\'s reply shows its strikes, and a late reply for the old expiry never replaces them', async () => {
    answers[STRIKES_URL(10, 'NIFTY', '2026-10-27')] = at27()
    const { w, releaseOld } = await switchWithOldPending()
    expect(w.findAll('[data-testid="strike-row"]').map((r) => r.attributes('data-strike'))).toEqual(['23000.00'])
    releaseOld()
    await flushPromises()
    expect(w.findAll('[data-testid="strike-row"]').map((r) => r.attributes('data-strike'))).toEqual(['23000.00'])
    expect(t(w, 'strikes-error').exists()).toBe(false)
  })

  it('an expiry switch: a failed reply for the new expiry shows the error, and a late old reply does not fill the list', async () => {
    answers[STRIKES_URL(10, 'NIFTY', '2026-10-27')] = new Error('down')
    const { w, releaseOld } = await switchWithOldPending()
    expect(t(w, 'strikes-error').exists()).toBe(true)
    releaseOld()
    await flushPromises()
    expect(w.findAll('[data-testid="strike-row"]')).toHaveLength(0)
    expect(t(w, 'strikes-error').exists()).toBe(true)
  })

  it('ADR-015: when a refresh fails the earlier list and prices are removed, never kept on screen as current', async () => {
    vi.useFakeTimers()
    try {
      const w = mountPicker()
      await flushPromises()
      await openStrikes(w)
      expect(w.findAll('[data-testid="strike-row"]')).toHaveLength(4)
      answers[STRIKES_URL()] = new Error('down')
      await vi.advanceTimersByTimeAsync(5000)
      expect(w.findAll('[data-testid="strike-row"]')).toHaveLength(0)
      expect(w.findAll('[data-testid="cell-ltp"]')).toHaveLength(0)
      expect(t(w, 'strikes-error').exists()).toBe(true)
    } finally {
      vi.useRealTimers()
    }
  })

  it('the open list refreshes on a timer and the timer stops when the picker is removed', async () => {
    vi.useFakeTimers()
    try {
      const w = mountPicker()
      await flushPromises()
      await openStrikes(w)
      const reads = () => calls.filter((x) => x.url.startsWith('/leg-picker/strikes')).length
      const first = reads()
      await vi.advanceTimersByTimeAsync(5000)
      expect(reads()).toBe(first + 1)
      w.unmount()
      await vi.advanceTimersByTimeAsync(20000)
      expect(reads()).toBe(first + 1)
    } finally {
      vi.useRealTimers()
    }
  })
})

describe('REQ-080 futures tab (W-147)', () => {
  const futuresAnswer = {
    state: 'LIVE', reason: null, underlying: 'NIFTY', spot: '22533.25', answered_at: AT,
    futures: [
      { expiry: '2026-10-27', instrument_id: 'NSE_FO:48704', lot_size: 65, ltp: '22610.40', health: 'available', ltp_reason: null },
      { expiry: '2026-11-24', instrument_id: 'NSE_FO:48705', lot_size: 65, ltp: null, health: 'unavailable', ltp_reason: 'NO_QUOTE' },
    ],
    forwards: [
      { expiry: '2026-10-13', forward: '22540.10', source: 'parity', label: null, strikes_used: 3, reason: null },
      { expiry: '2026-10-27', forward: '22548.00', source: 'spot_fallback', label: 'estimated from spot', strikes_used: 1, reason: null },
      { expiry: '2026-11-24', forward: null, source: null, label: null, strikes_used: 0, reason: 'NOT_PRICEABLE' },
    ],
  }
  it('ADR-015: a forward computed from a stale or delayed spot is labelled with that health; an available one is not', async () => {
    answers['GET /leg-picker/futures?underlying=NIFTY'] = {
      ...futuresAnswer,
      forwards: [
        { expiry: '2026-10-13', forward: '22557.59', source: 'spot_fallback', label: 'estimated from spot', strikes_used: 0, reason: null, spot_health: 'stale' },
        { expiry: '2026-10-27', forward: '22548.00', source: 'spot_fallback', label: 'estimated from spot', strikes_used: 0, reason: null, spot_health: 'delayed' },
        { expiry: '2026-11-24', forward: '22540.10', source: 'parity', label: null, strikes_used: 3, reason: null, spot_health: 'available' },
        { expiry: '2026-12-29', forward: '22540.10', source: 'parity', label: null, strikes_used: 3, reason: null },
      ],
    }
    const w = mountPicker()
    await flushPromises()
    await t(w, 'tab-futures').trigger('click')
    await flushPromises()
    const fw = w.findAll('[data-testid="forward-row"]')
    expect(fw[0].find('[data-testid="forward-health"]').text()).toContain('Stale:')
    expect(fw[1].find('[data-testid="forward-health"]').text()).toContain('Delayed:')
    expect(fw[2].find('[data-testid="forward-health"]').exists()).toBe(false)
    expect(fw[3].find('[data-testid="forward-health"]').text()).toContain('not known')
  })
  it('AC-6: every future with its LTP or reason, and each expiry\'s forward labelled "Forward used for pricing" with its source', async () => {
    answers['GET /leg-picker/futures?underlying=NIFTY'] = futuresAnswer
    const w = mountPicker()
    await flushPromises()
    await t(w, 'tab-futures').trigger('click')
    await flushPromises()
    const f = w.findAll('[data-testid="future-row"]')
    expect(f.map((r) => r.attributes('data-expiry'))).toEqual(['2026-10-27', '2026-11-24'])
    expect(f[0].find('[data-testid="future-ltp"]').text()).toBe('22610.40')
    expect(f[1].find('[data-testid="future-ltp"]').text()).toBe('-')
    expect(f[1].find('[data-testid="future-reason"]').text()).toBe('(No price has been received for this future yet.)')
    const fw = w.findAll('[data-testid="forward-row"]')
    expect(fw.map((r) => r.find('[data-testid="forward-value"]').text())).toEqual(['22540.10', '22548.00', '-'])
    expect(fw.every((r) => r.text().includes('Forward used for pricing'))).toBe(true)
    expect(fw[0].find('[data-testid="forward-source"]').text()).toBe('(from put-call parity)')
    expect(fw[1].find('[data-testid="forward-source"]').text()).toBe('(estimated from spot)')
    expect(fw[2].find('[data-testid="forward-reason"]').text()).toBe('(The engine cannot price this expiry right now.)')
    expect(t(w, 'futures-reason').exists()).toBe(false)
  })

  const openFutures = async () => {
    answers['GET /leg-picker/futures?underlying=NIFTY'] = futuresAnswer
    answers['GET /catalogue/NIFTY/contracts?expiry=2026-11-24'] = { underlying: 'NIFTY', contracts: [c(48705, 'FUT', null, 'NIFTY26NOVFUT', '2026-11-24')] }
    answers['POST /strategies/planned-entry'] = entryFor({ 48704: '22610.40' })
    const w = mountPicker()
    await flushPromises()
    await t(w, 'tab-futures').trigger('click')
    await flushPromises()
    return w
  }

  it('AC-9 (RD-134): Buy and Sell on a real future add a BUY / SELL futures leg, priced, through the normal capture path', async () => {
    const w = await openFutures()
    const row = (n) => w.findAll('[data-testid="future-row"]')[n]
    await row(0).find('[data-testid="future-buy"]').trigger('click')
    await flushPromises()
    expect(w.props('legs').map((l) => [l.instrument_id, l.instrument_type, l.strike, l.expiry, l.action, l.lots, l.planned_entry, l.captured_at]))
      .toEqual([['NSE_FO:48704', 'FUT', null, '2026-10-27', 'BUY', 1, '22610.40', AT]])
    expect(calls.filter((x) => x.method === 'POST').map((x) => x.body)).toEqual([{ underlying: 'NIFTY', instrument_ids: ['NSE_FO:48704'] }])
    await row(0).find('[data-testid="future-sell"]').trigger('click')
    await flushPromises()
    expect(w.props('legs').map((l) => l.action)).toEqual(['BUY', 'SELL'])
  })

  it('AC-9: an unpriced real future is still added, with no entry and the reprice prompt (existing unpriced rules)', async () => {
    const w = await openFutures()
    await w.findAll('[data-testid="future-row"]')[1].find('[data-testid="future-sell"]').trigger('click')
    await flushPromises()
    expect(w.props('legs')).toMatchObject([{ instrument_id: 'NSE_FO:48705', action: 'SELL', planned_entry: null, captured_at: null, reason_code: 'needs_reprice' }])
  })

  it('AC-9: a future the catalogue cannot confirm adds nothing and says so', async () => {
    const w = await openFutures()
    answers['GET /catalogue/NIFTY/contracts?expiry=2026-11-24'] = new Error('down')
    await w.findAll('[data-testid="future-row"]')[1].find('[data-testid="future-buy"]').trigger('click')
    await flushPromises()
    expect(w.props('legs')).toEqual([])
    expect(t(w, 'future-add-error').exists()).toBe(true)
    expect(calls.filter((x) => x.method === 'POST')).toHaveLength(0)
  })

  it('AC-9: the forward (calculated price) rows have no Buy or Sell; only real futures do', async () => {
    const w = await openFutures()
    expect(w.findAll('[data-testid="future-buy"]')).toHaveLength(2)
    expect(w.findAll('[data-testid="future-sell"]')).toHaveLength(2)
    const fw = w.findAll('[data-testid="forward-row"]')
    expect(fw).toHaveLength(3)
    expect(fw.every((r) => r.findAll('button').length === 0)).toBe(true)
  })

  it('AC-5: a list-level reason shows above the futures, and a failed read shows no old list', async () => {
    answers['GET /leg-picker/futures?underlying=NIFTY'] = { ...futuresAnswer, state: 'NOT_LIVE', reason: 'NOT_CONNECTED', futures: [], forwards: [] }
    const w = mountPicker()
    await flushPromises()
    await t(w, 'tab-futures').trigger('click')
    await flushPromises()
    expect(t(w, 'futures-reason').text()).toBe('Live data is not connected, so no prices are shown.')
    answers['GET /leg-picker/futures?underlying=NIFTY'] = new Error('down')
    const w2 = mountPicker()
    await flushPromises()
    await t(w2, 'tab-futures').trigger('click')
    await flushPromises()
    expect(t(w2, 'futures-error').exists()).toBe(true)
    expect(w2.findAll('[data-testid="future-row"]')).toHaveLength(0)
  })
})

describe('ADR-199 (4): the drawer opens on the reply\'s default_expiry', () => {
  it('with no legs it opens on default_expiry, not the first listed expiry', async () => {
    answers['GET /catalogue/NIFTY/expiries'] = { underlying: 'NIFTY', expiries: ['2026-10-13', '2026-10-27'], default_expiry: '2026-10-27' }
    const w = mountPicker()
    await flushPromises()
    expect(t(w, 'pick-expiry').element.value).toBe('2026-10-27')
  })

  it('with legs it opens on the legs\' expiry even when the default differs', async () => {
    answers['GET /catalogue/NIFTY/expiries'] = { underlying: 'NIFTY', expiries: ['2026-10-13', '2026-10-27'], default_expiry: '2026-10-27' }
    const legs = [{ id: 1, underlying: 'NIFTY', instrument_id: 'NSE_FO:44624', contract_id: 1, symbol: 'NIFTY26O1322800CE', expiry: '2026-10-13', instrument_type: 'CE', strike: '22800.00', lot_size: 65, action: 'SELL', lots: 1, planned_entry: null, captured_at: null, reason_code: 'needs_reprice' }]
    const w = mountPicker(legs)
    await flushPromises()
    expect(t(w, 'pick-expiry').element.value).toBe('2026-10-13')
  })
})

describe('REQ-135 AC-2: days beside every expiry in the picker (the server\'s count; the value stays the ISO date)', () => {
  const DAYS = [{ expiry: '2026-10-13', days: 0 }, { expiry: '2026-10-27', days: 14 }]
  it('the expiry select shows "Today (0 days)" and "27 Oct (14 days)" and keeps ISO values', async () => {
    answers['GET /catalogue/NIFTY/expiries'] = { underlying: 'NIFTY', expiries: ['2026-10-13', '2026-10-27'], expiry_days: DAYS }
    const w = mountPicker()
    await flushPromises()
    expect(t(w, 'pick-expiry').findAll('option').filter((o) => o.element.value).map((o) => o.text())).toEqual(['Today (0 days)', '27 Oct (14 days)'])
    expect(options(w, 'pick-expiry')).toEqual(['2026-10-13', '2026-10-27'])
    const before = calls.length
    await t(w, 'pick-expiry').setValue('2026-10-27')
    await flushPromises()
    const named = calls.slice(before).filter((c) => c.url.includes('expiry='))
    expect(named.length).toBeGreaterThan(0)
    expect(named.every((c) => c.url.includes('expiry=2026-10-27'))).toBe(true) // the ISO date, never the label
  })

  it('a reply with no day count shows the date alone, never raw ISO (REQ-148 AC-2)', async () => {
    const w = mountPicker()
    await flushPromises()
    expect(t(w, 'pick-expiry').findAll('option').filter((o) => o.element.value).map((o) => o.text())).toEqual(['13 Oct', '27 Oct']) // REQ-148 AC-2: never raw ISO
  })

  it('the Futures tab rows and forward rows take their label from the expiries reply', async () => {
    answers['GET /catalogue/NIFTY/expiries'] = { underlying: 'NIFTY', expiries: ['2026-10-13', '2026-10-27'], expiry_days: DAYS }
    answers['GET /leg-picker/futures?underlying=NIFTY'] = {
      underlying: 'NIFTY',
      futures: [{ expiry: '2026-10-27', instrument_id: 'NSE_FO:48704', ltp: '22610.40', reason: null }],
      forwards: [{ expiry: '2026-10-27', forward: '22548.00', source: 'parity', label: null, strikes_used: 3, reason: null }],
    }
    const w = mountPicker()
    await flushPromises()
    await t(w, 'tab-futures').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="future-row"]').text()).toContain('27 Oct (14 days) future')
    expect(w.find('[data-testid="future-row"]').attributes('data-expiry')).toBe('2026-10-27')
    expect(w.find('[data-testid="forward-row"]').text()).toContain('27 Oct (14 days)')
  })
})

// ---- W-195 (ADR-193 PR-3, UI-200..UI-207): the picker as Sensibull's left slide-in strike drawer. ----
describe('W-195 strike drawer (UI-200..UI-207)', () => {
  beforeEach(() => {
    answers['GET /catalogue/NIFTY/contracts?expiry=2026-10-13'] = catalogue13
    answers[STRIKES_URL()] = strikesAnswer()
    answers['POST /strategies/planned-entry'] = entryFor({ 44002: '151.30', 44005: '145.10' })
  })

  it('UI-202 (combined check A): the OI shown is the server number and no bar is drawn (a bar width would be browser maths, ADR-008)', async () => {
    const w = mountPicker()
    await flushPromises()
    await openStrikes(w)
    expect(sideOf(w, '22500.00', 'ce').find('[data-testid="cell-oi"]').text()).toBe('3218475')
    expect(w.findAll('[data-testid="cell-oi-bar"]')).toHaveLength(0)
  })

  it('UI-202: ITM halves are shaded from the server ATM flag only (calls below ATM, puts above); no ATM row shades nothing', async () => {
    const w = mountPicker()
    await flushPromises()
    await openStrikes(w)
    const shaded = (strike, side) => sideOf(w, strike, side).findAll('.bg-warn-soft').length > 0
    expect(GRID.map((s) => [shaded(s, 'ce'), shaded(s, 'pe')])).toEqual([[true, false], [true, false], [false, false], [false, true]])
    answers[STRIKES_URL()] = strikesAnswer({ centre: 'MIDDLE_STRIKE', spot: null, atm_strike: null, rows: strikesAnswer().rows.map((r) => ({ ...r, is_atm: false })) })
    const w2 = mountPicker()
    await flushPromises()
    await openStrikes(w2)
    expect(w2.findAll('[data-testid="strike-row"]')).toHaveLength(4)
    expect(w2.findAll('.bg-warn-soft')).toHaveLength(0)
  })

  it('UI-202/UI-205: the view switch changes the columns (LTP default, Greeks = Delta and IV); width and size sit in Settings', async () => {
    const w = mountPicker()
    await flushPromises()
    await openStrikes(w)
    expect(t(w, 'picker-view-ltp').attributes('aria-checked')).toBe('true')
    expect(t(w, 'strike-head').text()).toBe('Call DeltaCall LTPCall OICall IVStrikePut IVPut OIPut LTPPut Delta')
    await t(w, 'picker-view-greeks').trigger('click')
    expect(t(w, 'strike-head').text()).toBe('Call DeltaCall IVStrikePut IVPut Delta')
    expect(sideOf(w, '22500.00', 'ce').find('[data-testid="cell-ltp"]').exists()).toBe(false)
    expect(sideOf(w, '22500.00', 'ce').find('[data-testid="cell-delta"]').text()).toBe('0.5730')
    expect(sideOf(w, '22500.00', 'ce').find('[data-testid="cell-buy"]').exists()).toBe(true) // B/S stay in every view
    await t(w, 'picker-view-oi').trigger('click')
    expect(t(w, 'strike-head').text()).toBe('Call LTPCall OIStrikePut OIPut LTP')
    expect(t(w, 'picker-settings-popover').find('[data-testid="pick-width"]').exists()).toBe(true)
    expect(t(w, 'picker-settings-popover').find('[data-testid="pick-lots-mode"]').exists()).toBe(true)
  })

  it('UI-203: B and S are named for screen readers and the qty sub-row shows only under a chosen side', async () => {
    const w = mountPicker()
    await flushPromises()
    await openStrikes(w)
    const ce = sideOf(w, '22500.00', 'ce')
    expect(ce.find('[data-testid="cell-buy"]').attributes('aria-label')).toBe('Buy 22500 CE')
    expect(ce.find('[data-testid="cell-sell"]').attributes('aria-label')).toBe('Sell 22500 CE')
    const qty = () => ce.find('[data-testid="cell-lots"]').element.closest('label')
    expect(qty().style.display).toBe('none')
    await ce.find('[data-testid="cell-buy"]').trigger('click')
    expect(qty().style.display).toBe('')
    expect(ce.find('[data-testid="cell-buy"]').classes()).toContain('bg-buy')
  })

  it('UI-206 core: B on a strike then Done adds that leg with its planned entry and emits done (the Builder closes the drawer)', async () => {
    const w = mountPicker()
    await flushPromises()
    await openStrikes(w)
    await sideOf(w, '22500.00', 'ce').find('[data-testid="cell-buy"]').trigger('click')
    expect(t(w, 'picker-footer').find('[data-testid="picker-pick-chain"]').text()).toBe('Pick from Option Chain')
    await t(w, 'picker-done').trigger('click')
    await flushPromises()
    expect(w.props('legs').map((l) => [l.instrument_id, l.action, l.lots, l.planned_entry])).toEqual([['NSE_FO:44002', 'BUY', 1, '151.30']])
    expect(w.emitted('done')).toHaveLength(1)
  })

  it('UI-200: the Builder opens the picker as a LEFT drawer from Add/Edit, Done adds the leg and closes it, the close button shuts it', async () => {
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
    await router.push({ path: '/strategy/builder' })
    await router.isReady()
    const w = mount(StrategyBuilderPage, { attachTo: document.body, global: { plugins: [router] } })
    await flushPromises()
    const drawer = () => w.find('[data-testid="drawer"][data-side="left"]')
    expect(drawer().find('[data-testid="leg-picker"]').exists()).toBe(true) // mounted while shut, so Edit can open it on a leg
    expect(drawer().element.parentElement.style.display).toBe('none') // no inline add-leg form in the left column
    await t(w, 'add-edit').trigger('click')
    expect(drawer().element.parentElement.style.display).toBe('')
    expect(t(w, 'add-edit').attributes('aria-expanded')).toBe('true')
    await openStrikes(w)
    await sideOf(w, '22500.00', 'ce').find('[data-testid="cell-buy"]').trigger('click')
    await t(w, 'picker-done').trigger('click')
    await flushPromises()
    expect(drawer().element.parentElement.style.display).toBe('none')
    expect(w.findComponent(LegPicker).props('legs').map((l) => [l.instrument_id, l.action, l.planned_entry])).toEqual([['NSE_FO:44002', 'BUY', '151.30']])
    await t(w, 'add-edit').trigger('click')
    await drawer().find('[data-testid="drawer-close"]').trigger('click')
    expect(drawer().element.parentElement.style.display).toBe('none')
    w.unmount()
  })
})

describe('#582 item 7/8: the strike drawer list scrolls above its footer; strikes print as whole numbers', () => {
  const stackOf = (n) => Array.from({ length: n }, (_, i) => `${20000 + i * 50}.00`)
  const grid = (strikes) => ({
    ...strikesAnswer(),
    atm_strike: strikes[0] ?? null,
    rows: strikes.map((strike, i) => ({ strike, is_atm: i === 0, ce: cell(i, 'ce'), pe: cell(i, 'pe') })),
  })
  async function openWith(strikes) {
    answers['GET /catalogue/NIFTY/contracts?expiry=2026-10-13'] = catalogue13
    answers[STRIKES_URL()] = grid(strikes)
    const w = mountPicker()
    await flushPromises()
    await openStrikes(w)
    return w
  }

  it.each([0, 21, 60])('with %i strikes the list is the scroll area and the footer sits after it', async (n) => {
    const w = await openWith(stackOf(n))
    const panel = t(w, 'strikes-panel')
    expect(panel.classes()).toEqual(expect.arrayContaining(['overflow-y-auto', 'flex-1', 'min-h-0']))
    const footer = t(w, 'picker-footer')
    expect(footer.classes()).toContain('shrink-0')
    expect(footer.classes()).not.toContain('sticky')
    const tabs = t(w, 'picker-tabs')
    expect(tabs.classes()).toEqual(expect.arrayContaining(['flex-1', 'min-h-0', 'flex-col']))
    expect(panel.element.parentElement).toBe(tabs.element)
    const root = t(w, 'leg-picker')
    const kids = [...root.element.children]
    expect(kids.indexOf(tabs.element)).toBeGreaterThanOrEqual(0)
    expect(kids.indexOf(tabs.element)).toBeLessThan(kids.indexOf(footer.element))
    expect(root.classes()).toEqual(expect.arrayContaining(['h-full', 'min-h-0', 'flex-col']))
    expect(panel.element.contains(footer.element)).toBe(false)
    expect(w.findAll('[data-testid="strike-row"]')).toHaveLength(n)
  })

  it('prints each strike as a whole number in the row and keeps a real fraction', async () => {
    const w = await openWith(['22450.00', '22450.50'])
    expect(w.findAll('[data-testid="row-strike"]').map((e) => e.text().replace('ATM', ''))).toEqual(['22450', '22450.5'])
    expect(w.find('[data-testid="strike-row"]').attributes('data-strike')).toBe('22450.00')
  })
})

// GC-BM G-070 (REQ-150 AC-4, Sensibull S-032): the drawer opens on an expiry with its strikes listed.
describe('G-070: the drawer opens on the nearest expiry with its strikes', () => {
  const LIVE = (e) => ({ state: 'LIVE', rows: [], underlying: 'NIFTY', expiry: e })
  const strikeReads = () => calls.filter((x) => x.url.startsWith('/leg-picker/strikes'))
  beforeEach(() => {
    answers[STRIKES_URL(10, 'NIFTY', '2026-10-13')] = LIVE('2026-10-13')
    answers[STRIKES_URL(10, 'NIFTY', '2026-10-27')] = LIVE('2026-10-27')
  })

  it('no legs: the first listed expiry is chosen and its strikes are read once', async () => {
    const w = mountPicker()
    await flushPromises()
    expect(t(w, 'pick-expiry').element.value).toBe('2026-10-13')
    expect(t(w, 'strikes-choose-expiry').exists()).toBe(false)
    expect(strikeReads().map((x) => x.url)).toEqual(['/leg-picker/strikes?underlying=NIFTY&expiry=2026-10-13&width=10'])
  })

  it('a leg on the later expiry: the drawer opens on that expiry, not the nearest', async () => {
    const leg = { id: 1, underlying: 'NIFTY', expiry: '2026-10-27', instrument_type: 'FUT', strike: null, action: 'BUY', lots: 1, instrument_id: 'NSE_FO:48704' }
    const w = mountPicker([leg])
    await flushPromises()
    expect(t(w, 'pick-expiry').element.value).toBe('2026-10-27')
    expect(strikeReads().map((x) => x.url)).toEqual(['/leg-picker/strikes?underlying=NIFTY&expiry=2026-10-27&width=10'])
  })

  it('no expiry can be read: the reason shows, no strikes are requested', async () => {
    const parts = { what_happened: 'a', impact: 'b', what_is_blocked: 'c', next_action: 'd' }
    answers['GET /catalogue/NIFTY/expiries'] = Object.assign(new Error('x'), { parts, status: 422 })
    const w = mountPicker()
    await flushPromises()
    expect(t(w, 'picker-error').text()).toContain('a')
    expect(t(w, 'pick-expiry').element.value).toBe('')
    expect(strikeReads()).toEqual([])
  })

  it('an empty expiry list: nothing chosen, no strikes requested', async () => {
    answers['GET /catalogue/NIFTY/expiries'] = { underlying: 'NIFTY', expiries: [] }
    const w = mountPicker()
    await flushPromises()
    expect(t(w, 'pick-expiry').element.value).toBe('')
    expect(strikeReads()).toEqual([])
  })
})

// GC-BM F-12 (G-070 round 2): the opening state is decided when the drawer OPENS, not at mount. The real page order: the
// picker mounts shut with no legs, the legs arrive later, then the drawer opens.
describe('F-12: the drawer opens on the strategy expiry every time it is opened', () => {
  const NOV3 = '2026-11-03'
  const NOV9 = '2026-11-09'
  const strikeReads = () => calls.filter((x) => x.url.startsWith('/leg-picker/strikes')).map((x) => x.url)
  const leg = (id, expiry) => ({ id, underlying: 'NIFTY', expiry, instrument_type: 'CE', strike: '22800.00', action: 'SELL', lots: 1, instrument_id: `NSE_FO:${id}` })
  beforeEach(() => {
    answers['GET /catalogue/NIFTY/expiries'] = { underlying: 'NIFTY', expiries: ['2026-10-27', NOV3, NOV9] }
    for (const e of ['2026-10-27', NOV3, NOV9]) {
      answers[`GET /catalogue/NIFTY/contracts?expiry=${e}`] = { underlying: 'NIFTY', contracts: [] }
      answers[`GET /leg-picker/strikes?underlying=NIFTY&expiry=${e}&width=10`] = { state: 'LIVE', rows: [], underlying: 'NIFTY', expiry: e }
    }
  })
  async function shutPicker() {
    const w = mount(LegPicker, { props: { legs: [], active: false, 'onUpdate:legs': (v) => w.setProps({ legs: v }) } })
    await flushPromises()
    return w
  }
  const open = async (w) => { await w.setProps({ active: true }); await flushPromises() }
  const close = async (w) => { await w.setProps({ active: false }); await flushPromises() }
  const shown = (w) => t(w, 'pick-expiry').element.value

  it('1: mounted with no legs, then legs on 3 Nov, then opened: 3 Nov, its strikes read once', async () => {
    const w = await shutPicker()
    await w.setProps({ legs: [leg(1, NOV3), leg(2, NOV3)] })
    calls.length = 0
    await open(w)
    expect(shown(w)).toBe(NOV3)
    expect(strikeReads()).toEqual([`/leg-picker/strikes?underlying=NIFTY&expiry=${NOV3}&width=10`])
  })

  it('2: a hand pick of 9 Nov is kept while open and gone on the next open (3 Nov again)', async () => {
    const w = await shutPicker()
    await w.setProps({ legs: [leg(1, NOV3)] })
    await open(w)
    await t(w, 'pick-expiry').setValue(NOV9)
    await flushPromises()
    expect(shown(w)).toBe(NOV9)
    await close(w)
    await open(w)
    expect(shown(w)).toBe(NOV3)
  })

  it('3: legs cleared, then opened: the nearest expiry', async () => {
    const w = await shutPicker()
    await w.setProps({ legs: [leg(1, NOV3)] })
    await open(w)
    await close(w)
    await w.setProps({ legs: [] })
    await open(w)
    expect(shown(w)).toBe('2026-10-27')
  })

  it('4: Edit of a 9 Nov leg shows 9 Nov', async () => {
    const w = await shutPicker()
    await w.setProps({ legs: [leg(1, NOV3), leg(2, NOV9)] })
    await open(w)
    await w.vm.startEdit(leg(2, NOV9))
    await flushPromises()
    expect(shown(w)).toBe(NOV9)
  })

  it('5: the underlying switched while shut, then opened: that underlying nearest expiry', async () => {
    const w = await shutPicker()
    answers['GET /catalogue/SENSEX/expiries'] = { underlying: 'SENSEX', expiries: ['2026-10-29', '2026-11-05'] }
    answers['GET /catalogue/SENSEX/contracts?expiry=2026-10-29'] = { underlying: 'SENSEX', contracts: [] }
    answers['GET /leg-picker/strikes?underlying=SENSEX&expiry=2026-10-29&width=10'] = { state: 'LIVE', rows: [], underlying: 'SENSEX', expiry: '2026-10-29' }
    await t(w, 'pick-underlying').setValue('SENSEX')
    await flushPromises()
    await open(w)
    expect(shown(w)).toBe('2026-10-29')
  })

  // GC-BM F-13 items 3 and 4
  const reads = (prefix) => calls.filter((x) => x.url.startsWith(prefix)).map((x) => x.url)
  it('F-13 attack 5: page load with the drawer shut reads no strikes and no contracts; opening reads strikes once', async () => {
    calls.length = 0
    const w = await shutPicker()
    expect(reads('/leg-picker/strikes')).toEqual([])
    expect(reads('/catalogue/NIFTY/contracts')).toEqual([])
    await open(w)
    expect(reads('/leg-picker/strikes')).toEqual(['/leg-picker/strikes?underlying=NIFTY&expiry=2026-10-27&width=10'])
    expect(shown(w)).toBe('2026-10-27')
  })

  it('F-13 attack 4: Futures tab, drawer shut, legs move to another expiry, reopened: futures prices are read once on open', async () => {
    answers['GET /leg-picker/futures?underlying=NIFTY'] = { state: 'LIVE', futures: [], forwards: [], underlying: 'NIFTY' }
    const w = await shutPicker()
    await open(w)
    await t(w, 'tab-futures').trigger('click')
    await flushPromises()
    await close(w)
    await w.setProps({ legs: [leg(1, NOV3)] })
    calls.length = 0
    await open(w)
    expect(shown(w)).toBe(NOV3)
    expect(reads('/leg-picker/futures')).toEqual(['/leg-picker/futures?underlying=NIFTY'])
    expect(reads('/leg-picker/strikes')).toEqual([])
  })

  it('F-13: opened on the Strikes tab with the expiry unchanged, strikes are read once on every open', async () => {
    const w = await shutPicker()
    await open(w)
    await close(w)
    calls.length = 0
    await open(w)
    expect(reads('/leg-picker/strikes')).toEqual(['/leg-picker/strikes?underlying=NIFTY&expiry=2026-10-27&width=10'])
  })
})

// GC-BM F-14: the drawer works on the STRATEGY's underlying, decided when it opens (not at mount)
describe('F-14: the drawer opens on the strategy underlying', () => {
  const OCT29 = '2026-10-29'
  const sxLeg = (id) => ({ id, underlying: 'SENSEX', expiry: OCT29, instrument_type: 'CE', strike: '73600.00', action: 'SELL', lots: 1, instrument_id: `BSE_FO:${id}` })
  const nfLeg = (id) => ({ id, underlying: 'NIFTY', expiry: '2026-10-27', instrument_type: 'CE', strike: '22800.00', action: 'SELL', lots: 1, instrument_id: `NSE_FO:${id}` })
  const strikeReads = () => calls.filter((x) => x.url.startsWith('/leg-picker/strikes')).map((x) => x.url)
  const sxStrikes = `/leg-picker/strikes?underlying=SENSEX&expiry=${OCT29}&width=10`
  beforeEach(() => {
    answers['GET /catalogue/NIFTY/expiries'] = { underlying: 'NIFTY', expiries: ['2026-10-27', '2026-11-03'] }
    answers['GET /catalogue/NIFTY/contracts?expiry=2026-10-27'] = { underlying: 'NIFTY', contracts: [] }
    answers['GET /leg-picker/strikes?underlying=NIFTY&expiry=2026-10-27&width=10'] = { state: 'LIVE', rows: [], underlying: 'NIFTY', expiry: '2026-10-27' }
    answers['GET /catalogue/SENSEX/expiries'] = { underlying: 'SENSEX', expiries: [OCT29, '2026-11-05'] }
    answers[`GET /catalogue/SENSEX/contracts?expiry=${OCT29}`] = { underlying: 'SENSEX', contracts: [] }
    answers[`GET ${sxStrikes}`] = { state: 'LIVE', rows: [], underlying: 'SENSEX', expiry: OCT29 }
  })
  async function shut(extra = {}) {
    const w = mount(LegPicker, { props: { legs: [], active: false, ...extra, 'onUpdate:legs': (v) => w.setProps({ legs: v }) } })
    await flushPromises()
    return w
  }
  const open = async (w) => { await w.setProps({ active: true }); await flushPromises() }

  it('1: mounted empty (NIFTY), SENSEX legs arrive, opened: SENSEX, 29 Oct, SENSEX strikes read once, select locked', async () => {
    const w = await shut()
    await w.setProps({ legs: [sxLeg(1), sxLeg(2)] })
    calls.length = 0
    await open(w)
    expect(t(w, 'pick-underlying').element.value).toBe('SENSEX')
    expect(t(w, 'pick-underlying').element.disabled).toBe(true)
    expect(t(w, 'pick-expiry').element.value).toBe(OCT29)
    expect(strikeReads()).toEqual([sxStrikes])
  })

  it('2: no legs, page underlying SENSEX, opened: SENSEX and its nearest expiry', async () => {
    const w = await shut()
    await w.setProps({ pageUnderlying: 'SENSEX' })
    calls.length = 0
    await open(w)
    expect(t(w, 'pick-underlying').element.value).toBe('SENSEX')
    expect(t(w, 'pick-expiry').element.value).toBe(OCT29)
    expect(strikeReads()).toEqual([sxStrikes])
  })

  it('3: SENSEX legs cleared, page back to NIFTY, opened: NIFTY', async () => {
    const w = await shut({ pageUnderlying: 'SENSEX' })
    await w.setProps({ legs: [sxLeg(1)] })
    await open(w)
    await w.setProps({ active: false })
    await w.setProps({ legs: [], pageUnderlying: 'NIFTY' })
    await open(w)
    expect(t(w, 'pick-underlying').element.value).toBe('NIFTY')
    expect(t(w, 'pick-underlying').element.disabled).toBe(false)
    expect(t(w, 'pick-expiry').element.value).toBe('2026-10-27')
  })

  it('4: Edit of a SENSEX leg shows SENSEX and the leg expiry', async () => {
    const w = await shut()
    await w.setProps({ legs: [sxLeg(1)] })
    await open(w)
    await w.vm.startEdit(sxLeg(1))
    await flushPromises()
    expect(t(w, 'pick-underlying').element.value).toBe('SENSEX')
    expect(t(w, 'pick-expiry').element.value).toBe(OCT29)
  })

  it('5: a shut picker reads no strikes; NIFTY legs on a NIFTY mount read NIFTY once on open', async () => {
    calls.length = 0
    const w = await shut({ legs: [nfLeg(1)] })
    expect(strikeReads()).toEqual([])
    await open(w)
    expect(t(w, 'pick-underlying').element.value).toBe('NIFTY')
    expect(strikeReads()).toEqual(['/leg-picker/strikes?underlying=NIFTY&expiry=2026-10-27&width=10'])
  })
})
