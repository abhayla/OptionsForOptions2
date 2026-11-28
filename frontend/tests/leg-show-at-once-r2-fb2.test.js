// Lane FB2 item 2 (I-49, T2-11): a leg shows at once; the planned-entry reply fills it in. Helpers copied from leg-picker.test.js.
// W-068 / REQ-035 AC-8: the Builder adds and edits legs only from contracts the catalogue API offers, and the picked
// legs reach the outcome API as the draft it already prices.
// The mocked API answers are the REAL shapes of backend/ofo_app/routes/catalogue.py (exchange_segment and exchange_token
// apart, strike a string or null for FUT, lot_size an int) and routes/planned_entry.py (planned_entry string + captured_at
// + source, or null + reason_code). Tokens and symbols are the recorded NIFTY 13-Oct-2026 contracts of the outcome fixture
// (44595/44604/44624/44632) and the instruments slice (FUT 48704). No price here is computed or defaulted by the page.
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount as mountRaw, flushPromises, enableAutoUnmount } from '@vue/test-utils'
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
import { settingsData } from './helpers/servedLots'

// the page passes the served lot caps down (REQ-167 AC-5); a picker mounted alone gets them as props
const mount = (C, o = {}) => mountRaw(C, C === LegPicker ? { ...o, props: { maxLots: 10000, lotChoiceCount: 10, ...o.props } } : o)

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
    'GET /settings': settingsData(),
    'GET /catalogue/NIFTY/expiries': { underlying: 'NIFTY', today: '2026-10-10', expiries: ['2026-10-13', '2026-10-27'] },
    'GET /catalogue/SENSEX/expiries': { underlying: 'SENSEX', today: '2026-10-10', expiries: ['2026-10-15'] },
    'GET /catalogue/NIFTY/contracts?expiry=2026-10-13': NIFTY_13,
    'GET /catalogue/NIFTY/contracts?expiry=2026-10-27': NIFTY_27,
    'GET /leg-picker/strikes?underlying=NIFTY&expiry=2026-10-13': pkStrikes(),
  }
})

const t = (w, id) => w.find(`[data-testid="${id}"]`)

function mountPicker(initial = []) {
  const w = mount(LegPicker, {
    props: { legs: initial, 'onUpdate:legs': (v) => w.setProps({ legs: v }) },
  })
  return w
}

// GC-UI step 2 (D-C31): a leg is added only through the strike table's B / S buttons and Done; the by-contract form is
// the Edit / Reprice path only. These strikes are the four recorded NIFTY 13-Oct contracts of NIFTY_13 above.
const PK_ROWS = [['22200.00', 'PE', 44595], ['22400.00', 'PE', 44604], ['22800.00', 'CE', 44624], ['23000.00', 'CE', 44632]]
const pkCell = (token) => ({ instrument_id: `NSE_FO:${token}`, lot_size: 65, ltp: null, oi: null, iv_percent: null, delta: null, health: 'unavailable', at: null })
const pkStrikes = () => ({
  state: 'LIVE', reason: null, underlying: 'NIFTY', expiry: '2026-10-13', width: 10, spot: '22533.25', spot_at: AT, centre: 'LIVE_SPOT',
  atm_strike: '22800.00', answered_at: AT, market_closed: false,
  rows: PK_ROWS.map(([strike, type, token]) => ({ strike, is_atm: false, ce: type === 'CE' ? pkCell(token) : null, pe: type === 'PE' ? pkCell(token) : null })),
})
const PK_URL = 'GET /leg-picker/strikes?underlying=NIFTY&expiry=2026-10-13'

/** Choose a contract the only way the page offers: B or S on its cell in the strike table (lots from the cell's own select). */
async function pick(w, { expiry = '2026-10-13', type, strike, action = 'SELL', lots = '1' }) {
  answers[PK_URL] = pkStrikes()
  if (t(w, 'add-edit').exists() && t(w, 'add-edit').attributes('aria-expanded') !== 'true') { // on the page the picker is a drawer
    await t(w, 'add-edit').trigger('click')
    await flushPromises()
  }
  if (t(w, 'pick-expiry').element.value !== expiry) await t(w, 'pick-expiry').setValue(expiry)
  await flushPromises()
  const side = w.find(`[data-testid="strike-row"][data-strike="${strike}"] [data-testid="cell-${type.toLowerCase()}"]`)
  await side.find(`[data-testid="cell-${action === 'BUY' ? 'buy' : 'sell'}"]`).trigger('click')
  if (lots !== '1') await side.find('[data-testid="cell-lots"]').setValue(lots)
}


import LegList from '@/components/strategy/LegList.vue'
import { LEG_WORKING_TEXT } from '@/lib/sharedStateText'

let release
const slow = (price = '104.65') => { answers['POST /strategies/planned-entry'] = () => new Promise((res) => { release = () => res({ data: { entries: [entry(44624, price)] } }) }) }
async function doneWithOne(w) {
  await pick(w, { type: 'CE', strike: '22800.00' })
  await t(w, 'picker-done').trigger('click')
  await flushPromises()
}

describe('item 2: the leg shows at once, the planned-entry reply fills it in', () => {
  it('CORE: with the planned-entry reply still out, the leg is already in the list, marked as being priced, and Done has handed the page back', async () => {
    slow()
    const w = mountPicker()
    await flushPromises()
    await doneWithOne(w)
    expect(w.props('legs')).toHaveLength(1)
    expect(w.props('legs')[0]).toMatchObject({ instrument_id: 'NSE_FO:44624', action: 'SELL', lots: 1, planned_entry: null, captured_at: null, capturing: true })
    expect(w.emitted('done')).toHaveLength(1)
    release()
    await flushPromises()
    expect(w.props('legs')).toHaveLength(1)
    expect(w.props('legs')[0]).toMatchObject({ planned_entry: '104.65', captured_at: AT, source: 'ltp', reason_code: null })
    expect(w.props('legs')[0].capturing).toBeUndefined()
  })
  it('the leg list says "Working out the outcome..." on that leg, with no capture time and no "not connected" while it is priced', async () => {
    slow()
    const w = mountPicker()
    await flushPromises()
    await doneWithOne(w)
    const list = mount(LegList, { props: { legs: w.props('legs'), multiplierMax: 50 } })
    expect(list.find('[data-testid="leg-working"]').text()).toBe(LEG_WORKING_TEXT)
    expect(list.find('[data-testid="leg-unpriced"]').exists()).toBe(false)
    expect(list.find('[data-testid="leg-reprice-prompt"]').exists()).toBe(false)
    expect(list.find('[data-testid="leg-caption"]').exists()).toBe(false)
  })
  it('a failed capture says so on that leg only: no price, the reprice prompt, nothing else touched', async () => {
    answers['POST /strategies/planned-entry'] = Object.assign(new Error('down'), { status: 500 })
    const w = mountPicker([{ id: 90, underlying: 'NIFTY', instrument_id: 'NSE_FO:44632', contract_id: 1, symbol: 'X', expiry: '2026-10-13', instrument_type: 'CE', strike: '23000.00', lot_size: 65, action: 'BUY', lots: 1, planned_entry: '50.00', captured_at: AT, source: 'ltp', reason_code: null }])
    await flushPromises()
    await doneWithOne(w)
    const legs = w.props('legs')
    expect(legs).toHaveLength(2)
    expect(legs[0]).toMatchObject({ id: 90, planned_entry: '50.00' })
    expect(legs[1]).toMatchObject({ planned_entry: null, captured_at: null, reason_code: 'needs_reprice' })
    expect(legs[1].capturing).toBeUndefined()
  })
  it('a price the user typed on the leg while the reply was out is never overwritten', async () => {
    slow('104.65')
    const w = mountPicker()
    await flushPromises()
    await doneWithOne(w)
    await w.setProps({ legs: w.props('legs').map((l) => ({ ...l, planned_entry: '90.00', captured_at: AT, typed: true })) })
    release()
    await flushPromises()
    expect(w.props('legs')[0]).toMatchObject({ planned_entry: '90.00', typed: true })
    expect(w.props('legs')[0].capturing).toBeUndefined()
  })
  it('a leg removed while the reply was out stays removed', async () => {
    slow()
    const w = mountPicker()
    await flushPromises()
    await doneWithOne(w)
    await w.setProps({ legs: [] })
    release()
    await flushPromises()
    expect(w.props('legs')).toEqual([])
  })
})

describe('item 2 on the page: no outcome request until the entry is in', () => {
  it('the leg shows at once, POST /strategies/outcome is not sent for it, and goes once the planned entry arrives', async () => {
    slow()
    answers['POST /strategies/outcome'] = () => new Promise(() => {})
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
    await router.push({ path: '/strategy/builder' })
    await router.isReady()
    const w = mount(StrategyBuilderPage, { global: { plugins: [router] } })
    await flushPromises()
    await pick(w, { type: 'CE', strike: '22800.00' })
    await t(w, 'picker-done').trigger('click')
    await flushPromises()
    expect(w.findAll('[data-testid="leg-row"]').length + w.findAll('[data-testid="leg-working"]').length).toBeGreaterThan(0)
    expect(w.find('[data-testid="leg-working"]').text()).toBe(LEG_WORKING_TEXT)
    expect(calls.filter((c) => c.url === '/strategies/outcome')).toHaveLength(0)
    release()
    await flushPromises()
    expect(calls.filter((c) => c.url === '/strategies/outcome')).toHaveLength(1)
    expect(calls.find((c) => c.url === '/strategies/outcome').body.legs[0]).toMatchObject({ planned_entry: '104.65' })
  })
})

// Lane FB2, I-71 (Lane TD defect D-TD-1): "Pick from Option Chain" only set the column view; from Straddles, Strangles or Futures it did not open the Strikes tab.
describe('I-71: "Pick from Option Chain" opens the Strikes tab from every tab', () => {
  // the footer is not shown on the Futures tab (v-if tab !== 'futures')
  for (const from of ['straddles', 'strangles']) {
    it(`from ${from}: the Strikes tab is selected`, async () => {
      const w = mountPicker()
      await flushPromises()
      await t(w, `tab-${from}`).trigger('click')
      await flushPromises()
      expect(t(w, `tab-${from}`).attributes('aria-selected')).toBe('true')
      await t(w, 'picker-pick-chain').trigger('click')
      await flushPromises()
      expect(t(w, 'tab-strikes').attributes('aria-selected')).toBe('true')
      expect(t(w, `tab-${from}`).attributes('aria-selected')).toBe('false')
    })
  }
  it('on the Strikes tab it still brings the LTP columns back (UX-27)', async () => {
    const w = mountPicker()
    await flushPromises()
    await t(w, 'picker-view-oi').trigger('click')
    await t(w, 'picker-pick-chain').trigger('click')
    const on = t(w, 'picker-view').findAll('[role="radio"]').filter((b) => b.attributes('aria-checked') === 'true').map((b) => b.text())
    expect(on).toEqual(['LTP'])
  })
})
