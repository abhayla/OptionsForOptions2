// Lane U, ADR-330 (49) (owner, 27 Nov 2026): Exit in the Strategy Builder on a running paper trade while ANOTHER leg has a pending (staged)
// change. Only the changed leg's Exit is blocked ("This leg has a change waiting; review or discard it first."); an untouched leg's Exit
// exits THAT LEG ONLY: it posts one exit row, carries no add or modify row of the other leg, and the other leg's change stays staged
// after the exit (also after a refusal or an unknown outcome). Spec basis: ADR-330 (49), ADR-002 (the one order door), ADR-016..019,
// ADR-328 (4). The REAL page, the REAL book fixture (strategy 63 as answered live: 4 open legs of 1 lot), a paper POST that is recorded.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import { EXIT_BLOCKED_BY_CHANGE, stagedChangeIds } from '@/lib/paperDrafts'
import REAL from './fixtures/paper-book-63.json'
import { legacy } from './_paperList'

const NOT_LIVE = 'Prices are not live; try again when they update'
const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    const a = answers[`${method} ${url}`] ?? legacy(answers, method, url)
    if (a === undefined || a === null) return Promise.reject(new Error(`unmocked ${method} ${url}`))
    return typeof a === 'function' ? a(body) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u, b) => respond('POST', u, b), put: (u, b) => respond('PUT', u, b), patch: (u, b) => respond('PATCH', u, b) } }
})

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const CONTRACTS = REAL.positions.map((p) => ({ contract_id: p.contract_id, exchange_segment: 'NSE_FO', exchange_token: p.contract_id,
  instrument_type: p.instrument, expiry: p.expiry, strike: p.strike, lot_size: 65, symbol: `NIFTY${p.strike}${p.instrument}` }))
const BOOK = { ...REAL, strategy_id: 86, name: '"IC"' }
const OPEN_IDS = BOOK.positions.filter((p) => p.net_quantity !== 0).map((p) => p.contract_id) // [5572, 5587, 5585, 5574]
const afterExitOf = (id) => ({ ...BOOK, positions: BOOK.positions.map((p) => (p.contract_id === id ? { ...p, net_quantity: 0 } : p)) })
const orderPosts = () => calls.filter((c) => c.method === 'POST' && c.url === '/paper/strategies/86/orders')
const mounted = []
let router = null
async function builder(query = '?strategy=86', book = BOOK) {
  calls.length = 0
  answers = {
    'GET /strategies': { strategies: [] },
    'POST /paper/strategies/86/orders': book,
    'GET /paper/strategies/86': book,
    'GET /catalogue/NIFTY/contracts?expiry=2026-11-03': { underlying: 'NIFTY', contracts: CONTRACTS },
    'POST /strategies/outcome': () => new Promise(() => {}),
    'POST /strategies/leg-edit': () => new Promise(() => {}),
  }
  const r = router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await r.push(`/strategy/builder${query}`)
  await r.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [r], stubs: { PayoffChart: true } }, attachTo: document.body })
  mounted.push(w)
  await flushPromises()
  return w
}
const S = (w) => w.vm.$.setupState
const exitBtns = (w) => w.findAll('[data-testid="net-exit"]')
// leg 2 (index 1) gets a staged change: its lots raised from 1 to 2 (an add waiting)
const stageLeg2 = async (w) => { S(w).setLegs(S(w).paper.net.map((l, i) => (i === 1 ? { ...l, lots: 2 } : { ...l }))); await flushPromises() }
const kindsOf = (os) => (os ?? []).map((o) => [o.kind, o.contract_id])

beforeEach(() => { vi.useFakeTimers() })
afterEach(() => {
  vi.useRealTimers()
  while (mounted.length) mounted.pop().unmount()
  document.body.innerHTML = ''
})

describe('ADR-330 (49): Exit of an untouched leg exits that leg only', () => {
  it('CORE: 4 legs, leg 2 staged; leg 1 Exit posts exactly one exit row for leg 1, no add or modify row; leg 2 stays staged after the 201 and the re-read', async () => {
    const w = await builder()
    await stageLeg2(w)
    expect(kindsOf(S(w).pendingOrders)).toEqual([['add', OPEN_IDS[1]]]) // the staged change, before any Exit
    expect(exitBtns(w)[0].attributes('disabled')).toBeUndefined() // leg 1 is untouched: its Exit is on
    S(w).exitPaper(OPEN_IDS[0], 1)
    await flushPromises()
    expect(t(w, 'paper-confirm').exists()).toBe(true)
    expect(kindsOf(S(w).paperRows)).toEqual([['exit', OPEN_IDS[0]]]) // the dialog holds leg 1's exit only
    answers['POST /paper/strategies/86/orders'] = afterExitOf(OPEN_IDS[0])
    answers['GET /paper/strategies/86'] = afterExitOf(OPEN_IDS[0])
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(orderPosts()).toHaveLength(1)
    const sent = orderPosts()[0].body.orders
    expect(sent).toHaveLength(1)
    expect(sent[0]).toMatchObject({ contract_id: OPEN_IDS[0], kind: 'exit', quantity: 65 })
    expect(sent.some((o) => o.kind !== 'exit')).toBe(false)
    expect(S(w).paper.net.map((l) => l.contract_id)).toEqual(OPEN_IDS.slice(1)) // the re-read: leg 1 is gone from the book
    expect(kindsOf(S(w).pendingOrders)).toEqual([['add', OPEN_IDS[1]]]) // leg 2's change is STILL staged (exactly one pending change)
    expect(S(w).legs.find((l) => l.contract_id === OPEN_IDS[1]).lots).toBe(2)
    expect(S(w).exitOrigin).toBe(false) // the leftover edit is an ordinary edit, not an Exit
  })

  it('leg 2 (the changed leg): its Exit is off with the sentence; a click opens no dialog and posts nothing', async () => {
    const w = await builder()
    await stageLeg2(w)
    const btn = exitBtns(w)[1]
    expect(btn.attributes('disabled')).toBeDefined()
    expect(btn.attributes('title')).toBe(EXIT_BLOCKED_BY_CHANGE)
    expect(w.findAll('[data-testid="net-exit-reason"]').map((x) => x.text())).toEqual(['This leg has a change waiting; review or discard it first.'])
    await btn.trigger('click')
    S(w).exitPaper(OPEN_IDS[1], 1)
    await flushPromises()
    expect(t(w, 'paper-confirm').exists()).toBe(false)
    expect(orderPosts()).toHaveLength(0)
    expect(kindsOf(S(w).pendingOrders)).toEqual([['add', OPEN_IDS[1]]])
    // legs 3 and 4 stay on, whatever leg 2 holds
    expect(exitBtns(w)[2].attributes('disabled')).toBeUndefined()
    expect(exitBtns(w)[3].attributes('disabled')).toBeUndefined()
  })

  it('leg not live: the not-live rule still wins on the untouched leg (dialog stays, Confirm off, sentence), nothing posted, leg 2 stays staged', async () => {
    const w = await builder()
    await stageLeg2(w)
    S(w).paper = { ...S(w).paper, book: { ...BOOK, positions: BOOK.positions.map((p) => (p.contract_id === OPEN_IDS[0] ? { ...p, price_state: 'stale' } : p)) } }
    await flushPromises()
    S(w).exitPaper(OPEN_IDS[0], 1)
    await flushPromises()
    expect(t(w, 'paper-confirm').exists()).toBe(true)
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeDefined()
    expect(t(w, 'paper-error').text()).toMatch(/^No price for NIFTY/) // Lane FJ r3 (TD O-3): names the contract
    expect(orderPosts()).toHaveLength(0)
    expect(S(w).pendingOrders.some((o) => o.kind === 'add' && o.contract_id === OPEN_IDS[1])).toBe(true)
  })

  it('outcome unknown (503): unresolved as today, one POST, the exit and leg 2\'s change both still staged', async () => {
    const w = await builder()
    await stageLeg2(w)
    S(w).exitPaper(OPEN_IDS[0], 1)
    await flushPromises()
    answers['POST /paper/strategies/86/orders'] = () => Promise.reject({ status: 503, message: 'x', parts: null })
    answers['GET /paper/strategies/86'] = () => new Promise(() => {}) // U2 (ADR-017): the automatic re-read does not answer, so the outcome stays unknown
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(orderPosts()).toHaveLength(1)
    expect(orderPosts()[0].body.orders.map((o) => o.kind)).toEqual(['exit'])
    expect(S(w).paperState).toBe('unknown')
    expect(kindsOf(S(w).pendingOrders).sort()).toEqual([['add', OPEN_IDS[1]], ['exit', OPEN_IDS[0]]].sort())
  })

  it('refused (422): the server\'s four-part sentence is shown, nothing stored, and leg 2\'s change stays staged', async () => {
    const w = await builder()
    await stageLeg2(w)
    S(w).exitPaper(OPEN_IDS[0], 1)
    await flushPromises()
    const parts = { what_happened: 'The exit was refused.', impact: 'Nothing was placed.', what_is_blocked: 'This exit is blocked.', next_action: 'Review it and try again.' }
    answers['POST /paper/strategies/86/orders'] = () => Promise.reject({ status: 422, message: 'x', parts })
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(orderPosts()[0].body.orders.map((o) => o.kind)).toEqual(['exit'])
    expect(t(w, 'paper-error').text()).toContain('The exit was refused.')
    expect(S(w).pendingOrders.some((o) => o.kind === 'add' && o.contract_id === OPEN_IDS[1])).toBe(true)
    expect(S(w).legs.find((l) => l.contract_id === OPEN_IDS[1]).lots).toBe(2)
  })

  it('the user\'s Cancel of the dialog posts nothing; the exit and leg 2\'s change stay as edits (u513), still two pending', async () => {
    const w = await builder()
    await stageLeg2(w)
    S(w).exitPaper(OPEN_IDS[0], 1)
    await flushPromises()
    await t(w, 'paper-cancel').trigger('click')
    await flushPromises()
    expect(orderPosts()).toHaveLength(0)
    expect(S(w).pendingOrders).toHaveLength(2)
  })
})

describe('Exit all while a change is staged: today\'s behaviour, unchanged (ADR-330 (49) leaves it as is)', () => {
  it('Exit all clears the legs: the dialog holds one exit per open leg (4), the staged add of leg 2 is not in it, and Cancel-by-page restores the legs', async () => {
    const w = await builder()
    await stageLeg2(w)
    await t(w, 'paper-exit-all').trigger('click')
    await flushPromises()
    expect(S(w).paperRows.map((r) => r.contract_id).sort()).toEqual([...OPEN_IDS].sort())
    expect(S(w).paperRows.every((r) => r.kind === 'exit')).toBe(true)
    expect(S(w).paperRows).toHaveLength(4)
  })
})

const withNet = (book, over) => ({ ...book, positions: book.positions.map((p) => (over[p.contract_id] !== undefined ? { ...p, net_quantity: over[p.contract_id] } : p)) })
const exit1 = async (w, id) => { S(w).exitPaper(id, 1); await flushPromises(); await t(w, 'paper-confirm-button').trigger('click'); await flushPromises() }
const setLeg = (w, i, patch) => S(w).setLegs(S(w).paper.net.map((l, k) => (k === i ? { ...l, ...patch } : { ...l })))

describe('Round 2 F1: a per-leg Exit POST carries only its exit; acted, basket and approach stay for the staged change', () => {
  it('?acted=7&basket=4&approach=A-24, an add staged on 5587, Exit 5572: body is { orders: [one exit] } and the route keeps all three', async () => {
    const w = await builder('?strategy=86&acted=7&basket=4&approach=A-24')
    await stageLeg2(w)
    answers['POST /paper/strategies/86/orders'] = afterExitOf(OPEN_IDS[0])
    answers['GET /paper/strategies/86'] = afterExitOf(OPEN_IDS[0])
    await exit1(w, OPEN_IDS[0])
    expect(orderPosts()).toHaveLength(1)
    const body = orderPosts()[0].body
    expect(Object.keys(body).sort()).toEqual(['client_request_id', 'orders']) // Lane FB2: the request key
    expect(body.orders).toHaveLength(1)
    expect(body.orders[0].kind).toBe('exit')
    expect(router.currentRoute.value.query).toMatchObject({ acted: '7', basket: '4', approach: 'A-24' })
    expect(kindsOf(S(w).pendingOrders)).toEqual([['add', OPEN_IDS[1]]])
  })
})

describe('Round 2 F2: the staged change is put back only over the net the exit should leave', () => {
  const BOOK2 = withNet(BOOK, { 5572: 130 }) // leg 1 holds 2 lots
  it('A2: the staged leg\'s net went to 0 meanwhile (a stop fired): nothing is put back, the sentence is shown, no add is posted', async () => {
    const w = await builder('?strategy=86', BOOK2)
    await stageLeg2(w)
    const gone = withNet(afterExitOf(OPEN_IDS[0]), { 5587: 0 })
    answers['POST /paper/strategies/86/orders'] = gone
    answers['GET /paper/strategies/86'] = gone
    await exit1(w, OPEN_IDS[0])
    expect(S(w).pendingOrders).toEqual([])
    expect(S(w).legs.map((l) => l.contract_id)).not.toContain(OPEN_IDS[1])
    expect(t(w, 'staged-not-kept').text()).toContain('was not kept because the trade changed; stage it again.')
    expect(orderPosts()).toHaveLength(1)
  })
  it('A3: the exited leg went 2 -> 0 where 2 -> 1 was expected: nothing put back, never the exited contract\'s row, the sentence is shown', async () => {
    const w = await builder('?strategy=86', BOOK2)
    await stageLeg2(w)
    const odd = withNet(BOOK2, { 5572: 0 })
    answers['POST /paper/strategies/86/orders'] = odd
    answers['GET /paper/strategies/86'] = odd
    await exit1(w, OPEN_IDS[0])
    expect(S(w).legs.map((l) => l.contract_id)).not.toContain(OPEN_IDS[0])
    expect(S(w).pendingOrders).toEqual([])
    expect(t(w, 'staged-not-kept').exists()).toBe(true)
  })
  it('A3b control: 2 -> 1 as expected: the staged add on 5587 is put back, the exited leg\'s row is the re-read\'s, no sentence', async () => {
    const w = await builder('?strategy=86', BOOK2)
    await stageLeg2(w)
    const ok = withNet(BOOK2, { 5572: 65 })
    answers['POST /paper/strategies/86/orders'] = ok
    answers['GET /paper/strategies/86'] = ok
    await exit1(w, OPEN_IDS[0])
    expect(kindsOf(S(w).pendingOrders)).toEqual([['add', OPEN_IDS[1]]])
    expect(S(w).legs.find((l) => l.contract_id === OPEN_IDS[0]).lots).toBe(1)
    expect(t(w, 'staged-not-kept').exists()).toBe(false)
  })
})

describe('Round 2 F3: a held leg is untouched only if exactly one row carries its id with the same contract, side and lots', () => {
  it('A7 (merge): leg 1\'s row merged onto 5587 (Increase): both 5572 and 5587 are blocked, Exit 5572 opens no dialog', async () => {
    const w = await builder()
    const net = S(w).paper.net
    S(w).setLegs([{ ...net[1], lots: 2 }, { ...net[2] }, { ...net[3] }]) // row paper-5572 gone, 5587 raised
    await flushPromises()
    expect(stagedChangeIds(net, S(w).legs)).toEqual(expect.arrayContaining([OPEN_IDS[0], OPEN_IDS[1]]))
    S(w).exitPaper(OPEN_IDS[0], 1)
    await flushPromises()
    expect(t(w, 'paper-confirm').exists()).toBe(false)
    expect(orderPosts()).toHaveLength(0)
  })
  it('A8 (roll): leg 1 replaced by an adjust- row on another contract: 5572 is blocked, no dialog', async () => {
    const w = await builder()
    const net = S(w).paper.net
    S(w).setLegs([{ ...net[0], id: 'adjust-0', contract_id: 9999, instrument_id: 'NSE_FO:9999' }, { ...net[1] }, { ...net[2] }, { ...net[3] }])
    await flushPromises()
    expect(stagedChangeIds(net, S(w).legs)).toContain(OPEN_IDS[0])
    S(w).exitPaper(OPEN_IDS[0], 1)
    await flushPromises()
    expect(t(w, 'paper-confirm').exists()).toBe(false)
  })
})

describe('Round 2 F4: the staged change is never lost silently', () => {
  it('A4: an unreadable staged leg (lots missing, no order can be formed): it is still there after the exit and the re-read', async () => {
    const w = await builder()
    setLeg(w, 1, { lots: null })
    await flushPromises()
    expect(S(w).pendingOrders).toBeNull()
    answers['POST /paper/strategies/86/orders'] = afterExitOf(OPEN_IDS[0])
    answers['GET /paper/strategies/86'] = afterExitOf(OPEN_IDS[0])
    await exit1(w, OPEN_IDS[0])
    expect(orderPosts()[0].body.orders).toHaveLength(1)
    expect(S(w).legs.find((l) => l.contract_id === OPEN_IDS[1]).lots).toBeNull()
  })
  it('A5: a typed entry price on 5587 (no order): it is still there after the exit', async () => {
    const w = await builder()
    setLeg(w, 1, { planned_entry: '99.00', typed: true })
    await flushPromises()
    answers['POST /paper/strategies/86/orders'] = afterExitOf(OPEN_IDS[0])
    answers['GET /paper/strategies/86'] = afterExitOf(OPEN_IDS[0])
    await exit1(w, OPEN_IDS[0])
    expect(S(w).legs.find((l) => l.contract_id === OPEN_IDS[1]).planned_entry).toBe('99.00')
  })
  it('A4b: unknown outcome, then the Orderbook link: a re-read that matches puts the staged change back; one that does not says the sentence', async () => {
    const w = await builder()
    await stageLeg2(w)
    answers['POST /paper/strategies/86/orders'] = () => Promise.reject({ status: 503, message: 'x', parts: null })
    answers['GET /paper/strategies/86'] = () => new Promise(() => {}) // U2 (ADR-017): the automatic re-read does not answer, so the outcome stays unknown
    await exit1(w, OPEN_IDS[0])
    expect(S(w).paperState).toBe('unknown')
    answers['GET /paper/strategies/86'] = afterExitOf(OPEN_IDS[0]) // the exit WAS stored
    await S(w).openPaperOrderbook()
    await flushPromises()
    expect(kindsOf(S(w).pendingOrders)).toEqual([['add', OPEN_IDS[1]]])
  })
  it('A4c: unknown outcome, the Orderbook re-read shows the staged leg gone: nothing put back, the sentence is shown', async () => {
    const w = await builder()
    await stageLeg2(w)
    answers['POST /paper/strategies/86/orders'] = () => Promise.reject({ status: 503, message: 'x', parts: null })
    answers['GET /paper/strategies/86'] = () => new Promise(() => {}) // U2 (ADR-017): the automatic re-read does not answer, so the outcome stays unknown
    await exit1(w, OPEN_IDS[0])
    await vi.advanceTimersByTimeAsync(135000) // Group A R1 (a): `changed` (the book moved some other way than the exit's own) ends the lock only for a read sent past the commit window
    answers['GET /paper/strategies/86'] = withNet(afterExitOf(OPEN_IDS[0]), { 5587: 0 })
    await S(w).openPaperOrderbook()
    await flushPromises()
    expect(S(w).pendingOrders).toEqual([])
    expect(t(w, 'staged-not-kept').exists()).toBe(true)
  })
})
