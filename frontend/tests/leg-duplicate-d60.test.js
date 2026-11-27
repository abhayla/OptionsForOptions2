// D-60 (REQ-030 AC-5/AC-11/AC-12, REQ-059): adding a contract already in the strategy is never silent. Mock shapes are the
// leg-picker.test.js ones (recorded NIFTY 13-Oct-2026 contracts). Origin: 23 Nov live test, 'T1123-X scratch2'.
// W-068 / REQ-035 AC-8: the Builder adds and edits legs only from contracts the catalogue API offers, and the picked
// legs reach the outcome API as the draft it already prices.
// The mocked API answers are the REAL shapes of backend/ofo_app/routes/catalogue.py (exchange_segment and exchange_token
// apart, strike a string or null for FUT, lot_size an int) and routes/planned_entry.py (planned_entry string + captured_at
// + source, or null + reason_code). Tokens and symbols are the recorded NIFTY 13-Oct-2026 contracts of the outcome fixture
// (44595/44604/44624/44632) and the instruments slice (FUT 48704). No price here is computed or defaulted by the page.
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount as mountRaw, flushPromises, enableAutoUnmount } from '@vue/test-utils'

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
import LegList from '@/components/strategy/LegList.vue'
import { settingsData } from './helpers/servedLots'
import { admitLegs, lotsRangeText, sameContract } from '@/lib/legDoor'

// the page passes the served lot caps down (REQ-167 AC-5); a picker mounted alone gets them as props
const mount = (C, o = {}) => mountRaw(C, C === LegPicker ? { ...o, props: { maxLots: 10000, lotChoiceCount: 10, ...o.props } } : o)
import { NOT_CONNECTED_LABEL, REPRICE_PROMPT, lotsValid, lotChoices, instrumentId, buildDraft, oiCompact } from '@/lib/legPicker'

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
    'GET /settings': settingsData(),
    'GET /catalogue/NIFTY/expiries': { underlying: 'NIFTY', today: '2026-10-10', expiries: ['2026-10-13', '2026-10-27'] },
    'GET /catalogue/SENSEX/expiries': { underlying: 'SENSEX', today: '2026-10-10', expiries: ['2026-10-15'] },
    'GET /catalogue/NIFTY/contracts?expiry=2026-10-13': NIFTY_13,
    'GET /catalogue/NIFTY/contracts?expiry=2026-10-27': NIFTY_27,
    'GET /leg-picker/strikes?underlying=NIFTY&expiry=2026-10-13': pkStrikes(),
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


const PRICES = () => { answers['POST /strategies/planned-entry'] = (body) => Promise.resolve({ data: { entries: body.instrument_ids.map((i) => entry(Number(i.split(':')[1]), '100.00')) } }) }
async function addVia(w, o) { await pick(w, o); await t(w, 'picker-done').trigger('click'); await flushPromises() }
const rows = (w) => w.props('legs').map((l) => `${l.action} ${l.lots} ${l.instrument_id}`)
const ID = instrumentId('NSE_FO', 44595)

describe('D-60: a contract already in the strategy asks first', () => {
  async function twoOfSame(action2 = 'BUY', lots2 = '2') {
    PRICES()
    const w = mountPicker()
    await flushPromises()
    await addVia(w, { type: 'PE', strike: '22200.00', action: 'BUY', lots: '1' })
    expect(rows(w)).toEqual([`BUY 1 ${ID}`])
    await addVia(w, { type: 'PE', strike: '22200.00', action: action2, lots: lots2 })
    return w
  }

  it('CORE (23 Nov): the same contract and action picked again asks Increase quantity / Keep separate / Cancel and adds nothing yet', async () => {
    const w = await twoOfSame()
    expect(rows(w)).toEqual([`BUY 1 ${ID}`])
    expect(t(w, 'dup-dialog').exists()).toBe(true)
    expect(['dup-increase', 'dup-separate', 'dup-cancel'].map((id) => t(w, id).text())).toEqual(['Increase quantity', 'Keep separate', 'Cancel'])
  })

  it('Increase quantity: the existing row gets the picked lots, no new row', async () => {
    const w = await twoOfSame()
    await t(w, 'dup-increase').trigger('click')
    await flushPromises()
    expect(rows(w)).toEqual([`BUY 3 ${ID}`])
    expect(t(w, 'dup-dialog').exists()).toBe(false)
  })

  it('Keep separate: a second row', async () => {
    const w = await twoOfSame()
    await t(w, 'dup-separate').trigger('click')
    await flushPromises()
    expect(rows(w)).toEqual([`BUY 1 ${ID}`, `BUY 2 ${ID}`])
  })

  it('Cancel: nothing changes and the pick stays selected', async () => {
    const w = await twoOfSame()
    await t(w, 'dup-cancel').trigger('click')
    await flushPromises()
    expect(rows(w)).toEqual([`BUY 1 ${ID}`])
    expect(t(w, 'picker-count').text()).toBe('1 leg selected')
  })

  it('AC-11: the same contract with the opposite action is two legs, no question', async () => {
    const w = await twoOfSame('SELL', '1')
    expect(t(w, 'dup-dialog').exists()).toBe(false)
    expect(rows(w)).toEqual([`BUY 1 ${ID}`, `SELL 1 ${ID}`])
  })

  it('editing a leg onto a contract another leg holds asks the same question', async () => {
    PRICES()
    const w = mountPicker()
    await flushPromises()
    await addVia(w, { type: 'PE', strike: '22200.00', action: 'BUY' })
    await addVia(w, { type: 'PE', strike: '22400.00', action: 'BUY' })
    const second = w.props('legs')[1]
    answers['GET /catalogue/NIFTY/contracts?expiry=2026-10-13'] = NIFTY_13
    w.vm.startEdit(second)
    await flushPromises()
    await t(w, 'pick-strike').setValue('22200.00')
    await t(w, 'add-leg').trigger('click')
    await flushPromises()
    expect(t(w, 'dup-dialog').exists()).toBe(true)
    await t(w, 'dup-increase').trigger('click')
    await flushPromises()
    expect(rows(w)).toEqual([`BUY 2 ${ID}`])
  })
})

describe('D-60: two rows on one contract and action carry the gate wording', () => {
  const leg = (id, action) => ({ id, instrument_id: ID, underlying: 'NIFTY', symbol: 'NIFTY26O1322200PE', expiry: '2026-10-13', instrument_type: 'PE', strike: '22200.00', lot_size: 65, action, lots: 1, planned_entry: '100.00', captured_at: AT })
  it('both rows show it; an opposite-action pair shows nothing', () => {
    const same = mount(LegList, { props: { legs: [leg(1, 'BUY'), leg(2, 'BUY')] } })
    expect(same.findAll('[data-testid="duplicate-leg-warning"]').map((e) => e.text())).toEqual([
      'Leg 1 is the same contract as leg 2. The legs have not been combined; edit the strategy to keep one or combine them yourself.',
      'Leg 2 is the same contract as leg 1. The legs have not been combined; edit the strategy to keep one or combine them yourself.',
    ])
    const opposite = mount(LegList, { props: { legs: [leg(1, 'BUY'), leg(2, 'SELL')] } })
    expect(opposite.find('[data-testid="duplicate-leg-warning"]').exists()).toBe(false)
  })
})

// ---- D-60 round 2 (ADR-319): ONE door, Increase quantity obeys the lots limits, the question is a real modal ----
describe('D-60 r2: the one door (src/lib/legDoor.js)', () => {
  const held = [{ id: 1, instrument_id: ID, action: 'BUY', lots: 8, underlying: 'NIFTY' }]
  const incoming = (o = {}) => ({ id: 'x', instrument_id: ID, action: 'BUY', lots: 5, ...o })
  it('same contract = same instrument id and same action; a leg with no instrument id never matches another', () => {
    expect(sameContract(held[0], incoming())).toBe(true)
    expect(sameContract(held[0], incoming({ action: 'SELL' }))).toBe(false)
    expect(sameContract({ action: 'BUY' }, { action: 'BUY' })).toBe(false)
    expect(sameContract({ instrument_id: null, action: 'BUY' }, { instrument_id: null, action: 'BUY' })).toBe(false)
  })
  it('Increase beyond the maximum is refused with the manual-edit sentence and changes nothing', async () => {
    const r = await admitLegs(held, [incoming()], { ask: async () => 'increase', maxLots: 10 })
    expect(r).toEqual({ error: lotsRangeText(10) })
    expect(lotsRangeText(10)).toBe('Lots must be a whole number from 1 to 10.')
  })
  it('Increase inside the maximum raises the held row; Keep separate keeps the incoming; Cancel returns null', async () => {
    expect((await admitLegs(held, [incoming({ lots: 2 })], { ask: async () => 'increase', maxLots: 10 })).legs[0].lots).toBe(10)
    expect((await admitLegs(held, [incoming()], { ask: async () => 'separate', maxLots: 10 })).kept).toHaveLength(1)
    expect(await admitLegs(held, [incoming()], { ask: async () => 'cancel', maxLots: 10 })).toBeNull()
  })
  it('several held contracts: one question each, in order; Cancel on the second aborts the whole batch', async () => {
    const two = [...held, { id: 2, instrument_id: 'NSE_FO:2', action: 'SELL', lots: 1 }]
    const asked = []
    const r = await admitLegs(two, [incoming({ lots: 1 }), incoming({ id: 'y', instrument_id: 'NSE_FO:2', action: 'SELL', lots: 1 })], {
      ask: async (leg) => { asked.push(leg.id); return asked.length === 1 ? 'increase' : 'cancel' }, maxLots: 10,
    })
    expect(asked).toEqual([1, 2])
    expect(r).toBeNull()
  })
})

describe('D-60 r2: the picker obeys the door', () => {
  it('Increase quantity beyond the maximum shows the same lots sentence as a manual edit and adds nothing', async () => {
    PRICES()
    const w = mount(LegPicker, { props: { maxLots: 2, legs: [], 'onUpdate:legs': (v) => w.setProps({ legs: v }) } })
    await flushPromises()
    await addVia(w, { type: 'PE', strike: '22200.00', action: 'BUY', lots: '1' })
    await addVia(w, { type: 'PE', strike: '22200.00', action: 'BUY', lots: '2' })
    await t(w, 'dup-increase').trigger('click')
    await flushPromises()
    expect(rows(w)).toEqual([`BUY 1 ${ID}`])
    expect(t(w, 'done-error').text()).toBe(lotsRangeText(2))
  })
  it('Escape on the question is Cancel; the picks stay; the dialog is a modal with the controls behind it covered', async () => {
    PRICES()
    const w = mountPicker()
    await flushPromises()
    await addVia(w, { type: 'PE', strike: '22200.00', action: 'BUY' })
    await addVia(w, { type: 'PE', strike: '22200.00', action: 'BUY' })
    expect(t(w, 'modal-overlay').exists()).toBe(true)
    expect(t(w, 'modal').attributes('aria-modal')).toBe('true')
    await t(w, 'modal-root').trigger('keydown', { key: 'Escape' })
    await flushPromises()
    expect(t(w, 'dup-dialog').exists()).toBe(false)
    expect(rows(w)).toEqual([`BUY 1 ${ID}`])
    expect(t(w, 'picker-count').text()).toBe('1 leg selected')
  })
  it('a leg row with no instrument id shows no duplicate warning against another such row', () => {
    const bare = (id) => ({ id, underlying: 'NIFTY', action: 'BUY', lots: 1, symbol: 'X', expiry: '2026-10-13', instrument_type: 'PE', strike: '22200.00', lot_size: 65 })
    const w = mount(LegList, { props: { legs: [bare(1), bare(2)] } })
    expect(w.find('[data-testid="duplicate-leg-warning"]').exists()).toBe(false)
  })
})

describe('D-60 r3: Increase raises base lots with lots', () => {
  it('the door folds base_lots together with lots (lots stays base_lots x multiplier)', async () => {
    const held2 = [{ id: 1, instrument_id: ID, action: 'BUY', lots: 2, base_lots: 1, underlying: 'NIFTY' }]
    const inc = { id: 'x', instrument_id: ID, action: 'BUY', lots: 4, base_lots: 2 }
    const r = await admitLegs(held2, [inc], { ask: async () => 'increase', maxLots: 100 })
    expect([r.legs[0].lots, r.legs[0].base_lots]).toEqual([6, 3])
  })
  it('picker Increase then multiplier x1 keeps the total: the leg sent on carries base_lots equal to its lots', async () => {
    PRICES()
    const w = mountPicker()
    await flushPromises()
    await addVia(w, { type: 'PE', strike: '22200.00', action: 'BUY', lots: '1' })
    await addVia(w, { type: 'PE', strike: '22200.00', action: 'BUY', lots: '2' })
    await t(w, 'dup-increase').trigger('click')
    await flushPromises()
    const [leg] = w.props('legs')
    expect(leg.lots).toBe(3)
    expect(leg.base_lots).toBe(3) // x1: lots = base_lots x 1, so a later multiplier edit keeps 3
  })
})

// Phase 5 (ADR-328 (1)): the door's `opposite` option (new `it`s only; the rest of this file is unchanged)
describe('Phase 5: legDoor opposite option', () => {
  const held = [{ id: 'a', instrument_id: 'NSE_FO:1', action: 'BUY', lots: 1 }]
  it('the default is silent: a SELL of a held BUY asks nothing and is kept as its own row', async () => {
    const ask = vi.fn()
    const r = await admitLegs(held, [{ id: 'n', instrument_id: 'NSE_FO:1', action: 'SELL', lots: 1 }], { ask, maxLots: 10 })
    expect(ask).not.toHaveBeenCalled()
    expect(r.kept).toHaveLength(1)
  })
  it('opposite: ask asks with kind "opposite"; Cancel returns null', async () => {
    const ask = vi.fn().mockResolvedValue('cancel')
    expect(await admitLegs(held, [{ id: 'n', instrument_id: 'NSE_FO:1', action: 'SELL', lots: 1 }], { ask, maxLots: 10, opposite: 'ask' })).toBeNull()
    expect(ask).toHaveBeenCalledWith(held[0], 'opposite')
  })
})
