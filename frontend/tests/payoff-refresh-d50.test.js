// D-50 (seen once; docs/process/ic-live-test-2026-11-23-issues.md): the tester hovered at three levels and pressed
// ArrowRight x3 on condor C2 (157) and saw no tooltip. One attempt from the code: a parent that re-reads the outcome
// (live prices) hands the chart an EQUAL reply as a NEW array; the chart must keep the reading on screen.
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import real from './fixtures/outcome-condor.json'

const AREA = { left: 40, right: 440, top: 10, bottom: 250 }
const LO = 21500
const HI = 23500
const PER_PX = (HI - LO) / (AREA.right - AREA.left)
const px = (level) => AREA.left + (level - LO) / PER_PX
vi.mock('chart.js/auto', () => ({
  default: class {
    constructor(_ctx, config) {
      this.config = config
      this.chartArea = AREA
      this.scales = { x: { getPixelForValue: px, getValueForPixel: (p) => LO + (p - AREA.left) * PER_PX } }
    }
    destroy() {}
  },
}))
import ChartCard from '@/components/strategy/ChartCard.vue'

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const props = () => ({ points: structuredClone(real.payoff.points), spot: real.spot_level, view: real.payoff.view, table: structuredClone(real.table) })

describe('D-50: a refresh that sends the same payoff keeps the reading on screen', () => {
  it('mouse: the tooltip stays after the parent hands over an equal copy of the reply', async () => {
    const w = mount(ChartCard, { attachTo: document.body, props: props() })
    await t(w, 'payoff-plot').trigger('mousemove', { clientX: px(22300), clientY: 100 })
    expect(t(w, 'payoff-tooltip').exists()).toBe(true)
    await w.setProps(props())
    expect(t(w, 'payoff-tooltip').exists()).toBe(true)
    w.unmount()
  })

  it('keyboard: arrows keep showing a reading across the same refresh', async () => {
    const w = mount(ChartCard, { attachTo: document.body, props: props() })
    const plot = t(w, 'payoff-plot')
    await plot.trigger('focus')
    await plot.trigger('keydown', { key: 'ArrowRight' })
    await w.setProps(props())
    expect(t(w, 'payoff-tooltip').exists()).toBe(true)
    await plot.trigger('keydown', { key: 'ArrowRight' })
    expect(t(w, 'payoff-tooltip').exists()).toBe(true)
    w.unmount()
  })
})
