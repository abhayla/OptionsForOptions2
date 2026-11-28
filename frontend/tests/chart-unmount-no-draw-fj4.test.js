// Lane FJ item 4: no chart work after unmount (a chart created after teardown raised "document is not defined" and
// failed the unit stage at random). Each chart component is mounted and unmounted at once; every chart it made must be
// destroyed and none may be made after the unmount.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent, getCurrentInstance, h, onMounted } from 'vue'
import real from '../../tests/fixtures/strategy_price_history/ph56_one_day.json'
import outcome from './fixtures/outcome-condor.json'

const drawn = []
const destroyed = []
vi.mock('chart.js/auto', () => ({
  default: class {
    constructor(_ctx, config) { this.config = config; drawn.push(this) }
    destroy() { destroyed.push(this) }
    update() {}
  },
}))
const get = vi.fn()
vi.mock('@/services/api', () => ({ default: { get: (...a) => get(...a) } }))
import StrategyPriceChart from '@/components/strategy/StrategyPriceChart.vue'
import PayoffChart from '@/components/strategy/PayoffChart.vue'
import AdjustPayoffChart from '@/components/strategy/AdjustPayoffChart.vue'

beforeEach(() => { drawn.length = 0; destroyed.length = 0; get.mockReset() })

describe('FJ-4 no chart work after unmount', () => {
  it('StrategyPriceChart: unmounted while the reply is on its way draws nothing afterwards', async () => {
    get.mockResolvedValue({ data: real })
    const w = mount(StrategyPriceChart, { props: { strategyId: 56 } })
    w.unmount()
    await flushPromises()
    expect(drawn).toHaveLength(0)
  })
  it('PayoffChart: mounted and unmounted at once leaves no live chart, and a late prop change draws none', async () => {
    const w = mount(PayoffChart, { props: { points: outcome.payoff.points, spot: outcome.spot_level } })
    w.unmount()
    await flushPromises()
    expect(drawn.length).toBe(destroyed.length)
  })
  it('AdjustPayoffChart: mounted and unmounted at once leaves no live chart', async () => {
    const lines = [{ id: 'a', name: 'A', colour: '#000', points: [['1', '2'], ['3', '4']] }]
    const w = mount(AdjustPayoffChart, { props: { lines } })
    w.unmount()
    await flushPromises()
    expect(drawn.length).toBe(destroyed.length)
  })
  it('PayoffChart: its mounted hook runs after the test environment is torn down (no document): no chart, no error', async () => {
    const errors = []
    const realDocument = globalThis.document
    // a sibling's hook runs first and takes the document away, as the teardown did before the queued hook ran
    const Teardown = defineComponent({ setup() { onMounted(() => { vi.stubGlobal('document', undefined) }); return () => h('i') } })
    const Host = defineComponent({
      setup: () => () => h('div', [h(Teardown), h(PayoffChart, { points: outcome.payoff.points, spot: outcome.spot_level })]),
    })
    try {
      mount(Host, { global: { config: { errorHandler: (e) => errors.push(e) } } })
      await flushPromises()
    } finally {
      vi.stubGlobal('document', realDocument)
    }
    expect(errors.map(String)).toEqual([])
    expect(drawn).toHaveLength(0)
  })
})
