// Lane FB round 2, I-49 (T2-11): after picking a leg the first prices took 14 s. The request ORDER, recorded with slow mocked replies.
// FINDING (file for the owner lane: LegPicker.vue, see RESULTS-lane-fb.md): the leg is added to the page only AFTER the planned-entry
// reply (LegPicker.vue save() line ~555 and addChosen() line ~618 await capture() before emit('update:legs')), so the outcome request
// is sent when the planned-entry reply has ARRIVED: the two waits add up. The page itself sends the outcome and the leg-edit read in
// the same tick (setLegs), no one waits for the other: that half is proven here and needs no page change.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import { settingsData } from './helpers/servedLots'

const log = [] // { at, what }
const t0 = () => Date.now()
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    log.push({ at: Date.now(), what: `${method} ${url}` })
    const a = answers[`${method} ${url}`]
    if (a === undefined && method === 'GET' && url === '/settings') return Promise.resolve({ data: settingsData() })
    if (a === undefined) return Promise.reject(new Error(`unmocked ${method} ${url}`))
    return typeof a === 'function' ? a(body) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u, b) => respond('POST', u, b), put: (u, b) => respond('PUT', u, b) } }
})

const AT = '2026-11-27T10:00:00+05:30'
const c = (token, type, strike) => ({ exchange_segment: 'NSE_FO', exchange_token: token, contract_id: token, instrument_type: type, expiry: '2026-12-01', strike, lot_size: 65, symbol: `NIFTY${strike}${type}` })
const CONTRACTS = { underlying: 'NIFTY', contracts: [c(44624, 'CE', '22800.00'), c(44632, 'CE', '23000.00')] }
const cell = (token) => ({ instrument_id: `NSE_FO:${token}`, lot_size: 65, ltp: null, oi: null, iv_percent: null, delta: null, health: 'unavailable', at: null })
const STRIKES = { state: 'LIVE', reason: null, underlying: 'NIFTY', expiry: '2026-12-01', width: 10, spot: '22900.00', spot_at: AT, centre: 'LIVE_SPOT', atm_strike: '22800.00', answered_at: AT, market_closed: false,
  rows: [['22800.00', 44624], ['23000.00', 44632]].map(([strike, token]) => ({ strike, is_atm: false, ce: cell(token), pe: null })) }
const t = (w, id) => w.find(`[data-testid="${id}"]`)
const idx = (what) => log.findIndex((x) => x.what === what)
let replyPlannedEntry

beforeEach(() => {
  log.length = 0
  answers = {
    'GET /strategies': { strategies: [] },
    'GET /catalogue/NIFTY/expiries': { underlying: 'NIFTY', today: '2026-11-27', expiries: ['2026-12-01'], expiry_days: [{ expiry: '2026-12-01', days: 4 }], default_expiry: '2026-12-01', list_notice: null },
    'GET /catalogue/NIFTY/contracts?expiry=2026-12-01': CONTRACTS,
    'GET /leg-picker/strikes?underlying=NIFTY&expiry=2026-12-01': STRIKES,
    'POST /strategies/planned-entry': () => new Promise((res) => { replyPlannedEntry = () => res({ data: { answered_at: AT, entries: [{ exchange_segment: 'NSE_FO', exchange_token: 44624, planned_entry: '104.65', captured_at: AT, source: 'ltp', reason_code: null }] } }) }),
    'POST /strategies/outcome': () => new Promise(() => {}), // slow: never answers here
    'POST /strategies/leg-edit': () => new Promise(() => {}),
  }
})
afterEach(() => vi.useRealTimers())

const mountPage = async () => {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await router.push('/strategy/builder')
  await router.isReady()
  const w = mount(StrategyBuilderPage, { attachTo: document.body, global: { plugins: [router], stubs: { PayoffChart: true } } })
  await flushPromises()
  return w
}

describe('I-49: request order after a pick, with slow replies', () => {
  it('page half: a new leg list sends the outcome and the leg-edit read together, none waits for the other', async () => {
    const w = await mountPage()
    const mk = (id, token, strike) => ({ id, underlying: 'NIFTY', instrument_id: `NSE_FO:${token}`, contract_id: token, symbol: `NIFTY${strike}CE`, expiry: '2026-12-01', instrument_type: 'CE', strike, lot_size: 65, action: 'SELL', lots: 1, planned_entry: '104.65', captured_at: AT })
    log.length = 0
    w.vm.$.setupState.setLegs([mk(1, 44624, '22800.00'), mk(2, 44632, '23000.00')])
    await flushPromises()
    const o = idx('POST /strategies/outcome')
    const e = idx('POST /strategies/leg-edit')
    expect(o).toBeGreaterThanOrEqual(0)
    expect(e).toBeGreaterThanOrEqual(0)
    expect(log[e].at - log[o].at).toBeLessThan(50) // both sent in the same tick, neither answered yet
    w.unmount()
  })

  it('picker half (the cause): the outcome request goes out only AFTER the planned-entry reply has arrived', async () => {
    const w = await mountPage()
    await t(w, 'add-edit').trigger('click')
    await flushPromises()
    const side = w.find('[data-testid="strike-row"][data-strike="22800.00"] [data-testid="cell-ce"]')
    await side.find('[data-testid="cell-sell"]').trigger('click')
    log.length = 0
    await t(w, 'picker-done').trigger('click')
    await flushPromises()
    expect(idx('POST /strategies/planned-entry')).toBeGreaterThanOrEqual(0) // sent at Done
    expect(idx('POST /strategies/outcome')).toBe(-1) // ...and the outcome is NOT sent while that one waits: the two waits add up
    const before = t0()
    replyPlannedEntry()
    await flushPromises()
    expect(idx('POST /strategies/outcome')).toBeGreaterThan(idx('POST /strategies/planned-entry'))
    expect(log[idx('POST /strategies/outcome')].at).toBeGreaterThanOrEqual(before)
    w.unmount()
  })
})
