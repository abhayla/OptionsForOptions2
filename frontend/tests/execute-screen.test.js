// W-104 (REQ-056 AC-1, REQ-073 AC-1/AC-3; ADR-054, ADR-097 (2), ADR-008): the Execute screen, the basket form and the
// basket-return landing page. The reply below is the shape of the Execute route's ENTRY answer for strategy 1 on the
// recorded 2026-10-16 session (W-101/W-102 briefs: BUY 65 NIFTY26O1923650CE LIMIT 3.35, tag OFS1V1L0, net premium
// -217.75 = 65 x 3.35 paid); every expected value is that reply's own string, never a value this code computed.
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
    return { status: { value: 'off' }, follow: live.follow, stop: () => {} }
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
  // the engine's at-expiry risk of the one long call: max loss = the premium paid (65 x 3.35), profit unlimited
  review: { max_loss: '217.75', max_loss_unlimited: false, max_profit: null, max_profit_unlimited: true },
}
const DEF = { underlying: 'NIFTY', legs: [{ contract_id: 7, exchange_segment: 'NSE_FO', exchange_token: 12080386, action: 'BUY',
  instrument: 'CE', strike: '23650', expiry: '2026-10-19', quantity: 65, planned_entry: '3.35', captured_at: '2026-10-16T15:07:00+05:30' }] }
const CONTRACT = { contract_id: 7, exchange_segment: 'NSE_FO', exchange_token: 12080386, instrument_type: 'CE', expiry: '2026-10-19',
  strike: '23650.00', lot_size: 65, symbol: 'NIFTY26O1923650CE' }
const LIVE_PUSH = { state: 'COMPUTED', legs: [{ instrument_id: 'NSE_FO:12080386', action: 'BUY', lots: 1, planned_entry: '3.35', label: null }] }
const RETURN = { strategy_id: 1, read_at: '2026-10-16T15:22:00+05:30', strategy_state: 'holding',
  plans: [{ plan_number: 1, action: 'ENTRY', state: 'filled', choices: [], reason: null }],
  contracts: [{ tradingsymbol: 'NIFTY26O1923650CE', platform_units: 65, zerodha_units: 65, other_strategies_units: 0,
    unexplained_units: 0, mismatch: null, reconciliation_reason: null }],
  mismatches: 0, blocked: false, external_orders: [], realised_pnl: null }
const REFUSAL = { what_happened: 'Market closed. You can review your plan; execution opens at 09:15 on Wed 21 Oct.',
  impact: 'No order can be placed while the market is closed.', what_is_blocked: 'Execution of this strategy.',
  next_action: 'Return during market hours and execute again.' }

// ADR-119 (3): the server's market verdict, as GET /execute/market-status writes it (Dussehra Tue 2026-10-20 10:00 IST)
const MARKET_OPEN = { status: 'open', next_open: null, message: null, as_of: '2026-10-21T10:00:00+05:30' }
const MARKET_CLOSED = { status: 'closed', next_open: '2026-10-21', as_of: '2026-10-20T10:00:00+05:30',
  message: { what_happened: 'Market closed. You can review your plan; execution opens at 09:15 on Wed 21 Oct.',
    impact: 'No order can be placed while the market is closed.', what_is_blocked: 'Execution of this strategy.',
    next_action: 'Return during market hours and execute again.' } }
const MARKET_UNCONFIRMED = { status: 'unconfirmed', next_open: null, as_of: '2027-01-05T10:00:00+05:30',
  message: { what_happened: 'We could not confirm that the market is open. Execution is paused until it is confirmed.',
    impact: "No order can be placed while the market's status is unknown.", what_is_blocked: 'Execution of this strategy.',
    next_action: 'Try again once the market status is shown.' } }

const MARKET_PAUSED = { status: 'paused', next_open: null, as_of: '2026-10-21T10:00:00+05:30',
  message: { what_happened: 'Execution is paused by the platform right now. You can review and save your plan; no orders can be sent.',
    impact: 'No order can be sent while execution is paused.', what_is_blocked: 'Execution of this strategy.',
    next_action: 'Review and save your plan now, and come back when execution is on again.' } }

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
    'GET /strategies/1': ok({ definition: DEF }),
    'GET /catalogue/NIFTY/contracts?expiry=2026-10-19': ok({ contracts: [CONTRACT] }),
    'POST /strategies/1/execute': ok(REPLY),
    'POST /strategies/1/execution/return': ok(RETURN),
    'GET /execute/market-status': ok(MARKET_OPEN),
  }
  submitSpy = vi.spyOn(HTMLFormElement.prototype, 'submit').mockImplementation(() => {})
  localStorage.clear()
})
afterEach(() => submitSpy.mockRestore())

const posts = () => calls.filter(([m]) => m === 'POST').map(([, u, b]) => [u, b])

describe('AC-1: live first, then the exact orders and cost, then Kite only on the owner click', () => {
  it('AC-1: follows the strategy legs live and calls Execute only after a live push and the owner click', async () => {
    const w = await openExecute('1', 10000)
    expect(live.follow).toHaveBeenCalledTimes(1)
    expect(live.follow.mock.calls[0][0].legs.map((l) => l.instrument_id)).toEqual(['NSE_FO:12080386'])
    expect(w.find('[data-testid="prepare-entry"]').exists()).toBe(false) // not live yet: no Execute action
    live.onPush(LIVE_PUSH)
    await flushPromises()
    expect(posts()).toEqual([]) // live alone calls nothing
    await w.get('[data-testid="prepare-entry"]').trigger('click')
    await flushPromises()
    expect(posts()).toEqual([['/strategies/1/execute', { action: 'ENTRY' }]])
    const row = w.get('[data-testid="execute-order"]').findAll('td').map((c) => c.text())
    expect(row).toEqual(['1', 'BUY', '65', 'NIFTY26O1923650CE', 'LIMIT', '3.35', 'OFS1V1L0'])
    expect(text(w, 'cost-net-premium')).toBe('-217.75')
    expect(text(w, 'cost-charges')).toBe('41.27')
    expect(text(w, 'cost-funds')).toBe('25000.00')
    expect(text(w, 'cost-margin')).toBe('217.75')
  })

  it('AC-1: not live within the wait -> the catalogue not-live message and Execute is never called', async () => {
    const w = await openExecute('1', 20)
    await new Promise((r) => setTimeout(r, 40))
    await flushPromises()
    expect(text(w, 'execute-error-what')).toBe(NOT_LIVE_PARTS.what_happened)
    expect(w.find('[data-testid="prepare-entry"]').exists()).toBe(false)
    expect(posts()).toEqual([])
  })

  it('AC-1: a NOT_CONNECTED or labelled push is not live; a socket drop blocks Execute', async () => {
    expect(isLiveOutcome({ state: 'NOT_CONNECTED', legs: LIVE_PUSH.legs })).toBe(false)
    expect(isLiveOutcome({ state: 'COMPUTED', legs: [{ ...LIVE_PUSH.legs[0], label: 'stale' }] })).toBe(false)
    expect(isLiveOutcome({ state: 'COMPUTED', legs: [] })).toBe(false)
    const w = await openExecute('1', 10000)
    live.onPush(LIVE_PUSH)
    await flushPromises()
    live.onDown()
    await w.get('[data-testid="prepare-entry"]').trigger('click')
    await flushPromises()
    expect(posts()).toEqual([])
  })

  it('AC-1: a route refusal (409) shows the catalogue text as given', async () => {
    answers['POST /strategies/1/execute'] = () => Promise.reject({ status: 409, parts: REFUSAL })
    const w = await openExecute('1', 10000)
    live.onPush(LIVE_PUSH)
    await flushPromises()
    await w.get('[data-testid="prepare-exit"]').trigger('click')
    await flushPromises()
    expect(posts()).toEqual([['/strategies/1/execute', { action: 'EXIT' }]])
    expect(text(w, 'execute-error-what')).toBe(REFUSAL.what_happened)
    expect(text(w, 'execute-error-next')).toBe(REFUSAL.next_action)
    expect(w.find('[data-testid="basket-form"]').exists()).toBe(false)
  })

  it('AC-1: the form carries api_key and data verbatim and is submitted only by the click, once', async () => {
    const w = mount(BasketForm, { props: { reply: REPLY, strategyId: '1' } })
    await flushPromises()
    const form = w.get('[data-testid="basket-form"]').element
    expect(form.getAttribute('method')).toBe('post')
    expect(form.getAttribute('action')).toBe(KITE_URL)
    expect(form.getAttribute('target')).toBe('_blank')
    const inputs = [...form.querySelectorAll('input')].map((i) => [i.name, i.type, i.value])
    expect(inputs).toEqual([['api_key', 'hidden', 'replay_api_key'], ['data', 'hidden', DATA]])
    expect(submitSpy).not.toHaveBeenCalled() // mounting with the reply submits nothing
    expect(localStorage.getItem(LAST_EXECUTED_KEY)).toBeNull()
    await w.get('[data-testid="place-on-kite"]').trigger('click')
    expect(submitSpy).toHaveBeenCalledTimes(1)
    expect(localStorage.getItem(LAST_EXECUTED_KEY)).toBe('1')
    expect(w.find('[data-testid="place-on-kite"]').exists()).toBe(false) // never a second post of the same basket
  })

  it('AC-1: two clicks before the page re-renders still post the basket once', async () => {
    const w = mount(BasketForm, { props: { reply: REPLY, strategyId: '1' } })
    const button = w.get('[data-testid="place-on-kite"]').element
    button.click()
    button.click()
    expect(submitSpy).toHaveBeenCalledTimes(1)
  })

  it('AC-1: only Kite basket url exactly; a lookalike host or http gets no form', () => {
    expect(KITE_BASKET_URL).toBe(KITE_URL)
    for (const url of ['https://kite.zerodha.com.evil.example/connect/basket', 'http://kite.zerodha.com/connect/basket',
      'https://kite.zerodha.com/connect/basket/', 'https://kite.zerodha.com/connect/login']) {
      expect(basketFields({ basket: { ...REPLY.basket, url } })).toBeNull()
    }
  })

  it('AC-1: a lookalike basket url from the API shows the neutral refusal and builds no form', async () => {
    answers['POST /strategies/1/execute'] = ok({ ...REPLY, basket: { ...REPLY.basket, url: 'https://kite.zerodha.com.evil.example/connect/basket' } })
    const w = await openExecute('1', 10000)
    live.onPush(LIVE_PUSH)
    await flushPromises()
    await w.get('[data-testid="prepare-entry"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="basket-form"]').exists()).toBe(false)
    expect(text(w, 'execute-error-what')).toBe('The page could not get an answer from the server.')
  })

  it('AC-1: the socket dropping after live shows the not-live message and disables Execute; a live push restores it', async () => {
    const w = await openExecute('1', 10000)
    live.onPush(LIVE_PUSH)
    await flushPromises()
    live.onDown()
    await flushPromises()
    expect(text(w, 'execute-error-what')).toBe(NOT_LIVE_PARTS.what_happened)
    expect(w.get('[data-testid="prepare-entry"]').attributes('disabled')).toBeDefined()
    expect(w.get('[data-testid="prepare-exit"]').attributes('disabled')).toBeDefined()
    live.onPush({ ...LIVE_PUSH, state: 'NOT_CONNECTED' })
    await flushPromises()
    expect(w.get('[data-testid="prepare-entry"]').attributes('disabled')).toBeDefined()
    live.onPush(LIVE_PUSH)
    await flushPromises()
    expect(w.find('[data-testid="execute-error-what"]').exists()).toBe(false)
    expect(w.get('[data-testid="prepare-entry"]').attributes('disabled')).toBeUndefined()
  })

  it('AC-1: "Open Kite\'s page again" re-posts the same fields and calls no API', async () => {
    const w = mount(BasketForm, { props: { reply: REPLY, strategyId: '1' } })
    await w.get('[data-testid="place-on-kite"]').trigger('click')
    const before = [...w.get('[data-testid="basket-form"]').element.querySelectorAll('input')].map((i) => [i.name, i.value])
    await w.get('[data-testid="open-kite-again"]').trigger('click')
    const after = [...w.get('[data-testid="basket-form"]').element.querySelectorAll('input')].map((i) => [i.name, i.value])
    expect(submitSpy).toHaveBeenCalledTimes(2)
    expect(after).toEqual(before)
    expect(after).toEqual([['api_key', 'replay_api_key'], ['data', DATA]])
    expect(calls).toEqual([])
  })

  it('AC-3: a return reply without contracts or plans still renders', async () => {
    answers['POST /strategies/1/execution/return'] = ok({ ...RETURN, contracts: undefined, plans: undefined })
    rememberExecuted('1')
    const w = mount(ExecutionReturnedPage, { global: { stubs: { RouterLink: true } } })
    await w.get('[data-testid="check-with-zerodha"]').trigger('click')
    await flushPromises()
    expect(text(w, 'return-mismatches')).toBe('0')
    expect(w.find('[data-testid="return-contract"]').exists()).toBe(false)
  })

  it('AC-1: a live push for other legs never opens Execute', async () => {
    const w = await openExecute('1', 10000)
    live.onPush({ ...LIVE_PUSH, legs: [{ ...LIVE_PUSH.legs[0], instrument_id: 'NSE_FO:44624' }] })
    await flushPromises()
    expect(w.find('[data-testid="prepare-entry"]').exists()).toBe(false)
  })

  it('AC-1: an Execute reply with an unreadable basket shows the neutral message and no form', async () => {
    answers['POST /strategies/1/execute'] = ok({ ...REPLY, basket: { ...REPLY.basket, data: '' } })
    const w = await openExecute('1', 10000)
    live.onPush(LIVE_PUSH)
    await flushPromises()
    await w.get('[data-testid="prepare-entry"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="basket-form"]').exists()).toBe(false)
    expect(w.find('[data-testid="execute-orders"]').exists()).toBe(false)
    expect(text(w, 'execute-error-what')).toBe('The page could not get an answer from the server.')
  })

  it('AC-1: a reply whose basket is not exactly {url, api_key, data} gets no form', () => {
    expect(basketFields(REPLY)).toEqual(REPLY.basket)
    for (const bad of [{ ...REPLY.basket, extra: 'x' }, { url: KITE_URL, api_key: 'k' }, { ...REPLY.basket, data: '' },
      { ...REPLY.basket, url: 'http://example.test/' }, { ...REPLY.basket, api_key: 7 }, null]) {
      expect(basketFields({ basket: bad })).toBeNull()
    }
  })

  it('AC-1: a null Zerodha figure is labelled not available, never shown blank', async () => {
    answers['POST /strategies/1/execute'] = ok({ ...REPLY, cost: { ...REPLY.cost, funds_available: null, margin_required: null } })
    const w = await openExecute('1', 10000)
    live.onPush(LIVE_PUSH)
    await flushPromises()
    await w.get('[data-testid="prepare-entry"]').trigger('click')
    await flushPromises()
    expect(text(w, 'cost-funds')).toBe('Not available from Zerodha')
    expect(text(w, 'cost-margin')).toBe('Not available from Zerodha')
  })

  it('AC-1: charges absent -> the server note is shown, no number claims to include charges', async () => {
    answers['POST /strategies/1/execute'] = ok({ ...REPLY, cost: { ...REPLY.cost, charges: null, charges_note: 'Charges are not included.' } })
    const w = await openExecute('1', 10000)
    live.onPush(LIVE_PUSH)
    await flushPromises()
    await w.get('[data-testid="prepare-entry"]').trigger('click')
    await flushPromises()
    expect(text(w, 'cost-charges-note')).toBe('Charges are not included.')
    expect(w.find('[data-testid="cost-charges"]').exists()).toBe(false)
  })
})

describe('ADR-119 (3): the screen shows the server market verdict BEFORE the click', () => {
  const marketCase = async (verdict) => {
    answers['GET /execute/market-status'] = verdict
    const w = await openExecute('1', 10000)
    live.onPush(LIVE_PUSH)
    await flushPromises()
    return w
  }

  it('open: both actions enabled and no market sentence', async () => {
    const w = await marketCase(ok(MARKET_OPEN))
    expect(w.get('[data-testid="prepare-entry"]').attributes('disabled')).toBeUndefined()
    expect(w.get('[data-testid="prepare-exit"]').attributes('disabled')).toBeUndefined()
    expect(w.find('[data-testid="market-closed-what"]').exists()).toBe(false)
  })

  it('closed (Dussehra): both actions disabled, the server sentence is shown, and a click calls nothing', async () => {
    const w = await marketCase(ok(MARKET_CLOSED))
    expect(text(w, 'market-closed-what')).toBe(MARKET_CLOSED.message.what_happened)
    for (const id of ['prepare-entry', 'prepare-exit']) expect(w.get(`[data-testid="${id}"]`).attributes('disabled')).toBeDefined()
    await w.get('[data-testid="prepare-entry"]').trigger('click')
    await flushPromises()
    expect(posts()).toEqual([])
  })

  it('closed shows the disabled actions and the sentence even when the legs never go live (after hours)', async () => {
    answers['GET /execute/market-status'] = ok(MARKET_CLOSED)
    const w = await openExecute('1', 20)
    await new Promise((r) => setTimeout(r, 40))
    await flushPromises()
    expect(text(w, 'market-closed-what')).toBe(MARKET_CLOSED.message.what_happened)
    expect(w.get('[data-testid="prepare-entry"]').attributes('disabled')).toBeDefined()
  })

  it('unconfirmed: actions disabled with the could-not-confirm text; a failed read is the same (fail closed)', async () => {
    const w = await marketCase(ok(MARKET_UNCONFIRMED))
    expect(text(w, 'market-closed-what')).toBe(MARKET_UNCONFIRMED.message.what_happened)
    expect(w.get('[data-testid="prepare-entry"]').attributes('disabled')).toBeDefined()
    const failed = await marketCase(() => Promise.reject({ message: 'down', parts: null }))
    expect(text(failed, 'market-closed-what')).toBe(MARKET_UNCONFIRMED.message.what_happened)
    expect(failed.get('[data-testid="prepare-exit"]').attributes('disabled')).toBeDefined()
  })

  it('ADR-127 paused: both actions disabled, exactly the ADR-127 sentence is shown before any click, a click calls nothing', async () => {
    const w = await marketCase(ok(MARKET_PAUSED))
    expect(text(w, 'market-closed-what')).toBe(
      'Execution is paused by the platform right now. You can review and save your plan; no orders can be sent.')
    for (const id of ['prepare-entry', 'prepare-exit']) expect(w.get(`[data-testid="${id}"]`).attributes('disabled')).toBeDefined()
    await w.get('[data-testid="prepare-entry"]').trigger('click')
    await flushPromises()
    expect(posts()).toEqual([])
  })

  it('ADR-128 paused + an open position: the ADR-127 sentence, then the server Kite line under it, Exit disabled', async () => {
    const HINT = { what_happened: 'You can still close positions directly on Kite.', impact: 'x', what_is_blocked: 'y', next_action: 'z' }
    const w = await marketCase(ok({ ...MARKET_PAUSED, paused_hint: HINT }))
    expect(text(w, 'market-closed-what')).toBe(MARKET_PAUSED.message.what_happened)
    expect(text(w, 'paused-hint')).toBe('You can still close positions directly on Kite.')
    const html = w.html()
    expect(html.indexOf('market-closed-what')).toBeLessThan(html.indexOf('paused-hint')) // under the ADR-127 sentence
    expect(w.get('[data-testid="prepare-exit"]').attributes('disabled')).toBeDefined()
    expect(w.get('[data-testid="prepare-entry"]').attributes('disabled')).toBeDefined()
    expect(calls.find(([m, u]) => m === 'GET' && u === '/execute/market-status')[2]).toEqual({ params: { strategy_id: '1' } })
    await w.get('[data-testid="prepare-exit"]').trigger('click')
    await flushPromises()
    expect(posts()).toEqual([]) // exits stay blocked in the app
  })

  it('ADR-128 paused + no open position (no hint from the server): the ADR-127 sentence only', async () => {
    const w = await marketCase(ok({ ...MARKET_PAUSED, paused_hint: null }))
    expect(text(w, 'market-closed-what')).toBe(MARKET_PAUSED.message.what_happened)
    expect(w.find('[data-testid="paused-hint"]').exists()).toBe(false)
    expect(w.text()).not.toContain('Kite.') // the line is not retyped on the page
  })

  it('ADR-128: a hint on a verdict that is not paused is never shown', async () => {
    const w = await marketCase(ok({ ...MARKET_CLOSED, paused_hint: { what_happened: 'You can still close positions directly on Kite.' } }))
    expect(w.find('[data-testid="paused-hint"]').exists()).toBe(false)
  })

  it('the browser clock never decides: a closed verdict stays closed at a browser time inside the session', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-10-21T04:45:00Z')) // 10:15 IST on a trading day
    try {
      const w = await marketCase(ok(MARKET_CLOSED))
      expect(w.get('[data-testid="prepare-entry"]').attributes('disabled')).toBeDefined()
    } finally {
      vi.useRealTimers()
    }
  })
})

describe('AC-3: Check with Zerodha and the basket-return landing page', () => {
  it('AC-3: after the Kite click, Check with Zerodha shows plan 1 filled and 0 mismatches', async () => {
    const w = await openExecute('1', 10000)
    live.onPush(LIVE_PUSH)
    await flushPromises()
    await w.get('[data-testid="prepare-entry"]').trigger('click')
    await flushPromises()
    await w.get('[data-testid="place-on-kite"]').trigger('click')
    await flushPromises()
    expect(posts().map(([u]) => u)).toEqual(['/strategies/1/execute']) // the return route waits for the owner
    await w.get('[data-testid="check-with-zerodha"]').trigger('click')
    await flushPromises()
    expect(posts().map(([u]) => u)).toEqual(['/strategies/1/execute', '/strategies/1/execution/return'])
    expect(w.get('[data-testid="return-plan"]').attributes('data-state')).toBe('filled')
    expect(text(w, 'return-plan-state')).toBe('filled')
    expect(text(w, 'return-mismatches')).toBe('0')
  })

  it('AC-3: the landing page makes no request on load and checks only on the click', async () => {
    rememberExecuted('1')
    const w = mount(ExecutionReturnedPage, { global: { stubs: { RouterLink: true } } })
    await flushPromises()
    expect(w.text()).toContain("Your orders were handled on Kite's page.")
    expect(calls).toEqual([])
    await w.get('[data-testid="check-with-zerodha"]').trigger('click')
    await flushPromises()
    expect(posts().map(([u]) => u)).toEqual(['/strategies/1/execution/return'])
    expect(text(w, 'return-mismatches')).toBe('0')
  })

  it('AC-3: nothing stored -> a link back to the strategies and no Check action', async () => {
    const w = mount(ExecutionReturnedPage, { global: { stubs: { RouterLink: true } } })
    await flushPromises()
    expect(w.find('[data-testid="check-with-zerodha"]').exists()).toBe(false)
    expect(w.find('[data-testid="returned-no-strategy"]').exists()).toBe(true)
    expect(calls).toEqual([])
  })

  it('AC-3: the stored id reads back only as a positive whole-number string; storage failures never throw', () => {
    localStorage.setItem(LAST_EXECUTED_KEY, '12')
    expect(readLastExecuted()).toBe('12')
    for (const bad of ['0', '-1', '1.5', 'abc', '', '01']) {
      localStorage.setItem(LAST_EXECUTED_KEY, bad)
      expect(readLastExecuted()).toBeNull()
    }
    const broken = { getItem: () => { throw new Error('denied') }, setItem: () => { throw new Error('denied') } }
    expect(readLastExecuted(broken)).toBeNull()
    expect(rememberExecuted('3', broken)).toBe(false)
  })
})

describe('AC-1: the live matcher on the server\'s own recorded outcome answers (not a shape typed here)', () => {
  const load = (f) => JSON.parse(readFileSync(resolve(__dirname, 'fixtures', f), 'utf8'))
  const draftOf = (body) => ({ underlying: body.underlying, legs: body.legs.map((l) => ({ instrument_id: l.instrument_id,
    action: l.action, lots: l.lots, planned_entry: l.planned_entry, captured_at: l.captured_at })) })
  it('AC-1: a recorded COMPUTED answer matches the draft it was asked for and reads as live', () => {
    const body = load('outcome-condor-advanced.json')
    expect(body.state).toBe('COMPUTED')
    expect(matchesLegs(body, draftOf(body))).toBe(true)
    expect(isLiveOutcome(body)).toBe(true)
  })
  it('AC-1: a recorded answer without a quote never reads as live', () => {
    const body = load('outcome-condor-guided-no-quote.json')
    expect(matchesLegs(body, draftOf(body))).toBe(true)
    expect(isLiveOutcome(body)).toBe(false)
  })
})

describe('wording and money (ADR-003, ADR-008)', () => {
  const files = ['src/pages/ExecuteStrategyPage.vue', 'src/pages/ExecutionReturnedPage.vue', 'src/components/execution/BasketForm.vue',
    'src/components/execution/ExecuteCost.vue', 'src/components/execution/ReturnCheck.vue', 'src/lib/execute.js']
  const src = files.map((f) => readFileSync(resolve(__dirname, '..', f), 'utf8')).join('\n')
  it('no advice words', () => {
    expect(src).not.toMatch(/you should|best trade|guaranteed/i)
  })
  it('no money parsing in the browser', () => {
    expect(src).not.toMatch(/parseFloat|toFixed/)
  })
  it('the not-live text is the catalogue template gate_data_unhealthy', () => {
    const t = readFileSync(resolve(__dirname, '../../backend/ofo/errors/templates.py'), 'utf8')
    const at = t.indexOf('_gate("gate_data_unhealthy"')
    expect(at).toBeGreaterThan(0)
    const block = t.slice(at, t.indexOf('),', at))
    const filled = block.replace('{data_input}', 'leg prices').replace('{state}', 'is unavailable')
    for (const part of ['what_happened', 'impact', 'next_action']) expect(filled).toContain(NOT_LIVE_PARTS[part])
    expect(t).toContain(`_EXEC = "${NOT_LIVE_PARTS.what_is_blocked}"`)
  })
})

// ---- EXECUTE-REVIEW (S5): the reading order and the server-only figures --------------------------------------------------
// TWO_BUYS is a stand-in for a two-order all-BUY reply (the recorded session has one order): every figure is a made-up
// server string, and the expectations are those same strings, never a value this code computed.
const TWO_BUYS = {
  ...REPLY,
  orders: [
    { ...REPLY.orders[0], tag: 'OFS1V1L0' },
    { ...REPLY.orders[0], tradingsymbol: 'NIFTY26O1924150PE', quantity: 75, price: '29.90', tag: 'OFS1V1L1' },
  ],
  review: { max_loss: '5900.00', max_loss_unlimited: false, max_profit: '4100.00', max_profit_unlimited: false },
  cost: { ...REPLY.cost, margin_required: '110000.00', funds_available: '240000.00', charges: '310.00' },
}

async function prepared(reply, query = '', button = 'prepare-entry') {
  answers['POST /strategies/1/execute'] = ok(reply)
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/:id/execute', component: ExecuteStrategyPage }] })
  await router.push(`/strategy/1/execute${query}`)
  await router.isReady()
  const w = mount(ExecuteStrategyPage, { props: { waitMs: 10000 }, global: { plugins: [router] } })
  await flushPromises()
  live.onPush(LIVE_PUSH)
  await flushPromises()
  await w.get(`[data-testid="${button}"]`).trigger('click')
  await flushPromises()
  return w
}
const ids = (w) => [...w.element.querySelectorAll('[data-testid]')].map((e) => e.getAttribute('data-testid'))

describe('EXECUTE-REVIEW: reads in the approved order, with the server figures only', () => {
  it('the plain sentence is first, then margin + charges, max loss / profit, orders, ready', async () => {
    const w = await prepared(TWO_BUYS)
    expect(text(w, 'execute-sentence')).toBe('You will place 2 orders now (2 buy, 0 sell); worst case loss ₹5,900.00.')
    const order = ids(w)
    const at = (id) => order.indexOf(id)
    expect(at('execute-sentence')).toBeGreaterThan(-1)
    expect(at('execute-sentence')).toBeLessThan(at('margin-label'))
    expect(at('margin-label')).toBeLessThan(at('cost-charges'))
    expect(at('cost-charges')).toBeLessThan(at('execute-max-loss'))
    expect(at('execute-max-loss')).toBeLessThan(at('execute-orders'))
    expect(at('execute-orders')).toBeLessThan(at('execute-ready'))
    expect(at('execute-ready')).toBeLessThan(at('place-on-kite'))
  })

  it('margin required + available (labelled an estimate), charges, max loss and max profit are the server strings', async () => {
    const w = await prepared(TWO_BUYS)
    expect(text(w, 'margin-label')).toBe("planning estimate; Zerodha's figure is authoritative")
    expect(text(w, 'cost-margin')).toBe('110000.00')
    expect(text(w, 'cost-funds')).toBe('240000.00')
    expect(text(w, 'cost-charges')).toBe('310.00')
    expect(text(w, 'execute-max-loss')).toBe('5900.00')
    expect(text(w, 'execute-max-profit')).toBe('4100.00')
  })

  it('orders carry sequence numbers 1..n in the server order, with the sequence note', async () => {
    const w = await prepared(TWO_BUYS)
    expect(w.findAll('[data-testid="order-seq"]').map((c) => c.text())).toEqual(['1', '2'])
    expect(w.findAll('[data-testid="execute-order"]').map((r) => r.findAll('td')[3].text())).toEqual(['NIFTY26O1923650CE', 'NIFTY26O1924150PE'])
    expect(text(w, 'sequence-note')).toBe('protective buys first; exits buy back shorts first, then sell longs')
    expect(text(w, 'every-trade-note')).toBe('Every trade follows a strategy')
  })

  it('"Ready to execute: <n> orders" shows the server order count and Open on Kite is the only action', async () => {
    const w = await prepared(TWO_BUYS)
    expect(text(w, 'execute-ready')).toBe('Ready to execute: 2 orders')
    expect(text(w, 'place-on-kite')).toBe('Open on Kite')
    expect(w.text()).not.toMatch(/Place order|Market|Include existing/)
    expect(submitSpy).not.toHaveBeenCalled() // on click only
  })

  it('an entry whose loss the server could not state invents no sentence; its max loss shows the existing dash', async () => {
    const unknown = await prepared({ ...REPLY, review: { max_loss: null, max_loss_unlimited: false, max_profit: null, max_profit_unlimited: false } })
    expect(text(unknown, 'execute-max-loss')).toBe('-')
    expect(unknown.find('[data-testid="execute-sentence"]').exists()).toBe(false)
    expect(unknown.find('[data-testid="execute-risk-line"]').exists()).toBe(false) // no risk block from the server -> no risk line
  })
})

// ---- ADR-139 first sentence (owner 2026-10-20): every shape, character for character -------------------------------------
const UNLIMITED = { max_loss: null, max_loss_unlimited: true, max_profit: '4100.00', max_profit_unlimited: false }
const sellOf = (o, tag) => ({ ...o, transaction_type: 'SELL', tag })
const MIXED = { ...TWO_BUYS, orders: [TWO_BUYS.orders[0], TWO_BUYS.orders[1], sellOf(TWO_BUYS.orders[0], 'OFS1V1L2'), sellOf(TWO_BUYS.orders[1], 'OFS1V1L3')] }

describe('EXECUTE-REVIEW: the first sentence (ADR-139)', () => {
  it('two-basket step 1 (the server says step 1 of 2): buys only, sells come after', async () => {
    const w = await prepared({ ...TWO_BUYS, step: { number: 1, of: 2 } })
    expect(text(w, 'execute-sentence')).toBe('Step 1 of 2: you will place 2 buy orders now; sells come after these fill.')
  })

  it('a step 1 reply that carries a sell is not given the step sentence', async () => {
    const w = await prepared({ ...MIXED, step: { number: 1, of: 2 } })
    expect(w.find('[data-testid="execute-sentence"]').exists()).toBe(false)
  })

  it('exit: "You will place 1 order to exit now." (singular) and "2 orders" for two', async () => {
    const one = await prepared(REPLY, '', 'prepare-exit')
    expect(text(one, 'execute-sentence')).toBe('You will place 1 order to exit now.')
    const two = await prepared(TWO_BUYS, '', 'prepare-exit')
    expect(text(two, 'execute-sentence')).toBe('You will place 2 orders to exit now.')
  })

  it('entry with buys and sells names the split and the grouped loss', async () => {
    const w = await prepared(MIXED)
    expect(text(w, 'execute-sentence')).toBe('You will place 4 orders now (2 buy, 2 sell); worst case loss ₹5,900.00.')
  })

  it('entry of one order reads "1 order"', async () => {
    const w = await prepared(REPLY)
    expect(text(w, 'execute-sentence')).toBe('You will place 1 order now (1 buy, 0 sell); worst case loss ₹217.75.')
  })

  it('unlimited loss: "... worst case loss is unlimited."', async () => {
    const w = await prepared({ ...MIXED, review: UNLIMITED })
    expect(text(w, 'execute-sentence')).toBe('You will place 4 orders now (2 buy, 2 sell); worst case loss is unlimited.')
  })

  it('amounts use Indian digit grouping, from the string alone', async () => {
    const lakh = await prepared({ ...TWO_BUYS, review: { ...TWO_BUYS.review, max_loss: '1234567.50' } })
    expect(text(lakh, 'execute-sentence')).toBe('You will place 2 orders now (2 buy, 0 sell); worst case loss ₹12,34,567.50.')
    const small = await prepared({ ...TWO_BUYS, review: { ...TWO_BUYS.review, max_loss: '999.00' } })
    expect(text(small, 'execute-sentence')).toBe('You will place 2 orders now (2 buy, 0 sell); worst case loss ₹999.00.')
  })
})

// ---- ADR-140 risk tiers: the page renders the server's tier and never computes one ---------------------------------------
const risk = (tier, percent, reason = null) => ({ tier, percent_of_funds: percent, reason, needs_acceptance: tier === 'EXCEPTIONAL' })
const EXCEPTIONAL_REPLY = { ...MIXED, review: UNLIMITED, basket: null, risk: risk('EXCEPTIONAL', null, 'UNLIMITED') }

describe('EXECUTE-REVIEW: the risk line and the acceptance gate (ADR-140)', () => {
  it('NORMAL: Rs 5,900.00 with Rs 2,40,000.00 available and no limit', async () => {
    const w = await prepared({ ...TWO_BUYS, risk: risk('NORMAL', '2.5') })
    expect(text(w, 'execute-risk-line')).toBe('Worst case: you could lose ₹5,900.00 (2.5% of your available funds).')
    expect(w.get('[data-testid="execute-risk-line"]').attributes('data-tier')).toBe('NORMAL')
    expect(w.get('[data-testid="execute-risk-line"]').classes()).not.toContain('text-amber-700')
    expect(w.find('[data-testid="accept-risk"]').exists()).toBe(false)
    expect(w.find('[data-testid="place-on-kite"]').exists()).toBe(true)
  })

  it('ELEVATED: amber, with the dash wording', async () => {
    const w = await prepared({ ...TWO_BUYS, review: { ...TWO_BUYS.review, max_loss: '70000.00' }, risk: risk('ELEVATED', '29.2') })
    expect(text(w, 'execute-risk-line')).toBe('Worst case: you could lose ₹70,000.00 - 29.2% of your available funds.')
    expect(w.get('[data-testid="execute-risk-line"]').classes()).toContain('text-amber-700')
    expect(w.find('[data-testid="accept-risk"]').exists()).toBe(false)
    expect(w.find('[data-testid="place-on-kite"]').exists()).toBe(true) // ELEVATED warns; it needs no acceptance
  })

  it('funds unknown: no percentage part, at ELEVATED', async () => {
    const w = await prepared({ ...TWO_BUYS, risk: risk('ELEVATED', null) })
    expect(text(w, 'execute-risk-line')).toBe('Worst case: you could lose ₹5,900.00.')
  })

  it('EXCEPTIONAL (unlimited): the text, an "I accept this risk" button, and NO way to open Kite until it is pressed', async () => {
    const w = await prepared(EXCEPTIONAL_REPLY)
    expect(text(w, 'execute-risk-line')).toBe('This strategy has no limit on its loss')
    expect(w.get('[data-testid="execute-risk-line"]').attributes('data-tier')).toBe('EXCEPTIONAL')
    expect(text(w, 'accept-risk')).toBe('I accept this risk')
    expect(w.find('[data-testid="place-on-kite"]').exists()).toBe(false)
    expect(w.find('[data-testid="basket-form"]').exists()).toBe(false)
    expect(submitSpy).not.toHaveBeenCalled()
  })

  it('EXCEPTIONAL (above funds): its own text', async () => {
    const w = await prepared({ ...EXCEPTIONAL_REPLY, review: TWO_BUYS.review, risk: risk('EXCEPTIONAL', '120.0', 'ABOVE_FUNDS') })
    expect(text(w, 'execute-risk-line')).toBe('This strategy can lose more than your available funds')
    expect(w.find('[data-testid="place-on-kite"]').exists()).toBe(false)
  })

  it('pressing "I accept this risk" asks the SERVER again with accept_risk; Open on Kite then appears from the server basket', async () => {
    const w = await prepared(EXCEPTIONAL_REPLY)
    expect(posts()).toEqual([['/strategies/1/execute', { action: 'ENTRY' }]]) // the first press carried no acceptance
    answers['POST /strategies/1/execute'] = ok({ ...EXCEPTIONAL_REPLY, basket: REPLY.basket })
    await w.get('[data-testid="accept-risk"]').trigger('click')
    await flushPromises()
    expect(posts()[1]).toEqual(['/strategies/1/execute', { action: 'ENTRY', accept_risk: true }])
    expect(w.find('[data-testid="accept-risk"]').exists()).toBe(false)
    expect(text(w, 'place-on-kite')).toBe('Open on Kite')
    expect(submitSpy).not.toHaveBeenCalled() // accepting opens nothing; only Open on Kite does
  })

  it('if the server still sends no basket after the acceptance, Open on Kite stays unavailable (no browser-only flag)', async () => {
    const w = await prepared(EXCEPTIONAL_REPLY)
    await w.get('[data-testid="accept-risk"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="place-on-kite"]').exists()).toBe(false)
    expect(w.find('[data-testid="basket-form"]').exists()).toBe(false)
    expect(w.find('[data-testid="accept-risk"]').exists()).toBe(true)
  })

  it('an unknown tier from the server shows no risk line and no acceptance; a basket-less non-EXCEPTIONAL reply is refused', async () => {
    const w = await prepared({ ...TWO_BUYS, risk: risk('CATASTROPHIC', '1.0') })
    expect(w.find('[data-testid="execute-risk-line"]').exists()).toBe(false)
    const bad = await prepared({ ...TWO_BUYS, basket: null, risk: risk('NORMAL', '2.5') })
    expect(bad.find('[data-testid="execute-sentence"]').exists()).toBe(false) // unreadable reply: no review is shown
    expect(bad.find('[data-testid="place-on-kite"]').exists()).toBe(false)
  })

  it('the page computes no tier: a huge loss with a NORMAL tier from the server is shown as NORMAL', async () => {
    const w = await prepared({ ...TWO_BUYS, review: { ...TWO_BUYS.review, max_loss: '9999999.00' }, risk: risk('NORMAL', '1.0') })
    expect(w.get('[data-testid="execute-risk-line"]').attributes('data-tier')).toBe('NORMAL')
  })
})

describe('EXECUTE-REVIEW: the sentence and the risk line stay inside the money guard', () => {
  it('no number parsing in the helpers', () => {
    const src = readFileSync(resolve(__dirname, '../src/lib/execute.js'), 'utf8')
    expect(src).not.toMatch(/parseFloat|parseInt|Number\(|toFixed|Math\./)
  })
})

describe('EXECUTE-REVIEW: Guided level and the closed market', () => {

  it('Guided: LIMIT is glossed and basket tags are hidden; other levels show the server word and the tag', async () => {
    const guided = await prepared(TWO_BUYS, '?ux=guided')
    const cells = guided.get('[data-testid="execute-order"]').findAll('td').map((c) => c.text())
    expect(cells).toEqual(['1', 'BUY', '65', 'NIFTY26O1923650CE', 'LIMIT (price you set)', '3.35'])
    expect(guided.text()).not.toContain('OFS1V1L0')
    const standard = await prepared(TWO_BUYS)
    expect(standard.get('[data-testid="execute-order"]').findAll('td').map((c) => c.text())[4]).toBe('LIMIT')
  })

  it('a server verdict that is not open shows its one message and no review (no second market message)', async () => {
    answers['GET /execute/market-status'] = ok(MARKET_CLOSED)
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/:id/execute', component: ExecuteStrategyPage }] })
    await router.push('/strategy/1/execute')
    await router.isReady()
    const w = mount(ExecuteStrategyPage, { props: { waitMs: 10000 }, global: { plugins: [router] } })
    await flushPromises()
    expect(w.findAll('[data-testid="market-closed-what"]')).toHaveLength(1)
    expect(w.find('[data-testid="execute-ready"]').exists()).toBe(false)
    expect(w.find('[data-testid="execute-sentence"]').exists()).toBe(false)
  })
})
