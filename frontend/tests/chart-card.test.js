// W-194 (ADR-193 Region F, ADR-194; REQ-035 AC-1, AC-2, AC-7 as amended): the builder's tabbed chart card, mounted
// on a REAL outcome reply (tests/fixtures/outcome-condor.json, NIFTY 13-Oct iron condor). Every expected string is read
// from that file. Covers: the compact P&L view is the default; the Full table switch shows every AC-2 column in the
// reply's order; no Total row when the reply sent none (no browser sum); hover snaps to the levels the server sent;
// the Payoff Table view; the Greeks and Strategy chart empty states.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import real from './fixtures/outcome-condor.json'
import money from './fixtures/outcome-money-condor.json'

const drawn = vi.hoisted(() => [])
vi.mock('chart.js/auto', () => ({ default: class { constructor(_ctx, config) { drawn.push(config) } destroy() {} } }))
import ChartCard from '@/components/strategy/ChartCard.vue'
import { compactRows, greekRows, payoffLevelRows } from '@/lib/chartCard'

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const all = (w, id) => w.findAll(`[data-testid="${id}"]`)
const shown = (w, id) => t(w, id).element.style.display !== 'none'
const card = (table = real.table, extra = {}) =>
  mount(ChartCard, { attachTo: document.body, props: { points: real.payoff.points, spot: real.spot_level, table, legs: real.legs, ...extra } })
const AC2_ORDER = ['leg', 'action', 'instrument', 'expiry', 'strike', 'quantity', 'entry_price', 'ltp', 'entry_value', 'current_value',
  'unrealized_pnl', 'pnl_percent', 'iv', 'delta', 'gamma', 'theta', 'vega']
const withoutTotal = { ...real.table, rows: real.table.rows.filter((r) => r.row_id !== 'TOTAL') }


// What the server sends on each Greek cell now: `display` = per-position text, `per_unit_display` = per-unit text, and
// the IV `display` as a percent. Literal strings; the browser prints them as they are (REQ-145 AC-3).
const SERVER_TEXT = {
  1: { unit: ['0.63', '0.0008', '-0.12', '0.05'], pos: ['40.79', '0.0520', '-7.80', '3.25'], iv: '16.03%' },
  2: { unit: ['0.08', '0.0011', '-0.09', '0.04'], pos: ['5.20', '0.0715', '-5.85', '2.60'], iv: '12.46%' },
  3: { unit: ['-0.35', '0.0010', '-0.10', '0.04'], pos: ['-22.75', '0.0650', '-6.50', '2.60'], iv: '12.80%' },
  4: { unit: ['-0.18', '0.0009', '-0.11', '0.05'], pos: ['-11.70', '0.0585', '-7.15', '3.25'], iv: '13.52%' },
  TOTAL: { unit: null, pos: ['2.96', '0.0001', '-0.02', '0.01'], iv: null },
}
const GREEK_IDS = ['delta', 'gamma', 'theta', 'vega']
const serverGreekTable = (table = real.table) => ({
  ...table,
  rows: table.rows.map((r) => {
    const x = SERVER_TEXT[r.row_id]
    if (!x) return r
    const cells = { ...r.cells }
    GREEK_IDS.forEach((id, i) => {
      cells[id] = { ...cells[id], display: x.pos[i], per_unit_display: x.unit ? x.unit[i] : null }
    })
    cells.iv = { ...cells.iv, display: x.iv ?? '—' }
    return { ...r, cells }
  }),
})

beforeEach(() => { drawn.length = 0 })

describe('ADR-194 (1): the P&L Table tab opens compact (core)', () => {
  it('the card opens on Payoff; the P&L Table tab shows the compact view, the full table hidden behind the switch', async () => {
    const w = card()
    expect(t(w, 'tab-payoff').attributes('aria-selected')).toBe('true')
    expect(shown(w, 'panel-payoff')).toBe(true)
    await t(w, 'tab-pnl').trigger('click')
    expect(shown(w, 'panel-pnl')).toBe(true)
    expect(shown(w, 'compact-view')).toBe(true)
    expect(shown(w, 'full-view')).toBe(false)
    expect(t(w, 'full-table-switch').element.checked).toBe(false)
    expect(all(w, 'compact-head').map((h) => h.text())).toEqual(['Planned entry', 'LTP', 'P&L', 'P&L %'])
    w.unmount()
  })

  it('one row per leg plus the reply TOTAL row, every cell the reply display string', () => {
    const w = card()
    const rows = all(w, 'compact-row')
    expect(rows.map((r) => r.attributes('data-row'))).toEqual(real.table.rows.map((r) => r.row_id))
    for (const row of real.table.rows) {
      const tr = w.find(`[data-testid="compact-row"][data-row="${row.row_id}"]`)
      for (const id of ['entry_price', 'ltp', 'unrealized_pnl', 'pnl_percent']) {
        expect(tr.find(`[data-field="${id}"]`).text()).toBe(row.cells[id].display)
      }
      if (row.row_id !== 'TOTAL') {
        // GC-UI D-B29: "<lots> x <D Mon> <strike> <type>", the lots from the reply's own leg (outcome-condor.json: NIFTY 13 Oct)
        const leg = real.legs[Number(row.row_id) - 1]
        expect(tr.find('[data-testid="instrument-text"]').text()).toBe(`${leg.lots} x 13 Oct ${leg.strike} ${leg.instrument}`)
        expect(tr.text()).not.toContain(row.cells.expiry.display)
        expect(tr.find('[data-testid="chip"]').text()).toBe(row.cells.action.value === 'BUY' ? 'B' : 'S')
      }
    }
    expect(w.find('[data-row="TOTAL"]').text()).toContain('Total')
    w.unmount()
  })

  it('no browser sum: a reply without a TOTAL row shows no Total row (and the Payoff Table shows its empty state)', () => {
    const w = card(withoutTotal)
    expect(w.find('[data-testid="compact-row"][data-row="TOTAL"]').exists()).toBe(false)
    expect(all(w, 'compact-row')).toHaveLength(withoutTotal.rows.length)
    expect(w.text()).not.toContain('Total')
    expect(t(w, 'payoff-table-empty').exists()).toBe(true)
    expect(payoffLevelRows(withoutTotal)).toBeNull()
    w.unmount()
  })
})

describe('ADR-194 (3) / REQ-035 AC-2: the Full table switch shows the REQ-035 table unchanged', () => {
  it('every AC-2 column in the reply order, the heading pair, sticky left columns, Details under it', async () => {
    const w = card(real.table, {})
    await t(w, 'tab-pnl').trigger('click')
    await t(w, 'full-table-switch').setValue(true)
    expect(shown(w, 'full-view')).toBe(true)
    expect(shown(w, 'compact-view')).toBe(false)
    const heads = all(w, 'col-head')
    expect(heads.map((h) => h.attributes('data-col'))).toEqual(real.table.columns.map((c) => c.id))
    expect(heads.map((h) => h.text())).toEqual(real.table.columns.map((c) => c.label))
    const fixed = real.table.columns.filter((c) => !c.is_scenario_level).map((c) => c.id)
    expect(fixed).toEqual([...AC2_ORDER, 'lower_be', 'upper_be', 'status'])
    expect(t(w, 'scenario-caption-left').exists()).toBe(false) // this reply sent no heading pair: none is made up
    const m = card(money.table)
    await t(m, 'full-table-switch').setValue(true)
    expect(t(m, 'scenario-caption-left').text()).toBe(money.table.scenario_heading[0])
    expect(t(m, 'scenario-caption-right').text()).toBe(money.table.scenario_heading[1])
    expect(all(m, 'col-head').map((h) => h.attributes('data-col'))).toEqual(money.table.columns.map((c) => c.id))
    m.unmount()
    expect(heads.slice(0, 3).every((h) => h.classes().includes('sticky-col'))).toBe(true)
    await t(w, 'full-table-switch').setValue(false)
    expect(shown(w, 'compact-view')).toBe(true)
    w.unmount()
  })
})

describe('Payoff tab: Graph and Table (UI-121, REQ-137 kept separate)', () => {
  it('hover snaps to the levels the server sent: only sent points are drawn, nearest-on-x, tooltip = the sent strings', () => {
    const w = card()
    expect(drawn).toHaveLength(1)
    const cfg = drawn[0]
    expect(cfg.options.interaction).toEqual({ mode: 'nearest', axis: 'x', intersect: false })
    for (const ds of cfg.data.datasets) expect(ds.data.map((d) => d.x)).toEqual(real.payoff.points.map((p) => Number(p.level)))
    // G-051: the canvas tooltip is off; the DOM tooltip (tests/payoff-hover.test.js) shows the sent strings
    expect(cfg.options.plugins.tooltip).toEqual({ enabled: false })
    // GC-UI b1 D-B12: one labelled current-price marker (the line is drawn by the marks plugin), no legend duplicate
    expect(cfg.plugins.map((p) => p.id)).toContain('payoffMarks')
    expect(t(w, 'payoff-current-price').text()).toBe(`Current price: ${real.spot_level}`)
    expect(t(w, 'payoff-legend-spot').exists()).toBe(false)
    expect(t(w, 'payoff-graph').text()).not.toContain('%') // the reply carries no percent from spot, so none is shown
    w.unmount()
  })

  it('the Table sub-tab lists each sent level with the TOTAL row value, the CURRENT level highlighted', async () => {
    const w = card()
    await t(w, 'tab-table').trigger('click')
    expect(shown(w, 'payoff-table')).toBe(true)
    expect(shown(w, 'payoff-graph')).toBe(false)
    const total = real.table.rows.find((r) => r.row_id === 'TOTAL')
    const levels = real.table.columns.filter((c) => c.is_scenario_level)
    const rows = all(w, 'payoff-table-row')
    expect(rows).toHaveLength(levels.length)
    rows.forEach((r, i) => {
      expect(r.find('[data-testid="payoff-table-level"]').text()).toBe(levels[i].label)
      expect(r.find('[data-testid="payoff-table-pnl"]').text()).toBe(total.cells[levels[i].id].display)
      expect(r.attributes('data-current')).toBe((levels[i].markers ?? []).includes('CURRENT') ? 'true' : 'false')
    })
    expect(rows.filter((r) => r.attributes('data-current') === 'true')).toHaveLength(1)
    w.unmount()
  })
})

describe('Greeks and Strategy chart tabs', () => {
  it('Greeks: per-leg Delta, Theta, Decay, Gamma, Vega, IV (REQ-145 AC-2) printed exactly as the server sent them (Per unit)', async () => {
    const table = serverGreekTable()
    const w = card(table)
    await t(w, 'tab-greeks').trigger('click')
    // GC-UI b2 D-B34: the spec's order; this older recorded reply has no Decay column, so its Decay cells print a dash
    expect(all(w, 'greeks-head').map((h) => h.text())).toEqual(['Delta', 'Theta', 'Decay', 'Gamma', 'Vega', 'IV'])
    for (const row of table.rows) {
      const tr = w.find(`[data-testid="greeks-row"][data-row="${row.row_id}"]`)
      expect(tr.find('[data-field="iv"]').text()).toBe(row.cells.iv.display)
      for (const id of GREEK_IDS) expect(tr.find(`[data-field="${id}"]`).text()).toBe(row.cells[id].per_unit_display ?? '—')
    }
    w.unmount()
  })

  it('Greeks absent from the reply: the shared empty state, no placeholder numbers', () => {
    const drop = new Set(['delta', 'gamma', 'theta', 'vega', 'iv'])
    const noGreeks = { ...real.table, columns: real.table.columns.filter((c) => !drop.has(c.id)) }
    expect(greekRows(noGreeks)).toBeNull()
    const w = card(noGreeks)
    expect(t(w, 'greeks-empty').exists()).toBe(true)
    expect(t(w, 'greeks-table').exists()).toBe(false)
    w.unmount()
  })

  it('Strategy chart: the price chart body, no longer the coming-soon state (GC-UI step 5; unsaved = nothing to ask)', async () => {
    const w = card()
    await t(w, 'tab-strategy-chart').trigger('click')
    expect(shown(w, 'panel-strategy-chart')).toBe(true)
    expect(t(w, 'strategy-chart-empty').exists()).toBe(false)
    expect(t(w, 'price-chart-unsaved').exists()).toBe(true)
    w.unmount()
  })

  it('a reply table without the compact columns gives no compact rows (the full table stays one switch away)', () => {
    expect(compactRows({ columns: [], rows: [] })).toBeNull()
  })
})

// GC-UI step 2 (D-B36 / D-B37 / D-B35; REQ-084 AC-8, REQ-145 AC-3): one Per unit / Per position toggle on Greeks.
describe('D-B36 / D-B37 / D-B35: the Greeks tab toggle and the IV string', () => {
  const cellOf = (w, row, id) => w.find(`[data-testid="greeks-row"][data-row="${row}"] [data-field="${id}"]`).text()
  it('default Per unit prints per_unit_display as sent; Total has none so shows an em dash', async () => {
    const w = card(serverGreekTable())
    await t(w, 'tab-greeks').trigger('click')
    expect(t(w, 'greeks-unit-toggle').exists()).toBe(true)
    expect(t(w, 'greeks-unit-toggle').findAll('button')).toHaveLength(2)
    expect(cellOf(w, '1', 'delta')).toBe('0.63')
    expect(cellOf(w, '1', 'gamma')).toBe('0.0008')
    expect(cellOf(w, 'TOTAL', 'delta')).toBe('—')
    expect(cellOf(w, 'TOTAL', 'gamma')).toBe('—')
    expect(t(w, 'greeks-mode-heading').text()).toBe('Per unit')
    w.unmount()
  })
  it('Per position prints the cell display as sent, heading names the units', async () => {
    const w = card(serverGreekTable())
    await t(w, 'tab-greeks').trigger('click')
    await t(w, 'greeks-mode-position').trigger('click')
    expect(cellOf(w, '1', 'delta')).toBe('40.79')
    expect(cellOf(w, '1', 'gamma')).toBe('0.0520')
    expect(cellOf(w, 'TOTAL', 'delta')).toBe('2.96')
    expect(t(w, 'greeks-mode-heading').text()).toBe('Per position, 65 units')
    await t(w, 'greeks-mode-unit').trigger('click')
    expect(cellOf(w, '1', 'delta')).toBe('0.63')
    w.unmount()
  })
  it('the browser formats nothing: an unrounded server string prints as is', async () => {
    const t0 = serverGreekTable()
    const rows = t0.rows.map((r) => (r.row_id === '1' ? { ...r, cells: { ...r.cells, delta: { ...r.cells.delta, per_unit_display: '0.6300000' } } } : r))
    const w = card({ ...t0, rows })
    await t(w, 'tab-greeks').trigger('click')
    expect(cellOf(w, '1', 'delta')).toBe('0.6300000')
    w.unmount()
  })
  it('IV prints the server display in both modes; null / empty / dash / missing show an em dash, never 0 or NaN', async () => {
    const t0 = serverGreekTable()
    const rows = t0.rows.map((r, i) => {
      const cells = { ...r.cells }
      if (i === 1) cells.delta = { ...cells.delta, per_unit_display: '' }
      if (i === 2) cells.delta = { ...cells.delta, per_unit_display: null, display: null }
      if (i === 3) cells.delta = { ...cells.delta, per_unit_display: '—', display: '—' }
      if (i === 0) cells.vega = { ...cells.vega, per_unit_display: undefined }
      return { ...r, cells }
    })
    const w = card({ ...t0, rows })
    await t(w, 'tab-greeks').trigger('click')
    expect(cellOf(w, '1', 'iv')).toBe('16.03%')
    expect(cellOf(w, '1', 'vega')).toBe('—')
    expect(cellOf(w, '2', 'delta')).toBe('—')
    expect(cellOf(w, '3', 'delta')).toBe('—')
    expect(cellOf(w, '4', 'delta')).toBe('—')
    await t(w, 'greeks-mode-position').trigger('click')
    expect(cellOf(w, '1', 'iv')).toBe('16.03%')
    expect(cellOf(w, '3', 'delta')).toBe('—')
    expect(cellOf(w, '2', 'delta')).toBe('5.20')
    expect(t(w, 'greeks-table').text()).not.toMatch(/NaN/)
    w.unmount()
  })
})

// GC-UI step 2 (D-B33 / D-B38): the At Expiry / Estimated Now switch and the range drive the Payoff tab only; the
// P&L Table and Greeks cells are now-values and identical under both views (measured 13:40 IST).
describe('D-B33 / D-B38: the scenario controls show on the Payoff tab only', () => {
  const withControls = () =>
    mount(ChartCard, {
      attachTo: document.body,
      props: { points: real.payoff.points, spot: real.spot_level, table: real.table },
      slots: { controls: '<div data-testid="scenario-controls">At Expiry / Estimated Now</div>' },
    })
  it('shown on Payoff, hidden on P&L Table and Greeks, back on Payoff', async () => {
    // GC-UI b1 D-B04: the controls sit in the Payoff panel's one header row, so they hide with that panel
    const w = withControls()
    const header = t(w, 'payoff-header')
    expect(t(w, 'panel-payoff').find('[data-testid="payoff-header"]').exists()).toBe(true)
    expect(header.find('[data-testid="scenario-controls-slot"]').exists()).toBe(true)
    expect(header.find('[role="tablist"]').exists()).toBe(true) // the sub-tabs share the row
    expect(shown(w, 'panel-payoff')).toBe(true)
    await t(w, 'tab-pnl').trigger('click')
    expect(shown(w, 'panel-payoff')).toBe(false)
    await t(w, 'tab-greeks').trigger('click')
    expect(shown(w, 'panel-payoff')).toBe(false)
    await t(w, 'tab-strategy-chart').trigger('click')
    expect(shown(w, 'panel-payoff')).toBe(false)
    await t(w, 'tab-payoff').trigger('click')
    expect(shown(w, 'panel-payoff')).toBe(true)
    w.unmount()
  })
})

describe('GC-UI b1 D-B01 / D-B02: tab labels follow the reference (RD-123)', () => {
  it('"Payoff Graph | P&L Table | Greeks | Strategy Chart", sub-tabs "Payoff Graph | Payoff Table"', () => {
    const w = card()
    const tabs = w.findAll('[role="tablist"]')
    expect(tabs[0].findAll('[role="tab"]').map((b) => b.text())).toEqual(['Payoff Graph', 'P&L Table', 'Greeks', 'Strategy Chart'])
    expect(tabs[1].findAll('[role="tab"]').map((b) => b.text())).toEqual(['Payoff Graph', 'Payoff Table'])
    w.unmount()
  })
  it('the card hands the reply blocks to the graph and passes its zoom up', async () => {
    const extra = { curves: { at_expiry: { available: true, points: real.payoff.points }, estimated_now: { available: false, points: [], unavailable_reason: 'x' } },
      breakevens: ['22650'], sd: null, oi: null, zoom: { step: '100', start: '21500', end: '23500' } }
    const w = card(real.table, extra)
    const chart = w.findComponent({ name: 'PayoffChart' })
    expect(chart.props()).toMatchObject(extra)
    await t(w, 'payoff-zoom-in').trigger('click')
    expect(w.emitted('zoom')).toEqual([[{ rangeStart: '22000', rangeEnd: '23000' }]])
    w.unmount()
  })
})
