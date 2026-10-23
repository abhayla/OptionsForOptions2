// W-065 (REQ-035 AC-4; ADR-068 (2), ADR-077, ADR-008): the live socket lifecycle, with a fake socket and fake timers.
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

const apiCalls = []
let apiAnswer = null
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: () => Promise.reject(new Error('unmocked get')),
    post: (url, body) => { apiCalls.push({ url, body }); return typeof apiAnswer === 'function' ? apiAnswer(body) : Promise.resolve({ data: apiAnswer }) } } }
})
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import real from './fixtures/outcome-condor-advanced.json'
import { BASE_DELAY_MS, FAST_ATTEMPTS, LIVE_PATH, MAX_DELAY_MS, backoffDelay, createLiveSocket, isOutcome, liveUrl } from '@/composables/useStrategyLive'

class FakeSocket {
  static all = []
  constructor(url) {
    this.url = url
    this.sent = []
    this.readyState = 0
    this.closed = false
    FakeSocket.all.push(this)
  }
  send(text) {
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
    this.onmessage?.({ data: typeof obj === 'string' ? obj : JSON.stringify(obj) })
  }
  serverClose() {
    this.readyState = 3
    this.onclose?.()
  }
}

// A push as the server sends it: values are display strings already (the browser never computes them).
const push = (ltp, pnl) => ({ state: 'COMPUTED', legs: [{ instrument_id: 'NSE_FO:44626', ltp, label: null }],
  table: { rows: [{ row_id: '1', cells: { ltp: { display: `₹${ltp}` }, unrealized_pnl: { display: pnl } } }] } })
const BODY = { underlying: 'NIFTY', legs: [{ instrument_id: 'NSE_FO:44626', action: 'SELL', lots: 1 }], ux_level: 'standard' }

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
    live.follow({ ...BODY, ux_level: 'advanced' })
    expect(ws.sent.length).toBe(2)
    expect(JSON.parse(ws.sent[1]).ux_level).toBe('advanced')
    expect(FakeSocket.all.length).toBe(1)
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
// The COMPUTED answer is the real recorded condor outcome (tests/fixtures/outcome-condor-advanced.json); the not-live
// answer has the shape the server sends (NOT_CONNECTED, AC-5's text, no table, no ltp).
const AC5 = 'Live market data disconnected. Last updated: 09:20:09 AM. Live strategy monitoring is paused.'
const DRAFT = { underlying: 'NIFTY', legs: real.legs.map((l) => ({ instrument_id: l.instrument_id, action: l.action, lots: l.lots,
  planned_entry: l.planned_entry, captured_at: l.captured_at })) }
const NOT_LIVE = { ...real, state: 'NOT_CONNECTED', status_label: AC5, table: null, summary: null, payoff: null, scenario: null,
  advanced_details: undefined, legs: real.legs.map((l) => ({ ...l, ltp: null, label: AC5 })) }
const COMPUTED = real
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
    await w.vm.$router.replace({ query: { ...w.vm.$route.query, ux: 'guided' } })
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
    apiCalls.length = 0
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

