// #774 + ADR-330 (48), owner 27 Nov: when a leg's expiry is changed its leg stop is REMOVED with the move. The review says so before
// Confirm ("The stop on <leg> will be removed; set a new one after the move."); after the move the app offers "Set a stop on <new leg>"
// through the existing leg-stop set control and its route (POST .../triggers, kind leg_stop). A stop that follows the leg was not chosen.
// The offer rests on the server's two reads (the stops list and the book), never on the screen's guess: a refused move, an unknown
// answer or a leg without a stop offers nothing. New sentence: pending owner read.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import { STOP_OFFER_LABEL } from '@/lib/paperTriggers'
import REAL from './fixtures/paper-book-63.json'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    const a = answers[`${method} ${url}`]
    if (a === undefined) return Promise.reject(new Error(`unmocked ${method} ${url}`))
    return typeof a === 'function' ? a(body) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u, b) => respond('POST', u, b), put: (u, b) => respond('PUT', u, b), patch: (u, b) => respond('PATCH', u, b), delete: (u) => respond('DELETE', u) } }
})

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const CONTRACTS = REAL.positions.map((p) => ({ contract_id: p.contract_id, exchange_segment: 'NSE_FO', exchange_token: p.contract_id,
  instrument_type: p.instrument, expiry: p.expiry, strike: p.strike, lot_size: 65, symbol: `NIFTY${p.strike}${p.instrument}` }))
const BOOK = { ...REAL, strategy_id: 86, name: '"IC"' }
// the book after the move: the 22650 PE (5574) is closed and the 22700 PE (5576) is the new leg
const MOVED = { ...BOOK, positions: BOOK.positions.map((p) => (p.contract_id === 5574 ? { ...p, net_quantity: 0 } : p.contract_id === 5576 ? { ...p, net_quantity: -65 } : p)) }
const ORDERS_URL = '/paper/strategies/86/orders'
const BOOK_URL = '/paper/strategies/86'
const TRIG = '/paper/strategies/86/triggers'
const ARMED = '/paper/strategies/86/armed-exits'
const SENTENCE = 'The stop on NIFTY 3 Nov 22650 PE will be removed; set a new one after the move.'
const stop = (over = {}) => ({ id: 7, strategy_id: 86, kind: 'leg_stop', direction: 'above', level: '120.00', level_text: 'Option at or above 120.00', contract_id: 5574,
  contract_text: 'NIFTY 22650 PE', underlying: null, state: 'armed', created_at: '2026-11-27T05:00:00Z', fired_at: null, cancelled_at: null, ...over })
const TIMEOUT = { message: 'x', status: null, code: 'ECONNABORTED' }
const REFUSED = { message: 'x', status: 422, parts: { what_happened: 'That strike is not listed.', impact: 'i', what_is_blocked: 'b', next_action: 'n' } }
const posts = () => calls.filter((c) => c.method === 'POST' && c.url === ORDERS_URL)
const stopsReads = () => calls.filter((c) => c.method === 'GET' && c.url === TRIG).length

// the stops list as the server holds it: first read(s) before the move, then after it
let stopsNow = []
let bookNow = BOOK
beforeEach(() => {
  calls.length = 0
  bookNow = BOOK
  stopsNow = [stop()]
  answers = {
    'GET /strategies': { strategies: [] },
    [`POST ${ORDERS_URL}`]: () => { stopsNow = [stop({ state: 'cancelled', cancelled_at: '2026-11-27T05:30:00Z' })]; bookNow = MOVED; return Promise.resolve({ data: MOVED }) },
    [`GET ${BOOK_URL}`]: () => Promise.resolve({ data: bookNow }),
    [`GET ${TRIG}`]: () => Promise.resolve({ data: { triggers: stopsNow } }),
    [`POST ${TRIG}`]: () => Promise.resolve({ data: { triggers: stopsNow, already_set: false, already_armed: [] } }),
    [`GET ${ARMED}`]: { lines: [SENTENCE] },
    'GET /catalogue/NIFTY/contracts?expiry=2026-11-03': { underlying: 'NIFTY', contracts: CONTRACTS },
    'POST /strategies/outcome': () => new Promise(() => {}),
    'POST /strategies/leg-edit': () => new Promise(() => {}),
  }
})
const mounted = []
afterEach(() => {
  vi.useRealTimers()
  while (mounted.length) mounted.pop().unmount()
  document.body.innerHTML = ''
})

async function reviewDialog() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }, { path: '/positions/current-positions', component: { template: '<p />' } }] })
  await router.push('/strategy/builder?strategy=86')
  await router.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true } }, attachTo: document.body })
  mounted.push(w)
  await flushPromises()
  await t(w, 'paper-exit-all').trigger('click') // any basket: the stops and the book are the server's answers mocked above
  await flushPromises()
  expect(t(w, 'paper-confirm').exists()).toBe(true)
  return w
}
const confirm = async (w) => { await t(w, 'paper-confirm-button').trigger('click'); await flushPromises() }

describe('ADR-330 (48): the stop goes with the move, the app offers a new one on the new leg', () => {
  it('the review says the stop will be removed, word for word, before Confirm', async () => {
    const w = await reviewDialog()
    expect(w.findAll('[data-testid="paper-armed-exit"]').map((l) => l.text())).toEqual([SENTENCE])
    expect(posts()).toHaveLength(0)
  })

  it('a leg with a stop moved: after Confirm the stop is gone (re-read) and "Set a stop on <new leg>" is offered; saving it uses the existing route', async () => {
    const w = await reviewDialog()
    expect(t(w, 'stop-offer').exists()).toBe(false) // nothing offered before the move
    await confirm(w)
    expect(posts()).toHaveLength(1)
    const offer = w.findAll('[data-testid="stop-offer-open"]')
    expect(offer.map((b) => b.text())).toEqual([STOP_OFFER_LABEL('NIFTY 3 Nov 22700 PE')]) // the new leg only, not the old one
    expect(offer[0].text()).toBe('Set a stop on NIFTY 3 Nov 22700 PE')
    await offer[0].trigger('click')
    await flushPromises()
    expect(t(w, 'stop-offer').find('[data-testid="conditional-exit"]').exists()).toBe(false) // only the leg-stop control
    await t(w, 'stop-offer').find('[data-testid="stop-direction-5576"]').setValue('below')
    await t(w, 'stop-offer').find('[data-testid="stop-level-5576"]').setValue('60.00')
    await t(w, 'stop-offer').find('[data-testid="stop-save-5576"]').trigger('click')
    await flushPromises()
    const save = calls.find((c) => c.method === 'POST' && c.url === TRIG)
    expect(save.body).toEqual({ kind: 'leg_stop', contract_id: '5576', direction: 'below', level: '60.00' })
  })

  it('a leg without a stop: no offer', async () => {
    stopsNow = []
    answers[`GET ${ARMED}`] = { lines: [] }
    const w = await reviewDialog()
    await confirm(w)
    expect(posts()).toHaveLength(1)
    expect(t(w, 'stop-offer').exists()).toBe(false)
  })

  it('a stop on a leg that did not move stays armed on the re-read: no offer', async () => {
    stopsNow = [stop({ contract_id: 5572 })]
    answers[`POST ${ORDERS_URL}`] = () => Promise.resolve({ data: MOVED }) // the server cancelled nothing
    const w = await reviewDialog()
    await confirm(w)
    expect(t(w, 'stop-offer').exists()).toBe(false)
  })

  it('a move the server refuses: the stop is kept and nothing is offered', async () => {
    answers[`POST ${ORDERS_URL}`] = () => Promise.reject(REFUSED)
    const w = await reviewDialog()
    await confirm(w)
    expect(t(w, 'paper-error').text()).toBe('That strike is not listed.')
    expect(t(w, 'stop-offer').exists()).toBe(false)
    expect(stopsNow[0].state).toBe('armed')
  })

  it('the answer is unknown: nothing is claimed; the stop state comes from a re-read, and the offer only follows what it shows', async () => {
    answers[`POST ${ORDERS_URL}`] = () => Promise.reject(TIMEOUT) // the server may or may not have stored it: the stop is still armed here
    const w = await reviewDialog()
    await confirm(w)
    expect(t(w, 'paper-unknown').exists()).toBe(true)
    expect(t(w, 'stop-offer').exists()).toBe(false)
    expect(t(w, 'paper-placed').exists()).toBe(false) // no "placed" claim either
    const before = stopsReads()
    // the book re-read and the stops re-read both say the move was stored and the stop is gone
    stopsNow = [stop({ state: 'cancelled', cancelled_at: '2026-11-27T05:30:00Z' })]
    bookNow = MOVED
    await t(w, 'paper-open-orderbook').trigger('click')
    await flushPromises()
    expect(stopsReads()).toBeGreaterThan(before)
    expect(w.findAll('[data-testid="stop-offer-open"]').map((b) => b.text())).toEqual(['Set a stop on NIFTY 3 Nov 22700 PE'])
  })

  it('unknown, and the re-read shows the stop still armed (not stored): no offer', async () => {
    answers[`POST ${ORDERS_URL}`] = () => Promise.reject(TIMEOUT)
    const w = await reviewDialog()
    await confirm(w)
    await t(w, 'paper-open-orderbook').trigger('click')
    await flushPromises()
    expect(t(w, 'stop-offer').exists()).toBe(false)
  })
})
