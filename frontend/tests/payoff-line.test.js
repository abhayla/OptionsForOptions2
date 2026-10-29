// GC-BM F-8 (REQ-083 AC-2/AC-7; ADR-008; Sensibull S-012): the payoff chart draws ONE continuous line through every
// point the server sent (its kinks at the strikes, which the server now sends), coloured green above zero and red below
// without breaking the line, and the hover at a strike shows that point's own display text. Mounted on REAL replies
// (tests/fixtures/outcome-condor-f8*.json: NIFTY 22500 PE B / 22650 PE S / 22950 CE S / 23100 CE B at 110.00 / 166.00 /
// 101.05 / 59.10, written from the server's outcome_to_dict on the 2026-10-08 replay). chart.js is a stand-in that keeps
// the config and has a plain linear x scale (pixel 40 = 21500, pixel 440 = 23500).
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import atExpiry from './fixtures/outcome-condor-f8.json'
import estimated from './fixtures/outcome-condor-f8-estimated.json'
import { pointSigns, segmentColour } from '@/lib/payoffRegions'

const AREA = { left: 40, right: 440, top: 10, bottom: 250 }
const LO = 21500
const PER_PX = 5
const px = (level) => AREA.left + (level - LO) / PER_PX
const drawn = []
vi.mock('chart.js/auto', () => ({
  default: class {
    constructor(_ctx, config) {
      this.config = config
      this.chartArea = AREA
      this.scales = { x: { getPixelForValue: px, getValueForPixel: (p) => LO + (p - AREA.left) * PER_PX } }
      drawn.push(config)
    }
    destroy() {}
  },
}))
import PayoffChart from '@/components/strategy/PayoffChart.vue'

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const chart = (reply) => {
  drawn.length = 0
  const w = mount(PayoffChart, { attachTo: document.body, props: { points: reply.payoff.points, spot: reply.spot_level, view: reply.payoff.view } })
  return { w, cfg: drawn[drawn.length - 1] }
}
const COLOURS = { profit: 'green', loss: 'red', flat: 'grey' }
const crossings = (points) => {
  const s = pointSigns(points)
  return s.map((a, i) => (i && a && s[i - 1] && a !== s[i - 1] ? i : -1)).filter((i) => i > 0)
}

describe('F-8: one continuous payoff line, kinks at the sent strikes', () => {
  it('at expiry: one dataset through every sent point, no gap, 22650 and 22950 are points with the engine values', () => {
    const { w, cfg } = chart(atExpiry)
    expect(cfg.data.datasets).toHaveLength(1)
    const [ds] = cfg.data.datasets
    expect(ds.data.map((d) => d.x)).toEqual(atExpiry.payoff.points.map((p) => Number(p.level)))
    expect(ds.data.every((d) => d.y !== null && Number.isFinite(d.y))).toBe(true)
    const at = (level) => atExpiry.payoff.points.find((p) => p.level === level)
    expect(at('22650').pnl).toBe('6366.75')
    expect(at('22950').pnl).toBe('6366.75')
    expect(at('22500').pnl).toBe('-3383.25')
    expect(at('23100').pnl).toBe('-3383.25')
    expect(ds.fill).toMatchObject({ target: 'origin' })
    w.unmount()
  })

  it('estimated now crosses zero between two sent points: still one line with no null, the crossing segment split at zero', () => {
    const pts = estimated.payoff.points
    const idx = crossings(pts)
    expect(idx.length).toBeGreaterThan(0) // the real estimate goes from loss to profit with no 0-P&L level between
    const { w, cfg } = chart(estimated)
    const [ds] = cfg.data.datasets
    expect(cfg.data.datasets).toHaveLength(1)
    expect(ds.data.some((d) => d.y === null)).toBe(false)
    const stops = []
    const fakeChart = { chartArea: AREA, scales: { y: { getPixelForValue: () => 130 } },
      ctx: { createLinearGradient: () => ({ addColorStop: (at, c) => stops.push([at, c]) }) } }
    const colour = ds.segment.borderColor
    const i = idx[0]
    colour({ p0DataIndex: i - 1, p1DataIndex: i, chart: fakeChart })
    expect(stops).toEqual([[0, expect.anything()], [0.5, expect.anything()], [0.5, expect.anything()], [1, expect.anything()]])
    w.unmount()
  })

  it('segment colours: profit, loss, a 0.00 run on neither line, a crossing as a gradient (pure helper)', () => {
    const pts = ['-65.00', '0.00', '0.00', '120.00', '-10.00'].map((pnl, i) => ({ level: String(i), pnl }))
    const grad = { addColorStop: () => {} }
    const fakeChart = {}
    const c = segmentColour(pointSigns(pts), COLOURS, (ch) => (ch === fakeChart ? grad : null))
    const seg = (a) => c({ p0DataIndex: a, p1DataIndex: a + 1, chart: fakeChart })
    expect(seg(0)).toBe('red')
    expect(seg(1)).toBe('grey')
    expect(seg(2)).toBe('green')
    expect(seg(3)).toBe(grad)
  })

  it('the hover at the strike 22650 shows the sent point ₹6,366.75, never a value between 22600 and 22700', async () => {
    const { w } = chart(atExpiry)
    await t(w, 'payoff-plot').trigger('mousemove', { clientX: px(22655), clientY: 100 })
    expect(t(w, 'payoff-tooltip-title').text()).toBe('At 22,650 (+0.5%)')
    expect(t(w, 'payoff-tooltip-pnl').text()).toBe('₹6,366.75')
    w.unmount()
  })
})
