// W-127 (REQ-083 AC-1, AC-2, AC-4..AC-7): the payoff chart draws the API's two curves, the SD lines and the OI bars, and
// every string it shows is the server's. Chart.js is replaced by a recorder, so the test reads the config it was given.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'

const made = []
vi.mock('chart.js/auto', () => ({
  default: class {
    constructor(_ctx, config) {
      this.config = config
      made.push(config)
    }
    destroy() {}
  },
}))

import PayoffChart, { nearestIndex, markers, oiSeries, hoverRows } from '@/components/strategy/PayoffChart.vue'

const POINTS = [
  { level: '22500', pnl: '-1000.00' },
  { level: '22550', pnl: '-200.00' },
  { level: '22600', pnl: '300.00' },
]
const ESTIMATED = [
  { level: '22500', pnl: '-800.25' },
  { level: '22550', pnl: '-100.50' },
  { level: '22600', pnl: '410.75' },
]
const OI = {
  expiry: '2026-10-13',
  read_at: '2026-10-08T09:20:09+05:30',
  stale: false,
  strikes: [
    { strike: '22500.00', call_oi: 1000, put_oi: 2000, call_oi_change: -5, put_oi_change: 7 },
    { strike: '22550.00', call_oi: null, put_oi: 3000, call_oi_change: null, put_oi_change: null },
  ],
}

beforeEach(() => {
  made.length = 0
  HTMLCanvasElement.prototype.getContext = () => ({})
})
const last = () => made[made.length - 1]
const dataset = (name) => last().data.datasets.find((d) => d.label === name)

describe('REQ-083 AC-1: both curves on the same axes', () => {
  it('AC-1: the Estimated dataset is the server points, on the same labels as the expiry curve', () => {
    mount(PayoffChart, { props: { points: POINTS, estimated: ESTIMATED } })
    expect(last().data.labels).toEqual(['22500', '22550', '22600'])
    expect(dataset('Estimated').data).toEqual([-800.25, -100.5, 410.75])
    expect(dataset('Profit')).toBeTruthy()
    expect(dataset('Loss')).toBeTruthy()
  })
  it('AC-3: with no Estimated curve only the expiry curve is drawn, and the reason is shown under the legend', () => {
    const w = mount(PayoffChart, { props: { points: POINTS, estimated: [], estimatedReason: 'The Estimated curve is not shown: an option leg has no implied volatility. The expiry curve is exact.' } })
    expect(dataset('Estimated')).toBeUndefined()
    expect(w.get('[data-testid="estimate-reason"]').text()).toContain('no implied volatility')
  })
})

describe('REQ-083 AC-2: the hover shows the server strings at the nearest computed level', () => {
  it('AC-2: the tooltip label for each curve is the API string of that index, never an average of two points', () => {
    mount(PayoffChart, { props: { points: POINTS, estimated: ESTIMATED } })
    const label = last().options.plugins.tooltip.callbacks.label
    expect(label({ dataset: { label: 'Estimated' }, dataIndex: 1, label: '22550' })).toBe('Estimated P/L: ₹-100.50')
    expect(label({ dataset: { label: 'Loss' }, dataIndex: 1, label: '22550' })).toBe('At expiry P/L: ₹-200.00')
    expect(last().options.interaction).toEqual({ mode: 'index', intersect: false })
  })
  it('AC-2: hoverRows returns the strings of ONE index; a missing estimate is null, not 0', () => {
    expect(hoverRows(POINTS, ESTIMATED, 2)).toEqual({ level: '22600', expiry: '300.00', estimated: '410.75' })
    expect(hoverRows(POINTS, [], 2).estimated).toBeNull()
  })
})

describe('REQ-083 AC-4: SD lines', () => {
  it('AC-4: each band and the current price sit at the nearest computed level', () => {
    const m = markers(['22500', '22550', '22600'], [{ label: '-1SD', level: '22540' }, { label: '1SD', level: '22700' }], '22551')
    expect(m.map((x) => [x.text, x.index])).toEqual([['-1SD', 1], ['1SD', 2], ['Current price', 1]])
    expect(nearestIndex(['22500', '22600'], '22550')).toBe(0) // a tie goes to the lower level
  })
  it('AC-4: the chart is given the markers; with no bands the reason is shown', () => {
    const w = mount(PayoffChart, { props: { points: POINTS, bands: [], bandsReason: 'Expected-move bands are not shown: there is no at-the-money implied volatility.', currentLevel: '22550' } })
    expect(last().options.plugins.markers.items.map((x) => x.text)).toEqual(['Current price'])
    expect(w.get('[data-testid="bands-reason"]').text()).toContain('no at-the-money implied volatility')
  })
})

describe('REQ-083 AC-5, AC-6: OI bars', () => {
  it('AC-6: a strike with no OI figure and a level with no strike are null, never a zero-height bar', () => {
    const s = oiSeries(['22500', '22550', '22600'], OI, 'oi')
    expect(s.call).toEqual([1000, null, null])
    expect(s.put).toEqual([2000, 3000, null])
    expect(oiSeries(['22500'], OI, 'change').call).toEqual([-5])
  })
  it('AC-5: bars are drawn on their own axis by default; the switch moves them to Change in OI', async () => {
    const w = mount(PayoffChart, { props: { points: POINTS, oi: OI, showOi: true } })
    expect(dataset('Call OI').data).toEqual([1000, null, null])
    expect(dataset('Call OI').yAxisID).toBe('yOi')
    await w.get('[data-testid="oi-mode-change"]').setValue(true)
    expect(dataset('Call OI').data).toEqual([-5, null, null])
  })
  it('AC-5: at Guided (showOi false) there are no bars and no switch', () => {
    const w = mount(PayoffChart, { props: { points: POINTS, oi: OI, showOi: false } })
    expect(dataset('Call OI')).toBeUndefined()
    expect(w.find('[data-testid="oi-controls"]').exists()).toBe(false)
  })
  it('AC-6: no OI for the expiry shows the message and no bars', () => {
    const w = mount(PayoffChart, { props: { points: POINTS, oi: null, oiReason: 'OI is not available for this expiry.', showOi: true } })
    expect(dataset('Call OI')).toBeUndefined()
    expect(w.get('[data-testid="oi-reason"]').text()).toBe('OI is not available for this expiry.')
  })
  it('AC-6: a stale OI read is marked', () => {
    const w = mount(PayoffChart, { props: { points: POINTS, oi: { ...OI, stale: true }, showOi: true } })
    expect(w.get('[data-testid="oi-stale"]').text()).toContain('2026-10-08T09:20:09+05:30')
  })
})

describe('REQ-083 AC-7: nothing is drawn beyond the points sent', () => {
  it('AC-7: the labels and every dataset have exactly the length of the points sent', () => {
    mount(PayoffChart, { props: { points: POINTS, estimated: ESTIMATED, oi: OI, showOi: true } })
    for (const d of last().data.datasets) expect(d.data).toHaveLength(POINTS.length)
  })
})
