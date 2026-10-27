// Finding live-read-without-own-subscription (#583, I-6): on the EMPTY builder the header shows the index from the
// page's own index socket (/api/market/indices/live), and the existing dash when that source is down.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reject = (url) => Promise.reject(new Error(`unmocked ${url}`))
  return { ...actual, default: { get: reject, post: reject } }
})
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import { headerLevel } from '@/composables/useIndexLive'

class FakeSocket {
  static all = []
  constructor(url) { this.url = url; this.readyState = 0; FakeSocket.all.push(this) }
  send() {}
  close() {}
  serverOpen() { this.readyState = 1; this.onopen?.() }
  serverPush(obj) { this.onmessage?.({ data: JSON.stringify(obj) }) }
  serverClose() { this.readyState = 3; this.onclose?.() }
}
const AT = '2026-10-27T09:23:40+05:30'
const row = (underlying, value) => ({ underlying, instrument_id: `${underlying}_ID`, value, at: AT, health: 'available' })
const LIVE = { state: 'LIVE', indices: [row('NIFTY', '22810.00'), row('SENSEX', '74000.00')], answered_at: AT }
const spotText = (w) => w.find('[data-testid="underlying-spot"]').text()
const indexSocket = () => FakeSocket.all.find((s) => s.url.endsWith('/api/market/indices/live'))

beforeEach(() => {
  FakeSocket.all = []
  vi.stubGlobal('WebSocket', FakeSocket)
  document.body.innerHTML = ''
})
afterEach(() => vi.unstubAllGlobals())

async function emptyBuilder() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await router.push('/strategy/builder')
  await router.isReady()
  const w = mount(StrategyBuilderPage, { attachTo: document.body, global: { plugins: [router], stubs: { PayoffChart: true } } })
  await flushPromises()
  return w
}

describe('I-6: the empty builder header holds the index itself', () => {
  it('opens its own index socket and shows the pushed NIFTY value with no legs', async () => {
    const w = await emptyBuilder()
    expect(spotText(w)).toBe('—')
    const ws = indexSocket()
    expect(ws).toBeTruthy()
    ws.serverOpen()
    ws.serverPush(LIVE)
    await flushPromises()
    expect(spotText(w)).toBe('22810.00')
  })

  it('shows the dash and the not-live wording when the index source is down', async () => {
    const w = await emptyBuilder()
    const ws = indexSocket()
    ws.serverOpen()
    ws.serverPush(LIVE)
    ws.serverClose()
    await flushPromises()
    expect(spotText(w)).toBe('—')
    expect(w.find('[data-testid="underlying-spot"]').attributes('title')).toBe('Index values unavailable.')
  })

  it('headerLevel: the outcome level wins, else the index value, else null (never "Not available")', () => {
    expect(headerLevel('22,805.00', '22810.00')).toBe('22,805.00')
    expect(headerLevel(null, '22810.00')).toBe('22810.00')
    expect(headerLevel(undefined, 'Not available')).toBeNull()
  })
})
