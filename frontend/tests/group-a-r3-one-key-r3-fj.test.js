// Group A finding R3 (28 Nov, Opus review of the round-2 order paths; ADR-017): ONE key per user action, reused on a resend of that action.
// The key is the Confirm dialog's (made at the press); a resend of the same orders after an unknown outcome sends the SAME key; a new key only after a decided outcome.
// Every page that sends an order or a basket asks the same rule (lib/unknownLocks.js orderKeyFor / dropOrderKey): builder, Positions (and the Alerts door), save bar, Execute.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
vi.mock('@/services/api', async (importActual) => ({ ...(await importActual()), default: (await import('./helpers/group-a.js')).apiMock }))
import * as H from './helpers/group-a.js'
import * as L from '@/lib/unknownLocks'
import { UNKNOWN_EXIT_READ_AFTER_MS as WINDOW } from '@/lib/sharedStateText'

const live = { last: null }
vi.mock('@/composables/useStrategyLive', async (importActual) => { const a = await importActual(); return { ...a, useStrategyLive: (opts) => { live.last = opts; return a.useStrategyLive(opts) } } })
const { posts, adv, t, S, calls } = H
beforeEach(H.setup)
afterEach(H.teardown)
const keys = () => posts().map((c) => c.body?.client_request_id)
const confirmAgain = async (w) => { const b = t(w, 'paper-confirm-button'); if (b.exists()) await b.trigger('click'); await flushPromises() }

describe('R3: Positions', () => {
  it('503, a read past the window says not stored, a resend of the same Confirm: the SAME key; its 201 ends the key', async () => {
    const w = await H.showPositions()
    await H.positionsExit(w)
    expect(keys()).toHaveLength(1)
    await adv(WINDOW + 10000)
    H.state.answers[`POST ${H.ORDERS}`] = () => Promise.resolve({ data: { orders: [{ id: 1 }] } })
    await confirmAgain(w)
    expect(keys()).toHaveLength(2)
    expect(keys()[1], 'a resend of the same exit got a new key').toBe(keys()[0])
    expect(JSON.parse(globalThis.localStorage.getItem('ofo.orderKeys') ?? '{}')['1'], 'the key outlived its 201').toBeUndefined()
  })
  it('a decided outcome (201) ends the key: the next exit of the same leg gets a NEW key', async () => {
    H.state.answers[`POST ${H.ORDERS}`] = () => Promise.resolve({ data: { orders: [{ id: 1 }] } })
    const w = await H.showPositions()
    await H.positionsExit(w)
    await adv(8000)
    await H.positionsExit(w)
    expect(keys()).toHaveLength(2)
    expect(keys()[1]).not.toBe(keys()[0])
  })
  it('582 ("still being placed") is not a refusal: the key and the lock stay', async () => {
    const w = await H.showPositions()
    await H.positionsExit(w)
    const k1 = keys()[0]
    await adv(WINDOW + 10000)
    H.state.answers[`POST ${H.ORDERS}`] = () => Promise.reject({ status: 409, error_code: 'STRATEGY_VALIDATION_582', message: 'x', parts: null })
    await confirmAgain(w)
    expect(keys()).toEqual([k1, k1])
    expect(L.exitLockFor(1), '582 ended the lock').not.toBeNull()
    expect(JSON.parse(globalThis.localStorage.getItem('ofo.orderKeys'))['1'].key).toBe(k1)
  })
  it('a refusal (580 / 581 / 583, any 4xx) frees the key', async () => {
    H.state.answers[`POST ${H.ORDERS}`] = () => Promise.reject({ status: 503, error_code: 'STRATEGY_VALIDATION_583', message: 'x', parts: null })
    const w = await H.showPositions()
    await H.positionsExit(w)
    expect(L.exitLockFor(1)).toBeNull()
    expect(globalThis.localStorage.getItem('ofo.orderKeys') ?? '').not.toContain('"1"')
  })
})

describe('R3: builder', () => {
  it('503, a read past the window says not stored, a resend of the same exit: the SAME key', async () => {
    const w = await H.showBuilder()
    await H.builderExit(w)
    await adv(WINDOW + 10000)
    expect(L.exitLockFor(1)).toBeNull()
    H.state.answers[`POST ${H.ORDERS}`] = () => Promise.resolve({ data: { orders: [{ id: 1 }] } })
    await H.builderExit(w)
    expect(keys()).toHaveLength(2)
    expect(keys()[1]).toBe(keys()[0])
  })
  it('after its 201 the next exit gets a NEW key', async () => {
    H.state.answers[`POST ${H.ORDERS}`] = () => Promise.resolve({ data: { orders: [{ id: 1 }] } })
    const w = await H.showBuilder()
    await H.builderExit(w)
    await adv(8000)
    await H.builderExit(w)
    expect(keys()).toHaveLength(2)
    expect(keys()[1]).not.toBe(keys()[0])
  })
  it('the key of an exit pressed twice before the stops read answers is one key (one post)', async () => {
    let free
    H.state.answers['GET /paper/strategies/1/triggers'] = () => new Promise((res) => { free = () => res({ data: { triggers: [] } }) })
    const w = await H.showBuilder()
    S(w).exitPaper(776, 2)
    await flushPromises()
    await t(w, 'paper-confirm-button').trigger('click')
    await t(w, 'paper-confirm-button').trigger('click')
    free(); await flushPromises(); await adv(100)
    expect(keys()).toHaveLength(1)
  })
})

describe('R3: Execute page (the real basket page; mocked answers only; it calls the same endpoint as before)', () => {
  const EXEC = '/strategies/1/execute'
  const REPLY = { plan_number: 1, tags: ['T'], basket: { url: 'https://kite.zerodha.com/connect/basket', api_key: 'k', data: '[]' }, orders: [{ exchange: 'NFO', tradingsymbol: 'X', transaction_type: 'BUY', order_type: 'LIMIT', product: 'NRML', variety: 'regular', quantity: 65, price: '3.35', readonly: true, tag: 'T' }], cost: null }
  const DEF = { underlying: 'NIFTY', legs: [{ contract_id: 7, contract_state: 'live', exchange_segment: 'NSE_FO', exchange_token: 12080386, action: 'BUY', instrument: 'CE', strike: '23650', expiry: '2026-10-19', quantity: 65, planned_entry: '3.35', captured_at: '2026-10-16T15:07:00+05:30' }] }
  const CONTRACT = { contract_id: 7, exchange_segment: 'NSE_FO', exchange_token: 12080386, instrument_type: 'CE', expiry: '2026-10-19', strike: '23650.00', lot_size: 65, symbol: 'NIFTY26O1923650CE' }
  const LIVE_PUSH = { state: 'COMPUTED', legs: [{ instrument_id: 'NSE_FO:12080386', action: 'BUY', lots: 1, planned_entry: '3.35', label: null }] }
  async function mountExecute(handler) {
    const ExecuteStrategyPage = (await import('@/pages/ExecuteStrategyPage.vue')).default
    H.state.answers['GET /strategies/1'] = { definition: DEF, revision: 3 }
    H.state.answers['GET /catalogue/NIFTY/contracts?expiry=2026-10-19'] = { contracts: [CONTRACT] }
    H.state.answers[`POST ${EXEC}`] = handler
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/:id/execute', component: ExecuteStrategyPage }] })
    await router.push('/strategy/1/execute'); await router.isReady()
    const w = mount(ExecuteStrategyPage, { props: { waitMs: 60000 }, global: { plugins: [router] }, attachTo: document.body })
    H.mounted.push(w)
    await flushPromises()
    live.last.onPush(LIVE_PUSH)
    await flushPromises()
    return w
  }
  const execPosts = () => calls.filter((c) => c.method === 'POST' && c.url === EXEC)
  const press = async (w, id) => { await t(w, id).trigger('click'); await flushPromises() }
  it('the prepare press carries a client_request_id; the same press repeated after an unknown answer sends the SAME key; the decided answer frees it', async () => {
    let n = 0
    const w = await mountExecute(() => (++n === 1 ? Promise.reject({ status: 503, message: 'x', parts: null }) : Promise.resolve({ data: REPLY })))
    await press(w, 'prepare-exit')
    expect(execPosts()).toHaveLength(1)
    const k1 = execPosts()[0].body.client_request_id
    expect(typeof k1).toBe('string')
    await press(w, 'prepare-exit')
    expect(execPosts(), 'F2 I-182: a press right after an unknown answer sends nothing (the Execute lock)').toHaveLength(1)
    globalThis.localStorage.removeItem('ofo.addUnknown'); window.dispatchEvent(new StorageEvent('storage', { key: 'ofo.addUnknown' })) // the lock ended (a good read past the window, tested in execute-lock-f2-1128); the request key stays
    live.last.onPush(LIVE_PUSH); await flushPromises()
    await press(w, 'prepare-exit')
    expect(execPosts()).toHaveLength(2)
    expect(execPosts()[1].body.client_request_id, 'a repeat of the same action got a new key').toBe(k1)
    expect(execPosts()[1].url).toBe(EXEC)
    expect(globalThis.localStorage.getItem('ofo.orderKeys') ?? '', 'the key outlived its decided answer').not.toContain(k1)
  })
  it('after a refusal (4xx) the next press is a new action with a new key', async () => {
    let n = 0
    const w = await mountExecute(() => (++n === 1 ? Promise.reject({ status: 409, message: 'x', parts: null }) : Promise.resolve({ data: REPLY })))
    await press(w, 'prepare-entry')
    live.last.onPush(LIVE_PUSH); await flushPromises()
    await press(w, 'prepare-entry')
    expect(execPosts()).toHaveLength(2)
    expect(execPosts()[1].body.client_request_id).not.toBe(execPosts()[0].body.client_request_id)
  })
  it('a different action (entry after an unknown exit) is a new action: its own key', async () => {
    const w = await mountExecute(() => Promise.reject({ status: 503, message: 'x', parts: null }))
    await press(w, 'prepare-exit')
    live.last.onPush(LIVE_PUSH); await flushPromises()
    await press(w, 'prepare-entry')
    expect(execPosts(), 'F2 I-182: the other button is locked too: the page has one lock').toHaveLength(1)
    globalThis.localStorage.removeItem('ofo.addUnknown'); window.dispatchEvent(new StorageEvent('storage', { key: 'ofo.addUnknown' })) // the lock ended; the key of the other action is its own
    live.last.onPush(LIVE_PUSH); await flushPromises()
    await press(w, 'prepare-entry')
    expect(execPosts()).toHaveLength(2)
    expect(execPosts()[1].body.client_request_id).not.toBe(execPosts()[0].body.client_request_id)
  })
})
