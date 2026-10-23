// W-114 (REQ-072 AC-2; REQ-049 AC-4; ADR-077, ADR-008): the Underlying/index view and its read-only index socket, with a
// fake socket and a mocked REST read. Expected texts come from the pushes the tests write, never from the page's output.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

const apiCalls = []
let apiAnswer = null
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (url, config) => {
    apiCalls.push({ url, params: config?.params ?? {} })
    return typeof apiAnswer === 'function' ? apiAnswer(config?.params ?? {}) : Promise.resolve({ data: apiAnswer })
  } } }
})
import IndexViewPage from '@/pages/IndexViewPage.vue'
import { INDEX_LIVE_PATH, INDEX_REST_PATH, createIndexSocket, indexLiveUrl, isIndicesAnswer } from '@/composables/useIndexLive'
import { FAST_ATTEMPTS, MAX_ATTEMPTS } from '@/composables/useStrategyLive'

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

const row = (underlying, value, at, health = 'available') => ({
  underlying, instrument_id: underlying === 'NIFTY' ? 'NSE_INDEX:256265' : 'BSE_INDEX:265', value, at, health })
const live = (nifty, sensex) => ({ state: 'LIVE', indices: [nifty, sensex], answered_at: '2026-10-19T03:50:01+00:00' })
const notConnected = (at) => ({ state: 'NOT_CONNECTED', answered_at: '2026-10-19T03:50:09+00:00',
  indices: [row('NIFTY', null, at, null), row('SENSEX', null, at, null)] })
const T1 = '2026-10-19T09:20:00+05:30'
const T2 = '2026-10-19T09:20:01+05:30'

async function mountPage() {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/market/underlying-index-view', component: IndexViewPage },
    { path: '/:p(.*)*', component: { template: '<div />' } }] })
  router.push('/market/underlying-index-view')
  await router.isReady()
  const wrapper = mount(IndexViewPage, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

const panel = (w, u) => w.get(`[data-testid="index-panel-${u}"]`)

beforeEach(() => {
  FakeSocket.all = []
  apiCalls.length = 0
  apiAnswer = null
  vi.stubGlobal('WebSocket', FakeSocket)
})
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

describe('the index socket lifecycle', () => {
  it('AC-2: opens the same-origin path, sends nothing, passes each index answer untouched, ignores anything else', () => {
    const pushes = []
    const s = createIndexSocket({ url: 'ws://app.test' + INDEX_LIVE_PATH, WebSocketImpl: FakeSocket, onPush: (m) => pushes.push(m) })
    s.start()
    const ws = FakeSocket.all[0]
    ws.serverOpen() // the open handler is where a body would be sent
    ws.serverPush(live(row('NIFTY', '25145.50', T1), row('SENSEX', '82010.25', T1)))
    ws.serverPush({ what_happened: 'x' }) // a catalogue error is not an index answer
    ws.serverPush('not json')
    expect(ws.url).toBe('ws://app.test/api/market/indices/live')
    expect(ws.sent).toEqual([])
    expect(pushes).toHaveLength(1)
    expect(pushes[0].indices[0].value).toBe('25145.50')
    expect(indexLiveUrl({ protocol: 'https:', host: 'h.test' })).toBe('wss://h.test/api/market/indices/live')
    expect(isIndicesAnswer({ state: 'COMPUTED', indices: [] })).toBe(false)
  })

  it('AC-2: a drop calls onDown and reconnects on the shared backoff; it stops after the fast and slow limits', () => {
    const timers = []
    const onDown = vi.fn()
    const s = createIndexSocket({ url: 'ws://x', WebSocketImpl: FakeSocket, onPush: () => {}, onDown,
      setTimer: (fn, ms) => { timers.push({ fn, ms }); return timers.length }, clearTimer: () => {} })
    s.start()
    FakeSocket.all[0].serverClose()
    expect(onDown).toHaveBeenCalledTimes(1)
    expect(timers[0].ms).toBe(1000)
    const TOTAL = FAST_ATTEMPTS + MAX_ATTEMPTS
    for (let i = 1; i < TOTAL; i += 1) {
      timers[i - 1].fn()
      FakeSocket.all[i].serverClose()
    }
    expect(timers.map((t) => t.ms).slice(0, 3)).toEqual([1000, 1000, 1000])
    timers[TOTAL - 1].fn()
    FakeSocket.all[TOTAL].serverClose()
    expect(timers).toHaveLength(TOTAL) // no attempt past the limit
  })
})

describe('the Underlying/index view page', () => {
  it('AC-2: two pushes with different times show each value and its time, NIFTY 50 and SENSEX', async () => {
    apiAnswer = notConnected(null)
    const w = await mountPage()
    const ws = FakeSocket.all[0]
    ws.serverPush(live(row('NIFTY', '25145.50', T1), row('SENSEX', '82010.25', T1)))
    await flushPromises()
    expect(panel(w, 'NIFTY').get('[data-testid="index-value"]').text()).toBe('25145.50')
    expect(panel(w, 'NIFTY').get('[data-testid="index-at"]').text()).toBe('as of 19 Oct 2026, 09:20:00 IST')
    ws.serverPush(live(row('NIFTY', '25146.00', T2), row('SENSEX', '82012.75', T2)))
    await flushPromises()
    expect(panel(w, 'NIFTY').get('[data-testid="index-value"]').text()).toBe('25146.00')
    expect(panel(w, 'SENSEX').get('[data-testid="index-value"]').text()).toBe('82012.75')
    expect(panel(w, 'SENSEX').get('[data-testid="index-at"]').text()).toBe('as of 19 Oct 2026, 09:20:01 IST')
    expect(w.find('[data-testid="index-state"]').exists()).toBe(false)
    expect(panel(w, 'NIFTY').find('[data-testid="index-health"]').exists()).toBe(false) // available: no word
    expect(w.get('[data-testid="index-link-chain"]').attributes('href')).toBe('/market/option-chain')
    expect(w.get('[data-testid="index-link-live"]').attributes('href')).toBe('/strategies/live-strategies')
    expect(w.text()).not.toMatch(/buy|sell/i) // no order buttons (ADR-002)
  })

  it('AC-4 (RD-045): a health word carries its one-sentence reason; available carries none', async () => {
    apiAnswer = live(row('NIFTY', '25145.50', T1, 'stale'), row('SENSEX', '82010.25', T1, 'unavailable'))
    const w = await mountPage()
    expect(panel(w, 'NIFTY').get('[data-testid="index-health-reason"]').text()).toBe('Stale: the latest price for this contract is older than expected, so the figure may be out of date.')
    expect(panel(w, 'SENSEX').get('[data-testid="index-health-reason"]').text()).toBe('Unavailable: no price has been received for this contract, so no figure is shown.')
    apiAnswer = live(row('NIFTY', '25145.50', T1), row('SENSEX', '82010.25', T1))
    expect((await mountPage()).find('[data-testid="index-health-reason"]').exists()).toBe(false)
  })

  it('AC-2: a stale health shows its word beside the value', async () => {
    apiAnswer = live(row('NIFTY', '25145.50', T1, 'stale'), row('SENSEX', '82010.25', T1, 'unavailable'))
    const w = await mountPage()
    expect(panel(w, 'NIFTY').get('[data-testid="index-health"]').text()).toBe('stale')
    expect(panel(w, 'SENSEX').get('[data-testid="index-health"]').text()).toBe('unavailable')
  })

  it('AC-2: socket down -> the page asks REST with fallback and shows the not-live state, never the old number', async () => {
    apiAnswer = (params) => Promise.resolve({ data: params.fallback ? notConnected(T1) : notConnected(null) })
    const w = await mountPage()
    const ws = FakeSocket.all[0]
    ws.serverPush(live(row('NIFTY', '25145.50', T1), row('SENSEX', '82010.25', T1)))
    await flushPromises()
    ws.serverClose()
    await flushPromises()
    expect(apiCalls.at(-1)).toEqual({ url: INDEX_REST_PATH, params: { fallback: true } })
    expect(w.get('[data-testid="index-state"]').text()).toBe('Index values unavailable.')
    expect(panel(w, 'NIFTY').get('[data-testid="index-value"]').text()).toBe('Not available')
    expect(panel(w, 'NIFTY').get('[data-testid="index-at"]').text()).toBe('Last updated 19 Oct 2026, 09:20:00 IST')
    expect(w.text()).not.toContain('25145.50')
  })

  it('AC-2: a drop with a failing fallback read shows no number from the earlier LIVE push (round 2 finding 1)', async () => {
    apiAnswer = (params) => (params.fallback ? Promise.reject(new Error('down')) : Promise.resolve({ data: notConnected(null) }))
    const w = await mountPage()
    const ws = FakeSocket.all[0]
    ws.serverPush(live(row('NIFTY', '25150.00', T1), row('SENSEX', '82010.25', T1)))
    await flushPromises()
    expect(panel(w, 'NIFTY').get('[data-testid="index-value"]').text()).toBe('25150.00')
    ws.serverClose()
    await flushPromises()
    expect(w.text()).not.toContain('25150.00')
    expect(w.text()).not.toContain('82010.25')
    for (const u of ['NIFTY', 'SENSEX']) {
      expect(panel(w, u).get('[data-testid="index-value"]').text()).toBe('Not available')
      expect(panel(w, u).get('[data-testid="index-at"]').text()).toBe('Last updated 19 Oct 2026, 09:20:00 IST')
    }
    expect(w.get('[data-testid="index-state"]').text()).toBe('Index values unavailable.')
  })

  it('AC-2: a drop, then the fallback answers NOT_CONNECTED -> no number', async () => {
    apiAnswer = (params) => Promise.resolve({ data: params.fallback ? notConnected(T1) : notConnected(null) })
    const w = await mountPage()
    const ws = FakeSocket.all[0]
    ws.serverPush(live(row('NIFTY', '25150.00', T1), row('SENSEX', '82010.25', T1)))
    await flushPromises()
    ws.serverClose()
    await flushPromises()
    expect(w.text()).not.toContain('25150.00')
    expect(panel(w, 'SENSEX').get('[data-testid="index-value"]').text()).toBe('Not available')
  })

  it('AC-2: a first-paint read sent before the drop and resolving LIVE after it is ignored (round 2 finding 2)', async () => {
    let release
    const held = new Promise((resolve) => { release = resolve })
    apiAnswer = (params) => (params.fallback ? Promise.resolve({ data: notConnected(null) }) : held)
    const w = await mountPage()
    FakeSocket.all[0].serverClose()
    await flushPromises()
    release({ data: live(row('NIFTY', '25150.00', T1), row('SENSEX', '82010.25', T1)) })
    await flushPromises()
    expect(w.text()).not.toContain('25150.00')
    expect(panel(w, 'NIFTY').get('[data-testid="index-value"]').text()).toBe('Not available')
    expect(w.get('[data-testid="index-state"]').text()).toBe('Index values unavailable.')
  })

  it('AC-2: after a drop a NEW live push shows the number again', async () => {
    vi.useFakeTimers()
    apiAnswer = (params) => (params.fallback ? Promise.reject(new Error('down')) : Promise.resolve({ data: notConnected(null) }))
    const w = await mountPage()
    const ws = FakeSocket.all[0]
    ws.serverPush(live(row('NIFTY', '25150.00', T1), row('SENSEX', '82010.25', T1)))
    await flushPromises()
    ws.serverClose()
    await flushPromises()
    await vi.advanceTimersByTimeAsync(1000) // the reconnect backoff opens a new socket
    FakeSocket.all[1].serverPush(live(row('NIFTY', '25151.00', T2), row('SENSEX', '82011.00', T2)))
    await flushPromises()
    expect(panel(w, 'NIFTY').get('[data-testid="index-value"]').text()).toBe('25151.00')
    expect(panel(w, 'SENSEX').get('[data-testid="index-value"]').text()).toBe('82011.00')
    expect(w.find('[data-testid="index-state"]').exists()).toBe(false)
  })

  it('AC-2: a null value in a LIVE answer is never rendered as a number', async () => {
    apiAnswer = live(row('NIFTY', null, null, 'unavailable'), row('SENSEX', '82010.25', T1))
    const w = await mountPage()
    expect(panel(w, 'NIFTY').get('[data-testid="index-value"]').text()).toBe('Not available')
    expect(panel(w, 'SENSEX').get('[data-testid="index-value"]').text()).toBe('82010.25')
  })

  it('AC-2: a NOT_CONNECTED answer never shows a number, even one carrying a value', async () => {
    const answer = notConnected(T1)
    answer.indices[0].value = '25145.50'
    apiAnswer = answer
    const w = await mountPage()
    expect(panel(w, 'NIFTY').get('[data-testid="index-value"]').text()).toBe('Not available')
    expect(w.text()).not.toContain('25145.50')
  })
})
