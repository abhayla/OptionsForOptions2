// ADR-329 (2): leaving the builder for any OTHER page while it holds unsaved legs asks "Leave the builder? The N unsaved legs will be
// lost." with Stay (keeps page and legs) and Leave (discards them). A router-leave guard from one composable, one dialog; the tab
// close (`beforeunload`) is out (PLAN 2.2). Three layers: the guard on a small harness page (always), the Option Chain page's guard
// (always: rows L11) and the REAL builder page (rows L1-L9, which need the page wiring: they run when StrategyBuilderPage.vue names
// `useLeaveBuilder`, tests/helpers/phase5Wired.js).
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import { WIRED } from './helpers/phase5Wired'
import { echoSeq } from './helpers/echoSeq'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    const a = answers[`${method} ${url}`]
    if (a === undefined && url.startsWith('/paper/strategies/')) return Promise.reject({ status: 404 })
    if (a === undefined && url === '/settings') return Promise.resolve({ data: settingsData() })
    if (a === undefined && url.startsWith('/catalogue/') && url.endsWith('/expiries')) return Promise.resolve({ data: { expiries: ['2026-10-13'] } })
    if (a === undefined) return Promise.reject(new Error(`unmocked ${method} ${url}`))
    return typeof a === 'function' ? a(body) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u, b) => respond('POST', u, b), put: (u, b) => respond('PUT', u, b) } }
})
import { settingsData } from './helpers/servedLots'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import OptionChainPage from '@/pages/OptionChainPage.vue'
import LeaveBuilderDialog from '@/components/strategy/LeaveBuilderDialog.vue'
import { CHAIN_ROUTE, useLeaveBuilder, leaveQuestion } from '@/composables/useLeaveBuilder'
import { useBuilderHold } from '@/stores/builderHold'
import real from './fixtures/outcome-condor.json'

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const Stub = { template: '<div data-testid="stub" />' }
const BUILDER = 'strategies-strategy-builder'
const HOME = 'home-overview'
const makeRouter = (builder, chain) => createRouter({ history: createMemoryHistory(), routes: [
  { path: '/strategies/strategy-builder', name: BUILDER, component: builder },
  { path: '/strategy/builder', name: 'strategy-builder-screen', component: builder },
  { path: '/market/option-chain', name: CHAIN_ROUTE, component: chain },
  { path: '/home/overview', name: HOME, component: Stub },
  { path: '/market/other', name: 'market-other', component: Stub },
] })
const app = (router) => mount({ render: () => h(RouterView) }, { global: { plugins: [router] } })
const route = (r) => r.currentRoute.value.name
const closers = [
  ['Escape', (w) => t(w, 'modal-root').trigger('keydown', { key: 'Escape' })],
  ['x', (w) => t(w, 'modal-close').trigger('click')],
  ['overlay', (w) => t(w, 'modal-overlay').trigger('click')],
  ['Stay', (w) => t(w, 'leave-stay').trigger('click')],
]

// ---- layer 1: the guard on a harness that plays the builder (the page supplies the same three inputs) ----
const unsaved = ref(0)
let snapshot = null
const Harness = defineComponent({
  components: { LeaveBuilderDialog },
  setup() {
    const leave = useLeaveBuilder({ role: 'builder', unsaved: () => unsaved.value, snapshot: () => snapshot })
    return { leave }
  },
  template: '<div data-testid="harness"><LeaveBuilderDialog :leave="leave" /></div>',
})
const ChainHarness = defineComponent({
  components: { LeaveBuilderDialog },
  setup() {
    const leave = useLeaveBuilder({ role: 'chain' })
    return { leave }
  },
  template: '<div data-testid="chain-harness"><LeaveBuilderDialog :leave="leave" /></div>',
})
beforeEach(() => {
  setActivePinia(createPinia())
  unsaved.value = 0
  snapshot = null
  calls.length = 0
  answers = {}
})

describe('the leave guard (harness)', () => {
  async function start(from = BUILDER) {
    const router = makeRouter(Harness, ChainHarness)
    await router.push({ name: from })
    const w = app(router)
    await flushPromises()
    return { router, w }
  }
  it('L1 no unsaved legs: the push to Home resolves with no dialog (absent)', async () => {
    const { router, w } = await start()
    await router.push({ name: HOME })
    expect(route(router)).toBe(HOME)
    expect(t(w, 'leave-dialog').exists()).toBe(false)
  })
  it('L3 unsaved: the push waits, the dialog says the ADR sentence with exactly Stay and Leave', async () => {
    unsaved.value = 3
    const { router, w } = await start()
    const nav = router.push({ name: HOME })
    await flushPromises()
    expect(route(router)).toBe(BUILDER)
    expect(t(w, 'leave-dialog').exists()).toBe(true)
    expect(t(w, 'leave-question').text()).toBe('Leave the builder? The 3 unsaved legs will be lost.')
    expect(t(w, 'leave-question').text()).toBe(leaveQuestion(3))
    expect(t(w, 'leave-stay').text()).toBe('Stay')
    expect(t(w, 'leave-leave').text()).toBe('Leave')
    await t(w, 'leave-stay').trigger('click')
    await nav
  })
  it('L4 Stay, Escape, x and the overlay: the route is unchanged, the question closed, the hold untouched', async () => {
    for (const [name, close] of closers) {
      unsaved.value = 3
      const { router, w } = await start()
      const nav = router.push({ name: HOME })
      await flushPromises()
      await close(w)
      await nav
      await flushPromises()
      expect(route(router), name).toBe(BUILDER)
      expect(t(w, 'leave-dialog').exists(), name).toBe(false)
      expect(useBuilderHold().held, name).toBeNull()
      w.unmount()
    }
  })
  it('L5 Leave: the route is Home and the hold is empty', async () => {
    unsaved.value = 3
    const { router, w } = await start()
    useBuilderHold().hold({ legs: [{ id: 'old', instrument_id: 'NSE_FO:1', action: 'BUY', lots: 1 }] }) // a stale hold never survives a Leave
    const nav = router.push({ name: HOME })
    await flushPromises()
    await t(w, 'leave-leave').trigger('click')
    await nav
    await flushPromises()
    expect(route(router)).toBe(HOME)
    expect(useBuilderHold().held).toBeNull()
  })
  it('L7 never asks: the chain, the builder\'s other name, a replace of its own query', async () => {
    unsaved.value = 3
    snapshot = { legs: [{ id: 'a', instrument_id: 'NSE_FO:1', action: 'BUY', lots: 1 }] }
    const { router, w } = await start()
    await router.push({ name: 'strategy-builder-screen' })
    await router.replace({ name: 'strategy-builder-screen', query: { x: '1' } })
    expect(t(w, 'leave-dialog').exists()).toBe(false)
    expect(route(router)).toBe('strategy-builder-screen')
    await router.push({ name: CHAIN_ROUTE })
    expect(route(router)).toBe(CHAIN_ROUTE)
    expect(t(w, 'leave-dialog').exists()).toBe(false)
  })
  it('the chain trip holds what the builder shows (saved or not), with no question; no legs -> nothing held', async () => {
    unsaved.value = 0 // saved legs: not "unsaved", but the trip still keeps them (PLAN 2.2)
    snapshot = { legs: [{ id: 'a', instrument_id: 'NSE_FO:1', action: 'BUY', lots: 1 }], savedId: 7 }
    const { router } = await start()
    await router.push({ name: CHAIN_ROUTE })
    expect(useBuilderHold().held.legs).toHaveLength(1)
    expect(useBuilderHold().held.savedId).toBe(7)
    useBuilderHold().clear()
    snapshot = null
    const second = await start()
    await second.router.push({ name: CHAIN_ROUTE })
    expect(useBuilderHold().held).toBeNull()
  })
  it('L11 the chain page with a hold: Home asks the same question; Stay keeps the chain and the hold, Leave empties it', async () => {
    const fresh = () => { useBuilderHold().hold({ legs: [{ id: 'a', instrument_id: 'NSE_FO:1', action: 'BUY', lots: 1 }, { id: 'b', instrument_id: 'NSE_FO:2', action: 'SELL', lots: 1 }] }) }
    for (const [name, close] of closers) {
      fresh()
      const { router, w } = await start(CHAIN_ROUTE)
      const nav = router.push({ name: HOME })
      await flushPromises()
      expect(t(w, 'leave-question').text(), name).toBe('Leave the builder? The 2 unsaved legs will be lost.')
      await close(w)
      await nav
      await flushPromises()
      expect(route(router), name).toBe(CHAIN_ROUTE)
      expect(useBuilderHold().count, name).toBe(2)
      w.unmount()
    }
    const { router, w } = await start(CHAIN_ROUTE)
    const nav = router.push({ name: HOME })
    await flushPromises()
    await t(w, 'leave-leave').trigger('click')
    await nav
    expect(route(router)).toBe(HOME)
    expect(useBuilderHold().held).toBeNull()
    w.unmount()
  })
  it('L11 the chain page to the builder never asks (the hold waits for the builder); with no hold, no question anywhere', async () => {
    useBuilderHold().hold({ legs: [{ id: 'a', instrument_id: 'NSE_FO:1', action: 'BUY', lots: 1 }] })
    const { router, w } = await start(CHAIN_ROUTE)
    await router.push({ name: BUILDER })
    expect(route(router)).toBe(BUILDER)
    expect(useBuilderHold().count).toBe(1)
    expect(t(w, 'leave-dialog').exists()).toBe(false)
    useBuilderHold().clear()
    await router.push({ name: CHAIN_ROUTE })
    await router.push({ name: HOME })
    expect(route(router)).toBe(HOME)
  })
})

// ---- layer 2: the REAL Option Chain page carries the guard (L11 on the real page) ----
class FakeSocket {
  static all = []
  constructor(url) { this.url = url; this.sent = []; this.readyState = 0; FakeSocket.all.push(this) }
  send(text) { this.sent.push(text) }
  close() { this.readyState = 3 }
  serverOpen() { this.readyState = 1; this.onopen?.() }
  serverPush(obj) { this.onmessage?.({ data: JSON.stringify(echoSeq(this, obj)) }) }
}
describe('L11 on the real Option Chain page', () => {
  beforeEach(() => { FakeSocket.all = []; vi.stubGlobal('WebSocket', FakeSocket) })
  afterEach(() => vi.unstubAllGlobals())
  const cell = (id) => ({ instrument_id: id, ltp: '100.00', bid: null, ask: null, change: null, oi: '1000', oi_change: null, volume: '5', health: 'available', at: '2026-10-19T10:00:00+05:30', permitted: true, unavailable_reason: null })
  const CHAIN = { state: 'LIVE', underlying: 'NIFTY', expiry: '2026-10-13', spot: '22900.00', spot_at: '2026-10-19T10:00:00+05:30', spot_health: 'available',
    atm_strike: '22800.00', rows_missing: null, answered_at: '2026-10-19T10:00:01+05:30',
    rows: [{ strike: '22800.00', ce: cell('NSE_FO:44624'), pe: cell('NSE_FO:44625') }] }
  async function openChain() {
    const router = makeRouter(StrategyBuilderPage, OptionChainPage)
    await router.push({ name: CHAIN_ROUTE })
    const w = app(router)
    await flushPromises()
    FakeSocket.all.at(-1).serverOpen()
    FakeSocket.all.at(-1).serverPush(CHAIN)
    await flushPromises()
    return { router, w }
  }
  it('with a hold: Home asks (Stay keeps the chain and the hold); with no hold: no question (today)', async () => {
    useBuilderHold().hold({ legs: [{ id: 'a', instrument_id: 'NSE_FO:1', action: 'BUY', lots: 1 }] })
    const { router, w } = await openChain()
    const nav = router.push({ name: HOME })
    await flushPromises()
    expect(t(w, 'leave-question').text()).toBe('Leave the builder? The 1 unsaved leg will be lost.')
    await t(w, 'leave-stay').trigger('click')
    await nav
    expect(route(router)).toBe(CHAIN_ROUTE)
    expect(useBuilderHold().count).toBe(1)
    useBuilderHold().clear()
    await router.push({ name: HOME })
    expect(route(router)).toBe(HOME)
    expect(t(w, 'leave-dialog').exists()).toBe(false)
  })
})

describe('L10 the tab close is not asked (PLAN 2.2): no beforeunload anywhere in src', () => {
  const walk = (d) => readdirSync(d).flatMap((n) => (statSync(join(d, n)).isDirectory() ? walk(join(d, n)) : [join(d, n)]))
  it('scans every source file', () => {
    const hits = walk(resolve(__dirname, '../src')).filter((f) => /\.(vue|js)$/.test(f) && readFileSync(f, 'utf8').includes('beforeunload'))
    expect(hits).toEqual([])
  })
})

// ---- layer 3: the real builder page (needs the page wiring) ----
describe.runIf(WIRED.leave)('the real builder page leaves with a question (L1-L8)', () => {
  const link = (legs) => JSON.stringify({ underlying: 'NIFTY', legs: legs.map((l) => ({ instrument_id: l.instrument_id, action: l.action, lots: l.lots, planned_entry: l.planned_entry, captured_at: l.captured_at })) })
  const THREE = link(real.legs.slice(0, 3))
  const token = (l) => Number(l.instrument_id.split(':')[1])
  const savedLeg = (l) => ({ contract_id: token(l), contract_state: 'live', exchange_segment: 'NSE_FO', exchange_token: token(l), instrument: l.instrument, strike: l.strike,
    expiry: l.expiry, action: l.action, quantity: l.quantity, planned_entry: l.planned_entry, captured_at: l.captured_at, entry_source: 'captured' })
  const SAVED = { id: 7, name: '"NIFTY Oct condor"', status: 'draft', revision: 3, created_at: '2026-10-13T04:00:00Z', updated_at: '2026-10-13T05:10:00Z',
    definition: { underlying: 'NIFTY', legs: real.legs.map(savedLeg) }, versions: [] }
  const CATALOGUE = { underlying: 'NIFTY', contracts: real.legs.map((l) => ({ contract_id: token(l), exchange_segment: 'NSE_FO', exchange_token: token(l),
    instrument_type: l.instrument, expiry: l.expiry, strike: l.strike, lot_size: l.lot_size, symbol: l.symbol })) }
  beforeEach(() => {
    answers = { 'GET /strategies': { strategies: [] }, 'GET /strategies/7': SAVED, 'GET /catalogue/NIFTY/contracts?expiry=2026-10-13': CATALOGUE,
      'POST /strategies/outcome': real, 'POST /strategies/leg-edit': () => new Promise(() => {}) }
  })
  async function openBuilder(query) {
    const router = makeRouter(StrategyBuilderPage, OptionChainPage)
    await router.push({ name: BUILDER, query })
    const w = app(router)
    await flushPromises()
    return { router, w }
  }
  const rows = (w) => w.findAll('[data-testid="leg-row"]').length
  it('L1 no legs -> Home: no dialog', async () => {
    const { router, w } = await openBuilder({})
    await router.push({ name: HOME })
    expect(route(router)).toBe(HOME)
    expect(t(w, 'leave-dialog').exists()).toBe(false)
  })
  it('L2 saved legs, unedited (?strategy=7) -> Home: no dialog', async () => {
    const { router, w } = await openBuilder({ strategy: '7' })
    expect(rows(w)).toBe(4)
    await router.push({ name: HOME })
    expect(route(router)).toBe(HOME)
    expect(t(w, 'leave-dialog').exists()).toBe(false)
  })
  it('L3/L4 unsaved (3 legs from a draft link) -> Home asks with N = 3; Stay and its closers change nothing, no request is sent', async () => {
    for (const [name, close] of closers) {
      const { router, w } = await openBuilder({ draft: THREE })
      expect(rows(w)).toBe(3)
      const query = router.currentRoute.value.query
      const sent = calls.length
      const nav = router.push({ name: HOME })
      await flushPromises()
      expect(t(w, 'leave-question').text(), name).toBe('Leave the builder? The 3 unsaved legs will be lost.')
      await close(w)
      await nav
      await flushPromises()
      expect(route(router), name).toBe(BUILDER)
      expect(rows(w), name).toBe(3)
      expect(router.currentRoute.value.query, name).toEqual(query)
      expect(calls.length, name).toBe(sent)
      w.unmount()
    }
  })
  it('L5 Leave: Home, the hold empty, and the next builder is fresh (0 legs)', async () => {
    const { router, w } = await openBuilder({ draft: THREE })
    const nav = router.push({ name: HOME })
    await flushPromises()
    await t(w, 'leave-leave').trigger('click')
    await nav
    await flushPromises()
    expect(route(router)).toBe(HOME)
    expect(useBuilderHold().held).toBeNull()
    await router.push({ name: BUILDER })
    await flushPromises()
    expect(rows(w)).toBe(0)
  })
  it('L6 saved-but-edited (open ?strategy=7, remove a leg) -> Home asks with N = the legs now shown (3)', async () => {
    const { router, w } = await openBuilder({ strategy: '7' })
    await t(w, 'remove-leg').trigger('click')
    await flushPromises()
    const nav = router.push({ name: HOME })
    await flushPromises()
    expect(t(w, 'leave-question').text()).toBe('Leave the builder? The 3 unsaved legs will be lost.')
    await t(w, 'leave-stay').trigger('click')
    await nav
  })
  it('L7 the chain is never asked, and a replace of the page\'s own query is not a leave', async () => {
    const { router, w } = await openBuilder({ draft: THREE })
    await router.replace({ name: BUILDER, query: { draft: THREE, x: '1' } })
    await flushPromises()
    expect(t(w, 'leave-dialog').exists()).toBe(false)
    await router.push({ name: CHAIN_ROUTE })
    expect(route(router)).toBe(CHAIN_ROUTE)
    expect(useBuilderHold().held.legs).toHaveLength(3) // the trip holds them, no question
  })
})
