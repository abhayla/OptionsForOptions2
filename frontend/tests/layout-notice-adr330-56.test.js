// ADR-330 (56): the layout mounts the ONE price notice for a flagged route (My Strategies), and never for a route whose page
// mounts its own (Positions), so the notice never shows twice.
import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: () => Promise.resolve({ data: { state: 'NOT_CONNECTED', market_closed: false, last_price_at: '2026-11-27T10:28:01Z', indices: [] } }) } }
})
import LayoutPriceNotice from '@/components/layout/LayoutPriceNotice.vue'
import { routes } from '@/router/routes'

async function at(path, meta) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path, component: { template: '<div/>' }, meta }] })
  router.push(path)
  await router.isReady()
  const w = mount(LayoutPriceNotice, { global: { plugins: [router] } })
  await flushPromises()
  return w
}

describe('LayoutPriceNotice', () => {
  it('flagged route: one notice with the last captured price time', async () => {
    const w = await at('/x', { priceNotice: true })
    expect(w.findAll('[data-testid="price-notice"]')).toHaveLength(1)
    expect(w.get('[data-testid="price-notice-text"]').text()).toBe('Prices are not live. Figures are as of 15:58:01 IST.')
  })
  it('an unflagged route: nothing (its page mounts its own notice)', async () => {
    const w = await at('/y', {})
    expect(w.find('[data-testid="price-notice"]').exists()).toBe(false)
  })
  it('the route table flags My Strategies and not Positions or Live Strategies', () => {
    const meta = (p) => routes.find((r) => r.path === p)?.meta
    expect(meta('/strategies/my-strategies')?.priceNotice).toBe(true)
    expect(meta('/positions/current-positions')?.priceNotice).toBeUndefined()
    expect(meta('/strategies/live-strategies')?.priceNotice).toBeUndefined()
  })
})
