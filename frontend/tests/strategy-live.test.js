// W-065 (REQ-035 AC-4; ADR-068 (2), ADR-077, ADR-008): the live socket lifecycle, with a fake socket and fake timers.
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { BASE_DELAY_MS, LIVE_PATH, MAX_ATTEMPTS, MAX_DELAY_MS, backoffDelay, createLiveSocket, isOutcome, liveUrl } from '@/composables/useStrategyLive'

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
})
afterEach(() => vi.useRealTimers())

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

  it('AC-4: the backoff doubles, is capped, and stops after MAX_ATTEMPTS failures in a row', () => {
    expect([1, 2, 3, 4, 5, 6, 7].map(backoffDelay)).toEqual([1000, 2000, 4000, 8000, 16000, 30000, 30000])
    expect(backoffDelay(50)).toBe(MAX_DELAY_MS)
    const { live, statuses, onDown } = rig()
    live.follow(BODY)
    for (let i = 0; i < MAX_ATTEMPTS + 3; i++) {
      FakeSocket.all.at(-1).serverClose()
      vi.advanceTimersByTime(MAX_DELAY_MS)
    }
    expect(FakeSocket.all.length).toBe(1 + MAX_ATTEMPTS) // the first socket plus MAX_ATTEMPTS retries, then no more
    expect(statuses.at(-1)).toBe('off')
    expect(onDown).toHaveBeenCalledTimes(MAX_ATTEMPTS + 1) // every drop still asked REST
    live.follow({ ...BODY, ux_level: 'guided' }) // a new strategy after giving up tries again
    expect(FakeSocket.all.length).toBe(2 + MAX_ATTEMPTS)
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
