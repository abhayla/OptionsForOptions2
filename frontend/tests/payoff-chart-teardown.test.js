// Lane FK (28 Nov 2026): the payoff chart does no work once removed. Real case: full pre-push run 28 Nov, "Unhandled
// Rejection: ReferenceError: document is not defined" at PayoffChart.vue createChart, after the test environment was torn down.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, nextTick, ref } from 'vue'

const charts = []
vi.mock('chart.js/auto', () => ({
  default: class {
    constructor(_ctx, config) {
      this.config = config
      this.destroyed = false
      charts.push(this)
    }
    destroy() {
      this.destroyed = true
    }
  },
}))

import PayoffChart from '@/components/strategy/PayoffChart.vue'

const CURVE = [{ level: '22800', pnl: '-1000.00' }, { level: '23000', pnl: '6400.00' }, { level: '23200', pnl: '-900.00' }]
const live = () => charts.filter((c) => !c.destroyed)
let rejections
beforeEach(() => {
  charts.length = 0
  rejections = []
  HTMLCanvasElement.prototype.getContext = () => ({})
})
const watchRejections = () => {
  const on = (e) => rejections.push(e)
  process.on('unhandledRejection', on)
  return () => process.off('unhandledRejection', on)
}

describe('no chart work after the chart is removed', () => {
  it('a prop change and the removal in the same tick leaves no chart behind', async () => {
    const off = watchRejections()
    const w = mount(PayoffChart, { props: { points: CURVE, view: 'at_expiry' } })
    expect(live()).toHaveLength(1)
    const before = charts.length
    w.setProps({ points: [...CURVE, { level: '23400', pnl: '10.00' }] }) // queues the redraw ...
    w.unmount() // ... and the chart goes before the flush
    await flushPromises()
    await nextTick()
    expect(charts.length).toBe(before) // nothing new was built
    expect(live()).toHaveLength(0)
    off()
    expect(rejections).toEqual([])
  })

  it('a chart mounted by a parent and removed by the same flush does not survive', async () => {
    const off = watchRejections()
    const show = ref(true)
    const Parent = defineComponent({
      setup: () => () => (show.value ? h(PayoffChart, { points: CURVE, view: 'at_expiry' }) : h('div')),
    })
    const w = mount(Parent)
    show.value = false
    await flushPromises()
    expect(live()).toHaveLength(0)
    w.unmount()
    off()
    expect(rejections).toEqual([])
  })

  it('the draw entry point itself is inert after unmount (a late post-flush call builds nothing)', async () => {
    const w = mount(PayoffChart, { props: { points: CURVE, view: 'at_expiry' } })
    const vm = w.vm
    w.unmount()
    const before = charts.length
    // a queued post-flush callback may still call the exposed redraw path; simulate through a late prop write on the dead vm
    try { vm.$.proxy.$forceUpdate() } catch { /* a dead instance may refuse */ }
    await flushPromises()
    expect(charts.length).toBe(before)
    expect(live()).toHaveLength(0)
  })

  it('a chart still mounted when the test environment is torn down does no work on a late redraw', async () => {
    // Real case 28 Nov: tests leave components mounted; their queued redraw runs after happy-dom is gone and reads `document`.
    const off = watchRejections()
    const w = mount(PayoffChart, { props: { points: CURVE, view: 'at_expiry' } })
    const before = charts.length
    const realDocument = globalThis.document
    const realGetContext = HTMLCanvasElement.prototype.getContext
    // the teardown: the DOM globals go away while the component is still alive
    vi.stubGlobal('document', undefined)
    try {
      w.setProps({ points: [...CURVE, { level: '23400', pnl: '10.00' }] })
      await flushPromises()
      await new Promise((r) => setTimeout(r, 0))
    } finally {
      vi.stubGlobal('document', realDocument)
      HTMLCanvasElement.prototype.getContext = realGetContext
    }
    off()
    expect(rejections).toEqual([])
    expect(charts.length).toBe(before) // no chart was built on the dead DOM
    w.unmount()
  })
})

import StrategyPriceChart from '@/components/strategy/StrategyPriceChart.vue'
import AdjustPayoffChart from '@/components/strategy/AdjustPayoffChart.vue'

describe('sibling charts do no work after removal', () => {
  it('AdjustPayoffChart: a prop change then removal builds nothing new', async () => {
    const lines = [{ id: 'a', name: 'A', colour: '#000', points: [['1', '2'], ['3', '4']] }]
    const w = mount(AdjustPayoffChart, { props: { lines, hidden: [] } })
    const before = charts.length
    w.setProps({ hidden: ['a'] })
    w.unmount()
    await flushPromises()
    expect(charts.length).toBe(before)
    expect(live()).toHaveLength(0)
  })
  it('StrategyPriceChart mounts and unmounts at once with no unhandled rejection', async () => {
    const off = watchRejections()
    const w = mount(StrategyPriceChart, { props: { strategyId: null, version: null, active: false } })
    w.unmount()
    await flushPromises()
    off()
    expect(rejections).toEqual([])
    expect(live()).toHaveLength(0)
  })
})
