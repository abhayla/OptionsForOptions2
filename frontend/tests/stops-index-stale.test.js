// C-12b (owner Part C, 26 Nov 2026): with the price feed down the Stops panel kept "NIFTY now 25923.40 as of 12:06:13" for 86 s.
// Root cause: the index socket stays open while the feed is down; the server then pushes the SAME LIVE answer with the row's
// health no longer "available" (stale / unavailable), and the one reader (useIndexAnswer) took the answer's state alone.
// The panel must say "Index values unavailable." with no digits whenever the row it shows is not healthy. Expected texts are
// written here, never read back from the panel.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { echoSeq } from './helpers/echoSeq'

vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (url) => (url.includes('triggers') ? Promise.resolve({ data: { triggers: [] } }) : Promise.reject({ message: 'no answer' })) } }
})
import PaperStops from '@/components/strategy/PaperStops.vue'

class FakeSocket {
  static all = []
  constructor(url) { this.url = url; FakeSocket.all.push(this) }
  send() {}
  close() {}
  serverPush(obj) { this.onmessage?.({ data: JSON.stringify(echoSeq(this, obj)) }) }
}
const T = '2026-11-26T06:36:13Z' // 12:06:13 IST
const row = (u, value, health) => ({ underlying: u, instrument_id: u, value, at: T, health })
const answer = (rows, over = {}) => ({ state: 'LIVE', market_closed: false, last_price_at: T, answered_at: T, indices: rows, ...over })

async function open() {
  const w = mount(PaperStops, { props: { strategyId: 48, underlying: 'NIFTY', legs: [] } })
  await flushPromises()
  return w
}
const line = (w) => w.find('[data-testid="stops-index"]').text()

beforeEach(() => { FakeSocket.all = []; vi.stubGlobal('WebSocket', FakeSocket) })
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

describe('Stops panel index line follows the reader freshness (C-12b)', () => {
  it('live: shows the value and its time', async () => {
    const w = await open()
    FakeSocket.all[0].serverPush(answer([row('NIFTY', '25,923.40', 'available')]))
    await flushPromises()
    expect(line(w)).toBe('NIFTY now 25,923.40 as of 12:06:13')
  })
  it.each(['stale', 'unavailable', 'unhealthy', 'delayed'])('feed down: the same LIVE answer with row health %s reads "Index values unavailable."', async (health) => {
    const w = await open()
    const ws = FakeSocket.all[0]
    ws.serverPush(answer([row('NIFTY', '25,923.40', 'available')]))
    await flushPromises()
    ws.serverPush(answer([row('NIFTY', '25,923.40', health)]))
    await flushPromises()
    expect(line(w)).toBe('Index values unavailable.')
    expect(line(w)).not.toMatch(/\d/)
  })
  it('never answered: unavailable with no digits', async () => {
    const w = await open()
    expect(line(w)).toBe('Index values unavailable.')
  })
  it('wrong underlying: a SENSEX row never stands in for a NIFTY panel', async () => {
    const w = await open()
    FakeSocket.all[0].serverPush(answer([row('SENSEX', '82,010.25', 'available')]))
    await flushPromises()
    expect(line(w)).not.toMatch(/82,010/)
  })
})
