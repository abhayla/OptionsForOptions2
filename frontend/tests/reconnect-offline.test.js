// REQ-113 AC-11 (RD-058, offline half; W-137): while the device reports offline the browser retries every 5 s (plus the
// 1 s spread of AC-10) without growing the back-off, and the browser's `online` event retries at once. Fake socket,
// recorded timers, a faked navigator.onLine and a fake event target.
import { beforeEach, describe, expect, it } from 'vitest'
import { echoSeq } from './helpers/echoSeq'
import { JITTER_MS, OFFLINE_RETRY_MS, createLiveSocket } from '@/composables/useStrategyLive'

class FakeSocket {
  static all = []
  constructor(url) { this.url = url; this.readyState = 0; FakeSocket.all.push(this) }
  send() {}
  close() { this.readyState = 3 }
  serverOpen() { this.readyState = 1; this.onopen?.() }
  serverPush(obj) { this.onmessage?.({ data: JSON.stringify(echoSeq(this, obj)) }) }
  serverClose() { this.readyState = 3; this.onclose?.() }
}

class FakeEvents {
  constructor() { this.handlers = new Set() }
  addEventListener(name, fn) { if (name === 'online') this.handlers.add(fn) }
  removeEventListener(name, fn) { if (name === 'online') this.handlers.delete(fn) }
  fireOnline() { [...this.handlers].forEach((fn) => fn()) }
}

const BODY = { underlying: 'NIFTY', legs: [] }
let online
let events

beforeEach(() => { FakeSocket.all = []; online = true; events = new FakeEvents() })

function rig() {
  const timers = []
  const cleared = []
  const statuses = []
  const live = createLiveSocket({ url: 'ws://x/live', WebSocketImpl: FakeSocket, onPush: () => {}, onStatus: (s) => statuses.push(s),
    setTimer: (fn, ms) => { timers.push({ fn, ms }); return timers.length }, clearTimer: (id) => cleared.push(id),
    random: () => 0, isOnline: () => online, eventTarget: events })
  return { live, timers, cleared, statuses }
}

describe('AC-11: retrying while the device is offline', () => {
  it('AC-11: while offline every wait is 5 s, not the growing back-off; back online the back-off starts as before', () => {
    const { live, timers } = rig()
    live.follow(BODY)
    online = false
    FakeSocket.all[0].serverClose()
    for (let i = 0; i < 50; i += 1) { timers.at(-1).fn(); FakeSocket.all.at(-1).serverClose() }
    expect(new Set(timers.map((t) => t.ms))).toEqual(new Set([OFFLINE_RETRY_MS])) // 51 waits, all 5 s
    online = true
    timers.at(-1).fn()
    FakeSocket.all.at(-1).serverClose()
    expect(timers.at(-1).ms).toBe(1000) // the back-off was not advanced while offline
  })

  it('AC-10 / AC-11: the offline wait carries the spread too, and stays under 5 s + 1 s', () => {
    const timers = []
    const live = createLiveSocket({ url: 'ws://x/live', WebSocketImpl: FakeSocket, onPush: () => {}, setTimer: (fn, ms) => { timers.push(ms); return 1 },
      clearTimer: () => {}, random: () => 0.9999, isOnline: () => false, eventTarget: events })
    live.follow(BODY)
    FakeSocket.all[0].serverClose()
    expect(timers[0]).toBeGreaterThanOrEqual(OFFLINE_RETRY_MS)
    expect(timers[0]).toBeLessThan(OFFLINE_RETRY_MS + JITTER_MS)
  })

  it('AC-11: the online event opens a socket at once and cancels the pending timer', () => {
    const { live, timers, cleared } = rig()
    live.follow(BODY)
    online = false
    FakeSocket.all[0].serverClose()
    expect(FakeSocket.all).toHaveLength(1) // waiting out the 5 s
    online = true
    events.fireOnline()
    expect(FakeSocket.all).toHaveLength(2) // retried at once
    expect(cleared).toEqual([timers.length]) // the pending timer was cancelled, not left to open a second socket
  })

  it('AC-11 (red cases): online with a socket open, after stop(), or with no pending wait does nothing', () => {
    const { live } = rig()
    live.follow(BODY)
    events.fireOnline() // the first socket is still connecting
    expect(FakeSocket.all).toHaveLength(1)
    live.stop()
    expect(events.handlers.size).toBe(0) // the listener is gone after stop()
    events.fireOnline()
    expect(FakeSocket.all).toHaveLength(1)
  })
})
