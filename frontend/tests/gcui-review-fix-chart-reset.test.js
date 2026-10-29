// GC-UI review fix 1: the Strategy Chart never shows another strategy's or stale legs' prices.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import real from '../../tests/fixtures/strategy_price_history/ph56_one_day.json'

vi.mock('chart.js/auto', () => ({
  default: class {
    constructor(_ctx, config) { this.config = config }
    destroy() {}
    update() {}
  },
}))
const get = vi.fn()
vi.mock('@/services/api', () => ({ default: { get: (...a) => get(...a) } }))
import StrategyPriceChart from '@/components/strategy/StrategyPriceChart.vue'

const t = (w, id) => w.find(`[data-testid="${id}"]`)
beforeEach(() => { get.mockReset() })

describe('review fix 1: chart resets on strategy / saved-version change', () => {
  it('(a) a new strategy id clears the old chart and shows loading until the new answer', async () => {
    get.mockResolvedValue({ data: real })
    const w = mount(StrategyPriceChart, { props: { strategyId: 56 } })
    await flushPromises()
    expect(t(w, 'price-chart-plot').exists()).toBe(true)
    let resolve54
    get.mockReturnValue(new Promise((r) => { resolve54 = r }))
    await w.setProps({ strategyId: 54 })
    await flushPromises()
    expect(t(w, 'price-chart-plot').exists()).toBe(false)
    expect(t(w, 'price-chart-loading').exists()).toBe(true)
    resolve54({ data: real })
    await flushPromises()
    expect(t(w, 'price-chart-plot').exists()).toBe(true)
    expect(get.mock.calls[get.mock.calls.length - 1][0]).toBe('/strategies/54/price-history')
  })

  it('(b) same id, new saved version: asked again, old chart hidden meanwhile', async () => {
    get.mockResolvedValue({ data: real })
    const w = mount(StrategyPriceChart, { props: { strategyId: 56, version: 1 } })
    await flushPromises()
    expect(get).toHaveBeenCalledTimes(1)
    let resolve2
    get.mockReturnValue(new Promise((r) => { resolve2 = r }))
    await w.setProps({ version: 2 })
    await flushPromises()
    expect(get).toHaveBeenCalledTimes(2)
    expect(t(w, 'price-chart-plot').exists()).toBe(false)
    expect(t(w, 'price-chart-loading').exists()).toBe(true)
    resolve2({ data: real })
    await flushPromises()
    expect(t(w, 'price-chart-plot').exists()).toBe(true)
  })

  it('(c) a late answer for the earlier id is dropped', async () => {
    let resolve56
    get.mockReturnValueOnce(new Promise((r) => { resolve56 = r }))
    const w = mount(StrategyPriceChart, { props: { strategyId: 56 } })
    await flushPromises()
    get.mockResolvedValueOnce({ data: { ...real, future_label: 'NEW54' } })
    await w.setProps({ strategyId: 54 })
    await flushPromises()
    resolve56({ data: { ...real, future_label: 'OLD56' } })
    await flushPromises()
    expect(w.text()).not.toContain('OLD56')
  })
})
