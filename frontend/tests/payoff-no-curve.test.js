// G-065 round 2 (REQ-148 AC-5/AC-6, REQ-083 AC-3): a reply with no curve for the selected view (At Expiry on legs of two
// expiries) must clear the curve drawn for the previous reply and show the reply's own reason; never the old curve.
// Seen live 2026-10-27 16:28 IST: the same-expiry condor's curve stayed after leg 4 moved to 9 Nov.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'

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
import ChartCard from '@/components/strategy/ChartCard.vue'

const WORST = "Worst case: the loss for this strategy can't be estimated."
const CURVE = [{ level: '22800', pnl: '-1000.00' }, { level: '23000', pnl: '6400.00' }, { level: '23200', pnl: '-900.00' }]
const live = () => charts.filter((c) => !c.destroyed)

beforeEach(() => {
  charts.length = 0
  HTMLCanvasElement.prototype.getContext = () => ({})
})

describe('a reply without a curve clears the drawn one', () => {
  it('the old chart is destroyed when the next reply has no points, and the reason is shown', async () => {
    const w = mount(PayoffChart, { props: { points: CURVE, view: 'at_expiry' } })
    expect(live()).toHaveLength(1)
    await w.setProps({ points: [], unavailableReason: WORST })
    expect(live()).toHaveLength(0) // the previous condor's curve is gone
    expect(w.find('[data-testid="payoff-unavailable"]').text()).toBe(WORST)
  })

  it('a curve again after that draws it and hides the reason', async () => {
    const w = mount(PayoffChart, { props: { points: [], unavailableReason: WORST } })
    expect(live()).toHaveLength(0)
    await w.setProps({ points: CURVE, unavailableReason: null })
    expect(live()).toHaveLength(1)
    expect(w.find('[data-testid="payoff-unavailable"]').exists()).toBe(false)
  })

  it('ChartCard hands the reply reason to the chart', () => {
    const table = { columns: [], rows: [] }
    const w = mount(ChartCard, { props: { points: [], table, unavailableReason: WORST } })
    expect(w.find('[data-testid="payoff-unavailable"]').text()).toBe(WORST)
  })
})
