// Lane FJ round 2 (28 Nov, Opus review of items 1-2; ADR-016..019, ADR-330 (58)): ONE lock writer and ONE decision function (lib/unknownLocks.js)
// for the builder, the Positions / Alerts door (PaperStrategies) and the save bar. The lock carries the whole-book key (`before`), the signed units of
// each exited leg and the `expected` book; a reader that lacks a field it needs KEEPS the lock; empty or absent units never count as stored.
// F1 builder lock read on Positions, F2 Positions lock read in the builder, F3 add lock before the POST, F4 newer `at`, F5 malformed storage, F6 own record.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    const a = answers[`${method} ${url}`]
    if (a === undefined && method === 'GET' && url === '/market/exit-state') return Promise.resolve({ data: { closed: false, sentence: null, next_open_at: null } })
    if (a === undefined && method === 'GET' && url === '/strategies') return Promise.resolve({ data: { strategies: [] } })
    if (a === undefined) return Promise.reject({ message: `unmocked ${method} ${url}`, parts: null, status: null })
    return typeof a === 'function' ? a(body) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u, b) => respond('POST', u, b), put: (u, b) => respond('PUT', u, b), patch: (u, b) => respond('PATCH', u, b), delete: (u) => respond('DELETE', u) } }
})
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import SaveDraftBar from '@/components/strategy/SaveDraftBar.vue'
import { resetActiveAlerts } from '@/lib/paperAlerts'
import { UNKNOWN_EXIT_READ_AFTER_MS } from '@/lib/sharedStateText'
import { cancelledStopLines } from '@/lib/tracking'
import * as L from '@/lib/unknownLocks'
import REAL from './fixtures/paper-strategies.json'
import BOOK63 from './fixtures/paper-book-63.json'

const WINDOW = UNKNOWN_EXIT_READ_AFTER_MS
const ORDERS = '/paper/strategies/1/orders'
const UNKNOWN = () => Promise.reject({ message: 'x', status: 503, parts: null })
const clone = (o) => JSON.parse(JSON.stringify(o))
// strategy 1 with leg 776 at 4 lots (260 units): a builder exit of 2 of the 4 lots, a Positions exit of the whole leg
const LIST = (() => { const d = clone(REAL); d.strategies.find((s) => s.strategy_id === 1).positions.find((p) => p.contract_id === 776).net_quantity = 260; return d })()
const S1 = LIST.strategies.find((s) => s.strategy_id === 1)
const BOOK1 = { ...clone(BOOK63), strategy_id: 1, name: '"IC"', underlying: 'NIFTY', positions: clone(S1.positions) }
const CONTRACTS = S1.positions.map((p) => ({ contract_id: p.contract_id, exchange_segment: 'NSE_FO', exchange_token: p.contract_id, instrument_type: p.instrument, expiry: p.expiry, strike: p.strike, lot_size: 65, symbol: `NIFTY${p.strike}${p.instrument}` }))
const posts = () => calls.filter((c) => c.method === 'POST' && c.url === ORDERS)
const mounted = []
const S = (w) => w.vm.$.setupState
const t = (w, id) => w.find(`[data-testid="${id}"]`)
const adv = async (ms) => { await vi.advanceTimersByTimeAsync(ms); await flushPromises() }
function baseAnswers() {
  answers = {
    'GET /paper/strategies': () => Promise.resolve({ data: clone(LIST) }),
    'GET /paper/strategies/1': () => Promise.resolve({ data: clone(BOOK1) }),
    'GET /catalogue/NIFTY/contracts?expiry=2026-10-13': { underlying: 'NIFTY', contracts: CONTRACTS },
    'POST /strategies/outcome': () => new Promise(() => {}),
    'POST /strategies/leg-edit': () => new Promise(() => {}),
    [`POST ${ORDERS}`]: UNKNOWN,
  }
}
async function showPositions() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: PaperStrategies }, { path: '/strategy/builder', component: { template: '<div/>' } }] })
  router.push('/')
  await router.isReady()
  const w = mount(PaperStrategies, { global: { plugins: [router] }, attachTo: document.body })
  mounted.push(w)
  await flushPromises()
  return w
}
async function showBuilder() {
  const r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await r.push('/strategy/builder?strategy=1')
  await r.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [r], stubs: { PayoffChart: true } }, attachTo: document.body })
  mounted.push(w)
  await flushPromises()
  return w
}
const drop = (w) => { w.unmount(); mounted.splice(mounted.indexOf(w), 1) }
async function positionsExit(w) {
  const box = t(w, 'select-leg-1-776')
  if (!box.element.checked) await box.setValue(true)
  await t(w, 'exit-selected-1').trigger('click')
  await flushPromises()
  const b = t(w, 'paper-confirm-button')
  if (b.exists()) await b.trigger('click')
  await flushPromises()
}
async function builderExit(w) {
  S(w).exitPaper(776, 2)
  await flushPromises()
  const b = t(w, 'paper-confirm-button')
  if (b.exists()) await b.trigger('click')
  await flushPromises()
}
const stormEvent = (name = 'ofo.exitUnknown') => globalThis.dispatchEvent(new StorageEvent('storage', { key: name }))

beforeEach(() => {
  calls.length = 0; resetActiveAlerts(); vi.useFakeTimers(); L.resetExitLocks()
  try { globalThis.localStorage?.clear(); globalThis.sessionStorage?.clear() } catch { /* none */ }
  baseAnswers()
})
afterEach(() => { mounted.splice(0).forEach((w) => { try { w.unmount() } catch { /* gone */ } }); vi.useRealTimers(); document.body.innerHTML = '' })

describe('the ONE book key and the ONE decision (lib/unknownLocks.js)', () => {
  const posRows = [{ contractId: 784, units: -65 }, { contractId: 776, units: 260 }, { contractId: 761, units: 0 }]
  const netRows = [{ contract_id: 776, action: 'BUY', lots: 4, lot_size: 65 }, { contract_id: 784, action: 'SELL', lots: 1, lot_size: 65 }]
  const lock = (o = {}) => ({ kind: 'exit', at: 1000, before: L.bookOfNet(netRows).key, units: [{ id: 776, units: 260 }], expected: null, names: ['x'], ...o })
  const after = (u776) => L.bookOfPositions([{ contractId: 776, units: u776 }, { contractId: 784, units: -65 }])
  it('the builder net and the Positions rows give the SAME key for the same book (closed legs are not in it)', () => {
    expect(L.bookOfNet(netRows).key).toBe(L.bookOfPositions(posRows).key)
    expect(L.bookOfNet([{ contract_id: 1, action: 'BUY', lots: 1 }])).toBeNull() // no lot size: unreadable, never guessed
  })
  it('CORE: empty or absent units never count as stored (the book moved, the lock stays)', () => {
    for (const units of [[], null, undefined, [{}], [{ id: 776 }], 'x']) expect(L.decideLock(lock({ units }), after(130), 2000).verdict, JSON.stringify(units)).toBe('keep')
  })
  it('a field the reader needs is missing: keep (before, at for an unchanged book, an unreadable book)', () => {
    expect(L.decideLock(lock({ before: undefined }), after(130), 2000).verdict).toBe('keep')
    expect(L.decideLock(lock({ at: 'x' }), L.bookOfNet(netRows), 5e6).verdict).toBe('keep')
    expect(L.decideLock(lock(), null, 5e6).verdict).toBe('keep')
    expect(L.decideLock(null, after(130), 5e6).verdict).toBe('keep')
  })
  it('stored: the exited leg moved toward zero on the same side (2 of 4 lots too); changed: anything else; expected is checked', () => {
    expect(L.decideLock(lock(), after(130), 2000).verdict).toBe('stored')
    expect(L.decideLock(lock(), after(0), 2000).verdict).toBe('stored')
    // Group A R1 (a): `changed` never ends a lock inside the window (the first request can still commit): keep until a read SENT more than 130 s after the give-up
    expect(L.decideLock(lock(), after(325), 2000).verdict).toBe('keep') // grew: not an exit
    expect(L.decideLock(lock(), after(325), 1000 + WINDOW + 1).verdict).toBe('changed')
    expect(L.decideLock(lock({ expected: after(130).key }), after(130), 2000).verdict).toBe('stored')
    expect(L.decideLock(lock({ expected: after(65).key }), after(130), 2000).verdict).toBe('keep')
    expect(L.decideLock(lock({ expected: after(65).key }), after(130), 1000 + WINDOW + 1).verdict).toBe('changed')
  })
  it('unchanged: not stored only for a read sent MORE than 130 s after the client gave up', () => {
    const same = L.bookOfNet(netRows)
    expect(L.decideLock(lock(), same, 1000 + WINDOW).verdict).toBe('keep')
    expect(L.decideLock(lock(), same, 1000 + WINDOW + 1).verdict).toBe('not_stored')
  })
  it('an add lock: orders in the book = stored; the plan alone only after the window', () => {
    const add = { kind: 'add', at: 1000, before: '' }
    expect(L.decideLock(add, L.bookOfRead({ kind: 'paper', net: [] }), 2000).verdict).toBe('stored')
    expect(L.decideLock(add, L.bookOfRead({ kind: 'plan' }), 2000).verdict).toBe('keep')
    expect(L.decideLock(add, L.bookOfRead({ kind: 'plan' }), 1000 + WINDOW + 1).verdict).toBe('not_stored')
  })
})

describe('F1 (critical): a BUILDER lock read on the Positions / Alerts door is not decided as stored', () => {
  it('CORE: builder exit of 2 of 4 lots times out; the Positions list opens on the unchanged book: Exit stays locked, a Confirm there sends nothing', async () => {
    const b = await showBuilder()
    await builderExit(b)
    expect(posts()).toHaveLength(1)
    const lk = L.exitLockFor(1)
    expect(lk.units).toEqual([{ id: 776, units: 260 }]) // the per-leg units of the exited leg
    expect(typeof lk.before).toBe('string')
    drop(b)
    await adv(2000)
    const w = await showPositions()
    await adv(6000)
    expect(L.exitLockFor(1)).not.toBeNull()
    await positionsExit(w)
    expect(posts()).toHaveLength(1)
    expect(w.text()).not.toContain('Exit placed on paper')
  })
  it('the builder lock and a book that really moved (2 of 4 lots left): Positions decides it as stored and frees the lock', async () => {
    const b = await showBuilder()
    await builderExit(b)
    drop(b)
    const moved = clone(LIST); moved.strategies.find((s) => s.strategy_id === 1).positions.find((p) => p.contract_id === 776).net_quantity = 130
    answers['GET /paper/strategies'] = () => Promise.resolve({ data: moved })
    await showPositions()
    await adv(6000)
    expect(L.exitLockFor(1)).toBeNull()
  })
})

describe('F2 (critical): a POSITIONS lock read in the builder is not decided as moved', () => {
  it('CORE: a Positions exit times out; the builder opens on the unchanged book: Exit stays blocked, a Confirm there sends nothing', async () => {
    const p = await showPositions()
    await positionsExit(p)
    expect(posts()).toHaveLength(1)
    drop(p)
    await adv(2000)
    const w = await showBuilder()
    await adv(6000)
    expect(S(w).exitBlocked).toBe(true)
    expect(L.exitLockFor(1)).not.toBeNull()
    await builderExit(w)
    expect(posts()).toHaveLength(1)
  })
  it('the same through the storage event: the builder is open, the other tab writes its lock', async () => {
    const w = await showBuilder()
    const p = await showPositions() // a second tab
    await positionsExit(p)
    expect(posts()).toHaveLength(1)
    stormEvent()
    await adv(6000)
    expect(S(w).exitBlocked).toBe(true)
    await builderExit(w)
    expect(posts()).toHaveLength(1)
  })
  it('the Positions lock and a book that really moved: the builder frees it', async () => {
    const p = await showPositions()
    await positionsExit(p)
    drop(p)
    const moved = clone(BOOK1); moved.positions.find((x) => x.contract_id === 776).net_quantity = 0
    answers['GET /paper/strategies/1'] = () => Promise.resolve({ data: moved })
    const w = await showBuilder()
    await adv(6000)
    expect(S(w).exitBlocked).toBe(false)
    expect(L.exitLockFor(1)).toBeNull()
  })
})

describe('F3: the add lock is written BEFORE the post', () => {
  const LEGS = [{ id: 'l1', contract_id: 5, action: 'SELL', lots: 2, lot_size: 65, instrument: 'CE', strike: '22800', expiry: '2026-12-01', underlying: 'NIFTY', planned_entry: '100.00', captured_at: '2026-11-26T09:20:00+05:30', included: true }]
  const CUR = { id: 172, revision: 1, name: '"IC"' }
  const dom = (id) => document.querySelector(`[data-testid="${id}"]`)
  const ADD = '/paper/strategies/172/orders'
  const addPosts = () => calls.filter((c) => c.method === 'POST' && c.url === ADD)
  async function bar(props = {}) {
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<p />' } }] })
    const w = mount(SaveDraftBar, { props: { legs: LEGS, shownName: 'IC', current: CUR, ...props }, global: { plugins: [router] }, attachTo: document.body })
    mounted.push(w)
    await flushPromises()
    return w
  }
  const book404 = () => Promise.reject(Object.assign(new Error('nf'), { status: 404 }))
  it('S1: the post is out, the bar is remounted and the price moved: Add is blocked and no second POST goes out', async () => {
    answers[`POST ${ADD}`] = () => new Promise(() => {}) // still out
    answers['GET /paper/strategies/172'] = book404
    const w = await bar()
    await t(w, 'add-to-paper').trigger('click'); await flushPromises()
    dom('paper-confirm-button').click(); await flushPromises()
    expect(addPosts()).toHaveLength(1)
    expect(L.addLockFor(172)).not.toBeNull()
    drop(w)
    await adv(3000)
    const w2 = await bar({ legs: [{ ...LEGS[0], planned_entry: '101.50' }] }) // the price moved: the orders text differs
    expect(t(w2, 'add-to-paper').attributes('disabled')).toBeDefined()
    await t(w2, 'add-to-paper').trigger('click'); await flushPromises()
    expect(dom('paper-confirm-button')).toBeNull()
    expect(addPosts()).toHaveLength(1)
  })
  it('a definite answer drops it: a refusal, and a stored add (no lock left)', async () => {
    answers[`POST ${ADD}`] = () => Promise.reject(Object.assign(new Error('r'), { status: 422, parts: { what_happened: 'No.' } }))
    answers['GET /paper/strategies/172'] = book404
    const w = await bar()
    await t(w, 'add-to-paper').trigger('click'); await flushPromises()
    dom('paper-confirm-button').click(); await flushPromises()
    expect(L.addLockFor(172)).toBeNull()
    expect(t(w, 'add-to-paper').attributes('disabled')).toBeUndefined()
  })
  it('a tab closed while its post was out: the 130 s rule counts from the time the post went out (Group A R1 (b): its `at`, never from first sight)', async () => {
    answers['GET /paper/strategies/172'] = book404
    L.saveAddLock(172, { at: Date.now(), before: '', out: true, key: 'k1', sig: '[]' })
    const w = await bar()
    await adv(20000)
    expect(t(w, 'add-to-paper').attributes('disabled')).toBeDefined() // the post went out 20 s ago: it may still commit
    await adv(WINDOW + 20000)
    expect(t(w, 'add-to-paper').attributes('disabled')).toBeUndefined()
  })
  it('a post that went out an hour ago: the first good read sent past the window decides it', async () => {
    answers['GET /paper/strategies/172'] = book404
    L.saveAddLock(172, { at: Date.now() - 3600000, before: '', out: true, key: 'k1', sig: '[]' })
    const w = await bar()
    await adv(20000)
    expect(t(w, 'add-to-paper').attributes('disabled')).toBeUndefined()
  })
})

describe('F4: a lock adopted from another tab takes the newer `at`; a closed tab\'s pre-post time is not the give-up time', () => {
  it('Positions: the other tab rewrote the lock 100 s later; the window counts from that time (a read at 160 s does not decide)', async () => {
    const w = await showPositions()
    await positionsExit(w) // gave up at T1
    await adv(100000)
    const lk = L.exitLockFor(1)
    L.saveExitLock(1, { ...lk, at: Date.now() }) // the other tab gave up on its own request just now
    stormEvent()
    await flushPromises()
    await adv(60000) // T1 + 160 s: past 130 s from T1, inside 130 s of T2
    expect(L.exitLockFor(1)).not.toBeNull()
    await adv(80000)
    expect(L.exitLockFor(1)).toBeNull()
  })
  it('Positions: a lock whose post went out an hour ago: a good read sent past the window decides it (Group A R1 (b): from its `at`)', async () => {
    L.saveExitLock(1, { at: Date.now() - 3600000, out: true, before: L.bookOfPositions(S1.positions.map((p) => ({ contractId: p.contract_id, units: p.net_quantity }))).key, units: [{ id: 776, units: 260 }], names: ['x'], key: 'k', sig: '[]' })
    await showPositions()
    await adv(20000)
    expect(L.exitLockFor(1)).toBeNull()
  })
  it('Positions: a lock whose post went out just now: kept until a read sent 130 s after it', async () => {
    L.saveExitLock(1, { at: Date.now(), out: true, before: L.bookOfPositions(S1.positions.map((p) => ({ contractId: p.contract_id, units: p.net_quantity }))).key, units: [{ id: 776, units: 260 }], names: ['x'], key: 'k', sig: '[]' })
    await showPositions()
    await adv(20000)
    expect(L.exitLockFor(1)).not.toBeNull()
    await adv(WINDOW + 20000)
    expect(L.exitLockFor(1)).toBeNull()
  })
  it('builder: the other tab rewrote the lock later; the window counts from that time', async () => {
    const w = await showBuilder()
    await builderExit(w) // gave up at T1
    await adv(100000)
    const lk = L.exitLockFor(1)
    L.saveExitLock(1, { ...lk, at: Date.now() })
    stormEvent()
    await flushPromises()
    await adv(60000)
    expect(S(w).exitBlocked).toBe(true)
    await adv(80000)
    expect(S(w).exitBlocked).toBe(false)
  })
})

describe('F5: malformed stored data fails closed and never throws', () => {
  const GOOD_BEFORE = '753:65,776:260,784:-65'
  const raws = {
    'units [{}]': JSON.stringify({ 1: { at: Date.now(), before: GOOD_BEFORE, units: [{}], names: ['x'] } }),
    'units []': JSON.stringify({ 1: { at: Date.now(), before: GOOD_BEFORE, units: [], names: ['x'] } }),
    'at not a number': JSON.stringify({ 1: { at: 'x', before: GOOD_BEFORE, units: [{ id: 776, units: 260 }], names: ['x'] } }),
    'entry {}': JSON.stringify({ 1: {} }),
    'entry null': '{"1":null}',
    'entry 0': '{"1":0}',
    'an array': '[]',
    'a number': '5',
    'broken json': '{"1":{"at":',
  }
  it('exitLockFor keeps a lock for every one of them (never null, never a throw); decideLock keeps it', () => {
    for (const [name, raw] of Object.entries(raws)) {
      globalThis.localStorage.setItem('ofo.exitUnknown', raw)
      let lk
      expect(() => { lk = L.exitLockFor(1); L.exitLockIds() }, name).not.toThrow()
      expect(lk, name).not.toBeNull()
      // a book that moved: only a lock whose units and book key are readable can say stored (a bad `at` is needed for an UNCHANGED book only)
      const later = vi.spyOn(performance, 'now').mockReturnValue(performance.now() + 1e7) // Z2 T3: a read past the window is a real monotonic wait, never a skewed sent time
      expect(L.decideLock(lk, L.bookOfPositions([{ contractId: 776, units: 130 }]), Date.now()).verdict, name).toBe(name === 'at not a number' ? 'stored' : name.startsWith('units') || ['an array', 'a number', 'broken json'].includes(name) ? 'changed' : 'keep') // an unparseable whole store counts from its first sight (R5 N3); R5 N3: a lock with a valid `before` and no readable legs ends as 'changed' for a moved book read past the window
      if (name === 'at not a number') expect(L.decideLock(lk, { key: GOOD_BEFORE, units: { 776: 260 } }, Date.now()).verdict, name).toBe('keep') // unchanged needs `at`
      later.mockRestore()
    }
    globalThis.localStorage.setItem('ofo.exitUnknown', '{}')
    expect(L.exitLockFor(1)).toBeNull() // nothing stored: no lock
    globalThis.localStorage.removeItem('ofo.exitUnknown')
    expect(L.exitLockFor(1)).toBeNull()
  })
  it('Positions: Confirm sends nothing for each of them', async () => {
    for (const [name, raw] of Object.entries(raws)) {
      calls.length = 0
      mounted.splice(0).forEach((x) => x.unmount())
      globalThis.localStorage.setItem('ofo.exitUnknown', raw)
      const w = await showPositions()
      await positionsExit(w)
      expect(posts(), name).toHaveLength(0)
    }
  })
  it('builder: Exit is blocked for a lock without units', async () => {
    globalThis.localStorage.setItem('ofo.exitUnknown', raws['units []'])
    const w = await showBuilder()
    await adv(6000)
    expect(S(w).exitBlocked).toBe(true)
    await builderExit(w)
    expect(posts()).toHaveLength(0)
  })
  it('save bar: an entry null / 0, a stored number or array block Add where it is plausible; the storage listener never throws', async () => {
    const LEGS = [{ id: 'l1', contract_id: 5, action: 'SELL', lots: 2, lot_size: 65, instrument: 'CE', strike: '22800', expiry: '2026-12-01', underlying: 'NIFTY', planned_entry: '100.00', captured_at: '2026-11-26T09:20:00+05:30', included: true }]
    answers['GET /paper/strategies/172'] = () => Promise.reject(Object.assign(new Error('x'), { status: 500 }))
    for (const raw of ['{"172":null}', '{"172":0}', '5', '[]', '{"172":{}}']) {
      globalThis.localStorage.setItem('ofo.addUnknown', raw)
      const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<p />' } }] })
      let w
      expect(() => { w = mount(SaveDraftBar, { props: { legs: LEGS, shownName: 'IC', current: { id: 172, revision: 1, name: '"IC"' } }, global: { plugins: [router] }, attachTo: document.body }) }, raw).not.toThrow()
      mounted.push(w)
      await flushPromises()
      expect(() => globalThis.dispatchEvent(new StorageEvent('storage', { key: 'ofo.addUnknown' })), raw).not.toThrow()
      await flushPromises()
      expect(w.find('[data-testid="add-to-paper"]').attributes('disabled'), raw).toBeDefined()
      drop(w)
    }
  })
})

describe('F6: doExit also refuses when THIS instance\'s own record is unknown', () => {
  it('the stored lock is gone (another tab removed it) but this tab never heard an answer: Confirm sends nothing', async () => {
    const w = await showPositions()
    await positionsExit(w)
    expect(posts()).toHaveLength(1)
    globalThis.localStorage.clear()
    L.resetExitLocks()
    const box = t(w, 'select-leg-1-776')
    if (!box.element.checked) await box.setValue(true)
    await t(w, 'exit-selected-1').trigger('click')
    await flushPromises()
    await S(w).doExit(S(w).confirm.orders, null, false, 'k-second') // a Confirm that reaches the page whatever the dialog shows
    await flushPromises()
    expect(posts()).toHaveLength(1)
  })
})

describe('cancelledStopLines: an entry with no readable name is printed with a neutral leg name', () => {
  it('a nameless entry says "a leg"; named ones and [] are as before', () => {
    expect(cancelledStopLines([{ level: '120.00' }])).toEqual(['The stop on a leg (level 120.00) was removed with the move; set a new one on the new leg.'])
    expect(cancelledStopLines([{}, null, 'x'])).toHaveLength(3)
    expect(cancelledStopLines([{}])[0]).toBe('The stop on a leg was removed with the move; set a new one on the new leg.')
    expect(cancelledStopLines([{ leg: 'NIFTY 9 Nov 23500 CE', level: '' }])[0]).toContain('NIFTY 9 Nov 23500 CE')
    expect(cancelledStopLines([])).toEqual([])
    expect(cancelledStopLines(null)).toEqual([])
  })
})
