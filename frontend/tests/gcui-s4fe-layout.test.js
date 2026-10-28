// GC-UI step 4 FE round a, D-B47 (ADR-193 (2)): the grey band with two rules (~35 px of nothing) between the chart card and
// the next card. Cause: StrategyActions drew its padded grey bar with a top rule even when it held no action (an unsaved
// draft, or the order path not "on"). With nothing to hold it draws nothing; with Execute it is unchanged.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import StrategyActions from '@/components/strategy/StrategyActions.vue'

let orderPath = 'on'
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (url) => (url === '/broker/status'
    ? Promise.resolve({ data: { account_connection: { state: 'connected' } } })
    : Promise.resolve({ data: { order_path: orderPath } })) } }
})

const mountActions = async (props) => {
  const w = mount(StrategyActions, { props, global: { stubs: { RouterLink: { template: '<a data-testid="execute-strategy"><slot /></a>' } } } })
  await flushPromises()
  return w
}
beforeEach(() => { orderPath = 'on' })

describe('D-B47: no empty grey band under the chart card', () => {
  it('an unsaved draft: no bar at all (no padding, no rule)', async () => {
    const w = await mountActions({ savedId: null })
    expect(w.find('[data-testid="strategy-actions"]').exists()).toBe(false)
    expect(w.html()).not.toContain('border-t')
  })

  it('a saved strategy with the order path off: no bar', async () => {
    orderPath = 'off'
    const w = await mountActions({ savedId: 5 })
    expect(w.find('[data-testid="strategy-actions"]').exists()).toBe(false)
  })

  it('a saved strategy with the order path on: the bar and the Execute action stay', async () => {
    const w = await mountActions({ savedId: 5 })
    expect(w.find('[data-testid="strategy-actions"]').exists()).toBe(true)
    expect(w.find('[data-testid="execute-strategy"]').exists()).toBe(true)
  })

  it('the tracking panel draws nothing for an unsaved draft either (no second rule)', async () => {
    const { default: TrackingPanel } = await import('@/components/strategy/TrackingPanel.vue')
    const w = mount(TrackingPanel, { props: { savedId: null } })
    await flushPromises()
    expect(w.find('[data-testid="tracking-panel"]').exists()).toBe(false)
  })
})
