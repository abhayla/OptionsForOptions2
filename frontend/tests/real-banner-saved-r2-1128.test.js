// Spec basis: ADR-330 point (73). Walk findings S5 and the banner: the saved-stop line of a real position keeps its two sentences apart,
// and a real Stops panel or real Exit dialog never sits under "Paper trades - not real money".
import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createPinia } from 'pinia'

vi.mock('@/lib/saveDraft', async (importActual) => {
  const actual = await importActual()
  return { ...actual, fetchSavedDraft: () => Promise.resolve({ legs: [{ contract_id: 1001, instrument_id: 'NSE_FO:1001', underlying: 'NIFTY', expiry: '2026-12-01', instrument_type: 'CE', strike: '25500', lot_size: 65, action: 'SELL', lots: 1 }], id: 48, revision: 1, name: null }) }
})
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: {
    get: (url) => {
      if (url === '/strategies') return Promise.resolve({ data: { strategies: [{ id: 48, underlying: 'NIFTY', position_kind: 'real' }] } })
      if (url === '/paper/strategies') return Promise.resolve({ data: { strategies: [], totals: null, answered_at: '2026-11-28T10:00:00Z' } })
      if (url.endsWith('/triggers')) return Promise.resolve({ data: { triggers: [] } })
      if (url === '/market/exit-state') return Promise.resolve({ data: { closed: false, sentence: null, next_open_at: null } })
      return Promise.reject({ status: 404, parts: null })
    },
    post: () => Promise.resolve({ data: { triggers: [{ id: 1, strategy_id: 48, kind: 'conditional_exit', direction: 'above', level: '24500.00', level_text: 'Index at or above 24,500.00', contract_id: null, contract_text: null, underlying: 'NIFTY', state: 'armed', created_at: '2026-11-29T05:00:00Z', fired_at: null, cancelled_at: null, stored_not_sent: true, record: null }] } }),
    delete: () => Promise.reject({ status: 404 }) } }
})
import PaperStops from '@/components/strategy/PaperStops.vue'
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'

describe('real Stops: saved line', () => {
  it('"Saved: exit above 24,500.00. Not sent to Zerodha. Place it in Kite." (two sentences, a full stop and a space between)', async () => {
    const w = mount(PaperStops, { props: { strategyId: 48, underlying: 'NIFTY', legs: [], kind: 'real' } })
    await flushPromises()
    await w.get('[data-testid="ce-above"]').setValue('24500')
    await w.get('[data-testid="ce-save"]').trigger('click')
    await flushPromises()
    expect(w.get('[data-testid="stops-saved"]').text()).toBe('Saved: exit above 24,500.00. Not sent to Zerodha. Place it in Kite.')
    w.unmount()
  })
})

describe('banner', () => {
  const show = async (path) => {
    const r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:x(.*)*', component: { template: '<div/>' } }] })
    r.push(path)
    await r.isReady()
    const w = mount(PaperStrategies, { global: { plugins: [r, createPinia()] } })
    await flushPromises()
    return w
  }
  it('a real Stops panel or a real Exit dialog: the banner says a real position only stores; with neither, the paper banner stays', async () => {
    const stops = await show('/positions/current-positions?tab=paper&strategy=48')
    expect(stops.get('[data-testid="paper-banner"]').text()).toContain('only stores your actions')
    stops.unmount()
    const exit = await show('/positions/current-positions?tab=paper&strategy=48&exit=48')
    expect(exit.get('[data-testid="paper-banner"]').text()).toContain('only stores your actions')
    exit.unmount()
    const none = await show('/positions/current-positions?tab=paper')
    expect(none.get('[data-testid="paper-banner"]').text()).toBe('Paper trades - not real money')
    none.unmount()
  })
})
