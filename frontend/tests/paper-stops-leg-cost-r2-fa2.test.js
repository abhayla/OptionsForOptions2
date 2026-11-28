// Lane FA2 item 4 (PC note UX-A02): beside each leg's Stop price box the panel says what the leg costs now, from the leg's own price
// (`ltpText`, as the server sent it); "not priced" when absent; never a guess.
import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: () => Promise.resolve({ data: { triggers: [] } }), post: () => Promise.reject(new Error('x')), delete: () => Promise.reject(new Error('x')) } }
})
import PaperStops from '@/components/strategy/PaperStops.vue'

const legs = [{ index: 5000, label: 'NIFTY 22300 PE', contractId: '5000', ltpText: '131.40' }, { index: 5001, label: 'NIFTY 22400 PE', contractId: '5001', ltpText: null }, { index: 5002, label: 'NIFTY 22500 PE', contractId: '5002' }]
const cost = (w, i) => w.get(`[data-testid="stop-cost-${i}"]`).text()
describe('leg cost beside the Stop price box', () => {
  it('shows the price as given; "not priced" for null; nothing when the parent passes no price', async () => {
    const w = mount(PaperStops, { props: { strategyId: 48, underlying: 'NIFTY', legs } })
    await flushPromises()
    expect(cost(w, 5000)).toBe('Costs now 131.40')
    expect(cost(w, 5001)).toBe('Costs now: not priced')
    expect(w.find('[data-testid="stop-cost-5002"]').exists()).toBe(false) // review S4: a parent that passes no price says nothing (never a false "not priced")
    w.unmount()
  })
})
