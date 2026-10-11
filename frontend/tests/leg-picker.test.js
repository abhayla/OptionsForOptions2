// W-068 / REQ-035 AC-8: the Builder adds and edits legs only from contracts the catalogue API offers, and the picked
// legs reach the outcome API as the draft it already prices.
// The mocked API answers are the REAL shapes of backend/ofo_app/routes/catalogue.py (exchange_segment and exchange_token
// apart, strike a string or null for FUT, lot_size an int) and routes/planned_entry.py (planned_entry string + captured_at
// + source, or null + reason_code). Tokens and symbols are the recorded NIFTY 13-Oct-2026 contracts of the outcome fixture
// (44595/44604/44624/44632) and the instruments slice (FUT 48704). No price here is computed or defaulted by the page.
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
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
import { NOT_CONNECTED_LABEL, lotsValid, instrumentId, buildDraft } from '@/lib/legPicker'

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
    expect(calls.map((x) => x.url)).toEqual(['/catalogue/NIFTY/expiries'])
    await t(w, 'pick-expiry').setValue('2026-10-13')
    await flushPromises()
    expect(calls.at(-1).url).toBe('/catalogue/NIFTY/contracts?expiry=2026-10-13')
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
    expect(t(w, 'pick-expiry').element.value).toBe('')
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

describe('buildDraft: the body the outcome API takes', () => {
  const priced = { underlying: 'NIFTY', instrument_id: 'NSE_FO:44624', action: 'SELL', lots: 2, planned_entry: '104.65', captured_at: AT, symbol: 'x' }
  const unpriced = { ...priced, instrument_id: 'NSE_FO:44632', planned_entry: null, captured_at: null }
  it('sends only priced legs, with exactly the five fields its leg model has', () => {
    expect(buildDraft([priced, unpriced])).toEqual({
      underlying: 'NIFTY',
      legs: [{ instrument_id: 'NSE_FO:44624', action: 'SELL', lots: 2, planned_entry: '104.65', captured_at: AT }],
    })
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
      ux_level: 'standard',
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

  it('the existing ?draft= path still works: its legs are sent unchanged and listed in the picker', async () => {
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
    expect(out[0].body).toEqual({ ...draft, ux_level: 'standard' })
    expect(w.findAll('[data-testid="leg-row"]')).toHaveLength(2)
    expect(t(w, 'strategy-builder').attributes('data-state')).toBe('not-connected')
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
