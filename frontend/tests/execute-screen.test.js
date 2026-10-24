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
const PLAN_CHANGED = { what_happened: 'Your plan changed - review it again.',
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

const posts = () => calls.filter(([m]) => m === 'POST').map(([, u, b]) => [u, b])

describe('REQ-077 AC-8: the review shows the planned price and the order limit, per leg', () => {
  const withPlanned = (planned) => ({ ...REPLY, orders: [{ ...REPLY.orders[0], price: '79.40', planned_price: planned }] })

  async function review(reply) {
    answers['POST /strategies/1/execute'] = ok(reply)
    const w = await openExecute('1', 10000)
    live.onPush(LIVE_PUSH)
    await flushPromises()
    await w.get('[data-testid="prepare-entry"]').trigger('click')
    await flushPromises()
    return w
  }

  it('AC-8: a typed planned price is shown next to the order limit, both as given', async () => {
    const w = await review(withPlanned('81.30'))
    expect(text(w, 'execute-planned-line')).toBe('NIFTY26O1923650CE: Your planned price 81.30 - order limit 79.40')
  })

  it('AC-8: a leg with no planned price shows only the order limit, never a made-up planned price', async () => {
    const w = await review(withPlanned(null))
    expect(text(w, 'execute-planned-line')).toBe('NIFTY26O1923650CE: Order limit 79.40')
  })
})

describe('AC-1: live first, then the exact orders and cost, then Kite only on the owner click', () => {
  it('ADR-168: the strategy the Execute page follows live carries no level key', async () => {
    await openExecute('1', 10000)
    expect(live.follow).toHaveBeenCalledTimes(1)
    expect(live.follow.mock.calls[0][0]).not.toHaveProperty(['ux', 'level'].join('_'))
  })

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
    expect(posts()).toEqual([['/strategies/1/execute', { action: 'ENTRY', revision: REVISION }]])
    const row = w.get('[data-testid="execute-order"]').findAll('td').map((c) => c.text())
    expect(row).toEqual(['BUY', '65', 'NIFTY26O1923650CE', 'LIMIT', '3.35', 'OFS1V1L0'])
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
    expect(posts()).toEqual([['/strategies/1/execute', { action: 'EXIT', revision: REVISION }]])
    expect(text(w, 'execute-error-what')).toBe(REFUSAL.what_happened)
    expect(text(w, 'execute-error-next')).toBe(REFUSAL.next_action)
    expect(w.find('[data-testid="basket-form"]').exists()).toBe(false)
  })

  it('W-151 (REQ-119 AC-5): a 409 plan-changed refusal shows its four parts and no plan', async () => {
    answers['POST /strategies/1/execute'] = () => Promise.reject({ status: 409, parts: PLAN_CHANGED })
    const w = await openExecute('1', 10000)
    live.onPush(LIVE_PUSH)
    await flushPromises()
    await w.get('[data-testid="prepare-entry"]').trigger('click')
    await flushPromises()
    expect(posts()).toEqual([['/strategies/1/execute', { action: 'ENTRY', revision: REVISION }]])
    expect(calls.filter(([m, u]) => m === 'GET' && u === '/strategies/1')).toHaveLength(1) // no second read
    expect(text(w, 'execute-error-what')).toBe(PLAN_CHANGED.what_happened)
    expect(text(w, 'execute-error-impact')).toBe(PLAN_CHANGED.impact)
    expect(text(w, 'execute-error-blocked')).toBe(PLAN_CHANGED.what_is_blocked)
    expect(text(w, 'execute-error-next')).toBe(PLAN_CHANGED.next_action)
    expect(w.find('[data-testid="execute-orders"]').exists()).toBe(false)
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
    const body = load('outcome-condor.json')
    expect(body.state).toBe('COMPUTED')
    expect(matchesLegs(body, draftOf(body))).toBe(true)
    expect(isLiveOutcome(body)).toBe(true)
  })
  it('AC-1: a recorded answer without a quote never reads as live', () => {
    const body = load('outcome-condor-no-quote.json')
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
