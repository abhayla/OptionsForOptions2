// REQ-113 AC-10 and AC-11 (RD-057, RD-058; W-137): the browser never gives up on the live socket, and every wait carries a
// random spread of up to 1 s so tabs do not reconnect in the same second. Fake socket, recorded timers. Expected waits come
// from the requirement (1 s apart for the first 30 attempts, then 2, 4, 8 ... capped at 30 s, plus a spread under 1 s).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { FAST_ATTEMPTS, MAX_DELAY_MS, createLiveSocket, useStrategyLive } from '@/composables/useStrategyLive'
import { RECONNECTING_NO_TIME_TEXT } from '@/lib/sharedStateText'

class FakeSocket {
  static all = []
  constructor(url) { this.url = url; this.sent = []; this.readyState = 0; FakeSocket.all.push(this) }
  send(text) { this.sent.push(text) }
  close() { this.readyState = 3 }
  serverOpen() { this.readyState = 1; this.onopen?.() }
  serverPush(obj) { this.onmessage?.({ data: JSON.stringify(obj) }) }
  serverClose() { this.readyState = 3; this.onclose?.() }
}

const BODY = { underlying: 'NIFTY', legs: [{ instrument_id: 'NSE_FO:44626', action: 'SELL', lots: 1 }], ux_level: 'standard' }
const SPREAD_MS = 1000 // REQ-113 AC-10: "a random spread of up to 1 s"

beforeEach(() => { FakeSocket.all = [] })
afterEach(() => { vi.useRealTimers() })

function timedSocket(extra = {}) {
  const timers = []
  const statuses = []
  const live = createLiveSocket({ url: 'ws://x/live', WebSocketImpl: FakeSocket, onPush: () => {}, onStatus: (s) => statuses.push(s),
    setTimer: (fn, ms) => { timers.push({ fn, ms }); return timers.length }, clearTimer: () => {}, ...extra })
  return { live, timers, statuses }
}

/** Drop the socket `n` times in a row, each time running the scheduled retry. */
function failTimes(live, timers, n) {
  live.follow(BODY)
  FakeSocket.all[0].serverClose()
  for (let i = 0; i < n; i += 1) {
    timers[i].fn()
    FakeSocket.all.at(-1).serverClose()
  }
}

describe('AC-11: the browser never gives up on the live socket', () => {
  it('AC-11: after 40 failed attempts, attempt 41 is still scheduled, at the 30 s cap; and so is attempt 500', () => {
    const { live, timers, statuses } = timedSocket({ random: () => 0 })
    failTimes(live, timers, 499)
    expect(timers).toHaveLength(500)
    expect(timers[40].ms).toBe(MAX_DELAY_MS) // attempt 41
    expect(timers[499].ms).toBe(MAX_DELAY_MS) // attempt 500
    expect(statuses).not.toContain('off') // never reports "given up"
    expect(statuses.at(-1)).toBe('down')
  })

  it('AC-11: a real answer after many failures still resumes live and the next drop starts fast again', () => {
    const { live, timers, statuses } = timedSocket({ random: () => 0 })
    failTimes(live, timers, 60)
    timers.at(-1).fn()
    const ws = FakeSocket.all.at(-1)
    ws.serverOpen()
    ws.serverPush({ state: 'COMPUTED', legs: [] })
    expect(statuses.at(-1)).toBe('live')
    ws.serverClose()
    expect(timers.at(-1).ms).toBe(1000)
  })

  it('AC-11: stop() still ends the retries for good (leaving the page is not a drop)', () => {
    const { live, timers } = timedSocket({ random: () => 0 })
    failTimes(live, timers, 45)
    live.stop()
    FakeSocket.all.at(-1).serverClose()
    expect(timers).toHaveLength(46) // nothing scheduled after stop()
  })

  it('AC-11 / REQ-114 AC-5: while retrying past the old limit the screen keeps the reconnecting text, never a silent answer', async () => {
    vi.useFakeTimers()
    vi.spyOn(Math, 'random').mockReturnValue(0)
    const Probe = defineComponent({
      setup() {
        const live = useStrategyLive({ onPush: () => {}, WebSocketImpl: FakeSocket, url: 'ws://x/live' })
        live.follow(BODY)
        return () => h('div', [live.reconnecting.value ? h('p', { 'data-testid': 'live-reconnecting' }, live.reconnectingText.value) : null])
      },
    })
    const w = mount(Probe)
    const first = FakeSocket.all[0]
    first.serverOpen()
    first.serverPush({ state: 'COMPUTED', answered_at: '2026-10-19T05:32:10+00:00', last_price_at: '2026-10-19T05:32:10+00:00', legs: [] })
    await flushPromises()
    first.serverClose()
    for (let i = 0; i < FAST_ATTEMPTS + 15; i += 1) { // 45 failed attempts: past the old give-up point of 40
      vi.advanceTimersByTime(MAX_DELAY_MS + SPREAD_MS)
      FakeSocket.all.at(-1).serverClose()
    }
    await flushPromises()
    expect(w.get('[data-testid="live-reconnecting"]').text()).toBe('Reconnecting - prices as of 11:02:10') // the one helper's words
    expect(RECONNECTING_NO_TIME_TEXT).not.toBe('')
    w.unmount()
    vi.restoreAllMocks()
  })
})

describe('AC-10: every reconnect wait carries a random spread of up to 1 s', () => {
  it('AC-10: two clients started together with different random draws never pick the same wait', () => {
    const a = timedSocket({ random: () => 0.1 })
    const b = timedSocket({ random: () => 0.9 })
    for (const c of [a, b]) { c.live.follow(BODY); FakeSocket.all.at(-1).serverClose() }
    expect(a.timers[0].ms).toBe(1100)
    expect(b.timers[0].ms).toBe(1900)
    expect(a.timers[0].ms).not.toBe(b.timers[0].ms)
  })

  it('AC-10: the default random source (Math.random) gives a wait of base to base + under 1 s, and not the same value every time', () => {
    const seen = new Set()
    for (let i = 0; i < 30; i += 1) {
      const { live, timers } = timedSocket()
      live.follow(BODY)
      FakeSocket.all.at(-1).serverClose()
      seen.add(timers[0].ms)
      expect(timers[0].ms).toBeGreaterThanOrEqual(1000)
      expect(timers[0].ms).toBeLessThan(1000 + SPREAD_MS)
    }
    expect(seen.size).toBeGreaterThan(1)
  })

  it('AC-10: a wait never exceeds the cap plus 1 s, even for the largest draw', () => {
    const { live, timers } = timedSocket({ random: () => 0.9999999 })
    failTimes(live, timers, 80)
    expect(Math.max(...timers.map((t) => t.ms))).toBeLessThan(MAX_DELAY_MS + SPREAD_MS)
    expect(timers.at(-1).ms).toBeGreaterThanOrEqual(MAX_DELAY_MS)
  })

  it('AC-10: the spread is added to the wait, never taken from it (the wait is never below its base)', () => {
    const { live, timers } = timedSocket({ random: () => 0 })
    failTimes(live, timers, 36)
    expect(timers.map((t) => t.ms).slice(29, 37)).toEqual([1000, 2000, 4000, 8000, 16000, 30000, 30000, 30000])
  })
})
