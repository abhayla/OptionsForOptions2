// W-115 round 2 (REQ-049 AC-4; REQ-072 AC-2; REQ-008 AC-4): the four socket-drop cases run as ONE table over BOTH screens
// that show index values (the index page and the Home strip), because both read one state machine (useIndexAnswer).
// Expected texts are the pushes the tests write, never the screens' output.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

let apiAnswer = null
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (url, config) => (typeof apiAnswer === 'function'
    ? apiAnswer(config?.params ?? {}) : Promise.resolve({ data: apiAnswer })) } }
})
import IndexViewPage from '@/pages/IndexViewPage.vue'
import IndexStrip from '@/components/layout/IndexStrip.vue'

class FakeSocket {
  static all = []
  constructor(url) { this.url = url; FakeSocket.all.push(this) }
  send() {}
  close() {}
  serverPush(obj) { this.onmessage?.({ data: JSON.stringify(obj) }) }
  serverClose() { this.onclose?.() }
}

const row = (underlying, value, at, health = 'available') => ({
  underlying, instrument_id: underlying === 'NIFTY' ? 'NSE_INDEX:256265' : 'BSE_INDEX:265', value, at, health })
const live = (n, s, at) => ({ state: 'LIVE', indices: [row('NIFTY', n, at), row('SENSEX', s, at)], answered_at: at })
const notConnected = (at) => ({ state: 'NOT_CONNECTED', answered_at: at,
  indices: [row('NIFTY', null, at, null), row('SENSEX', null, at, null)] })
const T1 = '2026-10-19T09:20:00+05:30'
const T2 = '2026-10-19T09:20:01+05:30'

const SCREENS = [
  { name: 'index page', component: IndexViewPage, value: 'index-value', state: 'index-state' },
  { name: 'Home strip', component: IndexStrip, value: 'strip-value', state: 'strip-state' },
]

beforeEach(() => {
  FakeSocket.all = []
  apiAnswer = null
  vi.stubGlobal('WebSocket', FakeSocket)
})
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

describe.each(SCREENS)('$name: after its own socket drops no old number is shown', (screen) => {
  async function mountScreen() {
    const w = mount(screen.component, { global: { stubs: { 'router-link': true } } })
    await flushPromises()
    return w
  }
  const values = (w) => w.findAll(`[data-testid="${screen.value}"]`).map((e) => e.text())

  async function liveThenDrop(w) {
    const ws = FakeSocket.all[0]
    ws.serverPush(live('25150.00', '82010.25', T1))
    await flushPromises()
    expect(values(w)).toEqual(['25150.00', '82010.25'])
    ws.serverClose()
    await flushPromises()
  }

  const fallbacks = {
    'the fallback read rejects': () => Promise.reject(new Error('down')),
    'the fallback read answers NOT_CONNECTED': () => Promise.resolve({ data: notConnected(T1) }),
  }
  for (const [label, fallback] of Object.entries(fallbacks)) {
    it(`AC-4: LIVE push, drop, ${label} -> no number anywhere`, async () => {
      apiAnswer = (params) => (params.fallback ? fallback() : Promise.resolve({ data: notConnected(null) }))
      const w = await mountScreen()
      await liveThenDrop(w)
      expect(w.text()).not.toContain('25150.00')
      expect(w.text()).not.toContain('82010.25')
      expect(values(w)).toEqual(['Not available', 'Not available'])
      expect(w.get(`[data-testid="${screen.state}"]`).text()).toBe('Index values unavailable.')
    })
  }

  it('AC-4: LIVE push, drop, the fallback read hangs -> no number anywhere', async () => {
    apiAnswer = (params) => (params.fallback ? new Promise(() => {}) : Promise.resolve({ data: notConnected(null) }))
    const w = await mountScreen()
    await liveThenDrop(w)
    expect(w.text()).not.toContain('25150.00')
    expect(values(w)).toEqual(['Not available', 'Not available'])
    expect(w.get(`[data-testid="${screen.state}"]`).text()).toBe('Index values unavailable.')
  })

  it('AC-4: a read sent before the drop that resolves LIVE after it is ignored', async () => {
    let release
    const held = new Promise((resolve) => { release = resolve })
    apiAnswer = (params) => (params.fallback ? Promise.resolve({ data: notConnected(null) }) : held)
    const w = await mountScreen()
    FakeSocket.all[0].serverClose()
    await flushPromises()
    release({ data: live('25150.00', '82010.25', T1) })
    await flushPromises()
    expect(w.text()).not.toContain('25150.00')
    expect(values(w)).toEqual(['Not available', 'Not available'])
  })

  it('AC-4: a NEW live push after the drop shows the number again', async () => {
    vi.useFakeTimers()
    apiAnswer = (params) => (params.fallback ? Promise.reject(new Error('down')) : Promise.resolve({ data: notConnected(null) }))
    const w = await mountScreen()
    await liveThenDrop(w)
    await vi.advanceTimersByTimeAsync(1000) // the reconnect backoff opens a new socket
    FakeSocket.all[1].serverPush(live('25151.00', '82011.00', T2))
    await flushPromises()
    expect(values(w)).toEqual(['25151.00', '82011.00'])
    expect(w.find(`[data-testid="${screen.state}"]`).exists()).toBe(false)
  })
})
