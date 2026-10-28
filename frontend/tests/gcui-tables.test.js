// GC-UI step 4 round b2 (docs/process/ui-match-differences-2026-10-28.md Area B): the Greeks tab in the spec's order with
// Decay (D-B34, REQ-145 AC-2), the Payoff Table view from the server's `payoff_table` (D-B24 / D-B25 / D-B26, REQ-137
// AC-1), the TOTAL row's net Entry / LTP (D-B28), the lower card with portfolio Greeks and the SD table (D-B43, D-B45,
// D-B46). Mounted on the RECORDED replies in tests/fixtures/outcome_both_curves/flag_off.json (repo root; funds null, no
// funds figure) - every expected string below is read from that file or quoted from it.
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import flagOff from '../../tests/fixtures/outcome_both_curves/flag_off.json'
import recorded from '../../tests/fixtures/ui_data_check/both_s54_replay/outcome_both.json'

vi.mock('chart.js/auto', () => ({ default: class { constructor() {} destroy() {} } }))
import ChartCard from '@/components/strategy/ChartCard.vue'
import { DEFAULT_CHOICE, choiceFields, matchesChoice } from '@/lib/scenarioChoice'

const s54 = flagOff.s54_estimated_now
const fromEntries = flagOff.s54_from_entries
const t = (w, id) => w.find(`[data-testid="${id}"]`)
const all = (w, id) => w.findAll(`[data-testid="${id}"]`)
const card = (reply = s54, extra = {}) =>
  mount(ChartCard, { attachTo: document.body, props: { points: reply.payoff.points, spot: reply.spot_level, table: reply.table, legs: reply.legs, ...extra } })
const cellsOf = (row) => row.findAll('[data-testid="greeks-cell"]').map((c) => c.text())
const rowOf = (reply, id) => reply.table.rows.find((r) => r.row_id === id).cells

describe('core: D-B34 the Greeks tab columns follow REQ-145 AC-2 with Decay', () => {
  it('heads Delta, Theta, Decay, Gamma, Vega, IV (the server sends Delta, Gamma, Theta, Decay, Vega); Total row kept', async () => {
    const serverOrder = s54.table.columns.filter((c) => c.kind === 'greek').map((c) => c.label)
    expect(serverOrder).toEqual(['Delta', 'Gamma', 'Theta', 'Decay', 'Vega']) // the reply's own order differs
    const w = card()
    await t(w, 'tab-greeks').trigger('click')
    expect(all(w, 'greeks-head').map((h) => h.text().replace(/\s*\?$/, ''))).toEqual(['Delta', 'Theta', 'Decay', 'Gamma', 'Vega', 'IV'])
    const rows = all(w, 'greeks-row')
    expect(rows.map((r) => r.attributes('data-row'))).toEqual(['1', '2', 'TOTAL'])
  })

  it('Per unit prints per_unit_display, Per position prints display, Decay included, as the server wrote them', async () => {
    const w = card()
    await t(w, 'tab-greeks').trigger('click')
    const ids = ['delta', 'theta', 'decay', 'gamma', 'vega']
    const leg1 = rowOf(s54, '1')
    expect(cellsOf(all(w, 'greeks-row')[0])).toEqual([...ids.map((id) => leg1[id].per_unit_display), leg1.iv.display])
    expect(cellsOf(all(w, 'greeks-row')[0])[2]).toBe('-12.69') // Decay per unit, leg 1 (recorded)
    // the Total row has no per-unit text from the server: an em dash, never a browser division
    expect(cellsOf(all(w, 'greeks-row')[2]).slice(0, 5)).toEqual(['—', '—', '—', '—', '—'])
    await t(w, 'greeks-mode-position').trigger('click')
    const total = rowOf(s54, 'TOTAL')
    expect(cellsOf(all(w, 'greeks-row')[2])).toEqual([...ids.map((id) => total[id].display), '—'])
    expect(cellsOf(all(w, 'greeks-row')[2])[2]).toBe('-238.59') // Decay per position, Total (recorded)
  })

  it('FROM_ENTRIES (no IV): every Greek cell including Decay shows the dash the server sent, never a number', async () => {
    const w = card(fromEntries)
    await t(w, 'tab-greeks').trigger('click')
    await t(w, 'greeks-mode-position').trigger('click')
    for (const r of all(w, 'greeks-row')) expect(cellsOf(r)).toEqual(['—', '—', '—', '—', '—', '—'])
  })

  it('a reply without the decay column still shows the Greeks tab, Decay as an em dash (older reply, nothing invented)', async () => {
    const noDecay = ({ decay: _drop, ...cells }) => cells
    const table = {
      ...s54.table,
      columns: s54.table.columns.filter((c) => c.id !== 'decay'),
      rows: s54.table.rows.map((r) => ({ ...r, cells: noDecay(r.cells) })),
    }
    const w = card(s54, { table })
    await t(w, 'tab-greeks').trigger('click')
    expect(t(w, 'greeks-table').exists()).toBe(true)
    expect(cellsOf(all(w, 'greeks-row')[0])[2]).toBe('—')
  })
})

// D-B24 / D-B25 / D-B26 (REQ-137 AC-1): the Payoff Table view lists the server's `payoff_table` rows - the recorded s54
// reply asked with payoff_step 50 (tests/fixtures/ui_data_check/both_s54_replay/outcome_both.json, repo root).
// Show % is NOT built: PayoffRowOut carries no percent field, and the browser computes no percent (ADR-008).
describe('D-B24 / D-B25 / D-B26: the Payoff Table from the server rows, interval menu, both columns', () => {
  const pt = recorded.payoff_table
  const open = (payoffTable = pt) => card(s54, { payoffTable, payoffView: 'table' })
  it('the interval menu offers 10 / 25 / 50 / 100 and shows the server step; picking one asks the page', async () => {
    const w = open()
    const sel = t(w, 'payoff-step')
    expect(sel.findAll('option').map((o) => o.element.value)).toEqual(['10', '25', '50', '100'])
    expect(sel.element.value).toBe('50')
    await sel.setValue('25')
    expect(w.emitted('payoff-step')).toEqual([['25']])
  })
  it('both columns in the server order with its labels; one row per server row, every cell its display', () => {
    const w = open()
    expect(all(w, 'payoff-step-head').map((h) => h.text())).toEqual(['Index level', 'Estimated Now (estimate)', 'At Expiry'])
    const rows = all(w, 'payoff-step-row')
    expect(rows).toHaveLength(41)
    expect(rows[0].find('[data-testid="payoff-step-level"]').text()).toBe('21,500')
    expect(rows[0].find('[data-field="estimated_now"]').text()).toBe('−₹4,054.05')
    expect(rows[0].find('[data-field="at_expiry"]').text()).toBe('−₹4,056.00')
    const near = rows.filter((r) => r.attributes('data-current') === 'true')
    expect(near.map((r) => r.find('[data-testid="payoff-step-level"]').text())).toEqual(['22,550'])
  })
  it('no Show % switch (the reply has no percent field)', () => {
    expect(open().text()).not.toMatch(/Show %/)
  })
  it('a column the server marks unavailable prints the dash and its reason, never a number', () => {
    const reason = 'no implied volatility for this leg'
    const cols = pt.columns.map((c) => (c.view === 'estimated_now' ? { ...c, available: false, unavailable_reason: reason } : c))
    const rows = pt.rows.map((r) => ({ ...r, estimated_now: null }))
    const w = open({ ...pt, columns: cols, rows })
    expect(all(w, 'payoff-step-row')[0].find('[data-field="estimated_now"]').text()).toBe('—')
    expect(t(w, 'payoff-step-note').text()).toContain(reason)
  })
  it('the table unavailable: the empty state with the server reason, no rows', () => {
    const w = open({ ...pt, available: false, unavailable_reason: 'no live index level', rows: [] })
    expect(all(w, 'payoff-step-row')).toHaveLength(0)
    expect(t(w, 'payoff-table-empty').text()).toContain('no live index level')
  })
})

describe('D-B24: the picked interval goes into the outcome request; a late answer at another step is dropped', () => {
  it('payoff_step is sent as the integer the openapi names, only when picked; an off-menu value is never sent', () => {
    expect(choiceFields(DEFAULT_CHOICE)).toEqual({})
    expect(choiceFields({ ...DEFAULT_CHOICE, payoffStep: '25' })).toEqual({ payoff_step: 25 })
    expect(choiceFields({ ...DEFAULT_CHOICE, payoffStep: '30' })).toEqual({})
  })
  it('matchesChoice refuses an answer whose payoff_table.step differs from the pick, accepts the same step', () => {
    const body = { scenario: { view: 'at_expiry', customised: false }, payoff_table: { step: '50' } }
    expect(matchesChoice(body, { ...DEFAULT_CHOICE, payoffStep: '25' })).toBe(false)
    expect(matchesChoice(body, { ...DEFAULT_CHOICE, payoffStep: '50' })).toBe(true)
    expect(matchesChoice(body, DEFAULT_CHOICE)).toBe(true)
  })
})

// D-B28 (REQ-146 AC-3 TOTAL row; ADR-008): the compact P&L Total row prints the server's net Entry / LTP text.
describe('D-B28: the TOTAL row prints the net Entry / LTP the server sent', () => {
  const totalCell = (w, id) => w.find(`[data-testid="compact-row"][data-row="TOTAL"] [data-field="${id}"]`).text()
  it('s54 Entry and LTP "₹62.40 Dr"; calendar "₹76.70 Dr"; from-entries LTP is the server dash', () => {
    expect(totalCell(card(), 'entry_price')).toBe('₹62.40 Dr')
    expect(totalCell(card(), 'ltp')).toBe('₹62.40 Dr')
    expect(totalCell(card(flagOff.calendar_estimated_now), 'entry_price')).toBe('₹76.70 Dr')
    expect(totalCell(card(fromEntries), 'entry_price')).toBe('₹62.40 Dr')
    expect(totalCell(card(fromEntries), 'ltp')).toBe('—')
  })
})

// Carry-over (REQ-146 AC-5, REQ-151 AC-1): the Full table view's contract date is day and month and the strike has no
// grouping comma or trailing zeros ("13 Oct", "22600"), from the server's text only.
describe('REQ-146 AC-5 / REQ-151: the Full table view prints "13 Oct" and "22600", never the ISO date or "22,600"', () => {
  it('expiry and strike cells of every leg row; the TOTAL row keeps its dash', () => {
    const w = card(s54, { fullTable: true })
    const tds = (col) => w.findAll(`[data-testid="strategy-table"] td[data-col="${col}"]`).map((c) => c.text())
    expect(tds('expiry')).toEqual(['13 Oct', '13 Oct', '—'])
    expect(tds('strike')).toEqual(['22600', '22800', '—'])
    // the scenario column heads stay index levels with grouping ("22,600" there is a level, not a strike)
    expect(w.find('[data-testid="strategy-table"] tbody').text()).not.toMatch(/2026-10-13/)
  })
})
