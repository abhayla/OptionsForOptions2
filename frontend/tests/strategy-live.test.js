// W-065 (REQ-035 AC-4; ADR-068 (2), ADR-077, ADR-008): the live socket lifecycle, with a fake socket and fake timers.
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { echoSeq } from './helpers/echoSeq'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

const apiCalls = []
const readCalls = []
// the recorded condor's own strike, type and expiry for a leg (the read reply names them; the browser never invents them)
let legFacts = () => ({})
let apiAnswer = null
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: () => Promise.reject(new Error('unmocked get')),
    post: (url, body, opts) => {
      // The read control (REQ-076 AC-8) is its own request: it is recorded apart (readCalls) and answered with the legs as sent,
      // in the real LegEditOut shape, so the tests below keep counting OUTCOME requests only. A test that sets a function
      // answer handles every request itself.
      if (url === '/strategies/leg-edit' && typeof apiAnswer !== 'function') {
        readCalls.push({ url, body })
        return Promise.resolve({ data: { legs: body.legs.map((l) => ({ ...l, ...legFacts(l.instrument_id), price_source: 'captured', hedge: false, block: null })),
          shape: null, shape_name: null, outcome: null } })
      }
      apiCalls.push({ url, body, opts })
      return typeof apiAnswer === 'function' ? apiAnswer(body, url, opts) : Promise.resolve({ data: apiAnswer })
    } } }
})
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import StrategyActions from '@/components/strategy/StrategyActions.vue'
import ScenarioControls from '@/components/strategy/ScenarioControls.vue'
import LegList from '@/components/strategy/LegList.vue'
import { EXECUTE_WAITS_FOR_LATEST } from '@/lib/legEdit'
import real from './fixtures/outcome-condor.json'
legFacts = (id) => { const l = real.legs.find((x) => x.instrument_id === id); return { instrument: l.instrument, strike: l.strike, expiry: l.expiry } }
import { INDEX_LIVE_PATH } from '@/composables/useIndexLive'
import { BASE_DELAY_MS, FAST_ATTEMPTS, LIVE_PATH, MAX_DELAY_MS, backoffDelay, createLiveSocket, isCurrentVersion, isOutcome, liveUrl } from '@/composables/useStrategyLive'

class FakeSocket {
  static all = [] // the strategy socket(s) only
  static index = [] // the builder header's read-only index socket (/api/market/indices/live): its own URL, its own list
  constructor(url) {
    this.url = url
    this.sent = []
    this.readyState = 0
    this.closed = false
    this.isIndex = String(url).endsWith(INDEX_LIVE_PATH)
    ;(this.isIndex ? FakeSocket.index : FakeSocket.all).push(this)
  }
  send(text) {
    // a frame the server could not parse fails the test loudly; the index socket sends nothing at all
    if (this.isIndex) throw new Error(`the index socket must send nothing, it sent ${String(text)}`)
    JSON.parse(text)
    this.sent.push(text)
  }
  close() {
    this.closed = true
    this.readyState = 3
  }
  // test drivers
  serverOpen() {
    this.readyState = 1
    this.onopen?.()
  }
  serverPush(obj) {
    this.onmessage?.({ data: typeof obj === 'string' ? obj : JSON.stringify(echoSeq(this, obj)) })
  }
  serverClose() {
    this.readyState = 3
    this.onclose?.()
  }
}

// A push as the server sends it: values are display strings already (the browser never computes them).
const push = (ltp, pnl) => ({ state: 'COMPUTED', legs: [{ instrument_id: 'NSE_FO:44626', ltp, label: null }],
  table: { rows: [{ row_id: '1', cells: { ltp: { display: `₹${ltp}` }, unrealized_pnl: { display: pnl } } }] } })
const BODY = { underlying: 'NIFTY', legs: [{ instrument_id: 'NSE_FO:44626', action: 'SELL', lots: 1 }] }

function rig() {
  const pushes = []
  const others = []
  const statuses = []
  const onDown = vi.fn()
  const live = createLiveSocket({ url: 'ws://app.test/api/strategies/live', WebSocketImpl: FakeSocket,
    onPush: (b) => pushes.push(b), onMessage: (m) => others.push(m), onDown, onStatus: (s) => statuses.push(s) })
  return { live, pushes, others, statuses, onDown }
}

beforeEach(() => {
  FakeSocket.all = []
  FakeSocket.index = []
  vi.useFakeTimers()
  vi.spyOn(Math, 'random').mockReturnValue(0) // no spread here: the spread has its own tests (reconnect-forever.test.js)
})
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks() })

describe('AC-4: the Builder live socket', () => {
  it('AC-4: sends the strategy on open and hands every push over untouched (no maths in the browser)', () => {
    const { live, pushes, statuses } = rig()
    live.follow(BODY)
    const ws = FakeSocket.all[0]
    expect(ws.url).toBe('ws://app.test/api/strategies/live')
    ws.serverOpen()
    expect(ws.sent).toEqual([JSON.stringify(BODY)])
    const a = push('30.05', '₹4,546.75')
    const b = push('29.60', '₹4,576.00')
    ws.serverPush(a)
    ws.serverPush(b)
    expect(pushes).toEqual([a, b]) // deep-equal to what the server sent: nothing added, nothing recomputed
    expect(statuses).toEqual(['connecting', 'live', 'live'])
  })

  it('AC-4: a message that is not an outcome never reaches the numbers; unparsable text is ignored', () => {
    const { live, pushes, others } = rig()
    live.follow(BODY)
    const ws = FakeSocket.all[0]
    ws.serverOpen()
    const err = { what_happened: 'x', impact: 'y', what_is_blocked: 'z', next_action: 'w' }
    ws.serverPush(err)
    ws.serverPush('not json')
    ws.serverPush({ state: 'MADE_UP' })
    expect(pushes).toEqual([])
    expect(others).toEqual([err, { state: 'MADE_UP' }])
    expect(isOutcome({ state: 'NOT_CONNECTED' })).toBe(true)
    expect(isOutcome(null)).toBe(false)
  })

  it('AC-4: a changed strategy is sent on the open socket; an unchanged one sends nothing', () => {
    const { live } = rig()
    live.follow(BODY)
    const ws = FakeSocket.all[0]
    ws.serverOpen()
    live.follow({ ...BODY })
    expect(ws.sent.length).toBe(1)
    live.follow({ ...BODY, legs: [{ ...BODY.legs[0], lots: 2 }] })
    expect(ws.sent.length).toBe(2)
    expect(JSON.parse(ws.sent[1]).legs[0].lots).toBe(2)
    expect(FakeSocket.all.length).toBe(1)
  })

  it('REQ-133 AC-2: a versioned socket sends seq = its own counter, bumped once per changed body, and draws only that version', () => {
    const pushes = []
    const live = createLiveSocket({ url: 'ws://x', onPush: (m) => pushes.push(m), versioned: true, WebSocketImpl: FakeSocket })
    live.follow(BODY)
    const ws = FakeSocket.all[0]
    ws.serverOpen()
    expect(JSON.parse(ws.sent[0])).toEqual({ ...BODY, seq: 1 })
    live.follow({ ...BODY }) // unchanged: nothing sent, the version stays
    expect(ws.sent.length).toBe(1)
    live.follow({ ...BODY, legs: [{ ...BODY.legs[0], lots: 2 }] })
    expect(JSON.parse(ws.sent[1]).seq).toBe(2)
    expect(live.version()).toBe(2)
    ws.serverPush({ ...push('30.05', '₹1'), seq: 1 }) // v1 arriving after v2 was sent
    ws.serverPush(push('30.10', '₹2')) // the fake echoes v2
    expect(pushes.map((p) => p.seq)).toEqual([2])
    expect(isCurrentVersion({ seq: 3 }, 2)).toBe(false) // a seq never sent is not current either
    expect(isCurrentVersion({}, 0)).toBe(true) // no version sent, none echoed: the old behaviour
    expect(isCurrentVersion({}, 1)).toBe(false)
  })

  it('AC-4: a drop calls the REST fallback and reconnects with backoff; pushes resume on the new socket', () => {
    const { live, pushes, statuses, onDown } = rig()
    live.follow(BODY)
    FakeSocket.all[0].serverOpen()
    FakeSocket.all[0].serverPush(push('30.05', '₹1'))
    FakeSocket.all[0].serverClose()
    expect(onDown).toHaveBeenCalledTimes(1)
    expect(statuses.at(-1)).toBe('down')
    vi.advanceTimersByTime(BASE_DELAY_MS - 1)
    expect(FakeSocket.all.length).toBe(1) // not before the delay
    vi.advanceTimersByTime(1)
    expect(FakeSocket.all.length).toBe(2)
    const ws2 = FakeSocket.all[1]
    ws2.serverOpen()
    expect(ws2.sent).toEqual([JSON.stringify(BODY)]) // the strategy is sent again
    ws2.serverPush(push('29.60', '₹2'))
    expect(pushes.length).toBe(2)
    expect(statuses.at(-1)).toBe('live')
  })

  it('AC-4 / REQ-113 AC-2: 1 s apart for the first 30 attempts, then doubles to the cap, and never stops (REQ-113 AC-11)', () => {
    expect([1, 2, 30, 31, 32, 33, 34, 35, 36].map(backoffDelay)).toEqual([1000, 1000, 1000, 2000, 4000, 8000, 16000, 30000, 30000])
    expect(backoffDelay(50)).toBe(MAX_DELAY_MS)
    const { live, statuses, onDown } = rig()
    live.follow(BODY)
    const TOTAL = FAST_ATTEMPTS + 10 // the old give-up point
    for (let i = 0; i < TOTAL + 3; i++) {
      FakeSocket.all.at(-1).serverClose()
      vi.advanceTimersByTime(MAX_DELAY_MS)
    }
    expect(FakeSocket.all.length).toBe(1 + TOTAL + 3) // the first socket plus every retry, past the old limit
    expect(statuses.at(-1)).toBe('connecting')
    expect(statuses).not.toContain('off')
    expect(onDown).toHaveBeenCalledTimes(TOTAL + 3) // every drop still asked REST
  })

  it('AC-4: a fallback that calls follow() again opens no socket outside the backoff', () => {
    const pushes = []
    let live
    live = createLiveSocket({ url: 'ws://x/api/strategies/live', WebSocketImpl: FakeSocket, onPush: (b) => pushes.push(b),
      onDown: () => live.follow(BODY) })
    live.follow(BODY)
    FakeSocket.all[0].serverClose()
    expect(FakeSocket.all.length).toBe(1)
  })

  it('AC-4: stop() closes for good: no fallback, no reconnect', () => {
    const { live, onDown, statuses } = rig()
    live.follow(BODY)
    const ws = FakeSocket.all[0]
    ws.serverOpen()
    live.stop()
    expect(ws.closed).toBe(true)
    ws.serverClose()
    vi.advanceTimersByTime(MAX_DELAY_MS * 2)
    expect(onDown).not.toHaveBeenCalled()
    expect(FakeSocket.all.length).toBe(1)
    expect(statuses.at(-1)).toBe('off')
  })

  it('AC-4 / REQ-048 AC-5: the URL is same-origin with no query string or credential', () => {
    expect(liveUrl({ protocol: 'http:', host: '127.0.0.1:4175' })).toBe('ws://127.0.0.1:4175/api/strategies/live')
    expect(liveUrl({ protocol: 'https:', host: 'app.example' })).toBe('wss://app.example/api/strategies/live')
    expect(LIVE_PATH).not.toMatch(/[?#]/)
  })

  it('AC-4 (ADR-008): the composable and the page contain no arithmetic on a price or P&L value', () => {
    const src = readFileSync(resolve(__dirname, '../src/composables/useStrategyLive.js'), 'utf-8')
    for (const banned of ['parseFloat', 'Number(', 'toFixed', 'ltp *', 'pnl', 'planned_entry']) expect(src).not.toContain(banned)
    const page = readFileSync(resolve(__dirname, '../src/pages/StrategyBuilderPage.vue'), 'utf-8')
    for (const banned of ['parseFloat', 'Number(', 'toFixed']) expect(page).not.toContain(banned)
  })
})

// ---- W-065 phase 3 round 2 (ADR-077, REQ-049 AC-5): the fallback follows THIS page's own socket --------------------------
// The COMPUTED answer is the real recorded condor outcome (tests/fixtures/outcome-condor.json); the not-live
// answer has the shape the server sends (NOT_CONNECTED, AC-5's text, no table, no ltp).
const AC5 = 'Live market data disconnected. Last updated: 09:20:09 AM. Live strategy monitoring is paused.'
const DRAFT = { underlying: 'NIFTY', legs: real.legs.map((l) => ({ instrument_id: l.instrument_id, action: l.action, lots: l.lots,
  planned_entry: l.planned_entry, captured_at: l.captured_at })) }
const NOT_LIVE = { ...real, state: 'NOT_CONNECTED', status_label: AC5, table: null, summary: null, payoff: null, scenario: null,
  leg_quotes: undefined, legs: real.legs.map((l) => ({ ...l, ltp: null, label: AC5 })) }
const COMPUTED = real
// The shape `_assert_from_entries_after_drop` (tests_app/test_strategy_live_push.py) checks: AC-5's text on the state,
// REQ-077 AC-9's label as the output label, the At Expiry table kept, no ltp, no leg_quotes.
const FROM_YOUR_PRICES = 'From your prices - no live data'
const FROM_ENTRIES = { ...real, state: 'FROM_ENTRIES', status_label: AC5, output_label: FROM_YOUR_PRICES, spot_level: null, spot_at: null,
  leg_quotes: undefined, legs: real.legs.map((l) => ({ ...l, ltp: null, iv: null, health: null })),
  table: { ...real.table, spot_level: null, spot_at: null, output_label: FROM_YOUR_PRICES } }
const OTHER_STRATEGY = { ...real, legs: real.legs.map((l, i) => (i === 0 ? { ...l, lots: 2 } : l)) }

describe('W-065 p3 r2: the page asks for the not-live answer when its own socket is down', () => {
  async function openPage() {
    vi.stubGlobal('WebSocket', FakeSocket)
    apiCalls.length = 0
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
    await router.push({ path: '/strategy/builder', query: { draft: JSON.stringify(DRAFT) } })
    await router.isReady()
    const w = mount(StrategyBuilderPage, { global: { plugins: [router] } })
    await flushPromises()
    return w
  }
  const state = (w) => w.find('[data-testid="strategy-builder"]').attributes('data-state')
  const reconnect = () => {
    vi.advanceTimersByTime(MAX_DELAY_MS + 1)
    return FakeSocket.all.at(-1)
  }
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] }) // flushPromises needs the real microtask/immediate queue
  })

  it('ADR-168 attack 3: neither the REST request nor the socket body the builder sends carries a level key', async () => {
    apiAnswer = COMPUTED
    const w = await openPage()
    FakeSocket.all[0].serverOpen()
    expect(apiCalls.length).toBeGreaterThan(0)
    for (const c of apiCalls) expect(c.body).not.toHaveProperty(['ux', 'level'].join('_'))
    expect(JSON.parse(FakeSocket.all[0].sent[0])).not.toHaveProperty(['ux', 'level'].join('_'))
    w.unmount()
  })

  it('a normal load sends fallback false; the socket drop sends fallback true; the socket body never carries it', async () => {
    apiAnswer = COMPUTED
    const w = await openPage()
    expect(apiCalls.map((c) => c.body.fallback)).toEqual([false])
    const ws = FakeSocket.all[0]
    ws.serverOpen()
    expect(JSON.parse(ws.sent[0])).not.toHaveProperty('fallback')
    apiAnswer = NOT_LIVE
    ws.serverClose()
    await flushPromises()
    expect(apiCalls.map((c) => c.body.fallback)).toEqual([false, true])
    expect(state(w)).toBe('not-connected')
    expect(w.text()).toContain(AC5)
    w.unmount()
  })

  it('a push after the reconnect clears the flag: the next load is false again', async () => {
    apiAnswer = NOT_LIVE
    const w = await openPage()
    FakeSocket.all[0].serverOpen()
    FakeSocket.all[0].serverClose()
    await flushPromises()
    expect(apiCalls.at(-1).body.fallback).toBe(true)
    const second = reconnect()
    second.serverOpen()
    second.serverPush(COMPUTED)
    await flushPromises()
    expect(state(w)).toBe('computed')
    expect(w.find('[data-testid="recalculate"]').exists()).toBe(false) // REQ-135 AC-3: no manual refresh; the push above is the refresh
    expect(w.text()).not.toContain('ReCalculate')
    second.serverPush({ ...COMPUTED, legs: COMPUTED.legs.map((l) => ({ ...l, ltp: '41.00' })) })
    await flushPromises()
    expect(state(w)).toBe('computed')
    await w.vm.load() // what any later reload does (the old button called it): the flag was cleared by the push
    await flushPromises()
    expect(apiCalls.at(-1).body.fallback).toBe(false)
    w.unmount()
  })

  it('a push whose legs differ from the legs on screen is not applied; the matching one is', async () => {
    apiAnswer = NOT_LIVE
    const w = await openPage()
    expect(state(w)).toBe('not-connected')
    const ws = FakeSocket.all[0]
    ws.serverOpen()
    ws.serverPush(OTHER_STRATEGY)
    await flushPromises()
    expect(state(w)).toBe('not-connected')
    ws.serverPush({ ...COMPUTED, legs: COMPUTED.legs.map((l, i) => (i === 1 ? { ...l, planned_entry: '101.00' } : l)) })
    await flushPromises()
    expect(state(w)).toBe('not-connected')
    ws.serverPush({ ...COMPUTED, legs: [...COMPUTED.legs].reverse() }) // same legs, other order = another strategy as sent
    await flushPromises()
    expect(state(w)).toBe('not-connected')
    ws.serverPush(COMPUTED)
    await flushPromises()
    expect(state(w)).toBe('computed')
    w.unmount()
  })

  it('REQ-133 AC-2: a push for an older strategy version is dropped by the Builder even when its legs match; the current one is drawn', async () => {
    apiAnswer = NOT_LIVE
    const w = await openPage()
    expect(state(w)).toBe('not-connected')
    const ws = FakeSocket.all[0]
    ws.serverOpen()
    const current = JSON.parse(ws.sent.at(-1)).seq
    expect(Number.isInteger(current) && current >= 1).toBe(true) // the follow message carries the page's version
    ws.serverPush({ ...COMPUTED, seq: current - 1 }) // late frame of the previous version, same legs (v1 after v2)
    await flushPromises()
    expect(state(w)).toBe('not-connected')
    // no version although the page sent one (sent as raw text: the fake socket echoes the seq into an object push)
    ws.serverPush(JSON.stringify(Object.fromEntries(Object.entries(COMPUTED).filter(([k]) => k !== 'seq'))))
    await flushPromises()
    expect(state(w)).toBe('not-connected')
    ws.serverPush({ ...COMPUTED, seq: current })
    await flushPromises()
    expect(state(w)).toBe('computed')
    w.unmount()
  })

  it('the not-live message stays on screen during a fallback reload (no loading in between)', async () => {
    apiAnswer = NOT_LIVE
    const w = await openPage()
    FakeSocket.all[0].serverOpen()
    FakeSocket.all[0].serverClose()
    await flushPromises()
    expect(state(w)).toBe('not-connected')
    let release
    apiAnswer = () => new Promise((res) => { release = () => res({ data: NOT_LIVE }) })
    const second = reconnect()
    second.serverOpen()
    second.serverClose() // the second drop asks REST again; the answer is still in flight
    await flushPromises()
    expect(state(w)).toBe('not-connected') // not 'loading'
    expect(w.text()).toContain(AC5)
    release()
    await flushPromises()
    expect(state(w)).toBe('not-connected')
    w.unmount()
  })

  it('REQ-049 AC-5 + REQ-077 AC-9: a FROM_ENTRIES answer after the drop shows the server\'s AC-5 message and the from-your-prices label, no live number', async () => {
    apiAnswer = COMPUTED
    const w = await openPage()
    FakeSocket.all[0].serverOpen()
    apiAnswer = FROM_ENTRIES
    FakeSocket.all[0].serverClose()
    await flushPromises()
    expect(state(w)).toBe('from-entries')
    expect(w.find('[data-testid="status-label"]').text()).toBe(AC5)
    expect(w.find('[data-testid="output-label"]').text()).toBe(FROM_YOUR_PRICES)
    expect(w.find('[data-testid="underlying-spot"]').text()).toBe('—') // W-193: the level card is gone; the spot is in the underlying bar
    expect(w.find('[data-testid="advanced-details"]').exists()).toBe(false)
    expect(w.find('[data-testid="state-not-connected"]').exists()).toBe(false)
    w.unmount()
  })

  it('a FROM_ENTRIES push is applied like any outcome (the socket of an ended session pushes it)', async () => {
    apiAnswer = COMPUTED
    const w = await openPage()
    const ws = FakeSocket.all[0]
    ws.serverOpen()
    ws.serverPush(FROM_ENTRIES)
    await flushPromises()
    expect(state(w)).toBe('from-entries')
    expect(w.find('[data-testid="status-label"]').text()).toBe(AC5)
    w.unmount()
  })

  it('ADR-168 attack 2: the builder opens ONE same-origin index socket, separate from the strategy socket, and it sends nothing', async () => {
    apiAnswer = COMPUTED
    const w = await openPage()
    expect(FakeSocket.index).toHaveLength(1)
    expect(FakeSocket.all).toHaveLength(1)
    expect(FakeSocket.index[0].url).toMatch(/^wss?:\/\/[^/]+\/api\/market\/indices\/live$/)
    FakeSocket.index[0].serverOpen()
    FakeSocket.all[0].serverOpen()
    expect(FakeSocket.index[0].sent).toEqual([])
    expect(() => JSON.parse(FakeSocket.all[0].sent[0])).not.toThrow()
    w.unmount()
  })

  it('attack 5: a fake socket given a non-JSON frame throws instead of ignoring it', () => {
    const strategy = new FakeSocket('ws://app.test/api/strategies/live')
    expect(() => strategy.send('undefined')).toThrow()
    const index = new FakeSocket(`ws://app.test${INDEX_LIVE_PATH}`)
    expect(() => index.send('{}')).toThrow(/send nothing/)
    FakeSocket.all = []
    FakeSocket.index = []
  })

  it('REQ-077 AC-9: a draft with one priced leg and one unpriced leg sends no outcome request, opens no socket, shows the unpriced state', async () => {
    apiAnswer = COMPUTED
    vi.stubGlobal('WebSocket', FakeSocket)
    apiCalls.length = 0
    FakeSocket.all.length = 0
    FakeSocket.index.length = 0
    const partly = { ...DRAFT, legs: [DRAFT.legs[0], { ...DRAFT.legs[1], planned_entry: null, captured_at: null }] }
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
    await router.push({ path: '/strategy/builder', query: { draft: JSON.stringify(partly) } })
    await router.isReady()
    const w = mount(StrategyBuilderPage, { global: { plugins: [router] } })
    await flushPromises()
    expect(state(w)).toBe('unpriced')
    expect(w.find('[data-testid="state-unpriced"]').exists()).toBe(true)
    // the text is true for a partly priced draft (one leg HAS an entry), so it must not say "none of the legs"
    const text = w.find('[data-testid="state-unpriced"]').text()
    expect(text).toContain('not every leg has a planned entry')
    expect(text).not.toContain('none of the legs')
    expect(w.find('[data-testid="strategy-table"]').exists()).toBe(false)
    expect(apiCalls).toEqual([])
    expect(FakeSocket.all).toHaveLength(0)
    w.unmount()
  })
})

describe('FROM_ENTRIES on the socket: accepted, never marks the socket live', () => {
  it('isOutcome accepts exactly the four outcome states', () => {
    for (const s of ['COMPUTED', 'NOT_CONNECTED', 'REFUSED', 'FROM_ENTRIES']) expect(isOutcome({ state: s })).toBe(true)
    for (const s of ['LIVE', 'from-entries', '', undefined]) expect(isOutcome({ state: s })).toBe(false)
  })
  it('a FROM_ENTRIES push reaches onPush untouched and records no last-price time', async () => {
    const { useStrategyLive } = await import('@/composables/useStrategyLive')
    const { effectScope } = await import('vue')
    const got = []
    const scope = effectScope()
    const live = scope.run(() => useStrategyLive({ url: 'ws://app.test/x', WebSocketImpl: FakeSocket, onPush: (m) => got.push(m) }))
    live.follow(BODY)
    const ws = FakeSocket.all.at(-1)
    ws.serverOpen()
    ws.serverPush({ ...FROM_ENTRIES, last_price_at: '2026-10-19T10:15:00+05:30' })
    expect(got).toHaveLength(1)
    expect(got[0].state).toBe('FROM_ENTRIES')
    expect(live.reconnectingText.value).not.toMatch(/\d\d:\d\d/) // a typed-price answer is not a price time
    ws.serverPush({ ...COMPUTED, last_price_at: '2026-10-19T10:15:00+05:30' })
    expect(live.reconnectingText.value).toMatch(/\d\d:\d\d/) // the control: a COMPUTED push does
    scope.stop()
  })
})

describe('W-073: draft URL with un-normalized values, and a leg edit while the socket is down', () => {
  const RAW = { underlying: 'NIFTY', legs: real.legs.map((l) => ({ instrument_id: l.instrument_id, action: l.action, lots: String(l.lots),
    planned_entry: `0${l.planned_entry}`, captured_at: l.captured_at })) }
  async function openRaw() {
    vi.stubGlobal('WebSocket', FakeSocket)
    apiCalls.length = 0
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
    await router.push({ path: '/strategy/builder', query: { draft: JSON.stringify(RAW) } })
    await router.isReady()
    const w = mount(StrategyBuilderPage, { global: { plugins: [router] } })
    await flushPromises()
    return w
  }
  const st = (w) => w.find('[data-testid="strategy-builder"]').attributes('data-state')
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  })

  it('AC-4: a draft URL with lots "2"-style strings and a zero-padded entry keeps applying live pushes', async () => {
    apiAnswer = NOT_LIVE
    const w = await openRaw()
    expect(st(w)).toBe('not-connected')
    const ws = FakeSocket.all[0]
    ws.serverOpen()
    ws.serverPush(COMPUTED)
    await flushPromises()
    expect(st(w)).toBe('computed')
    ws.serverPush(NOT_LIVE)
    await flushPromises()
    expect(st(w)).toBe('not-connected')
    ws.serverPush(COMPUTED)
    await flushPromises()
    expect(st(w)).toBe('computed')
    w.unmount()
  })

  async function editLeg(w) {
    const picker = w.findComponent({ name: 'LegPicker' })
    const next = picker.props('legs').map((l, i) => (i === 0 ? { ...l, lots: 3 } : l))
    picker.vm.$emit('update:legs', next)
    await flushPromises()
  }

  it('#234 item 3: a leg edit during an outage sends fallback true', async () => {
    apiAnswer = NOT_LIVE
    const w = await openRaw()
    FakeSocket.all[0].serverOpen()
    FakeSocket.all[0].serverClose()
    await flushPromises()
    apiCalls.length = 0
    await editLeg(w)
    expect(apiCalls.length).toBeGreaterThan(0)
    expect(apiCalls.every((c) => c.body.fallback === true)).toBe(true)
    w.unmount()
  })

  it('#234 item 3: after 40 failed reconnects (the old limit), a leg edit still sends fallback true', async () => {
    apiAnswer = NOT_LIVE
    const w = await openRaw()
    FakeSocket.all[0].serverOpen()
    FakeSocket.all[0].serverClose()
    for (let i = 0; i < FAST_ATTEMPTS + 10; i++) {
      vi.advanceTimersByTime(MAX_DELAY_MS + 1)
      FakeSocket.all.at(-1).serverClose()
    }
    await flushPromises()
    const before = FakeSocket.all.length
    vi.advanceTimersByTime(MAX_DELAY_MS + 1)
    expect(FakeSocket.all.length).toBe(before + 1) // still retrying past the old limit (REQ-113 AC-11)
    FakeSocket.all.at(-1).serverClose()
    apiCalls.length = 0
    await editLeg(w)
    expect(apiCalls.length).toBeGreaterThan(0)
    expect(apiCalls.every((c) => c.body.fallback === true)).toBe(true)
    w.unmount()
  })
})

describe('W-073 round 2: the draft link is canonicalized once at the page boundary or refused', () => {
  const link = (over) => ({ underlying: 'NIFTY', legs: real.legs.map((l, i) => ({ instrument_id: l.instrument_id, action: l.action,
    lots: l.lots, planned_entry: l.planned_entry, captured_at: l.captured_at, ...(i === 0 ? over : {}) })) })
  async function openLink(d) {
    vi.stubGlobal('WebSocket', FakeSocket)
    FakeSocket.all = []
    FakeSocket.index = []
    apiCalls.length = 0
    readCalls.length = 0
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
    await router.push({ path: '/strategy/builder', query: { draft: JSON.stringify(d) } })
    await router.isReady()
    const w = mount(StrategyBuilderPage, { global: { plugins: [router] } })
    await flushPromises()
    return w
  }
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  })

  it.each([['2.0'], ['+2'], [true], [' 2']])('lots %j: the link is refused with the four-part error, no request, no socket', async (lots) => {
    apiAnswer = COMPUTED
    const w = await openLink(link({ lots }))
    expect(w.find('[data-testid="strategy-builder"]').attributes('data-state')).toBe('error')
    const err = w.find('[data-testid="state-error"]').text()
    expect(err).toContain('Some of the values sent with this request are missing or not in the expected form.')
    expect(err).toContain('Check the values you entered and try again.')
    expect(apiCalls.length).toBe(0)
    expect(readCalls.length).toBe(0) // a refused link sends no read either
    expect(FakeSocket.all.length).toBe(0)
    w.unmount()
  })

  it('lots "02" and entry "0" + 42.70 style: accepted, sent as 2 / "42.70" on REST and the socket, pushes applied', async () => {
    apiAnswer = NOT_LIVE
    const w = await openLink(link({ lots: '02', planned_entry: `0${real.legs[0].planned_entry}` }))
    const sentLeg = apiCalls[0].body.legs[0]
    expect(sentLeg.lots).toBe(2)
    expect(sentLeg.planned_entry).toBe(real.legs[0].planned_entry)
    expect(w.find('[data-testid="strategy-builder"]').attributes('data-state')).toBe('not-connected')
    const ws = FakeSocket.all[0]
    ws.serverOpen()
    expect(JSON.parse(ws.sent[0]).legs[0]).toMatchObject({ lots: 2, planned_entry: real.legs[0].planned_entry })
    ws.serverPush({ ...COMPUTED, legs: COMPUTED.legs.map((l, i) => (i === 0 ? { ...l, lots: 2 } : l)) })
    await flushPromises()
    expect(w.find('[data-testid="strategy-builder"]').attributes('data-state')).toBe('computed')
    w.unmount()
  })
})

describe('W-148 (REQ-076 AC-3, AC-6): the live push still matches after a leg edit', () => {
  // The reply of POST /strategies/leg-edit after leg 1 is unticked: all four legs back, leg 1 included:false, and the
  // outcome of the other three (the recorded condor outcome without its first leg).
  const replyLegs = real.legs.map((l, i) => ({ instrument_id: l.instrument_id, action: l.action, instrument: l.instrument,
    strike: l.strike, expiry: l.expiry, lots: l.lots, base_lots: l.lots, quantity: l.quantity, planned_entry: l.planned_entry,
    captured_at: l.captured_at, price_source: 'captured', included: i !== 0, hedge: false, block: null }))
  const THREE = { ...real, output_label: 'THREE LEGS', legs: real.legs.slice(1) }
  it('AC-6: after an untick the socket is told the included legs only, and a push of exactly those is applied', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    vi.stubGlobal('WebSocket', FakeSocket)
    apiCalls.length = 0
    FakeSocket.all = []
    FakeSocket.index = []
    const readLegs = replyLegs.map((l) => ({ ...l, included: true })) // the read on load changes no tick
    apiAnswer = (body) => Promise.resolve({ data: body?.edit?.control === 'read' ? { legs: readLegs, shape_name: null, outcome: null }
      : body?.edit ? { legs: replyLegs, shape_name: null, outcome: THREE } : COMPUTED })
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
    await router.push({ path: '/strategy/builder', query: { draft: JSON.stringify(DRAFT) } })
    await router.isReady()
    const w = mount(StrategyBuilderPage, { global: { plugins: [router] } })
    await flushPromises()
    const ws = FakeSocket.all[0]
    ws.serverOpen()
    await w.findComponent({ name: 'LegList' }).vm.$emit('edit', { control: 'include', index: 0, included: false })
    await flushPromises()
    expect(apiCalls.filter((c) => c.body?.edit && c.body.edit.control !== 'read')).toHaveLength(1) // the read on load is not an edit
    expect(w.text()).toContain('THREE LEGS') // the reply's outcome is on screen without a second outcome request
    const told = JSON.parse(FakeSocket.all.at(-1).sent.at(-1))
    expect(told.legs.map((l) => l.instrument_id)).toEqual(real.legs.slice(1).map((l) => l.instrument_id))
    FakeSocket.all.at(-1).serverOpen()
    FakeSocket.all.at(-1).serverPush({ ...THREE, output_label: 'PUSHED' })
    await flushPromises()
    expect(w.text()).toContain('PUSHED')
    FakeSocket.all.at(-1).serverPush({ ...COMPUTED, output_label: 'ALL FOUR' }) // another strategy as sent: dropped
    await flushPromises()
    expect(w.text()).not.toContain('ALL FOUR')
    w.unmount()
  })
})


// W-151 (REQ-119 AC-2, AC-3, AC-4): two edits sent as seq 1 then seq 2, answered 2 then 1, on the mounted Builder page.
describe('REQ-119 23b core: the newest edit wins on the mounted page, out of order', () => {
  const REPLY = (label, id) => ({ legs: real.legs.map((l, i) => ({ instrument_id: i === 0 ? id : l.instrument_id, action: l.action, instrument: l.instrument,
    strike: l.strike, expiry: l.expiry, lots: l.lots, base_lots: l.lots, quantity: l.quantity, planned_entry: l.planned_entry, captured_at: l.captured_at,
    price_source: 'captured', included: true, hedge: false, block: null })), shape: null, shape_name: null,
  outcome: { ...real, legs: real.legs.map((l, i) => (i === 0 ? { ...l, instrument_id: id } : l)), summary: { ...real.summary, what_can_i_lose: label } } })
  const parked = [] // the edit requests (and, when parkOutcome is set, the outcome requests) in flight, each with its resolver, rejecter and abort signal
  let parkOutcome = false
  async function openRig() {
    vi.stubGlobal('WebSocket', FakeSocket)
    apiCalls.length = 0
    parked.length = 0
    parkOutcome = false
    apiAnswer = (body, url, opts) => {
      if (url === '/strategies/outcome' && !parkOutcome) return Promise.resolve({ data: { ...real, seq: body.seq } })
      if (url !== '/strategies/outcome' && body.edit.control === 'read') return Promise.resolve({ data: { ...REPLY('read', real.legs[0].instrument_id), outcome: null, seq: body.seq } })
      return new Promise((resolve, reject) => {
        const signal = opts?.signal
        const entry = { url, body, seq: body.seq, signal, answer: (data) => resolve({ data: { ...data, seq: body.seq } }), fail: reject }
        signal?.addEventListener('abort', () => honourAbort && reject(Object.assign(new Error('canceled'), { code: 'ERR_CANCELED', __CANCEL__: true })))
        parked.push(entry)
      })
    }
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
    await router.push({ path: '/strategy/builder', query: { draft: JSON.stringify(DRAFT) } })
    await router.isReady()
    const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true } } })
    await flushPromises()
    return w
  }
  const txt = (w, id) => w.find(`[data-testid="${id}"]`).text()
  let honourAbort = true // false = a transport that ignores the abort: the reply still arrives, and is dropped by its seq
  afterEach(() => { apiAnswer = null; honourAbort = true })

  it('a reply 1 that arrives after reply 2 although its request was aborted is still dropped by its seq', async () => {
    honourAbort = false
    const w = await openRig()
    await w.findAll('[data-testid="strike-plus"]')[0].trigger('click')
    await w.findAll('[data-testid="strike-plus"]')[0].trigger('click')
    await flushPromises()
    parked[1].answer(REPLY('REPLY TWO', 'NSE_FO:44625'))
    await flushPromises()
    parked[0].answer(REPLY('REPLY ONE', 'NSE_FO:44625'))
    await flushPromises()
    expect(txt(w, 'sum-lose')).toBe('REPLY TWO')
    expect(w.text()).not.toContain('REPLY ONE')
    w.unmount()
  })

  it('replies 2 then 1: the screen keeps reply 2, and request 1 was aborted', async () => {
    const w = await openRig()
    await w.findAll('[data-testid="strike-plus"]')[0].trigger('click')
    await w.findAll('[data-testid="strike-plus"]')[0].trigger('click')
    await flushPromises()
    expect(parked).toHaveLength(2)
    parked[1].answer(REPLY('REPLY TWO', 'NSE_FO:44625'))
    await flushPromises()
    expect(txt(w, 'sum-lose')).toBe('REPLY TWO')
    parked[0].answer(REPLY('REPLY ONE', 'NSE_FO:44625'))
    await flushPromises()
    expect(txt(w, 'sum-lose')).toBe('REPLY TWO')
    expect(parked[0].signal?.aborted).toBe(true)
    expect(parked[1].seq).toBeGreaterThan(parked[0].seq) // each edit carries its own, rising seq (the server echoes it)
    expect(w.text()).not.toContain('Something went wrong')
    expect(w.find('[data-testid="edit-error"]').exists()).toBe(false) // the abort of request 1 is no edit error (AC-3)
    expect(w.text()).toContain('REPLY TWO')
    w.unmount()
  })

  it('AC-4: the numbers are marked updating and Execute is refused with its reason until the latest reply is applied', async () => {
    const w = await openRig()
    const refusal = () => w.findComponent(StrategyActions).props('executeRefusal')
    expect(refusal()).toBeNull()
    expect(w.get('[data-testid="numbers"]').attributes('data-updating')).toBe('false')
    await w.findAll('[data-testid="strike-plus"]')[0].trigger('click')
    await w.findAll('[data-testid="strike-plus"]')[0].trigger('click')
    await flushPromises()
    expect(w.get('[data-testid="numbers"]').attributes('data-updating')).toBe('true')
    expect(w.find('[data-testid="numbers-updating"]').exists()).toBe(true)
    expect(refusal()).toBe(EXECUTE_WAITS_FOR_LATEST)
    parked[1].answer(REPLY('REPLY TWO', 'NSE_FO:44625')) // the newest answers; the older was aborted
    await flushPromises()
    expect(w.get('[data-testid="numbers"]').attributes('data-updating')).toBe('false')
    expect(refusal()).toBeNull()
    w.unmount()
  })

  // The checker's probe P1 (23b fix round 1): the leg-edit reply used to draw its At Expiry numbers under an Estimated Now
  // choice and cancel the newer outcome request. One rule now: numbers are drawn only when they match the legs AND choice.
  const choose = (w, c) => w.findComponent(ScenarioControls).vm.$emit('update:choice', c)
  const ESTIMATED = { view: 'estimated_now', rangeStart: '', rangeEnd: '' }
  const estimatedBody = (label, id) => ({ ...REPLY(label, id).outcome, scenario: { ...real.scenario, view: 'estimated_now', customised: false } })
  const actions = (w) => w.findComponent(StrategyActions)
  const executeWaits = (w) => !actions(w).exists() || actions(w).props('executeRefusal') !== null // no Execute button, or a refusal
  const edits = () => parked.filter((p) => p.url !== '/strategies/outcome')
  const outcomes = () => parked.filter((p) => p.url === '/strategies/outcome')

  it('P1 core: leg-edit reply first, then the newer Estimated Now request: no at-expiry numbers, newer request kept, Execute waits', async () => {
    const w = await openRig()
    await w.findAll('[data-testid="strike-plus"]')[0].trigger('click')
    await flushPromises()
    parkOutcome = true
    choose(w, ESTIMATED)
    await flushPromises()
    const [edit] = edits()
    const [newer] = outcomes()
    edit.answer(REPLY('LEG-EDIT REPLY (at_expiry)', 'NSE_FO:44625'))
    await flushPromises()
    expect(w.text()).not.toContain('LEG-EDIT REPLY (at_expiry)')
    expect(newer.signal.aborted).toBe(false)
    // AC-4 (combined check F): while the matching numbers are awaited the previous block stays mounted, marked updating,
    // never as current; the leg-edit reply's numbers are not drawn (asserted above)
    expect(w.get('[data-testid="numbers"]').attributes('data-updating')).toBe('true')
    expect(executeWaits(w)).toBe(true)
    newer.answer(estimatedBody('OUTCOME estimated_now (old legs)', 'NSE_FO:44625'))
    await flushPromises()
    expect(w.get('[data-testid="numbers"]').attributes('data-updating')).toBe('false')
    expect(txt(w, 'sum-lose')).toBe('OUTCOME estimated_now (old legs)')
    expect(actions(w).props('executeRefusal')).toBeNull()
    w.unmount()
  })

  it('an outcome reply made for the legs before the edit is dropped and asked again for the new legs', async () => {
    const w = await openRig()
    await w.findAll('[data-testid="strike-plus"]')[0].trigger('click')
    await flushPromises()
    parkOutcome = true
    choose(w, ESTIMATED)
    await flushPromises()
    const [edit] = edits()
    edit.answer(REPLY('LEG-EDIT REPLY', 'NSE_FO:44625'))
    await flushPromises()
    outcomes()[0].answer(estimatedBody('OLD LEGS', real.legs[0].instrument_id)) // sent with the legs before the edit
    await flushPromises()
    expect(w.text()).not.toContain('OLD LEGS')
    expect(outcomes()).toHaveLength(2)
    expect(outcomes()[1].body.legs[0].instrument_id).toBe('NSE_FO:44625')
    expect(outcomes()[1].body.view).toBe('estimated_now')
    expect(executeWaits(w)).toBe(true)
    outcomes()[1].answer(estimatedBody('NEW LEGS', 'NSE_FO:44625'))
    await flushPromises()
    expect(txt(w, 'sum-lose')).toBe('NEW LEGS')
    expect(actions(w).props('executeRefusal')).toBeNull()
    w.unmount()
  })

  it('edit while on Estimated Now, no race: the request carries the view and no at-expiry numbers are ever drawn', async () => {
    const w = await openRig()
    choose(w, ESTIMATED)
    await flushPromises()
    await w.findAll('[data-testid="strike-plus"]')[0].trigger('click')
    await flushPromises()
    const [edit] = edits()
    expect(edit.body.view).toBe('estimated_now')
    expect(edit.body.range_start).toBeUndefined() // the server's leg-edit has no range field
    edit.answer({ ...REPLY('ESTIMATED NOW', 'NSE_FO:44625'), outcome: estimatedBody('ESTIMATED NOW', 'NSE_FO:44625') })
    await flushPromises()
    expect(txt(w, 'sum-lose')).toBe('ESTIMATED NOW')
    expect(actions(w).props('executeRefusal')).toBeNull()
    w.unmount()
  })

  it('edit with a custom range on screen: the legs are applied and the numbers are asked again with the range', async () => {
    const w = await openRig()
    choose(w, { view: 'at_expiry', rangeStart: '24000', rangeEnd: '26000' })
    await flushPromises()
    parkOutcome = true
    await w.findAll('[data-testid="strike-plus"]')[0].trigger('click')
    await flushPromises()
    const [edit] = edits()
    expect(edit.body.range_start).toBeUndefined()
    edit.answer(REPLY('AT EXPIRY DEFAULT RANGE', 'NSE_FO:44625'))
    await flushPromises()
    expect(w.text()).not.toContain('AT EXPIRY DEFAULT RANGE')
    expect(w.findComponent(LegList).props('legs')[0].instrument_id).toBe('NSE_FO:44625') // the edit itself is kept
    expect(outcomes()).toHaveLength(1)
    expect(outcomes()[0].body.range_start).toBe('24000')
    expect(outcomes()[0].body.range_end).toBe('26000')
    expect(executeWaits(w)).toBe(true)
    w.unmount()
  })

  it('every outcome request carries a seq and an abort signal', async () => {
    const w = await openRig()
    const outcomes = apiCalls.filter((c) => c.url === '/strategies/outcome')
    expect(outcomes.length).toBeGreaterThan(0)
    for (const c of outcomes) {
      expect(Number.isInteger(c.body.seq)).toBe(true)
      expect(c.opts.signal).toBeInstanceOf(AbortSignal)
    }
    w.unmount()
  })

  it('a failed newest edit shows its error and ends the updating mark', async () => {
    const w = await openRig()
    await w.findAll('[data-testid="strike-plus"]')[0].trigger('click')
    await flushPromises()
    parked[0].fail({ parts: { what_happened: 'That strike is not listed.', impact: 'Nothing changed.', what_is_blocked: 'No step was made.', next_action: 'Pick another strike.' } })
    await flushPromises()
    expect(w.text()).toContain('That strike is not listed.')
    expect(w.get('[data-testid="numbers"]').attributes('data-updating')).toBe('false')
    w.unmount()
  })
})

// ---- W-155 (REQ-135 AC-3, AC-4): one 'Prices as of' stamp, no manual refresh, the lone futures leg ------------------------
// COMPUTED is the recorded condor outcome; the fields the engine added for REQ-135 (last_price_at, summary extras) are set to
// the shapes backend/ofo/outcome/serialize.py writes (pinned by tests_app/test_outcome_route.py and tests/engine/test_lone_future_summary.py).
describe('REQ-135 AC-3: one Prices-as-of stamp from last_price_at, never a refresh button', () => {
  const PRICED = '2026-10-19T10:15:00+05:30'
  const ANSWERED = '2026-10-19T10:15:07+05:30'
  const FRESH = { ...real, last_price_at: PRICED, answered_at: ANSWERED }
  async function open(answer = FRESH, draft = DRAFT) {
    vi.stubGlobal('WebSocket', FakeSocket)
    apiCalls.length = 0
    apiAnswer = answer
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
    await router.push({ path: '/strategy/builder', query: { draft: JSON.stringify(draft) } })
    await router.isReady()
    const w = mount(StrategyBuilderPage, { global: { plugins: [router] } })
    await flushPromises()
    return w
  }
  const stamp = (w) => w.find('[data-testid="prices-as-of"]')
  beforeEach(() => { vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] }) })

  it('shows exactly one stamp read from last_price_at (not answered_at); the two old clocks and the refresh button are gone', async () => {
    const w = await open()
    expect(stamp(w).text()).toBe('Prices as of 10:15:00 IST')
    expect(w.findAll('[data-testid="prices-as-of"]')).toHaveLength(1)
    expect(w.text().match(/Prices as of/g)).toHaveLength(1)
    expect(w.find('[data-testid="footer-valuation"]').exists()).toBe(false)
    expect(w.text()).not.toContain('Priced at')
    expect(w.find('[data-testid="recalculate"]').exists()).toBe(false)
    expect(w.text()).not.toContain('ReCalculate')
    w.unmount()
  })

  it('each live push moves the stamp, and no push changes any leg\'s planned entry or capture time', async () => {
    const w = await open()
    const before = w.findAll('[data-testid="leg-row"]').map((r) => [r.attributes('data-entry'), r.attributes('data-captured')])
    const ws = FakeSocket.all.at(-1)
    ws.serverOpen()
    ws.serverPush({ ...FRESH, last_price_at: '2026-10-19T10:15:01+05:30', legs: FRESH.legs.map((l) => ({ ...l, ltp: '41.00' })) })
    await flushPromises()
    expect(stamp(w).text()).toBe('Prices as of 10:15:01 IST')
    expect(w.findAll('[data-testid="leg-row"]').map((r) => [r.attributes('data-entry'), r.attributes('data-captured')])).toEqual(before)
    expect(before.every(([entry, at]) => entry && at)).toBe(true)
    w.unmount()
  })

  it('a stale answer shows its data-health label in place of the time', async () => {
    const w = await open({ ...FRESH, output_label: 'Prices are 4 minutes old' })
    expect(stamp(w).text()).toBe('Prices are 4 minutes old')
    expect(stamp(w).attributes('data-kind')).toBe('health')
    expect(w.text()).not.toContain('Prices as of')
    w.unmount()
  })

  it('a stale leg label (staleLegs) also replaces the time', async () => {
    const w = await open({ ...FRESH, legs: FRESH.legs.map((l, i) => (i === 0 ? { ...l, label: 'Price 3 minutes old' } : l)) })
    expect(stamp(w).text()).toBe('Price 3 minutes old')
    expect(w.text()).not.toContain('Prices as of')
    w.unmount()
  })

  it('while the feed reconnects the reconnecting sentence is shown and no second time is', async () => {
    const w = await open()
    const ws = FakeSocket.all.at(-1)
    ws.serverOpen()
    ws.serverPush(FRESH)
    await flushPromises()
    ws.serverClose()
    await flushPromises()
    expect(w.find('[data-testid="live-reconnecting"]').text()).toContain('10:15:00')
    expect(stamp(w).exists()).toBe(false)
    w.unmount()
  })

  it('no stamp while the market-closed banner carries the time, and none when the answer has no price time', async () => {
    const closed = await open({ ...FRESH, market_closed: true })
    expect(closed.findComponent({ name: 'MarketClosedBanner' }).exists()).toBe(true)
    expect(stamp(closed).exists()).toBe(false)
    closed.unmount()
    const none = await open({ ...real, last_price_at: null })
    expect(none.find('[data-testid="numbers"]').exists()).toBe(true)
    expect(stamp(none).exists()).toBe(false)
    none.unmount()
  })
})

describe('REQ-135 AC-4: a strategy of one futures leg', () => {
  const FUT = { ...real.legs[0], instrument: 'FUT', strike: null }
  const LONE = { ...real, legs: [{ ...FUT, action: 'BUY' }], last_price_at: '2026-10-19T10:15:00+05:30',
    summary: { ...real.summary, max_profit: null, max_profit_unlimited: true, max_loss: '1560000.00', max_loss_unlimited: false,
      reward_risk: null, reward_risk_reason: 'No fixed maximum', time_value: '0.00', intrinsic_value: '0.00' } }
  const DRAFT_ONE = { underlying: 'NIFTY', legs: [{ instrument_id: FUT.instrument_id, action: 'BUY', lots: FUT.lots, planned_entry: FUT.planned_entry, captured_at: FUT.captured_at }] }
  beforeEach(() => { vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] }) })

  async function open(answer) {
    vi.stubGlobal('WebSocket', FakeSocket)
    apiAnswer = answer
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
    await router.push({ path: '/strategy/builder', query: { draft: JSON.stringify(DRAFT_ONE) } })
    await router.isReady()
    const w = mount(StrategyBuilderPage, { global: { plugins: [router] } })
    await flushPromises()
    return w
  }

  it('shows Unlimited profit, Reward/Risk dash with the server reason, Time and Intrinsic value as sent, and no strike stepper', async () => {
    const w = await open(LONE)
    expect(w.find('[data-testid="max-profit"]').text()).toBe('Unlimited')
    expect(w.find('[data-testid="reward-risk"]').text()).toBe('-')
    expect(w.find('[data-testid="reward-risk-reason"]').text()).toBe('(No fixed maximum)')
    expect(w.find('[data-testid="time-value"]').text()).toBe('0.00')
    expect(w.find('[data-testid="intrinsic-value"]').text()).toBe('0.00')
    expect(w.findAll('[data-testid="leg-row"]')).toHaveLength(1)
    expect(w.find('[data-testid="strike-minus"]').exists()).toBe(false)
    expect(w.find('[data-testid="strike-plus"]').exists()).toBe(false)
    w.unmount()
  })

  it('an ordinary strategy (the extras are null) shows none of the three rows', async () => {
    const w = await open(real)
    expect(w.find('[data-testid="summary-extras"]').exists()).toBe(false)
    w.unmount()
  })
})
