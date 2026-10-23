// W-137 (REQ-113 AC-2, browser half; ADR-015, ADR-077): when the live socket drops, every live screen stops calling its
// prices live at once, says "reconnecting", and resumes within 10 s of the server being back. Fake socket, fake timers,
// no real waits. Expected delays come from the requirement (attempts 1 s apart for the first 30 s, then 2, 4, 8 ... 30 s),
// never from running the helper.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

const reads = []
let restAnswer = () => Promise.reject(new Error('unmocked'))
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (url, cfg) => { reads.push({ url, params: cfg?.params }); return restAnswer(url, cfg?.params) },
    post: () => Promise.reject(new Error('no post')) } }
})
import { createPinia, setActivePinia } from 'pinia'
import IndexViewPage from '@/pages/IndexViewPage.vue'
import IndexStrip from '@/components/layout/IndexStrip.vue'
import OptionChainPage from '@/pages/OptionChainPage.vue'
import { createIndexSocket } from '@/composables/useIndexLive'
import { createLiveSocket, useStrategyLive } from '@/composables/useStrategyLive'

class FakeSocket {
  static all = []
  constructor(url) {
    this.url = url
    this.sent = []
    this.readyState = 0
    FakeSocket.all.push(this)
  }
  send(text) { this.sent.push(text) }
  close() { this.readyState = 3 }
  serverOpen() { this.readyState = 1; this.onopen?.() }
  serverPush(obj) { this.onmessage?.({ data: typeof obj === 'string' ? obj : JSON.stringify(obj) }) }
  serverClose() { this.readyState = 3; this.onclose?.() }
}

const BODY = { underlying: 'NIFTY', legs: [{ instrument_id: 'NSE_FO:44626', action: 'SELL', lots: 1 }], ux_level: 'standard' }
const T1 = '2026-10-19T05:32:10+00:00' // 11:02:10 IST
const T1_TEXT = 'Reconnecting - prices as of 11:02:10'
const OUTCOME = (ltp, at = T1) => ({ state: 'COMPUTED', answered_at: at, legs: [{ instrument_id: 'NSE_FO:44626', ltp, label: null }] })
const SLOW_DELAYS = [2000, 4000, 8000, 16000, 30000, 30000, 30000, 30000, 30000, 30000] // requirement: 2, 4, 8 ... capped at 30 s

beforeEach(() => {
  FakeSocket.all = []
  reads.length = 0
  setActivePinia(createPinia())
  vi.stubGlobal('WebSocket', FakeSocket)
  vi.spyOn(Math, 'random').mockReturnValue(0) // no spread here: the spread has its own tests (reconnect-forever.test.js)
})
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks() })

/** A socket whose timers are recorded, so the exact delay of every reconnect attempt can be read. */
function timedSocket(extra = {}) {
  const timers = []
  const statuses = []
  const live = createLiveSocket({ url: 'ws://x/live', WebSocketImpl: FakeSocket, onPush: () => {}, onStatus: (s) => statuses.push(s),
    setTimer: (fn, ms) => { timers.push({ fn, ms }); return timers.length }, clearTimer: () => {}, ...extra })
  return { live, timers, statuses }
}

/** A live screen in miniature: the same useStrategyLive the pages use, its marker, its reconnecting line and a stop button. */
const Probe = defineComponent({
  setup() {
    const live = useStrategyLive({ onPush: () => {}, WebSocketImpl: FakeSocket, url: 'ws://x/live' })
    live.follow(BODY)
    return () => h('div', { 'data-testid': 'screen', 'data-live': live.status.value }, [
      live.reconnecting.value ? h('p', { 'data-testid': 'live-reconnecting' }, live.reconnectingText.value) : null,
      h('i', { 'data-testid': 'rc' }, String(live.reconnecting.value)),
      h('b', { onClick: live.stop }),
    ])
  },
})

describe('AC-2 core: a drop reads as reconnecting at once and the server coming back resumes the screen', () => {
  it('AC-2: live, drop (same tick) -> reconnecting and not live; server refuses 5 s, then back -> live again within 10 s', async () => {
    vi.useFakeTimers()
    const w = mount(Probe)
    expect(w.find('[data-testid="live-reconnecting"]').exists()).toBe(false) // never live yet: connecting is not "reconnecting"
    const first = FakeSocket.all[0]
    first.serverOpen()
    first.serverPush(OUTCOME('30.05'))
    await flushPromises()
    expect(w.get('[data-testid="screen"]').attributes('data-live')).toBe('live')
    first.serverClose()
    await flushPromises() // no timer has run: the same tick
    expect(w.get('[data-testid="screen"]').attributes('data-live')).not.toBe('live')
    expect(w.get('[data-testid="live-reconnecting"]').text()).toBe(T1_TEXT)
    for (let s = 0; s < 5; s += 1) { // the server refuses every attempt for 5 s
      vi.advanceTimersByTime(1000)
      FakeSocket.all.at(-1).serverClose()
      await flushPromises()
      expect(w.get('[data-testid="screen"]').attributes('data-live')).not.toBe('live')
      expect(w.find('[data-testid="live-reconnecting"]').exists()).toBe(true)
    }
    const RESUME_BUDGET_MS = 10000 // REQ-113 AC-2
    let waitedMs = 0
    vi.advanceTimersByTime(1000) // the next attempt: the server accepts
    waitedMs += 1000
    const back = FakeSocket.all.at(-1)
    back.serverOpen()
    await flushPromises()
    expect(w.get('[data-testid="screen"]').attributes('data-live')).not.toBe('live') // accepted but no answer yet: not live
    back.serverPush(OUTCOME('29.60'))
    await flushPromises()
    expect(w.get('[data-testid="screen"]').attributes('data-live')).toBe('live')
    expect(w.find('[data-testid="live-reconnecting"]').exists()).toBe(false)
    expect(waitedMs).toBeLessThanOrEqual(RESUME_BUDGET_MS) // one 1 s attempt after the server was back
  })
})

describe('AC-2: the reconnect timing of the one socket helper', () => {
  it('AC-2: attempts are 1 s apart for the first 30 attempts, then 2, 4, 8 ... capped at 30 s; it never gives up (REQ-113 AC-9)', () => {
    const { live, timers, statuses } = timedSocket()
    live.follow(BODY)
    FakeSocket.all[0].serverClose()
    for (let i = 0; i < 30 + SLOW_DELAYS.length; i += 1) {
      timers[i].fn()
      FakeSocket.all.at(-1).serverClose()
    }
    expect(timers.map((t) => t.ms)).toEqual([...Array(30).fill(1000), ...SLOW_DELAYS, 30000]) // attempt 41 stays at the cap
    expect(statuses.at(-1)).toBe('down') // past the old limit of 40: still retrying, never 'off'
    expect(timers).toHaveLength(41) // attempt 41 is scheduled (at the cap)
  })

  it('AC-2: a real answer ends the drop: the next drop starts again in the fast phase', () => {
    const { live, timers } = timedSocket()
    live.follow(BODY)
    FakeSocket.all[0].serverClose()
    for (let i = 0; i < 34; i += 1) { // deep into the slow phase
      timers[i].fn()
      FakeSocket.all.at(-1).serverClose()
    }
    expect(timers.at(-1).ms).toBe(30000) // the 35th attempt is the 5th slow one: 2, 4, 8, 16, 30 s
    timers.at(-1).fn()
    const ws = FakeSocket.all.at(-1)
    ws.serverOpen()
    ws.serverPush(OUTCOME('30.05'))
    ws.serverClose()
    expect(timers.at(-1).ms).toBe(1000)
  })
})

describe('AC-2: never an old price as live', () => {
  it('AC-2: a push delivered late on the socket that already dropped is not shown, not counted live', () => {
    const pushes = []
    const statuses = []
    const live = createLiveSocket({ url: 'ws://x/live', WebSocketImpl: FakeSocket, onPush: (b) => pushes.push(b), onStatus: (s) => statuses.push(s),
      setTimer: () => 1, clearTimer: () => {} })
    live.follow(BODY)
    const old = FakeSocket.all[0]
    old.serverOpen()
    old.serverPush(OUTCOME('30.05'))
    old.serverClose()
    old.serverPush(OUTCOME('99.99')) // queued before the drop, delivered after it
    expect(pushes).toEqual([OUTCOME('30.05')])
    expect(statuses.at(-1)).toBe('down')
  })

  it('AC-2 (answer states): only an answer push is live; a non-answer, a malformed message, a refused connect and accept-then-silence are not', () => {
    const { live, statuses } = timedSocket()
    live.follow(BODY)
    const ws = FakeSocket.all[0]
    ws.serverPush({ what_happened: 'x' }) // a non-answer message
    ws.serverPush('not json') // malformed
    ws.serverOpen() // accepted, then silent
    expect(statuses).toEqual(['connecting']) // never live
    ws.serverClose() // refused / closed before any answer
    expect(statuses.at(-1)).toBe('down')
    expect(statuses).not.toContain('live')
    ws.serverPush(OUTCOME('1')) // an answer on a socket that is gone is ignored
    expect(statuses).not.toContain('live')
  })

  it('AC-2: live, stop(), follow() again -> the first connect is not "reconnecting"; a drop once live again is', async () => {
    vi.useFakeTimers()
    let handle
    const Again = defineComponent({
      setup() {
        handle = useStrategyLive({ onPush: () => {}, WebSocketImpl: FakeSocket, url: 'ws://x/live' })
        handle.follow(BODY)
        return () => h('i', { 'data-testid': 'rc' }, String(handle.reconnecting.value))
      },
    })
    const w = mount(Again)
    FakeSocket.all[0].serverOpen()
    FakeSocket.all[0].serverPush(OUTCOME('30.05'))
    await flushPromises()
    handle.stop()
    handle.follow(BODY)
    await flushPromises()
    expect(FakeSocket.all).toHaveLength(2) // a new socket, still connecting
    expect(w.get('[data-testid="rc"]').text()).toBe('false')
    FakeSocket.all[1].serverOpen()
    FakeSocket.all[1].serverPush(OUTCOME('29.60'))
    FakeSocket.all[1].serverClose()
    await flushPromises()
    expect(w.get('[data-testid="rc"]').text()).toBe('true')
  })

  it('AC-2: stop() (page left) never reads as reconnecting and never reconnects', async () => {
    vi.useFakeTimers()
    const w = mount(Probe)
    FakeSocket.all[0].serverOpen()
    FakeSocket.all[0].serverPush(OUTCOME('30.05'))
    FakeSocket.all[0].serverClose()
    await flushPromises()
    expect(w.get('[data-testid="rc"]').text()).toBe('true')
    await w.get('b').trigger('click')
    expect(w.get('[data-testid="rc"]').text()).toBe('false')
    vi.advanceTimersByTime(60000)
    expect(FakeSocket.all).toHaveLength(1)
  })
})

describe('AC-2: the chain and index screens show the same reconnecting text from the one constant', () => {
  it('AC-2: the index socket is built on the one helper (same fast phase)', () => {
    const timers = []
    const s = createIndexSocket({ url: 'ws://x', WebSocketImpl: FakeSocket, onPush: () => {}, setTimer: (fn, ms) => { timers.push({ fn, ms }); return timers.length }, clearTimer: () => {} })
    s.start()
    FakeSocket.all[0].serverClose()
    for (let i = 0; i < 3; i += 1) { timers[i].fn(); FakeSocket.all.at(-1).serverClose() }
    expect(timers.map((t) => t.ms)).toEqual([1000, 1000, 1000, 1000])
  })

  it('AC-2: the index page says reconnecting after a drop (once live), nothing before and nothing after stop', async () => {
    const indexRow = (u, value) => ({ underlying: u, instrument_id: `I:${u}`, value, at: '2026-10-19T09:20:00+05:30', health: 'available' })
    const answer = { state: 'LIVE', indices: [indexRow('NIFTY', '25145.50'), indexRow('SENSEX', '82010.25')], answered_at: '2026-10-19T03:50:01+00:00' }
    restAnswer = () => Promise.resolve({ data: { state: 'NOT_CONNECTED', indices: [] } })
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:p(.*)*', component: { template: '<div />' } }] })
    const w = mount(IndexViewPage, { global: { plugins: [router] } })
    await flushPromises()
    expect(w.find('[data-testid="live-reconnecting"]').exists()).toBe(false)
    FakeSocket.all[0].serverPush(answer)
    await flushPromises()
    expect(w.find('[data-testid="live-reconnecting"]').exists()).toBe(false)
    FakeSocket.all[0].serverClose()
    await flushPromises()
    expect(w.get('[data-testid="live-reconnecting"]').text()).toBe('Reconnecting - prices as of 09:20:01')
    const strip = mount(IndexStrip, { global: { plugins: [router] } })
    await flushPromises()
    FakeSocket.all.at(-1).serverPush(answer)
    await flushPromises()
    FakeSocket.all.at(-1).serverClose()
    await flushPromises()
    expect(strip.get('[data-testid="live-reconnecting"]').text()).toBe('Reconnecting - prices as of 09:20:01')
  })

  it('AC-2: the chain page says the same text after a drop, and the live marker leaves live', async () => {
    restAnswer = (url) => {
      if (url.startsWith('/catalogue/')) return Promise.resolve({ data: { expiries: ['2026-10-27'] } })
      return Promise.resolve({ data: { state: 'NOT_CONNECTED', underlying: 'NIFTY', expiry: '2026-10-27', spot: null, spot_at: null, spot_health: null, atm_strike: null, rows_missing: null, rows: [] } })
    }
    const w = mount(OptionChainPage)
    await flushPromises()
    const ws = FakeSocket.all[0]
    ws.serverOpen()
    ws.serverPush({ state: 'LIVE', underlying: 'NIFTY', expiry: '2026-10-27', spot: '24510.00', spot_at: '2026-10-19T10:00:00+05:30', spot_health: 'available', atm_strike: '24500.00', rows_missing: null, rows: [], answered_at: '2026-10-19T04:30:05+00:00' })
    await flushPromises()
    expect(w.get('[data-testid="socket-status"]').text()).toBe('live')
    expect(w.find('[data-testid="live-reconnecting"]').exists()).toBe(false)
    ws.serverClose()
    await flushPromises()
    expect(w.get('[data-testid="live-reconnecting"]').text()).toBe('Reconnecting - prices as of 10:00:05')
    expect(w.get('[data-testid="socket-status"]').text()).not.toBe('live')
  })
})

describe('REQ-114 AC-5: "Reconnecting - prices as of <time>" until the first fresh push', () => {
  async function liveThenDrop(first = OUTCOME('30.05')) {
    const w = mount(Probe)
    FakeSocket.all[0].serverOpen()
    FakeSocket.all[0].serverPush(first)
    await flushPromises()
    FakeSocket.all[0].serverClose()
    await flushPromises()
    return w
  }
  const text = (w) => w.find('[data-testid="live-reconnecting"]').text()

  it('AC-5 (1): reconnected with no fresh push -> the exact text with the last push time (IST); nothing live', async () => {
    vi.useFakeTimers()
    const w = await liveThenDrop()
    vi.advanceTimersByTime(1000)
    FakeSocket.all.at(-1).serverOpen() // reconnected, no push yet
    await flushPromises()
    expect(text(w)).toBe('Reconnecting - prices as of 11:02:10')
    expect(w.get('[data-testid="screen"]').attributes('data-live')).not.toBe('live')
  })

  it('AC-5 (2): the first fresh push -> live, the text gone; the next drop shows the NEW push time', async () => {
    vi.useFakeTimers()
    const w = await liveThenDrop()
    vi.advanceTimersByTime(1000)
    const back = FakeSocket.all.at(-1)
    back.serverOpen()
    back.serverPush(OUTCOME('29.60', '2026-10-19T05:40:00+00:00'))
    await flushPromises()
    expect(w.get('[data-testid="screen"]').attributes('data-live')).toBe('live')
    expect(w.find('[data-testid="live-reconnecting"]').exists()).toBe(false)
    back.serverClose()
    await flushPromises()
    expect(text(w)).toBe('Reconnecting - prices as of 11:10:00')
  })

  it('AC-5 (3): the time is the push server time in IST, not the browser clock (clock 5 h off changes nothing)', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-10-19T10:32:10+00:00')) // 5 h ahead of the push
    const w = await liveThenDrop()
    expect(text(w)).toBe('Reconnecting - prices as of 11:02:10')
    expect(text(w)).not.toContain('16:02')
  })

  it('AC-5 (4): no price ever arrived (or an unreadable / missing push time) -> the text without a time', async () => {
    vi.useFakeTimers()
    const w = await liveThenDrop(OUTCOME('30.05', 'not a time'))
    expect(text(w)).toBe('Live prices are reconnecting')
    w.unmount()
    FakeSocket.all = []
    const w2 = await liveThenDrop({ state: 'COMPUTED', legs: [] }) // no answered_at at all
    expect(w2.find('[data-testid="live-reconnecting"]').text()).toBe('Live prices are reconnecting')
  })

  it('AC-5 (answer states): a not-connected answer is no price: it does not move the time', async () => {
    vi.useFakeTimers()
    const w = mount(Probe)
    const ws = FakeSocket.all[0]
    ws.serverOpen()
    ws.serverPush(OUTCOME('30.05'))
    ws.serverPush({ state: 'NOT_CONNECTED', answered_at: '2026-10-19T09:00:00+00:00', legs: [] })
    ws.serverClose()
    await flushPromises()
    expect(text(w)).toBe('Reconnecting - prices as of 11:02:10')
  })

  it('AC-5 (5): every live screen takes its text from the one helper; none builds its own string', () => {
    const sources = import.meta.glob(['/src/pages/*.vue', '/src/components/**/*.vue'], { query: '?raw', import: 'default', eager: true })
    const withMarker = Object.entries(sources).filter(([, src]) => src.includes('live-reconnecting'))
    const names = withMarker.map(([f]) => f.split('/').pop()).sort()
    expect(names).toEqual(['ExecuteStrategyPage.vue', 'IndexStrip.vue', 'IndexViewPage.vue', 'LiveStrategyCard.vue', 'OptionChainPage.vue', 'StrategyBuilderPage.vue'])
    for (const [, src] of withMarker) {
      expect(src).toMatch(/reconnectingText/)
      expect(src).not.toMatch(/Reconnecting - prices|reconnecting'|Live prices are/i)
    }
  })
})
