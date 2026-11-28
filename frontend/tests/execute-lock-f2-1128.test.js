// Lane F2 item 4 (I-182)
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url, body) => {
    calls.push([method, url, body])
    const a = answers[`${method} ${url}`]
    return a ? a() : Promise.reject({ message: 'no answer', parts: null })
  }
  return { ...actual, default: { get: reply('GET'), post: reply('POST') } }
})
const live = { onPush: null, onDown: null, follow: vi.fn() }
vi.mock('@/composables/useStrategyLive', () => ({
  useStrategyLive: (opts) => {
    live.onPush = opts.onPush
    live.onDown = opts.onDown
    return { status: { value: 'off' }, reconnecting: { value: false }, follow: live.follow, stop: () => {} }
  },
}))

import { matchesLegs } from '@/lib/liveMatch'
import ExecuteStrategyPage from '@/pages/ExecuteStrategyPage.vue'
import ExecutionReturnedPage from '@/pages/ExecutionReturnedPage.vue'
import BasketForm from '@/components/execution/BasketForm.vue'
import { KITE_BASKET_URL, LAST_EXECUTED_KEY, NOT_LIVE_PARTS, basketFields, isLiveOutcome, readLastExecuted, rememberExecuted } from '@/lib/execute'

const DATA = '[{"variety": "regular", "tradingsymbol": "NIFTY26O1923650CE", "exchange": "NFO", "transaction_type": "BUY", ' +
  '"order_type": "LIMIT", "product": "NRML", "price": 3.35, "quantity": 65, "readonly": true, "tag": "OFS1V1L0"}]'
const KITE_URL = 'https://kite.zerodha.com/connect/basket' // Kite's basket endpoint (basket_post.py); tests may name hosts
// charges / funds_available / margin_required are stand-in strings: these tests prove a string is shown as given, the
// real values are asserted by the e2e against the replay API.
const REPLY = {
  plan_number: 1,
  tags: ['OFS1V1L0'],
  basket: { url: KITE_URL, api_key: 'replay_api_key', data: DATA },
  orders: [{ exchange: 'NFO', tradingsymbol: 'NIFTY26O1923650CE', transaction_type: 'BUY', order_type: 'LIMIT', product: 'NRML',
    variety: 'regular', quantity: 65, price: '3.35', readonly: true, tag: 'OFS1V1L0' }],
  cost: { net_premium: '-217.75', charges: '41.27', charges_note: null, funds_available: '25000.00', margin_required: '217.75',
    figures_read_at: '2026-10-16T15:07:20+05:30' },
}
const DEF = { underlying: 'NIFTY', legs: [{ contract_id: 7, contract_state: 'live', exchange_segment: 'NSE_FO', exchange_token: 12080386, action: 'BUY',
  instrument: 'CE', strike: '23650', expiry: '2026-10-19', quantity: 65, planned_entry: '3.35', captured_at: '2026-10-16T15:07:00+05:30' }] }
const CONTRACT = { contract_id: 7, exchange_segment: 'NSE_FO', exchange_token: 12080386, instrument_type: 'CE', expiry: '2026-10-19',
  strike: '23650.00', lot_size: 65, symbol: 'NIFTY26O1923650CE' }
const LIVE_PUSH = { state: 'COMPUTED', legs: [{ instrument_id: 'NSE_FO:12080386', action: 'BUY', lots: 1, planned_entry: '3.35', label: null }] }
const RETURN = { strategy_id: 1, read_at: '2026-10-16T15:22:00+05:30', strategy_state: 'holding',
  plans: [{ plan_number: 1, action: 'ENTRY', state: 'filled', choices: [], reason: null }],
  contracts: [{ tradingsymbol: 'NIFTY26O1923650CE', platform_units: 65, zerodha_units: 65, other_strategies_units: 0,
    unexplained_units: 0, mismatch: null, reconciliation_reason: null }],
  mismatches: 0, blocked: false, external_orders: [], realised_pnl: null }
const REFUSAL = { what_happened: 'The market is closed. Orders can be placed once it opens.',
  impact: 'No order can be placed while the market is closed.', what_is_blocked: 'Execution of this strategy.',
  next_action: 'Return during market hours and execute again.' }

// W-151 (REQ-119 AC-5): the saved revision the review was loaded at (GET /strategies/1), sent with every Execute
const REVISION = 3
// the server's execute_plan_changed parts (backend/ofo/errors/templates.py), shown as given
const PLAN_CHANGED = { what_happened: 'Your plan changed after you reviewed it.',
  impact: 'No order was prepared and nothing was stored; orders are only prepared from the plan you reviewed.',
  what_is_blocked: 'Preparing orders from an older version of this strategy.',
  next_action: 'Review the current plan, then prepare the orders again.' }

const ok = (data) => () => Promise.resolve({ data })
const text = (w, id) => w.get(`[data-testid="${id}"]`).text()

async function openExecute(id = '1', waitMs = 50) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/:id/execute', component: ExecuteStrategyPage }] })
  await router.push(`/strategy/${id}/execute`)
  await router.isReady()
  const w = mount(ExecuteStrategyPage, { props: { waitMs }, global: { plugins: [router] } })
  await flushPromises()
  return w
}

let submitSpy
beforeEach(() => {
  calls.length = 0
  live.follow.mockReset()
  answers = {
    'GET /strategies/1': ok({ definition: DEF, revision: REVISION }),
    'GET /catalogue/NIFTY/contracts?expiry=2026-10-19': ok({ contracts: [CONTRACT] }),
    'POST /strategies/1/execute': ok(REPLY),
    'POST /strategies/1/execution/return': ok(RETURN),
  }
  submitSpy = vi.spyOn(HTMLFormElement.prototype, 'submit').mockImplementation(() => {})
  localStorage.clear()
})
afterEach(() => submitSpy.mockRestore())


const posts = () => calls.filter(([m]) => m === 'POST' && m !== undefined).map(([, u, b]) => [u, b]).filter(([u]) => u.endsWith('/execute'))
const LOCK_STORE = 'ofo.addUnknown'

// Lane F2 item 4 (I-182; ADR-016 to ADR-019; FJ question 4): "Execute page real basket has no lock after an unknown outcome and a repeat press is undefined".
// The page now uses the ONE lock rule (lib/unknownLocks.js decideLock): an Execute request of unknown outcome (no answer, 5xx, a cancelled request) keeps both
// Prepare buttons off, in this browser (a reload and a second tab hold it too), until a good read sent past the server's commit window releases it. The
// server also refuses a repeat (Lane B2's per-strategy block); this is the second line. A release keeps the request key, so a repeat press after it is the same request.
const UNKNOWN = () => Promise.reject({ message: 'no answer', parts: null })
async function pressEntry(w) {
  live.onPush(LIVE_PUSH)
  await flushPromises()
  await w.get('[data-testid="prepare-entry"]').trigger('click')
  await flushPromises()
}
const lockNote = (w) => w.find('[data-testid="execute-unknown-note"]')

describe('I-182: no second press after an unknown outcome', () => {
  it('unknown outcome, then a second press: nothing is sent, one plain sentence, both buttons off', async () => {
    answers['POST /strategies/1/execute'] = UNKNOWN
    const w = await openExecute('1', 10000)
    await pressEntry(w)
    expect(posts()).toHaveLength(1)
    expect(lockNote(w).text()).toContain('no answer')
    expect(w.get('[data-testid="prepare-entry"]').attributes('disabled')).toBeDefined()
    expect(w.get('[data-testid="prepare-exit"]').attributes('disabled')).toBeDefined()
    await w.get('[data-testid="prepare-entry"]').trigger('click')
    await w.get('[data-testid="prepare-exit"]').trigger('click')
    await flushPromises()
    expect(posts()).toHaveLength(1)
    expect(JSON.parse(localStorage.getItem(LOCK_STORE))['execute:1']).toBeTruthy()
  })

  it('a reload inside the window (a new page instance, same browser): still locked, still nothing sent', async () => {
    answers['POST /strategies/1/execute'] = UNKNOWN
    const w = await openExecute('1', 10000)
    await pressEntry(w)
    w.unmount()
    const again = await openExecute('1', 10000)
    live.onPush(LIVE_PUSH)
    await flushPromises()
    expect(lockNote(again).exists()).toBe(true)
    expect(again.get('[data-testid="prepare-entry"]').attributes('disabled')).toBeDefined()
    await again.get('[data-testid="prepare-entry"]').trigger('click')
    await flushPromises()
    expect(posts()).toHaveLength(1)
  })

  it('a lock written by another tab (storage only) holds a page that never sent anything', async () => {
    localStorage.setItem(LOCK_STORE, JSON.stringify({ 'execute:1': { at: Date.now(), out: false, before: '', key: 'k-other-tab', sig: 's' } }))
    const w = await openExecute('1', 10000)
    live.onPush(LIVE_PUSH)
    await flushPromises()
    expect(lockNote(w).exists()).toBe(true)
    await w.get('[data-testid="prepare-entry"]').trigger('click')
    await flushPromises()
    expect(posts()).toHaveLength(0)
  })

  it('a lock that cannot be read blocks (fail closed)', async () => {
    localStorage.setItem(LOCK_STORE, '{not json')
    const w = await openExecute('1', 10000)
    live.onPush(LIVE_PUSH)
    await flushPromises()
    await w.get('[data-testid="prepare-entry"]').trigger('click')
    await flushPromises()
    expect(posts()).toHaveLength(0)
  })

  // the 130 s rule counts REAL (monotonic) time in this page instance, never a wall clock set forward (lib/unknownLocks.js, Z2 T3): a test moves both clocks
  const clocks = () => {
    const c = { mono: 5000, wall: 1_800_000_000_000 }
    vi.spyOn(performance, 'now').mockImplementation(() => c.mono)
    vi.spyOn(Date, 'now').mockImplementation(() => c.wall)
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    return c
  }
  const later = async (c, ms) => { c.mono += ms; c.wall += ms; vi.advanceTimersByTime(5000); await flushPromises() }
  afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks() })

  it('a good read sent past the commit window releases it; the repeat press carries the SAME request key', async () => {
    const c = clocks()
    answers['POST /strategies/1/execute'] = UNKNOWN
    const w = await openExecute('1', 10000)
    await pressEntry(w)
    const firstKey = posts()[0][1].client_request_id
    expect(lockNote(w).exists()).toBe(true)
    await later(c, 60_000) // inside the window: still locked
    expect(lockNote(w).exists()).toBe(true)
    await later(c, 80_000) // 140 s of real time after the client gave up: the saved-strategy read decides "not stored"
    expect(lockNote(w).exists()).toBe(false)
    answers['POST /strategies/1/execute'] = ok(REPLY)
    await w.get('[data-testid="prepare-entry"]').trigger('click')
    await flushPromises()
    expect(posts()).toHaveLength(2)
    expect(posts()[1][1].client_request_id).toBe(firstKey)
  })

  it('a wall clock set forward 200 s with no real time passing never releases it', async () => {
    const c = clocks()
    answers['POST /strategies/1/execute'] = UNKNOWN
    const w = await openExecute('1', 10000)
    await pressEntry(w)
    c.wall += 200_000
    vi.advanceTimersByTime(5000)
    await flushPromises()
    expect(lockNote(w).exists()).toBe(true)
  })

  it('a failed read decides nothing: the lock stays even past the window', async () => {
    const c = clocks()
    answers['POST /strategies/1/execute'] = UNKNOWN
    const w = await openExecute('1', 10000)
    await pressEntry(w)
    answers['GET /strategies/1'] = () => Promise.reject({ message: 'down', parts: null })
    await later(c, 140_000)
    expect(lockNote(w).exists()).toBe(true)
  })

  it('answer states that need no lock: a reply and a definite refusal free the press (a new action)', async () => {
    const w = await openExecute('1', 10000)
    await pressEntry(w)
    expect(posts()).toHaveLength(1)
    expect(localStorage.getItem(LOCK_STORE) === null || !JSON.parse(localStorage.getItem(LOCK_STORE))['execute:1']).toBe(true)
    const w2 = await openExecute('1', 10000)
    answers['POST /strategies/1/execute'] = () => Promise.reject({ status: 409, parts: PLAN_CHANGED, message: 'x' })
    await pressEntry(w2)
    expect(lockNote(w2).exists()).toBe(false)
    expect(localStorage.getItem(LOCK_STORE) === null || !JSON.parse(localStorage.getItem(LOCK_STORE))['execute:1']).toBe(true)
  })
})
