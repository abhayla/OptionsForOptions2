// Lane FC2 (R2, 28 Nov) chart teardown: PayoffChart must do no chart work after it is unmounted. Seen in the pre-push run: "Unhandled
// Rejection: ReferenceError: document is not defined" at PayoffChart.vue createChart, raised after the test environment was torn down
// (tests/charges-dialog-drafts-d13-d14.test.js), because createChart ran from a pending mounted / watcher callback after unmount.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'
import real from './fixtures/outcome-both-s54.json'

const made = []
let destroyed = 0
vi.mock('chart.js/auto', () => ({
  default: class {
    constructor(_ctx, config) { this.config = config; this.chartArea = { left: 0, right: 1, top: 0, bottom: 1 }; this.scales = {}; made.push(config) }
    destroy() { destroyed += 1 }
  },
}))
import PayoffChart from '@/components/strategy/PayoffChart.vue'

const props = () => ({ curves: real.curves, points: real.payoff.points, view: real.payoff.view, spot: real.spot_level, breakevens: real.summary.breakevens, sd: real.standard_deviation })
beforeEach(() => { made.length = 0; destroyed = 0 })

describe('PayoffChart teardown', () => {
  it('unmounted before its mounted callback runs: no chart is created afterwards', async () => {
    const w = mount(PayoffChart, { props: props() })
    w.unmount() // no await: the post-flush mounted callback is still pending
    const before = made.length
    await flushPromises()
    await nextTick()
    expect(made.length).toBe(before)
  })
  it('a prop change queued together with the unmount creates nothing after it', async () => {
    const w = mount(PayoffChart, { props: props() })
    await flushPromises()
    const before = made.length
    w.setProps({ spot: '1' })
    w.unmount()
    await flushPromises()
    await nextTick()
    expect(made.length).toBe(before)
    expect(destroyed).toBeGreaterThan(0) // the chart it had is destroyed
  })
  it('REPRODUCTION of the pre-push failure: a redraw that runs when the page environment is gone (no document) does no chart work and raises nothing', async () => {
    const w = mount(PayoffChart, { props: props() })
    await flushPromises()
    const before = made.length
    const errors = vi.spyOn(console, 'error').mockImplementation(() => {})
    const warns = vi.spyOn(console, 'warn').mockImplementation(() => {})
    vi.stubGlobal('document', undefined) // the test environment is torn down ...
    try {
      await w.setProps({ spot: '22000.00' }) // ... when the queued redraw (watcher) runs
      await flushPromises()
      expect(made.length).toBe(before)
      expect(errors).not.toHaveBeenCalled()
    } finally {
      vi.unstubAllGlobals()
      errors.mockRestore()
      warns.mockRestore()
      w.unmount()
    }
  })
})
