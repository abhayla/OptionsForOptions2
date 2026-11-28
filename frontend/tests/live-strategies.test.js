// W-113 (REQ-049 AC-4, AC-5, AC-6; ADR-008, ADR-077): the Live Strategies page, with a fake socket per card and a mocked
// API. Expected texts come from the pushes and answers the test hands in; the page must show them untouched.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { echoSeq } from './helpers/echoSeq'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

const posts = []
let listAnswer
let postAnswer
let failDetailFor = new Set()
let notLiveFor = new Set() // issue #500: drafts whose leg's stored contract is no longer live
let indicesAnswer = null // ADR-177/212: the page's own market read (GET /market/indices); null = the read fails
let partlyPricedFor = new Set() // REQ-077 AC-9: drafts with one priced leg and one leg that has no planned entry
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const get = (url) => {
    if (url === '/strategies') return typeof listAnswer === 'function' ? listAnswer() : Promise.resolve({ data: withWords(listAnswer) })
    // ADR-299 / issue 16: the book of a running trade (only the contract held now, one leg already closed)
    const book = /^\/paper\/strategies\/(\d+)$/.exec(url)
    if (book) {
      paperGets.push(Number(book[1]))
      if (expiredBook.has(Number(book[1]))) { // D-40: every open leg is on an expired contract the catalogue no longer lists
        return Promise.resolve({ data: { strategy_id: Number(book[1]), underlying: 'NIFTY', answered_at: '2026-10-19T10:00:00+05:30', orders: [{ id: 1 }],
          positions: [{ contract_id: 777, net_quantity: -65, average: '88.50', expiry: '2026-10-13', price_at: null }],
          pause_reason: 'contract_retired', pause_reason_text: EXPIRED_REASON, expired_open: true,
          unpriced_legs: [{ leg_index: 0, contract_text: 'NIFTY 13 Oct 22800 CE', expired: true }], unpriced_text: expiredNoLine ? null : EXPIRED_LINE } })
      }
      if (unreadableBook.has(Number(book[1]))) { // D-40 r2: a not-live leg that is NOT expired, and a catalogue without it: a genuine unreadable book
        return Promise.resolve({ data: { strategy_id: Number(book[1]), underlying: 'NIFTY', answered_at: '2026-10-19T10:00:00+05:30', orders: [{ id: 1 }],
          positions: [{ contract_id: 777, net_quantity: -65, average: '88.50', expiry: '2026-10-13', price_at: null }],
          pause_reason: 'token_reassigned', pause_reason_text: 'This contract is not live.', expired_open: false,
          unpriced_legs: [{ leg_index: 0, contract_text: 'NIFTY 13 Oct 22800 CE', expired: false }], unpriced_text: 'No price for: NIFTY 13 Oct 22800 CE.' } })
      }
      if (realOnly.has(Number(book[1]))) return Promise.reject({ status: 404, parts: { what_happened: 'No paper book', impact: 'i', what_is_blocked: 'b', next_action: 'n' } }) // a real trade has no practice book
      return Promise.resolve({ data: { strategy_id: Number(book[1]), underlying: 'NIFTY', answered_at: '2026-10-19T10:00:00+05:30',
        orders: [{ id: 1 }, { id: 2 }], positions: [{ contract_id: 5, net_quantity: -65, average: '88.50', expiry: '2026-10-13', price_at: '2026-10-19T10:00:00+05:30' },
          { contract_id: 6, net_quantity: 0, average: '90.00', expiry: '2026-10-13' }] } })
    }
    const detail = /^\/strategies\/(\d+)$/.exec(url)
    if (detail) {
      const id = Number(detail[1])
      detailGets.push(id)
      if (failDetailFor.has(id)) return Promise.reject({ parts: { what_happened: `Server says draft ${id} failed`, impact: 'i', what_is_blocked: 'b', next_action: 'n' } })
      return Promise.resolve({ data: { id, definition: { underlying: 'NIFTY', legs: [{ contract_id: id, ...(notLiveFor.has(id) ? { contract_state: 'token_reassigned', exchange_segment: null, exchange_token: null } : { contract_state: 'live', exchange_segment: 'NSE_FO', exchange_token: 1000 + id }),
        action: 'SELL', instrument: 'CE', strike: '22800', expiry: '2026-10-13', quantity: 65, planned_entry: '100.00', captured_at: '2026-10-08T09:20:09+05:30' },
      // REQ-077 AC-9: a second, live leg with no planned entry next to the priced one
      ...(partlyPricedFor.has(id) ? [{ contract_id: id + 1, contract_state: 'live', exchange_segment: 'NSE_FO', exchange_token: 1001 + id,
        action: 'BUY', instrument: 'CE', strike: '22900', expiry: '2026-10-13', quantity: 65, planned_entry: null, captured_at: null }] : [])] } } })
    }
    const cat = /^\/catalogue\/NIFTY\/contracts/.exec(url)
    if (cat) {
      return Promise.resolve({ data: { contracts: [...Array(40).keys()].map((i) => ({ contract_id: i + 1, exchange_segment: 'NSE_FO', exchange_token: 1001 + i,
        instrument_type: 'CE', expiry: '2026-10-13', strike: '22800.00', lot_size: 65, symbol: `NIFTY${i + 1}` })) } })
    }
    if (url === '/market/indices') return indicesAnswer ? Promise.resolve({ data: indicesAnswer }) : Promise.reject(new Error('indices failed'))
    return Promise.reject(new Error(`unmocked get ${url}`))
  }
  const post = (url, body) => {
    posts.push({ url, body })
    return typeof postAnswer === 'function' ? postAnswer(body) : Promise.resolve({ data: postAnswer })
  }
  return { ...actual, default: { get, post } }
})
import { withWords } from './_statusWord'
import LiveStrategiesPage from '@/pages/LiveStrategiesPage.vue'
import { LEG_NOT_LIVE_LABEL, NOT_CONNECTED_LABEL } from '@/lib/legPicker'

class FakeSocket {
  static all = []
  constructor(url) {
    this.url = url
    this.sent = []
    this.readyState = 0
    this.closed = false
    FakeSocket.all.push(this)
  }
  send(t) { this.sent.push(t) }
  close() { this.closed = true; this.readyState = 3 }
  serverOpen() { this.readyState = 1; this.onopen?.() }
  serverPush(obj) { this.onmessage?.({ data: JSON.stringify(echoSeq(this, obj)) }) }
  serverClose() { this.readyState = 3; this.onclose?.() }
}

const row = (id, updated = '2026-10-19T10:00:00+05:30') => ({ id, underlying: 'NIFTY', status: 'draft', created_at: updated, updated_at: updated })
const leg = (over = {}) => ({ instrument_id: 'NSE_FO:1001', symbol: 'NIFTY1', action: 'SELL', ltp: '39.15', health: 'available', label: null, ...over })
const computed = (over = {}) => ({ state: 'COMPUTED', underlying: 'NIFTY', status_label: null, reason: null, output_label: null,
  spot_level: '25123.45', spot_at: '2026-10-19T10:15:00+05:30', answered_at: '2026-10-19T10:15:01+05:30',
  summary: { max_profit: '0.00', max_loss: '13000.00', max_profit_unlimited: false, max_loss_unlimited: false }, legs: [leg()], ...over })
const SERVER_LABEL = 'Server wrote this not-live sentence 10:15:00 IST'
const notConnected = () => ({ state: 'NOT_CONNECTED', status_label: SERVER_LABEL, reason: null, answered_at: '2026-10-19T10:16:00+05:30', legs: [], spot_level: null, spot_at: null })
const FROM_YOUR_PRICES = 'From your prices — no live data'
// The FROM_ENTRIES answer as the server sends it after a drop (tests_app/test_strategy_live_push.py `_assert_from_entries_after_drop`).
const fromEntries = () => ({ state: 'FROM_ENTRIES', underlying: 'NIFTY', status_label: SERVER_LABEL, output_label: FROM_YOUR_PRICES, reason: null,
  answered_at: '2026-10-19T10:16:00+05:30', spot_level: null, spot_at: null, summary: computed().summary, legs: [leg({ ltp: null, health: null })] })

async function mountPage() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }, { path: '/strategy/builder', component: { template: '<div/>' } }, { path: '/positions/adjustment-opportunities', component: { template: '<div/>' } }] })
  router.push('/')
  await router.isReady()
  const w = mount(LiveStrategiesPage, { global: { plugins: [router] } })
  // GC-TPD R-12: a page a test leaves mounted keeps real timers (the socket reconnect backoff, the 8 s queue release) and
  // reopens FakeSockets into the NEXT test's shared FakeSocket.all / detailGets on a slow machine. Every page is
  // unmounted after its test (a test that unmounts itself is not unmounted twice).
  const unmount = w.unmount.bind(w)
  let gone = false
  w.unmount = () => { if (!gone) { gone = true; unmount() } }
  mountedPages.push(w)
  await flushPromises()
  return w
}
const mountedPages = []
const cards = (w) => w.findAll('[data-testid="live-strategy-card"]')
const openAll = () => FakeSocket.all.forEach((s) => s.serverOpen())
// Cards start one at a time: answer the newest socket, let the next card start, and repeat.
async function answerNext(body) {
  const s = FakeSocket.all[FakeSocket.all.length - 1]
  s.serverOpen()
  s.serverPush(body)
  await flushPromises()
  return s
}
const detailGets = []
const paperGets = []
const realOnly = new Set()
const expiredBook = new Set()
const unreadableBook = new Set()
let expiredNoLine = false
const EXPIRED_REASON = 'This contract has expired and is no longer traded.'
const EXPIRED_LINE = 'Expired contracts have no price: NIFTY 13 Oct 22800 CE.'

beforeEach(() => {
  FakeSocket.all = []
  posts.length = 0
  detailGets.length = 0
  paperGets.length = 0
  realOnly.clear()
  expiredBook.clear()
  unreadableBook.clear()
  expiredNoLine = false
  vi.useRealTimers()
  vi.spyOn(Math, 'random').mockReturnValue(0) // no reconnect spread here: it has its own tests (reconnect-forever.test.js)
  failDetailFor = new Set()
  notLiveFor = new Set()
  partlyPricedFor = new Set()
  indicesAnswer = null
  listAnswer = { strategies: [row(1), row(2)] }
  postAnswer = notConnected()
  global.WebSocket = FakeSocket
})
afterEach(() => {
  while (mountedPages.length) mountedPages.pop().unmount()
  vi.restoreAllMocks()
})

const closedIndices = (over = {}) => ({ state: 'NOT_CONNECTED', indices: [], answered_at: '2026-11-27T08:30:00+05:30', market_closed: true, last_price_at: '2026-11-26T15:30:00+05:30', ...over })

describe('A3 (ADR-177, ADR-212): the one market-closed banner comes from the page-level market read, not from a card', () => {
  it('before the open, every card unpriced (none ever says market_closed): the banner still shows, with the close time', async () => {
    indicesAnswer = closedIndices()
    const w = await mountPage()
    expect(w.findAll('[data-testid="market-closed-text"]')).toHaveLength(1)
    expect(w.get('[data-testid="market-closed-text"]').text()).toBe('Market closed. Prices are from 26 Nov 2026, 15:30:00 IST.')
  })

  it('market open: no banner, even when the market read answers', async () => {
    indicesAnswer = closedIndices({ state: 'LIVE', market_closed: false })
    const w = await mountPage()
    expect(w.find('[data-testid="market-closed-banner"]').exists()).toBe(false)
  })

  it('the market read fails: no banner (never a made-up time)', async () => {
    const w = await mountPage()
    expect(w.find('[data-testid="market-closed-banner"]').exists()).toBe(false)
  })
})

describe('U20: after hours and Sensibull 090 layout', () => {
  const closedLeg = (over = {}) => leg({ symbol: 'NIFTY26N0322950CE', instrument: 'CE', strike: '22950.00', expiry: '2026-11-03', health: 'stale', lots: 2,
    planned_entry_display: '150.00', ltp_display: '150.60', ...over })
  const closedAnswer = (over = {}) => computed({ market_closed: true, last_price_at: '2026-10-29T15:30:00+05:30', spot_at: '2026-10-30T08:18:54+05:30',
    summary: { max_profit: '7113.83', max_loss: '5886.17', max_profit_display: '+7,114', max_loss_display: '−5,886', breakevens_display: ['22,688 (-0.1%)'],
      max_profit_unlimited: false, max_loss_unlimited: false }, legs: [closedLeg()], ...over })

  it('closed market: price-time banner, no fetch time, no stale noise, contract name, server money strings', async () => {
    indicesAnswer = closedIndices({ last_price_at: '2026-10-29T15:30:00+05:30' })
    const w = await mountPage()
    openAll()
    FakeSocket.all[0].serverPush(closedAnswer())
    await flushPromises()
    const c = cards(w)[0]
    expect(c.find('[data-testid="market-closed-text"]').exists()).toBe(false) // one banner per screen, not per card
    expect(w.findAll('[data-testid="market-closed-text"]')).toHaveLength(1)
    expect(w.find('[data-testid="market-closed-text"]').text()).toContain('29 Oct 2026, 15:30:00 IST')
    expect(c.find('[data-testid="live-spot-at"]').exists()).toBe(false)
    expect(c.find('[data-testid="live-leg-health"]').exists()).toBe(false)
    expect(c.find('[data-testid="live-leg-health-reason"]').exists()).toBe(false)
    expect(c.text()).not.toContain('NIFTY26N0322950CE')
    expect(c.find('[data-testid="live-leg"]').text()).toContain('NIFTY 3 Nov 22950 CE')
    expect(c.find('[data-testid="live-max-profit"]').text()).toBe('+7,114')
    expect(c.find('[data-testid="live-max-loss"]').text()).toBe('−5,886')
    expect(c.find('[data-testid="live-breakevens"]').text()).toContain('22,688')
    expect(c.find('[data-testid="live-leg-ltp"]').text()).toBe('150.60')
  })

  it('market open + stale leg: unchanged (health word and sentence stay, level time shown, no banner)', async () => {
    const w = await mountPage()
    openAll()
    FakeSocket.all[0].serverPush(closedAnswer({ market_closed: false }))
    await flushPromises()
    const c = cards(w)[0]
    expect(c.find('[data-testid="market-closed-banner"]').exists()).toBe(false)
    expect(c.find('[data-testid="live-leg-health"]').text()).toBe('(stale)')
    expect(c.find('[data-testid="live-leg-health-reason"]').exists()).toBe(true)
    expect(c.find('[data-testid="live-spot-at"]').exists()).toBe(true)
  })

  it('a column with no value in the answer is omitted, never computed', async () => {
    const w = await mountPage()
    openAll()
    FakeSocket.all[0].serverPush(computed())
    await flushPromises()
    expect(cards(w)[0].text()).not.toContain('Planned entry')
    expect(cards(w)[0].text()).not.toContain('Lots')
  })
})

describe('AC-4: stale or unavailable data is marked, never shown as live', () => {
  it('AC-4 (RD-045): each health state is explained in one sentence with its reason; available shows none', async () => {
    const SENTENCES = [
      'Stale: the latest price for this contract is older than expected, so the figure may be out of date.',
      'Delayed: prices for this contract are arriving later than they should, so the figure may be behind the market.',
      'Unhealthy: the data for this contract looks wrong or incomplete, so do not rely on the figure.',
      'Unavailable: no price has been received for this contract, so no figure is shown.',
    ]
    const w = await mountPage()
    openAll()
    const states = ['stale', 'delayed', 'unhealthy', 'unavailable', 'available', null, 'weird']
    FakeSocket.all[0].serverPush(computed({ legs: states.map((h, i) => leg({ instrument_id: `NSE_FO:${2000 + i}`, symbol: `N${i}`, health: h })) }))
    await flushPromises()
    const legs = cards(w)[0].findAll('[data-testid="live-leg"]')
    const reason = (i) => legs[i].find('[data-testid="live-leg-health-reason"]')
    expect([0, 1, 2, 3].map((i) => reason(i).text())).toEqual(SENTENCES)
    expect(reason(4).exists()).toBe(false)
    expect(reason(5).text()).toBe(SENTENCES[3])
    expect(reason(6).text()).toBe('The health of the data for this contract is not known, so the figure may not be current.')
  })

  it('AC-4: a leg whose health is not available shows its health word; an available leg shows none', async () => {
    const w = await mountPage()
    openAll()
    FakeSocket.all[0].serverPush(computed({ legs: [leg({ health: 'stale' }), leg({ instrument_id: 'NSE_FO:1002', symbol: 'NIFTY2', health: 'available' }),
      leg({ instrument_id: 'NSE_FO:1003', symbol: 'NIFTY3', health: null })] }))
    await flushPromises()
    const legs = cards(w)[0].findAll('[data-testid="live-leg"]')
    expect(legs[0].find('[data-testid="live-leg-health"]').text()).toBe('(stale)')
    expect(legs[1].find('[data-testid="live-leg-health"]').exists()).toBe(false)
    expect(legs[2].find('[data-testid="live-leg-health"]').text()).toBe('(unavailable)')
  })

  it('AC-4: push values are rendered untouched (spot_level as the exact string)', async () => {
    const w = await mountPage()
    openAll()
    FakeSocket.all[0].serverPush(computed({ spot_level: '25123.45' }))
    await flushPromises()
    expect(cards(w)[0].find('[data-testid="live-spot"]').text()).toBe('25123.45')
    expect(cards(w)[0].find('[data-testid="live-leg-ltp"]').text()).toBe('39.15')
    expect(cards(w)[0].find('[data-testid="live-spot-at"]').text()).toBe('19 Oct 2026, 10:15:00 IST')
  })

  it('the spot line keeps a space between the level and "at" (whitespace condense must not glue them)', async () => {
    const w = await mountPage()
    openAll()
    FakeSocket.all[0].serverPush(computed({ spot_level: '25123.45' }))
    await flushPromises()
    const line = cards(w)[0].find('[data-testid="live-spot"]').element.parentElement.textContent
    expect(line).toContain('25123.45 at 19 Oct 2026, 10:15:00 IST')
  })

  it('REQ-133 AC-2: the card drops a push for an older strategy version and draws the current one', async () => {
    const w = await mountPage()
    openAll()
    const ws = FakeSocket.all[0]
    const current = JSON.parse(ws.sent.at(-1)).seq
    expect(Number.isInteger(current) && current >= 1).toBe(true)
    ws.serverPush(computed({ spot_level: '11111.11', seq: current - 1 })) // a late frame of the previous version
    await flushPromises()
    expect(cards(w)[0].find('[data-testid="live-spot"]').exists()).toBe(false)
    ws.serverPush(computed({ spot_level: '25123.45', seq: current }))
    await flushPromises()
    expect(cards(w)[0].find('[data-testid="live-spot"]').text()).toBe('25123.45')
    ws.serverPush(computed({ spot_level: '11111.11', seq: current - 1 }))
    await flushPromises()
    expect(cards(w)[0].find('[data-testid="live-spot"]').text()).toBe('25123.45') // never drawn over the current one
  })

  it('AC-4: spot_at null is shown as a dash, never the request time', async () => {
    const w = await mountPage()
    openAll()
    FakeSocket.all[0].serverPush(computed({ spot_at: null }))
    await flushPromises()
    expect(cards(w)[0].find('[data-testid="live-spot-at"]').text()).toBe('-')
  })

  it('AC-4: a REFUSED answer shows the server reason and is not paused', async () => {
    const w = await mountPage()
    openAll()
    FakeSocket.all[0].serverPush({ state: 'REFUSED', status_label: 'Refused label', reason: 'Because the server said so', answered_at: '2026-10-19T10:15:01+05:30' })
    await flushPromises()
    const c = cards(w)[0]
    expect(c.find('[data-testid="live-reason"]').text()).toBe('Because the server said so')
    expect(c.find('[data-testid="live-paused-badge"]').exists()).toBe(false)
    expect(c.find('[data-testid="live-spot"]').exists()).toBe(false)
  })

  it('AC-4: a strategy whose detail fails shows the server error; the other card still loads', async () => {
    failDetailFor = new Set([1])
    const w = await mountPage()
    openAll()
    FakeSocket.all[0].serverPush(computed())
    await flushPromises()
    expect(cards(w)[0].find('[data-testid="live-error-what"]').text()).toBe('Server says draft 1 failed')
    expect(cards(w)[1].find('[data-testid="live-spot"]').text()).toBe('25123.45')
  })

  it('issue #500: a strategy with a leg no longer live shows that reason, opens no socket, sends no outcome', async () => {
    notLiveFor = new Set([1])
    listAnswer = { strategies: [row(1)] }
    const w = await mountPage()
    const label = cards(w)[0].find('[data-testid="live-status-label"]')
    expect(label.attributes('data-not-live')).toBe('true')
    expect(label.text()).toBe(LEG_NOT_LIVE_LABEL)
    expect(label.text()).not.toBe(NOT_CONNECTED_LABEL)
    expect(FakeSocket.all).toHaveLength(0)
    expect(posts).toHaveLength(0)
  })

  it('REQ-077 AC-9: a strategy with one priced leg and one unpriced leg is unpriced and paused, never followed, shows no figure', async () => {
    partlyPricedFor = new Set([1])
    listAnswer = { strategies: [row(1)] }
    const w = await mountPage()
    const card = cards(w)[0]
    expect(card.attributes('data-state')).toBe('unpriced')
    expect(card.find('[data-testid="live-paused-badge"]').exists()).toBe(true)
    expect(card.find('[data-testid="live-spot"]').exists()).toBe(false)
    expect(FakeSocket.all).toHaveLength(0)
    expect(posts).toHaveLength(0)
  })
})

describe('AC-5: the disconnect message is the server\'s', () => {
  it('AC-5: onDown asks the REST outcome route (fallback true) and renders its label verbatim', async () => {
    const w = await mountPage()
    openAll()
    FakeSocket.all[0].serverPush(computed())
    await flushPromises()
    FakeSocket.all[0].serverClose()
    await flushPromises()
    expect(posts).toHaveLength(1)
    expect(posts[0].url).toBe('/strategies/outcome')
    expect(posts[0].body.fallback).toBe(true)
    const c = cards(w)[0]
    expect(c.find('[data-testid="live-status-label"]').text()).toBe(SERVER_LABEL)
    expect(c.find('[data-testid="live-spot"]').exists()).toBe(false) // no number shown as live
  })

  it('REQ-049 AC-5 + REQ-077 AC-9: a FROM_ENTRIES answer after the drop shows both server labels, stays paused, shows no figure', async () => {
    postAnswer = fromEntries()
    const w = await mountPage()
    openAll()
    FakeSocket.all[0].serverPush(computed())
    await flushPromises()
    FakeSocket.all[0].serverClose()
    await flushPromises()
    const c = cards(w)[0]
    expect(c.find('[data-testid="live-status-label"]').text()).toBe(SERVER_LABEL)
    expect(c.find('[data-testid="live-output-label"]').text()).toBe(FROM_YOUR_PRICES)
    expect(c.attributes('data-paused')).toBe('true')
    expect(c.find('[data-testid="live-paused-badge"]').exists()).toBe(true)
    expect(c.find('[data-testid="live-health-dot"]').attributes('data-health')).toBe('unknown')
    for (const id of ['live-spot', 'live-leg', 'live-leg-ltp', 'live-max-profit']) expect(c.find(`[data-testid="${id}"]`).exists()).toBe(false)
  })

  it('a FROM_ENTRIES push (an ended session) is accepted and the card shows it paused', async () => {
    const w = await mountPage()
    FakeSocket.all[0].serverOpen()
    FakeSocket.all[0].serverPush(fromEntries())
    await flushPromises()
    const c = cards(w)[0]
    expect(c.find('[data-testid="live-status-label"]').text()).toBe(SERVER_LABEL)
    expect(c.find('[data-testid="live-output-label"]').text()).toBe(FROM_YOUR_PRICES)
    expect(c.attributes('data-paused')).toBe('true')
    expect(c.find('[data-testid="live-spot"]').exists()).toBe(false)
  })

  it('ADR-168: neither the socket body nor the REST fallback body a live card sends carries a level key', async () => {
    const LEVEL_KEY = ['ux', 'level'].join('_')
    const w = await mountPage()
    openAll()
    expect(JSON.parse(FakeSocket.all[0].sent[0])).not.toHaveProperty(LEVEL_KEY)
    FakeSocket.all[0].serverPush(computed())
    await flushPromises()
    FakeSocket.all[0].serverClose()
    await flushPromises()
    expect(posts).toHaveLength(1)
    expect(posts[0].body).not.toHaveProperty(LEVEL_KEY)
    expect(w.exists()).toBe(true)
  })

  it('AC-5: the page source writes no copy of the disconnect sentence', async () => {
    const { readFileSync } = await import('node:fs')
    for (const f of ['src/pages/LiveStrategiesPage.vue', 'src/components/live/LiveStrategyCard.vue']) {
      expect(readFileSync(f, 'utf8')).not.toMatch(/disconnected|Last updated/i)
    }
  })

  it('AC-5: a REST fallback that fails leaves no old number on screen', async () => {
    postAnswer = () => Promise.reject({ parts: { what_happened: 'REST failed', impact: 'i', what_is_blocked: 'b', next_action: 'n' } })
    const w = await mountPage()
    openAll()
    FakeSocket.all[0].serverPush(computed())
    await flushPromises()
    FakeSocket.all[0].serverClose()
    await flushPromises()
    expect(cards(w)[0].find('[data-testid="live-spot"]').exists()).toBe(false)
    expect(cards(w)[0].find('[data-testid="live-error-what"]').text()).toBe('REST failed')
  })
})

describe('AC-6: monitoring is paused per strategy', () => {
  it('AC-6: two cards, one NOT_CONNECTED and one live, show independent badges and dots', async () => {
    const w = await mountPage()
    await answerNext(notConnected())
    await answerNext(computed())
    const [a, b] = cards(w)
    expect(a.find('[data-testid="live-paused-badge"]').text()).toBe('⏸ Monitoring paused')
    expect(a.find('[data-testid="live-health-dot"]').text()).toBe('Health unknown')
    expect(a.find('[data-testid="live-status-label"]').text()).toBe(SERVER_LABEL)
    expect(b.find('[data-testid="live-paused-badge"]').exists()).toBe(false)
    expect(b.find('[data-testid="live-health-dot"]').exists()).toBe(false)
    expect(b.find('[data-testid="live-spot"]').text()).toBe('25123.45')
  })

  it('AC-4: a card whose socket is reconnecting is paused before the REST answer arrives; old figures carry no live look', async () => {
    postAnswer = () => new Promise(() => {}) // the REST fallback is held back
    const w = await mountPage()
    await answerNext(computed())
    expect(cards(w)[0].find('[data-testid="live-spot"]').exists()).toBe(true)
    FakeSocket.all[0].serverClose()
    await flushPromises()
    await new Promise((r) => setTimeout(r, 1300)) // the backoff reopens a socket: status 'connecting', nothing live yet
    await flushPromises()
    const c = cards(w)[0]
    expect(c.attributes('data-live')).toBe('connecting')
    expect(c.attributes('data-paused')).toBe('true')
    expect(c.find('[data-testid="live-paused-badge"]').exists()).toBe(true)
    expect(c.find('[data-testid="live-health-dot"]').exists()).toBe(true)
    expect(c.find('[data-testid="live-spot"]').exists()).toBe(false)
    expect(c.find('[data-testid="live-legs"]').exists()).toBe(false)
  })

  it('AC-4: the very first connect, before any answer, is waiting and not paused', async () => {
    const w = await mountPage()
    const c = cards(w)[0]
    expect(c.attributes('data-live')).toBe('connecting')
    expect(c.attributes('data-paused')).toBe('false')
    expect(c.find('[data-testid="live-waiting"]').exists()).toBe(true)
  })

  it('AC-6: a socket that drops pauses only its own card', async () => {
    postAnswer = () => new Promise(() => {}) // the REST answer never arrives: the badge comes from the socket state alone
    const w = await mountPage()
    await answerNext(computed())
    await answerNext(computed())
    FakeSocket.all[1].serverClose()
    await flushPromises()
    const [a, b] = cards(w)
    expect(a.attributes('data-paused')).toBe('false')
    expect(b.attributes('data-paused')).toBe('true')
    expect(b.find('[data-testid="live-paused-badge"]').exists()).toBe(true)
  })
})

describe('page lifecycle', () => {
  it('AC-5: every socket is closed on unmount, and a push after unmount is ignored', async () => {
    const w = await mountPage()
    await answerNext(computed())
    openAll()
    expect(FakeSocket.all).toHaveLength(2)
    const first = FakeSocket.all[0]
    w.unmount()
    expect(FakeSocket.all.every((s) => s.closed)).toBe(true)
    first.serverPush(computed()) // must not throw or render
    await flushPromises()
    expect(posts).toHaveLength(0)
  })

  it('AC-4: no saved strategies shows one line pointing to the Strategy Builder and no card', async () => {
    listAnswer = { strategies: [] }
    const w = await mountPage()
    expect(cards(w)).toHaveLength(0)
    expect(w.find('[data-testid="live-empty"] a').attributes('href')).toBe('/strategy/builder')
  })

  it('AC-4: 25 strategies show the 20 most recently updated and say so', async () => {
    listAnswer = { strategies: [...Array(25).keys()].map((i) => row(i + 1, `2026-10-${String(i + 1).padStart(2, '0')}T10:00:00+05:30`)) }
    const w = await mountPage()
    expect(cards(w)).toHaveLength(20)
    expect(w.find('[data-testid="live-capped"]').text()).toBe('Showing the 20 most recent')
    const ids = cards(w).map((c) => Number(c.attributes('data-strategy-id')))
    expect(ids).not.toContain(1)
    expect(ids).toContain(25)
  })

  it('AC-4: the page has no order or execute control (ADR-002)', async () => {
    const w = await mountPage()
    expect(w.find('button').exists()).toBe(false)
    expect(w.html()).not.toMatch(/\/execute/i)
  })
})

const many = (n) => ({ strategies: [...Array(n).keys()].map((i) => row(i + 1, `2026-10-${String(i + 1).padStart(2, '0')}T10:00:00+05:30`)) })

describe('start queue: one card loading at a time (F-45, db-role-limit-below-pool-size)', () => {
  it('AC-4: 13 strategies - one detail GET before the first card answers; the second starts after it', async () => {
    listAnswer = many(13)
    const w = await mountPage()
    expect(detailGets).toEqual([13]) // newest first, only one in flight
    expect(FakeSocket.all).toHaveLength(1)
    expect(w.findAll('[data-testid="live-queued"]')).toHaveLength(12)
    await answerNext(computed())
    expect(detailGets).toEqual([13, 12])
    for (let i = 0; i < 12; i++) await answerNext(computed())
    expect(detailGets).toHaveLength(13)
    expect(FakeSocket.all).toHaveLength(13)
    expect(w.findAll('[data-testid="live-queued"]')).toHaveLength(0)
  })

  it('AC-4: a card whose GET fails releases the queue', async () => {
    failDetailFor = new Set([2])
    listAnswer = { strategies: [row(2, '2026-10-19T11:00:00+05:30'), row(1)] }
    await mountPage()
    expect(detailGets).toEqual([2, 1])
  })

  it('AC-4: a card with no answer releases the queue after 8 s', async () => {
    vi.useFakeTimers()
    listAnswer = many(3)
    await mountPage()
    expect(detailGets).toEqual([3])
    await vi.advanceTimersByTimeAsync(7900)
    expect(detailGets).toEqual([3])
    await vi.advanceTimersByTimeAsync(200)
    expect(detailGets).toEqual([3, 2])
  })

  it('AC-4: unmount mid-queue opens no further sockets', async () => {
    vi.useFakeTimers()
    listAnswer = many(3)
    const w = await mountPage()
    w.unmount()
    await vi.advanceTimersByTimeAsync(30000)
    expect(FakeSocket.all).toHaveLength(1)
    expect(detailGets).toEqual([3])
  })

  it('ADR-299: running and draft strategies sit under two headings that are the status words, newest first', async () => {
    listAnswer = { strategies: [row(1, '2026-10-17T10:00:00+05:30'), { ...row(2, '2026-10-18T10:00:00+05:30'), has_order: true }, row(3, '2026-10-19T10:00:00+05:30')] }
    const w = await mountPage()
    const ex = w.find('[data-testid="live-group-executed"]')
    const dr = w.find('[data-testid="live-group-drafts"]')
    expect(ex.find('h2').text()).toBe('Running')
    expect(dr.find('h2').text()).toBe('Draft')
    expect(ex.findAll('[data-testid="live-strategy-card"]').map((c) => c.attributes('data-strategy-id'))).toEqual(['2'])
    expect(dr.findAll('[data-testid="live-strategy-card"]').map((c) => c.attributes('data-strategy-id'))).toEqual(['3', '1'])
  })

  it('AC-4: an empty group is not shown', async () => {
    const w = await mountPage()
    expect(w.find('[data-testid="live-group-executed"]').exists()).toBe(false)
    expect(w.find('[data-testid="live-group-drafts"]').exists()).toBe(true)
  })
})

describe('REQ-134 reader sweep: the card title is the strategy name (quoted user words, shown without the API quotes)', () => {
  it('a named row shows its name as text, then the underlying; a row without a name (older server) keeps "Draft <id>"', async () => {
    listAnswer = { strategies: [{ ...row(1), name: '"<b>NIFTY</b> Oct condor"' }, row(2)] }
    const w = await mountPage()
    const titles = w.findAll('[data-testid="live-strategy-title"]').map((x) => x.text())
    expect(titles).toContain('<b>NIFTY</b> Oct condor (#1), NIFTY') // ADR-330 (19): number added; this row has no first leg, so no expiry
    expect(titles).toContain('Draft 2, NIFTY')
    expect(w.find('[data-testid="live-strategy-title"] b').exists()).toBe(false)
  })
})

// ADR-299 + ADR-259, user test 2026-11-13 (#22, #77, N-3, X-1): status words and what Live Strategies lists.
describe('issue 16: status words and closed trades on Live Strategies', () => {
  it('a fully closed trade is absent; Draft and Running cards carry the one set of words, never "Waiting to start"', async () => {
    listAnswer = { strategies: [row(1, '2026-10-17T10:00:00+05:30'), { ...row(2, '2026-10-18T10:00:00+05:30'), status: 'closed', has_order: true },
      { ...row(3, '2026-10-19T10:00:00+05:30'), has_order: true }] }
    const w = await mountPage()
    expect(w.find('[data-strategy-id="2"]').exists()).toBe(false)
    expect(w.find('[data-strategy-id="1"] [data-testid="live-strategy-status"]').text()).toBe('Draft')
    expect(w.find('[data-strategy-id="3"] [data-testid="live-strategy-status"]').text()).toBe('Running')
    expect(w.text()).not.toContain('Waiting to start')
    expect(detailGets).not.toContain(2) // a completed trade starts no card and no socket
  })
  it('only closed trades: no card, and the page does not say "No saved strategies yet"; it says nothing is running and where completed trades are', async () => {
    listAnswer = { strategies: [{ ...row(2), status: 'closed', has_order: true }] }
    const w = await mountPage()
    expect(cards(w)).toHaveLength(0)
    expect(FakeSocket.all).toHaveLength(0)
    expect(w.text()).not.toContain('No saved strategies yet')
    expect(w.get('[data-testid="live-empty"]').text()).toContain('Nothing is running')
    expect(w.get('[data-testid="live-empty"] a').attributes('href')).toBe('/strategies/completed-strategies')
  })
  it('an unknown server status is listed (never hidden), with the "not available" words, and followed as a plan', async () => {
    listAnswer = { strategies: [{ ...row(4), status: 'weird' }] }
    const w = await mountPage()
    expect(w.get('[data-strategy-id="4"] [data-testid="live-strategy-status"]').text()).toBe('Status not available')
  })
  it('a REAL trade (has_order, no practice book): no error state; it follows its saved legs and says "as saved"', async () => {
    realOnly.add(8)
    listAnswer = { strategies: [{ ...row(8), has_order: true }] }
    const w = await mountPage()
    openAll()
    expect(paperGets).toEqual([8])
    expect(detailGets).toContain(8)
    const c = w.get('[data-strategy-id="8"]')
    expect(c.attributes('data-state')).not.toBe('error')
    expect(c.get('[data-testid="live-strategy-status"]').text()).toBe('Running')
    expect(c.get('[data-testid="live-legs-as-saved"]').text()).toBe('Legs as saved')
    expect(JSON.parse(FakeSocket.all[0].sent[0]).legs).toHaveLength(1)
  })
  it('D-40: a running trade whose open legs are all on expired contracts shows the server\'s plain reason, not an error', async () => {
    expiredBook.add(9)
    listAnswer = { strategies: [{ ...row(9), has_order: true }] }
    const w = await mountPage()
    openAll()
    await flushPromises()
    const c = w.get('[data-strategy-id="9"]')
    expect(c.attributes('data-state')).toBe('unpriced')
    expect(c.text()).toContain(EXPIRED_LINE)
    expect(c.text()).not.toContain('Something went wrong')
    expect(FakeSocket.all.every((s) => s.sent.length === 0)).toBe(true) // nothing is priced: no outcome follow
  })
  it('D-40 r2: a book with a not-live leg that has NOT expired and an unreadable catalogue still shows the error', async () => {
    unreadableBook.add(9)
    listAnswer = { strategies: [{ ...row(9), has_order: true }] }
    const w = await mountPage()
    openAll()
    await flushPromises()
    const c = w.get('[data-strategy-id="9"]')
    expect(c.attributes('data-state')).toBe('error')
    expect(c.text()).not.toContain('No price for')
  })
  it('D-40 r2: an expired trade shows only the expiry sentence, never the book\'s pause reason', async () => {
    expiredBook.add(9)
    expiredNoLine = true // the server sent no expiry sentence: nothing else is borrowed in its place
    listAnswer = { strategies: [{ ...row(9), has_order: true }] }
    const w = await mountPage()
    openAll()
    await flushPromises()
    const c = w.get('[data-strategy-id="9"]')
    expect(c.attributes('data-state')).toBe('unpriced')
    expect(c.text()).not.toContain(EXPIRED_REASON)
  })
  it('a partly closed running trade follows the legs it holds NOW (the book), not the legs it was saved with', async () => {
    listAnswer = { strategies: [{ ...row(7), has_order: true }] }
    const w = await mountPage()
    expect(paperGets).toEqual([7])
    expect(detailGets).not.toContain(7)
    openAll()
    const sent = JSON.parse(FakeSocket.all[0].sent[0])
    expect(sent.legs).toHaveLength(1)
    expect(sent.legs[0]).toMatchObject({ action: 'SELL', lots: 1, planned_entry: '88.50' })
    expect(w.find('[data-strategy-id="7"]').exists()).toBe(true)
  })
})

// GC-MU A3 (ADR-230 (2)): the server's mark words reach the card; none at 0 or unread; the link names the strategy.
describe('GC-MU A3: the adjustment opportunities mark', () => {
  const marked = (id, count, text) => ({ ...row(id), open_opportunities: count, open_opportunities_text: text })
  it('0 and unread show no mark; 1 and 3 show the server words; the link carries the strategy id', async () => {
    listAnswer = { strategies: [marked(1, 0, null), marked(2, 1, '1 adjustment opportunity'), marked(3, 3, '3 adjustment opportunities'), marked(4, null, null)] }
    const w = await mountPage()
    const byId = (id) => w.find(`[data-strategy-id="${id}"]`)
    expect(byId(1).find('[data-testid="live-opportunity-mark"]').exists()).toBe(false)
    expect(byId(4).find('[data-testid="live-opportunity-mark"]').exists()).toBe(false)
    expect(byId(2).find('[data-testid="live-opportunity-mark"]').text()).toBe('1 adjustment opportunity')
    const three = byId(3).find('[data-testid="live-opportunity-mark"]')
    expect(three.text()).toBe('3 adjustment opportunities')
    expect(three.attributes('href')).toBe('/positions/adjustment-opportunities?strategy=3')
  })
})

// ADR-330 (56) round 2: ONE notice at the top; tiles greyed with no sentence of their own; exactly one affected: only it carries the line
describe('ADR-330 (56): price notice and cards', () => {
  const down = { state: 'NOT_CONNECTED', market_closed: false, last_price_at: '2026-10-19T04:28:01Z', indices: [] }
  it('two strategies with no price and the feed down: one page notice, greyed cards, no per-card sentence', async () => {
    notLiveFor = new Set([1, 2])
    indicesAnswer = down
    listAnswer = { strategies: [row(1), row(2)] }
    const w = await mountPage()
    expect(w.findAll('[data-testid="price-notice"]')).toHaveLength(1)
    expect(w.get('[data-testid="price-notice-text"]').text()).toBe('Prices are not live. Figures are as of 09:58:01 IST.')
    for (const c of cards(w)) {
      expect(c.find('[data-testid="live-status-label"]').exists()).toBe(false)
      expect(c.classes()).toContain('price-greyed')
    }
  })
  it('exactly one strategy with no price: no page notice, only that card carries the line', async () => {
    notLiveFor = new Set([1])
    indicesAnswer = down
    listAnswer = { strategies: [row(1), row(2)] }
    const w = await mountPage()
    expect(w.find('[data-testid="price-notice"]').exists()).toBe(false)
    const c1 = w.get('[data-strategy-id="1"]')
    const c2 = w.get('[data-strategy-id="2"]')
    expect(c1.get('[data-testid="live-status-label"]').text()).toBe(LEG_NOT_LIVE_LABEL)
    expect(c1.classes()).toContain('price-greyed')
    expect(c2.classes()).not.toContain('price-greyed')
  })
})
