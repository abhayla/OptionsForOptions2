// D-48 (REQ-078 AC-11, AC-12, AC-13; ADR-330 (42)): "Change expiry" of one leg or every leg goes through the ONE leg door (useLegDoor).
// Real page, the recorded condor (outcome-condor.json) and the real strategy 63 paper book (Drafts Mode). The server's reply is the
// stub: the browser sends only the control and the listed date text, and draws the reply through door.admitMoved.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
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
import LegList from '@/components/strategy/LegList.vue'
import { EXPIRY_BLOCKED_BY_EXIT, MOVE_CONTROLS, RELATIVE_CONTROLS, buildEditRequest } from '@/lib/legEdit'
import { paperOrdersFor, stagedExitIds } from '@/lib/paperDrafts'
import real from './fixtures/outcome-condor.json'
import BOOK from '../../tests/fixtures/paper/strategy-63-roll.json'

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const NEXT = '2026-10-20'
const EXPIRIES = { underlying: 'NIFTY', expiries: [real.legs[0].expiry, NEXT], expiry_days: [{ expiry: real.legs[0].expiry, days: 3 }, { expiry: NEXT, days: 10 }], today: '2026-10-10', default_expiry: real.legs[0].expiry }
const DRAFT = { underlying: 'NIFTY', legs: real.legs.map((l) => ({ instrument_id: l.instrument_id, action: l.action, lots: l.lots, planned_entry: l.planned_entry, captured_at: l.captured_at })) }
const replyLeg = (l, extra = {}) => ({ instrument_id: l.instrument_id, action: l.action, instrument: l.instrument, strike: l.strike, expiry: l.expiry, lots: l.lots,
  base_lots: l.lots, quantity: l.quantity, planned_entry: l.planned_entry, captured_at: l.captured_at, price_source: 'captured', included: true, hedge: false, block: null, ...extra })
const READ = { legs: real.legs.map((l) => replyLeg(l)), shape: 'iron_condor', shape_name: 'Short Iron Condor', outcome: real, controls: { shift: true, width: true, hedge: true }, shift_total: 0 }
const SELL_PE = real.legs[2]
const BEFORE = real.legs.map((l) => l.instrument_id)
const ids = (w) => w.vm.$.setupState.legs.map((l) => l.instrument_id)
const edits = () => calls.filter((c) => c.url === '/strategies/leg-edit').slice(1) // the first one is the page's read

beforeEach(() => { calls.length = 0; answers = {} })
afterEach(() => vi.restoreAllMocks())

async function openPage() {
  answers['POST /strategies/outcome'] = real
  answers['POST /strategies/leg-edit'] = READ
  answers['GET /catalogue/NIFTY/expiries'] = EXPIRIES
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await router.push({ path: '/strategy/builder', query: { draft: JSON.stringify(DRAFT) } })
  await router.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true } } })
  await flushPromises()
  return w
}
// leg 0 (SELL 22800 CE) lands on the contract of leg 2 (SELL 22400 PE): the same contract and action as a held leg
const landing = (body) => Promise.resolve({ data: { seq: body.seq, shape: null, shape_name: null, outcome: null, controls: { shift: true, width: true, hedge: true }, shift_total: null,
  legs: body.legs.map((sent, i) => (i === 0 ? replyLeg(real.legs[0], { instrument_id: SELL_PE.instrument_id, instrument: SELL_PE.instrument, strike: SELL_PE.strike, expiry: NEXT }) : replyLeg(real.legs[i], { instrument_id: sent.instrument_id }))) } })

describe('D-48 the request', () => {
  it('expiry is a move control but not a relative one; the request is the date text, index only for one leg, never steps', () => {
    expect(MOVE_CONTROLS).toContain('expiry')
    expect(RELATIVE_CONTROLS).not.toContain('expiry')
    const legs = DRAFT.legs
    expect(buildEditRequest('NIFTY', legs, { control: 'expiry', expiry: NEXT, steps: 3 }).edit).toEqual({ control: 'expiry', expiry: NEXT })
    expect(buildEditRequest('NIFTY', legs, { control: 'expiry', index: 2, expiry: NEXT }).edit).toEqual({ control: 'expiry', index: 2, expiry: NEXT })
    expect(buildEditRequest('NIFTY', legs, { control: 'expiry' })).toBeNull()
    expect(buildEditRequest('NIFTY', legs, { control: 'expiry', expiry: new Date() })).toBeNull()
  })
})

describe('D-48 through the one door (ADR-319 (1))', () => {
  it('all legs: sends only the date; a landing on a held contract asks Increase / Keep separate / Cancel and Cancel leaves the legs', async () => {
    const w = await openPage()
    answers['POST /strategies/leg-edit'] = landing
    void w.vm.$.setupState.editLeg({ control: 'expiry', expiry: NEXT })
    await flushPromises()
    expect(edits()[0].body.edit).toEqual({ control: 'expiry', expiry: NEXT })
    expect(t(w, 'dup-question').text()).toBe('NIFTY 13 Oct 22400 PE is already in this strategy.')
    expect(t(w, 'dup-increase').exists()).toBe(true)
    expect(ids(w)).toEqual(BEFORE) // unchanged until answered
    await t(w, 'dup-cancel').trigger('click')
    await flushPromises()
    expect(ids(w)).toEqual(BEFORE)
  })

  it('the leg chip sends one leg by index; a refused change draws the refusal and leaves every leg unchanged', async () => {
    const w = await openPage()
    answers['POST /strategies/leg-edit'] = () => Promise.reject({ status: 422, parts: { what_happened: 'No 22,800 CE is listed for 20 Oct 2026, so leg 1 cannot move there.', impact: 'The change was refused and no leg changed.', what_is_blocked: 'This expiry change.', next_action: 'Pick another expiry.' } })
    const select = w.findAll('[data-testid="leg-expiry-select"]')[0]
    expect(select.attributes('disabled')).toBeUndefined()
    await select.setValue(NEXT)
    await flushPromises()
    expect(edits()[0].body.edit).toEqual({ control: 'expiry', index: 0, expiry: NEXT })
    expect(ids(w)).toEqual(BEFORE)
    expect(w.vm.$.setupState.legs.map((l) => l.expiry)).toEqual(real.legs.map((l) => l.expiry))
  })

  it('choosing the leg\'s own expiry sends nothing', async () => {
    const w = await openPage()
    const before = calls.length
    await w.findAll('[data-testid="leg-expiry-select"]')[0].setValue(real.legs[0].expiry)
    await flushPromises()
    expect(calls.length).toBe(before)
  })
})

describe('D-48 Drafts Mode on a running paper trade (REQ-109 AC-9)', () => {
  it('the move stages an exit of the old contract and an add of the new one, and posts nothing', async () => {
    const never = () => new Promise(() => {})
    answers = {
      'GET /paper/strategies/63': BOOK, 'GET /strategies': { strategies: [] }, 'POST /strategies/outcome': never, 'GET /catalogue/NIFTY/expiries': EXPIRIES,
      'GET /catalogue/NIFTY/contracts?expiry=2026-11-03': { underlying: 'NIFTY', contracts: BOOK.positions.map((p) => ({ contract_id: p.contract_id,
        exchange_segment: 'NSE_FO', exchange_token: p.contract_id, instrument_type: p.instrument, expiry: p.expiry, strike: p.strike, lot_size: 65, symbol: `N${p.strike}${p.instrument}` })) },
    }
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
    await router.push({ path: '/strategy/builder', query: { strategy: '63' } })
    await router.isReady()
    const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true } } })
    await flushPromises()
    const S = () => w.vm.$.setupState
    const old = S().legs[0]
    expect(S().pendingOrders).toHaveLength(0)
    answers['POST /strategies/leg-edit'] = (body) => Promise.resolve({ data: { seq: body.seq, shape: null, shape_name: null, outcome: null, controls: { shift: true, width: true, hedge: true }, shift_total: null,
      legs: S().legs.map((l, i) => ({ ...replyLeg({ ...l, instrument: l.instrument_type, quantity: null }), base_lots: l.lots, contract_id: l.contract_id, lot_size: l.lot_size,
        ...(i === 0 ? { instrument_id: 'NSE_FO:999001', contract_id: 999001, expiry: NEXT } : {}) })) } })
    await S().editLeg({ control: 'expiry', index: 0, expiry: NEXT })
    await flushPromises()
    const pending = S().pendingOrders
    expect(pending.map((o) => [o.kind, o.contract_id]).sort()).toEqual([['add', 999001], ['exit', old.contract_id]].sort())
    expect(pending).toEqual(paperOrdersFor(S().paper.net, S().legs)) // the one diff, no second path
    expect(calls.filter((c) => c.method === 'POST' && c.url.includes('/paper')).length).toBe(0) // nothing posted by the move
  })
})

describe('D-48 a leg with an exit waiting (REQ-078 AC-13)', () => {
  it('stagedExitIds names the contracts held with fewer lots than the net position', () => {
    const net = [{ contract_id: 1, lots: 2 }, { contract_id: 2, lots: 1 }]
    expect(stagedExitIds(net, [{ contract_id: 1, lots: 1 }, { contract_id: 2, lots: 1 }])).toEqual([1])
    expect(stagedExitIds(net, [{ contract_id: 1, lots: 3 }])).toEqual([])
    expect(stagedExitIds(null, [{ contract_id: 1, lots: 1 }])).toEqual([])
  })

  it('its chip select and the all-legs select are disabled with the exact reason; the other leg stays available', async () => {
    answers['GET /catalogue/NIFTY/expiries'] = EXPIRIES
    const legs = real.legs.map((l, i) => ({ id: `l${i}`, ...replyLeg(l), instrument_type: l.instrument, contract_id: 100 + i, underlying: 'NIFTY' }))
    const w = mount(LegList, { props: { legs, stagedExitIds: [100] }, global: { stubs: { PayoffChart: true } } })
    await flushPromises()
    const selects = w.findAll('[data-testid="leg-expiry-select"]')
    expect(selects[0].attributes('disabled')).toBeDefined()
    expect(selects[0].attributes('title')).toBe(EXPIRY_BLOCKED_BY_EXIT)
    expect(EXPIRY_BLOCKED_BY_EXIT).toBe('This leg has an exit waiting; review or discard it first.')
    expect(t(w, 'leg-expiry-reason').text()).toBe(EXPIRY_BLOCKED_BY_EXIT)
    expect(selects[1].attributes('disabled')).toBeUndefined()
    expect(t(w, 'expiry-all').attributes('disabled')).toBeDefined()
    expect(t(w, 'expiry-all-reason').text()).toBe(EXPIRY_BLOCKED_BY_EXIT)
  })
})
