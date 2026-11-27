// ADR-330 (56) (owner 27 Nov 2026): "the notice shows ONCE at the top of the screen, with the time". Expected texts are written
// here, never read back from the component. Sweep rows: Stops panel closed-market line, Live Strategies load time, Positions banner.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { echoSeq } from './helpers/echoSeq'

vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (url) => (url.includes('triggers') ? Promise.resolve({ data: { triggers: [] } }) : Promise.reject({ message: 'no answer' })) } }
})
import PriceNotice from '@/components/states/PriceNotice.vue'
import PaperStops from '@/components/strategy/PaperStops.vue'
import { notLiveNotice } from '@/lib/priceState'

const CLOSE = '2026-11-27T10:00:00Z' // 15:30:00 IST
const LAST = '2026-11-27T10:28:01Z' // 15:58:01 IST
const idx = (over = {}) => ({ state: 'LIVE', market_closed: false, last_price_at: LAST, indices: [], ...over })

describe('ADR-330 (56) the one price notice', () => {
  it('closed: the market-closed banner with the CLOSE time, no not-live sentence', () => {
    const w = mount(PriceNotice, { props: { answer: idx({ market_closed: true, last_price_at: CLOSE }) } })
    expect(w.get('[data-testid="market-closed-text"]').text()).toBe('Market closed. Prices are from 27 Nov 2026, 15:30:00 IST.')
    expect(w.find('[data-testid="price-notice"]').exists()).toBe(false)
  })
  it('feed down while open: ONE sentence with the last captured price time, never a load time', () => {
    const w = mount(PriceNotice, { props: { answer: idx({ state: 'NOT_CONNECTED' }) } })
    expect(w.findAll('[data-testid="price-notice"]')).toHaveLength(1)
    expect(w.get('[data-testid="price-notice-text"]').text()).toBe('Prices are not live. Figures are as of 15:58:01 IST.')
  })
  it('feed down with no readable time: no clause and no invented time', () => {
    expect(notLiveNotice(null)).toBe('Prices are not live.')
    expect(notLiveNotice('garbage')).toBe('Prices are not live.')
  })
  it('live: nothing is shown', () => {
    const w = mount(PriceNotice, { props: { answer: idx() } })
    expect(w.text()).toBe('')
  })
  it('no answer yet: nothing is shown (no guessed state)', () => {
    expect(mount(PriceNotice, { props: { answer: null } }).text()).toBe('')
  })
  it('a reply that is stale carries its own last price time', () => {
    const w = mount(PriceNotice, { props: { answer: idx(), reply: { last_price_at: LAST }, pageState: 'stale' } })
    expect(w.get('[data-testid="price-notice-text"]').text()).toBe('Prices are not live. Figures are as of 15:58:01 IST.')
  })
})

class FakeSocket {
  static all = []
  constructor(url) { this.url = url; FakeSocket.all.push(this) }
  send() {}
  close() {}
  serverPush(obj) { this.onmessage?.({ data: JSON.stringify(echoSeq(this, obj)) }) }
}
describe('Stops panel after the close (sweep row)', () => {
  beforeEach(() => { FakeSocket.all = []; vi.stubGlobal('WebSocket', FakeSocket) })
  afterEach(() => { vi.unstubAllGlobals() })
  it('closed market with a value: the last value and its time, not "Index values unavailable."', async () => {
    const w = mount(PaperStops, { props: { strategyId: 48, underlying: 'NIFTY', legs: [] } })
    await flushPromises()
    FakeSocket.all[0].serverPush({ state: 'LIVE', market_closed: true, last_price_at: LAST, answered_at: LAST,
      indices: [{ underlying: 'NIFTY', instrument_id: 'NIFTY', value: '25,607.20', at: LAST, health: 'available' }] })
    await flushPromises()
    expect(w.get('[data-testid="stops-index"]').text()).toBe('NIFTY last 25,607.20 as of 15:58:01')
  })
})
