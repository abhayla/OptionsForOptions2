// Lane FC2 (R2, 28 Nov) D-6: the OI-unavailable line prints "OI not available for this expiry" once, the reason after it.
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import real from './fixtures/outcome-both-s54.json'

vi.mock('chart.js/auto', () => ({ default: class { constructor(_c, config) { this.config = config; this.chartArea = { left: 0, right: 1, top: 0, bottom: 1 }; this.scales = {} } destroy() {} } }))
import PayoffChart from '@/components/strategy/PayoffChart.vue'

const NONE = 'OI not available for this expiry'
const oi = (reason) => ({ available: false, unavailable_reason: reason, expiry: '2026-10-13', expiry_note: null, read_at: null, read_at_display: null, contracts: 0, rows: [] })
const line = (reason) => mount(PayoffChart, {
  props: { curves: real.curves, points: real.payoff.points, view: real.payoff.view, spot: real.spot_level, breakevens: real.summary.breakevens, sd: real.standard_deviation, oi: oi(reason) },
}).get('[data-testid="payoff-oi-unavailable"]').text()

describe('D-6 OI unavailable line', () => {
  it('a reason that already starts with the sentence is printed once', () => {
    expect(line(`${NONE}: live market data is stale.`)).toBe(`${NONE}: live market data is stale.`)
  })
  it('a plain reason follows the sentence', () => { expect(line('OI is not streaming.')).toBe(`${NONE}: OI is not streaming.`) })
  it('no reason: the sentence alone', () => { expect(line(null)).toBe(NONE) })
  it('a reason that is only the sentence is printed once', () => { expect(line(NONE)).toBe(NONE) })
})
