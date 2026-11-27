// ADR-330 (56) round 2: with the page notice up, the strip's own "Index values unavailable." is not repeated.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

let indices = null
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: () => (indices ? Promise.resolve({ data: indices }) : Promise.reject(new Error('no answer'))) } }
})
import IndexStrip from '@/components/layout/IndexStrip.vue'

class FakeSocket { constructor() { this.readyState = 0 } send() {} close() {} }
beforeEach(() => { vi.stubGlobal('WebSocket', FakeSocket) })

describe('IndexStrip not-live line (ADR-330 (56))', () => {
  it('feed down, answer read: the notice with the last price time, and no second sentence', async () => {
    indices = { state: 'NOT_CONNECTED', market_closed: false, last_price_at: '2026-11-27T10:28:01Z', answered_at: '2026-11-27T10:43:47Z',
      indices: [{ underlying: 'NIFTY', instrument_id: 'n', value: null, at: '2026-11-27T10:28:01Z', health: null }] }
    const w = mount(IndexStrip)
    await flushPromises()
    expect(w.get('[data-testid="price-notice-text"]').text()).toBe('Prices are not live. Figures are as of 15:58:01 IST.')
    expect(w.find('[data-testid="strip-state"]').exists()).toBe(false)
  })
  it('no answer at all (the read failed): the strip keeps its own line, there is no notice to repeat', async () => {
    indices = null
    const w = mount(IndexStrip)
    await flushPromises()
    expect(w.find('[data-testid="price-notice"]').exists()).toBe(false)
    expect(w.get('[data-testid="strip-state"]').text()).toBe('Index values unavailable.')
  })
})
