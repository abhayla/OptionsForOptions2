// GC-UI step 4 round b1 (REQ-083 AC-1..AC-7; ADR-008; Sensibull screens 012, 017, 018, 019 and sb-02, layout only):
// the payoff chart draws the server's new blocks. Mounted on a REAL recorded reply asked with both_views + sd_bands
// (tests/fixtures/outcome-both-s54.json, trimmed from tests/fixtures/ui_data_check/both_s54_replay/outcome_both.json in
// the repo root: NIFTY bull spread, spot 22533.25, 23 levels 21500..23500). Every expected money string is read from
// that file. The OI block is not in that recording (it was not asked), so the OI states use the OiRowOut shape of
// docs/api/outcome.openapi.json with made-up counts. chart.js is a stand-in with a linear x scale (pixel 40 = 21500,
// pixel 440 = 23500), so a hover lands at a known level; jsdom draws no pixels, so the tests assert structure.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import real from './fixtures/outcome-both-s54.json'

const AREA = { left: 40, right: 440, top: 10, bottom: 250 }
const LO = 21500
const HI = 23500
const PER_PX = (HI - LO) / (AREA.right - AREA.left)
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
import { hatchPattern } from '@/lib/payoffRegions'

beforeEach(() => { drawn.length = 0 })

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const all = (w, id) => w.findAll(`[data-testid="${id}"]`)
const clone = (o) => JSON.parse(JSON.stringify(o))
const last = () => drawn[drawn.length - 1]
const lines = () => last().data.datasets.filter((d) => d.type === 'line' && d.curve)
const base = (extra = {}) => ({
  curves: real.curves, points: real.payoff.points, view: real.payoff.view, spot: real.spot_level,
  breakevens: real.summary.breakevens, sd: real.standard_deviation,
  zoom: { step: real.scenario.step, start: real.scenario.start, end: real.scenario.end }, ...extra,
})
const chart = (extra = {}) => mount(PayoffChart, { attachTo: document.body, props: base(extra) })
const hover = (w, level) => t(w, 'payoff-plot').trigger('mousemove', { clientX: px(level), clientY: 100 })
const point = (view, level) => real.curves[view].points.find((p) => p.level === level)

const OI = {
  available: true, unavailable_reason: null, expiry: '2026-10-13', expiry_note: null, read_at: '2026-10-13T09:20:00+05:30',
  read_at_display: 'OI read at 09:20', contracts: 3,
  rows: [
    { strike: '22500', call_oi: 120000, call_oi_display: '1.2L', put_oi: 98000, put_oi_display: '98K' },
    { strike: '22600', call_oi: null, call_oi_display: '—', put_oi: 0, put_oi_display: '0' },
    { strike: '22700', call_oi: 77000, call_oi_display: '77K', put_oi: 41000, put_oi_display: '41K' },
  ],
}

describe('core: both curves of one reply on one chart, the hover shows both engine values (REQ-083 AC-1, AC-2)', () => {
  it('two line datasets on ONE chart, same x axis, labelled per the spec, with a legend entry each', () => {
    const w = chart()
    expect(drawn).toHaveLength(1) // one chart instance, one canvas: same axes
    expect(w.findAll('canvas')).toHaveLength(1)
    expect(lines().map((d) => d.label)).toEqual(['At expiry', 'Estimated now'])
    expect(lines().map((d) => d.data.length)).toEqual([23, 23])
    expect(lines().every((d) => (d.xAxisID ?? 'x') === 'x')).toBe(true)
    expect(all(w, 'payoff-legend-curve').map((e) => e.text())).toEqual(['At expiry', 'Estimated now'])
  })
  it('a hover between 22600 and 22662.4 shows the NEAREST computed level 22662.4 and its two display strings', async () => {
    const w = chart()
    await hover(w, 22640)
    expect(t(w, 'payoff-tooltip-title').text()).toBe('At 22,662.4 (+0.6%)')
    const rows = all(w, 'payoff-tooltip-line')
    expect(rows.map((r) => r.attributes('data-view'))).toEqual(['estimated_now', 'at_expiry'])
    expect(rows[0].text()).toBe(`Estimated now ${point('estimated_now', '22662.4').display}`)
    expect(rows[1].text()).toBe(`At expiry ${point('at_expiry', '22662.4').display}`)
  })
  it('never a value between two computed levels: every shown string is one of the sent displays', async () => {
    const w = chart()
    const sent = new Set([...real.curves.at_expiry.points, ...real.curves.estimated_now.points].map((p) => p.display))
    for (const lv of [21510, 21987, 22333, 22777, 23111, 23499]) {
      await hover(w, lv)
      for (const s of all(w, 'payoff-tooltip-pnl').map((e) => e.text())) expect(sent.has(s), `${lv}: ${s}`).toBe(true)
    }
  })
})

describe('answer states of the curves (REQ-083 AC-3; ADR-143)', () => {
  it('Estimated unavailable: only At expiry is drawn, the reason in small text, no blank hover line', async () => {
    const curves = clone(real.curves)
    Object.assign(curves.estimated_now, { available: false, points: [], unavailable_reason: 'Estimated Now needs live prices.' })
    const w = chart({ curves })
    expect(lines().map((d) => d.label)).toEqual(['At expiry'])
    expect(t(w, 'payoff-curve-note').text()).toContain('Estimated Now needs live prices.')
    await hover(w, 22600)
    expect(all(w, 'payoff-tooltip-line').map((r) => r.attributes('data-view'))).toEqual(['at_expiry'])
  })
  it("calendar: the at-expiry curve is absent and the server's ADR-143 line is shown", () => {
    const curves = clone(real.curves)
    const adr143 = "Worst case: the loss for this strategy can't be estimated."
    Object.assign(curves.at_expiry, { available: false, points: [], unavailable_reason: adr143 })
    const w = chart({ curves })
    expect(lines().map((d) => d.label)).toEqual(['Estimated now'])
    expect(t(w, 'payoff-curve-note').text()).toContain(adr143)
  })
  it("FROM_ENTRIES: the curve's own output label (prices from your entries) is shown", () => {
    const curves = clone(real.curves)
    curves.at_expiry.output_label = 'Prices from your entries'
    Object.assign(curves.estimated_now, { available: false, points: [], unavailable_reason: 'Estimated Now needs live prices.' })
    const w = chart({ curves })
    expect(t(w, 'payoff-curve-note').text()).toContain('Prices from your entries')
  })
  it('an empty point list: no chart, the reason, no tooltip on hover', async () => {
    const curves = clone(real.curves)
    for (const v of ['at_expiry', 'estimated_now']) Object.assign(curves[v], { available: false, points: [], unavailable_reason: 'Not connected.' })
    const w = chart({ curves, points: [], unavailableReason: 'Not connected.' })
    expect(drawn).toHaveLength(0)
    expect(t(w, 'payoff-unavailable').text()).toBe('Not connected.')
    await hover(w, 22600)
    expect(t(w, 'payoff-tooltip').exists()).toBe(false)
  })
  it('a reply without curves (no both_views) still draws its one payoff line, labelled by its view', () => {
    chart({ curves: null })
    expect(lines().map((d) => d.label)).toEqual(['At expiry'])
  })
})

describe('axes, domain, markers (D-B08, B09, B11, B12; REQ-083 AC-7)', () => {
  it('no x-axis title, left axis "Profit / loss", no right axis without OI; no range line under the axis', () => {
    const w = chart()
    const s = last().options.scales
    expect(s.x.title?.display ?? false).toBe(false)
    expect(s.y.title).toMatchObject({ display: true, text: 'Profit / loss' })
    expect(s.y1?.display ?? false).toBe(false)
    expect(w.text()).not.toContain('Index level at expiry')
    expect(t(w, 'payoff-first').exists()).toBe(false)
  })
  it('the x domain is the first and last SENT level: the browser never extends a curve', () => {
    chart()
    expect(last().options.scales.x).toMatchObject({ min: 21500, max: 23500 })
  })
  it('one labelled current-price marker, no "Spot" legend duplicate', () => {
    const w = chart()
    expect(t(w, 'payoff-current-price').text()).toBe(`Current price: ${real.spot_level}`)
    expect(t(w, 'payoff-legend-spot').exists()).toBe(false)
  })
  it('a mark at every breakeven from summary.breakevens; none when the reply has none', () => {
    chart()
    const be = last().data.datasets.find((d) => d.label === 'Breakeven')
    expect(be.data.map((p) => p.x)).toEqual([22662.4])
    chart({ breakevens: [] })
    expect(last().data.datasets.find((d) => d.label === 'Breakeven')).toBeUndefined()
  })
  it('the zones fill to zero on the at-expiry curve only, so two fills never overlap', () => {
    chart()
    expect(lines()[0].fill.target).toBe('origin')
    expect(lines()[1].fill).toBe(false)
  })
  it('hatchPattern: an 8 px tile with one diagonal stroke, repeated; no canvas -> the plain colour', () => {
    const calls = []
    const g = new Proxy({}, { get: (_o, k) => (k === 'createPattern' ? (tile, rep) => ({ tile, rep }) : (...a) => calls.push([k, ...a])), set: (_o, k, v) => (calls.push([`=${String(k)}`, v]), true) })
    const tile = { getContext: () => g }
    const pat = hatchPattern({ createElement: () => tile }, '#178a55')
    expect(pat).toEqual({ tile, rep: 'repeat' })
    expect(tile).toMatchObject({ width: 8, height: 8 })
    expect(calls).toContainEqual(['=strokeStyle', '#178a55'])
    expect(calls).toContainEqual(['moveTo', 0, 8])
    expect(calls).toContainEqual(['lineTo', 8, 0])
    expect(hatchPattern({ createElement: () => ({ getContext: () => null }) }, '#d14343')).toBe('#d14343')
  })
})

describe('Zoom asks the engine for a new range (D-B10; REQ-083 AC-7)', () => {
  it('one Zoom control: in narrows, out widens, on the reply grid; the event carries only the range', async () => {
    const w = chart()
    await t(w, 'payoff-zoom-in').trigger('click')
    await t(w, 'payoff-zoom-out').trigger('click')
    expect(w.emitted('zoom')).toEqual([[{ rangeStart: '22000', rangeEnd: '23000' }], [{ rangeStart: '21000', rangeEnd: '24000' }]])
  })
  it('no zoom range from the reply: no zoom buttons (nothing guessed)', () => {
    const w = chart({ zoom: null })
    expect(t(w, 'payoff-zoom').exists()).toBe(false)
  })
})

describe('OI bars and the "OI data at" strip (D-B16, B17; REQ-083 AC-5, AC-6)', () => {
  it('call and put bars per strike on the right axis "Open Interest"; a null side draws NO bar (never a 0)', () => {
    chart({ oi: OI })
    const call = last().data.datasets.find((d) => d.label === 'Call OI')
    const put = last().data.datasets.find((d) => d.label === 'Put OI')
    expect(call.yAxisID).toBe('y1')
    expect(call.data).toEqual([{ x: 22500, y: 120000 }, { x: 22600, y: null }, { x: 22700, y: 77000 }])
    expect(put.data[1]).toEqual({ x: 22600, y: 0 }) // a real 0 stays 0
    expect(last().options.scales.y1.title).toMatchObject({ display: true, text: 'Open Interest' })
  })
  it('the strip follows the hovered strike and shows the read time', async () => {
    const w = chart({ oi: OI })
    await hover(w, 22690)
    expect(t(w, 'payoff-oi-strip').text()).toContain('OI data at 22700 | Call OI 77K | Put OI 41K')
    await hover(w, 22610)
    expect(t(w, 'payoff-oi-strip').text()).toContain('OI data at 22600 | Call OI — | Put OI 0')
    expect(t(w, 'payoff-oi-read-at').text()).toBe('OI read at 09:20')
  })
  it('OI unavailable: "OI not available for this expiry" with the reason, no bars, no right axis', () => {
    const w = chart({ oi: { ...OI, available: false, rows: [], unavailable_reason: 'OI is not streaming.' } })
    expect(t(w, 'payoff-oi-unavailable').text()).toBe('OI not available for this expiry: OI is not streaming.')
    expect(last().data.datasets.find((d) => d.label === 'Call OI')).toBeUndefined()
    expect(last().options.scales.y1?.display ?? false).toBe(false)
  })
})

describe('SD bands (D-B19, B20; REQ-083 AC-4)', () => {
  it('a line per band and a "-2SD -1SD 1SD 2SD" top axis, Fixed horizon from the reply', () => {
    const w = chart()
    expect(all(w, 'payoff-sd-label').map((e) => e.text())).toEqual(['-2SD', '-1SD', '1SD', '2SD'])
    expect(all(w, 'payoff-sd-label').map((e) => e.attributes('data-level'))).toEqual(real.standard_deviation.bands.map((b) => b.level))
    expect(t(w, 'payoff-sd-mode').text()).toBe(`SD Fixed, ${real.standard_deviation.horizon_days} days`)
  })
  it('SD unavailable: no bands, the reason in the info line', () => {
    const w = chart({ sd: { available: false, reason: 'No IV for the nearest expiry.', bands: [], rows: [], horizon_days: null } })
    expect(all(w, 'payoff-sd-label')).toHaveLength(0)
    expect(t(w, 'payoff-sd-mode').text()).toBe('SD bands: No IV for the nearest expiry.')
  })
})
