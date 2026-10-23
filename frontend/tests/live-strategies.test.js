// W-113 (REQ-049 AC-4, AC-5, AC-6; ADR-008, ADR-077): the Live Strategies page, with a fake socket per card and a mocked
// API. Expected texts come from the pushes and answers the test hands in; the page must show them untouched.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

const posts = []
let listAnswer
let postAnswer
let failDetailFor = new Set()
let notLiveFor = new Set() // issue #500: drafts whose leg's stored contract is no longer live
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const get = (url) => {
    if (url === '/strategies') return typeof listAnswer === 'function' ? listAnswer() : Promise.resolve({ data: listAnswer })
    const detail = /^\/strategies\/(\d+)$/.exec(url)
    if (detail) {
      const id = Number(detail[1])
      detailGets.push(id)
      if (failDetailFor.has(id)) return Promise.reject({ parts: { what_happened: `Server says draft ${id} failed`, impact: 'i', what_is_blocked: 'b', next_action: 'n' } })
      return Promise.resolve({ data: { id, definition: { underlying: 'NIFTY', legs: [{ contract_id: id, ...(notLiveFor.has(id) ? { contract_state: 'token_reassigned', exchange_segment: null, exchange_token: null } : { contract_state: 'live', exchange_segment: 'NSE_FO', exchange_token: 1000 + id }),
        action: 'SELL', instrument: 'CE', strike: '22800', expiry: '2026-10-13', quantity: 65, planned_entry: '100.00', captured_at: '2026-10-08T09:20:09+05:30' }] } } })
    }
    const cat = /^\/catalogue\/NIFTY\/contracts/.exec(url)
    if (cat) {
      return Promise.resolve({ data: { contracts: [...Array(40).keys()].map((i) => ({ contract_id: i + 1, exchange_segment: 'NSE_FO', exchange_token: 1001 + i,
        instrument_type: 'CE', expiry: '2026-10-13', strike: '22800.00', lot_size: 65, symbol: `NIFTY${i + 1}` })) } })
    }
    return Promise.reject(new Error(`unmocked get ${url}`))
  }
  const post = (url, body) => {
    posts.push({ url, body })
    return typeof postAnswer === 'function' ? postAnswer(body) : Promise.resolve({ data: postAnswer })
  }
  return { ...actual, default: { get, post } }
})
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
  serverPush(obj) { this.onmessage?.({ data: JSON.stringify(obj) }) }
  serverClose() { this.readyState = 3; this.onclose?.() }
}

const row = (id, updated = '2026-10-19T10:00:00+05:30') => ({ id, underlying: 'NIFTY', status: 'draft', created_at: updated, updated_at: updated })
const leg = (over = {}) => ({ instrument_id: 'NSE_FO:1001', symbol: 'NIFTY1', action: 'SELL', ltp: '39.15', health: 'available', label: null, ...over })
const computed = (over = {}) => ({ state: 'COMPUTED', underlying: 'NIFTY', status_label: null, reason: null, output_label: null,
  spot_level: '25123.45', spot_at: '2026-10-19T10:15:00+05:30', answered_at: '2026-10-19T10:15:01+05:30',
  summary: { max_profit: '0.00', max_loss: '13000.00', max_profit_unlimited: false, max_loss_unlimited: false }, legs: [leg()], ...over })
const SERVER_LABEL = 'Server wrote this not-live sentence 10:15:00 AM'
const notConnected = () => ({ state: 'NOT_CONNECTED', status_label: SERVER_LABEL, reason: null, answered_at: '2026-10-19T10:16:00+05:30', legs: [], spot_level: null, spot_at: null })

async function mountPage() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }, { path: '/strategy/builder', component: { template: '<div/>' } }] })
  router.push('/')
  await router.isReady()
  const w = mount(LiveStrategiesPage, { global: { plugins: [router] } })
  await flushPromises()
  return w
}
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

beforeEach(() => {
  FakeSocket.all = []
  posts.length = 0
  detailGets.length = 0
  vi.useRealTimers()
  vi.spyOn(Math, 'random').mockReturnValue(0) // no reconnect spread here: it has its own tests (reconnect-forever.test.js)
  failDetailFor = new Set()
  notLiveFor = new Set()
  listAnswer = { strategies: [row(1), row(2)] }
  postAnswer = notConnected()
  global.WebSocket = FakeSocket
})
afterEach(() => vi.restoreAllMocks())

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

  it('AC-4: executed and draft strategies sit under two headings, newest first', async () => {
    listAnswer = { strategies: [row(1, '2026-10-17T10:00:00+05:30'), { ...row(2, '2026-10-18T10:00:00+05:30'), status: 'executed' }, row(3, '2026-10-19T10:00:00+05:30')] }
    const w = await mountPage()
    const ex = w.find('[data-testid="live-group-executed"]')
    const dr = w.find('[data-testid="live-group-drafts"]')
    expect(ex.find('h2').text()).toBe('Executed')
    expect(dr.find('h2').text()).toBe('Saved drafts (live prices)')
    expect(ex.findAll('[data-testid="live-strategy-card"]').map((c) => c.attributes('data-strategy-id'))).toEqual(['2'])
    expect(dr.findAll('[data-testid="live-strategy-card"]').map((c) => c.attributes('data-strategy-id'))).toEqual(['3', '1'])
  })

  it('AC-4: an empty group is not shown', async () => {
    const w = await mountPage()
    expect(w.find('[data-testid="live-group-executed"]').exists()).toBe(false)
    expect(w.find('[data-testid="live-group-drafts"]').exists()).toBe(true)
  })
})
