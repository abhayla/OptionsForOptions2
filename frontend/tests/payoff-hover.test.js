// GC-BM step 6, gap G-051 (REQ-083 AC-2; ADR-008; Sensibull S-122): hovering the payoff chart shows the index level,
// its % from spot and the P&L the ENGINE computed at the nearest level it sent, never a value in between. Mounted on a
// REAL outcome reply (tests/fixtures/outcome-condor.json, NIFTY 13-Oct iron condor, spot 22533.25, at_expiry view);
// every expected money string is read from that file. chart.js is replaced by a stand-in with a plain linear x scale
// (pixel 40 = 21500, pixel 440 = 23500: 5 index points per pixel) so a hover lands at a known level.
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import real from './fixtures/outcome-condor.json'

const AREA = { left: 40, right: 440, top: 10, bottom: 250 }
const LO = 21500
const HI = 23500
const PER_PX = (HI - LO) / (AREA.right - AREA.left) // 5, exact, so a tie is a true tie
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
const total = real.table.rows.find((r) => r.row_id === 'TOTAL')
const cellOf = (level) => total.cells[level].display // the table's own display string for that level (same reply)
const card = (extra = {}) =>
  mount(ChartCard, { attachTo: document.body, props: { points: real.payoff.points, spot: real.spot_level, view: real.payoff.view, table: real.table, ...extra } })
const hover = async (w, level) => t(w, 'payoff-plot').trigger('mousemove', { clientX: px(level), clientY: 100 })
const tip = (w) => t(w, 'payoff-tooltip')

describe('G-051 core: the tooltip shows the engine point at the nearest sent level (REQ-083 AC-2)', () => {
  it('fails closed before any hover: no tooltip, no guide line', () => {
    const w = card()
    expect(tip(w).exists()).toBe(false)
    expect(t(w, 'payoff-guide').exists()).toBe(false)
    w.unmount()
  })

  it('attack 1: three hovers show the level, its % from spot and the P&L strings of the nearest sent point', async () => {
    const w = card()
    // exactly on a sent level
    await hover(w, 22300)
    expect(t(w, 'payoff-tooltip-title').text()).toBe('At 22,300 (-1.0%)')
    expect(t(w, 'payoff-tooltip-pnl').text()).toBe(cellOf('22300'))
    expect(t(w, 'payoff-tooltip-pnl').text()).toBe('−₹6,500.00')
    // 22520: 20 from 22500, 13.25 from 22533.25 -> the spot point itself
    await hover(w, 22520)
    expect(t(w, 'payoff-tooltip-title').text()).toBe('At 22,533.25 (0.0%)')
    expect(t(w, 'payoff-tooltip-pnl').text()).toBe(cellOf('22533.25'))
    // 22940: nearest is 22900
    await hover(w, 22940)
    expect(t(w, 'payoff-tooltip-title').text()).toBe('At 22,900 (+1.6%)')
    expect(t(w, 'payoff-tooltip-pnl').text()).toBe(cellOf('22900'))
    w.unmount()
  })

  it('attack 1: a hover exactly between two sent levels takes the LOWER level', async () => {
    const w = card()
    await hover(w, 22350) // 50 from 22300 and 50 from 22400
    expect(t(w, 'payoff-tooltip-title').text()).toBe('At 22,300 (-1.0%)')
    expect(t(w, 'payoff-tooltip-pnl').text()).toBe(cellOf('22300'))
    w.unmount()
  })

  it('attack 2: between two computed levels the tooltip never shows an interpolated value', async () => {
    const w = card()
    // 22940 lies between 22900 (-6500.00) and 23000 (-13000.00); a straight-line value there would be -9100.00
    await hover(w, 22940)
    const text = tip(w).text()
    expect(text).not.toContain('9,100')
    expect(text).not.toContain('9100')
    expect(text).not.toContain('22,940')
    // every money string the tooltip can show is one the reply sent for a level
    const sent = new Set(Object.values(total.cells).map((c) => c.display))
    expect(sent.has(t(w, 'payoff-tooltip-pnl').text())).toBe(true)
    w.unmount()
  })

  it('attack 3: a reply without the estimated curve shows the at-expiry line only, no blank Estimated line', async () => {
    expect(real.payoff.view).toBe('at_expiry')
    const w = card()
    await hover(w, 22300)
    const lines = tip(w).findAll('[data-testid="payoff-tooltip-line"]')
    expect(lines).toHaveLength(1)
    expect(lines[0].attributes('data-view')).toBe('at_expiry')
    expect(lines[0].text()).toBe('At expiry ' + cellOf('22300'))
    expect(tip(w).text()).not.toMatch(/estimated/i)
    w.unmount()
  })

  it('an estimated-now reply labels its one line "Estimated now" (the reply view decides the label)', async () => {
    const w = card({ view: 'estimated_now' })
    await hover(w, 22300)
    const lines = tip(w).findAll('[data-testid="payoff-tooltip-line"]')
    expect(lines).toHaveLength(1)
    expect(lines[0].attributes('data-view')).toBe('estimated_now')
    expect(lines[0].text()).toBe('Estimated now ' + cellOf('22300'))
    w.unmount()
  })

  it('attack 4: the hovered P&L equals the Payoff Table row for the same level (one reply feeds both)', async () => {
    const w = card()
    for (const level of ['21500', '22300', '22533.25', '22900', '23500']) {
      await hover(w, Number(level))
      const row = w.findAll('[data-testid="payoff-table-row"]').find((r) => r.find('[data-testid="payoff-table-level"]').text().endsWith(cellLevelLabel(level)))
      expect(row, level).toBeTruthy()
      expect(t(w, 'payoff-tooltip-pnl').text()).toBe(row.find('[data-testid="payoff-table-pnl"]').text())
      // and the engine point itself carries the same amount as the table cell's value
      const point = real.payoff.points.find((p) => p.level === level)
      expect(total.cells[level].value).toBe(point.pnl)
    }
    w.unmount()
  })

  it('attack 5: the mouse leaving the chart hides the tooltip and the guide line', async () => {
    const w = card()
    await hover(w, 22300)
    expect(tip(w).exists()).toBe(true)
    await t(w, 'payoff-plot').trigger('mouseleave')
    expect(tip(w).exists()).toBe(false)
    expect(t(w, 'payoff-guide').exists()).toBe(false)
    w.unmount()
  })

  it('a vertical guide line sits at the hovered sent level, inside the chart area', async () => {
    const w = card()
    await hover(w, 22940)
    const guide = t(w, 'payoff-guide')
    expect(guide.exists()).toBe(true)
    expect(guide.attributes('style')).toContain(`left: ${px(22900)}px`)
    expect(guide.attributes('style')).toContain(`top: ${AREA.top}px`)
    expect(guide.attributes('style')).toContain(`height: ${AREA.bottom - AREA.top}px`)
    w.unmount()
  })

  it('the tooltip never leaves the chart area at either edge', async () => {
    const w = card()
    await hover(w, 21500)
    const left = Number(/left: (-?[\d.]+)px/.exec(tip(w).attributes('style'))[1])
    expect(left).toBeGreaterThanOrEqual(AREA.left)
    await hover(w, 23500)
    const left2 = Number(/left: (-?[\d.]+)px/.exec(tip(w).attributes('style'))[1])
    expect(left2).toBeLessThanOrEqual(AREA.right)
    w.unmount()
  })

  it('keyboard: focus shows the level nearest spot, arrows step through sent levels, blur hides', async () => {
    const w = card()
    const plot = t(w, 'payoff-plot')
    expect(plot.attributes('tabindex')).toBe('0')
    await plot.trigger('focus')
    expect(t(w, 'payoff-tooltip-title').text()).toBe('At 22,533.25 (0.0%)')
    await plot.trigger('keydown', { key: 'ArrowLeft' })
    expect(t(w, 'payoff-tooltip-title').text()).toBe('At 22,500 (-0.1%)')
    await plot.trigger('keydown', { key: 'ArrowRight' })
    await plot.trigger('keydown', { key: 'ArrowRight' })
    expect(t(w, 'payoff-tooltip-title').text()).toBe('At 22,600 (+0.3%)')
    expect(t(w, 'payoff-tooltip-pnl').text()).toBe(cellOf('22600'))
    await plot.trigger('blur')
    expect(tip(w).exists()).toBe(false)
    w.unmount()
  })

  it('a reply with no points (NOT_CONNECTED) drops the old tooltip: no stale numbers', async () => {
    const w = card()
    await hover(w, 22300)
    expect(tip(w).exists()).toBe(true)
    await w.setProps({ points: [] })
    expect(tip(w).exists()).toBe(false)
    await hover(w, 22300)
    expect(tip(w).exists()).toBe(false)
    w.unmount()
  })
})

// The Payoff Table shows the column label ('22,300', 'CURRENT 22,533.25', '0-P&L 22,400'); its level text ends with it.
function cellLevelLabel(level) {
  return real.table.columns.find((c) => c.id === level).label.replace(/^(CURRENT|0-P&L) /, '')
}
