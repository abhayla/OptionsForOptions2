// GC-UI step 4 round b2/2 (docs/process/ui-match-differences-2026-10-28.md Area B): the lower card under the chart
// (D-B43 portfolio Greeks, D-B45 Standard Deviation table, D-B46 layout) and the Decay info mark (REQ-145 AC-5).
// Replies: tests/fixtures/outcome_both_curves/flag_off.json (recorded; funds null) plus the recorded
// standard_deviation block of tests/fixtures/ui_data_check/both_s54_replay/outcome_both.json. The recorded TOTAL
// Greek cells carry no per_unit_display, so the test adds distinct per-unit strings (clearly not the recorded ones).
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import flagOff from '../../tests/fixtures/outcome_both_curves/flag_off.json'
import recorded from '../../tests/fixtures/ui_data_check/both_s54_replay/outcome_both.json'

vi.mock('chart.js/auto', () => ({ default: class { constructor() {} destroy() {} } }))
import LowerCard from '@/components/strategy/LowerCard.vue'
import ChartCard from '@/components/strategy/ChartCard.vue'
import { FIGURES } from '@/lib/figureDefinitions'

const s54 = flagOff.s54_estimated_now
const IDS = ['delta', 'theta', 'decay', 'gamma', 'vega']
const PER_UNIT = { delta: '0.21', theta: '-3.21', decay: '-3.67', gamma: '0.0003', vega: '2.77' } // test strings
const withTotalPerUnit = (reply, per = PER_UNIT) => ({
  ...reply,
  table: {
    ...reply.table,
    rows: reply.table.rows.map((r) =>
      r.row_id === 'TOTAL'
        ? { ...r, cells: { ...r.cells, ...Object.fromEntries(IDS.map((id) => [id, { ...r.cells[id], per_unit_display: per[id] ?? null }])) } }
        : r),
  },
})
const sdBlock = recorded.standard_deviation
const t = (w, id) => w.find(`[data-testid="${id}"]`)
const all = (w, id) => w.findAll(`[data-testid="${id}"]`)
const lower = (reply, sd = sdBlock) => mount(LowerCard, { props: { table: reply.table, legs: reply.legs, sd } })
const total = (reply) => reply.table.rows.find((r) => r.row_id === 'TOTAL').cells

describe('core: D-B43 / D-B45 the lower card prints the TOTAL row Greeks and the SD table as server text', () => {
  it('middle: Delta, Theta, Decay, Gamma, Vega with the TOTAL display (per position) and per_unit_display (per unit)', async () => {
    const reply = withTotalPerUnit(s54)
    const w = lower(reply)
    expect(all(w, 'lower-greek-name').map((n) => n.text().replace(/\s*\?$/, ''))).toEqual(['Delta', 'Theta', 'Decay', 'Gamma', 'Vega'])
    expect(all(w, 'lower-greek-value').map((v) => v.text())).toEqual(IDS.map((id) => PER_UNIT[id])) // Per unit is the default
    await t(w, 'lower-greeks-mode-position').trigger('click')
    expect(all(w, 'lower-greek-value').map((v) => v.text())).toEqual(IDS.map((id) => total(reply)[id].display))
    expect(total(reply).decay.display).toBe('-238.59') // recorded
  })

  it('right: one row per standard_deviation.rows entry with label, move_display, lower_display, upper_display', () => {
    const w = lower(withTotalPerUnit(s54))
    const rows = all(w, 'lower-sd-row')
    expect(rows).toHaveLength(sdBlock.rows.length)
    sdBlock.rows.forEach((r, i) => {
      const cells = rows[i].findAll('[data-testid="lower-sd-cell"]').map((c) => c.text())
      expect(cells).toEqual([r.label, r.move_display, r.lower_display, r.upper_display])
    })
    expect(rows[0].text()).toContain('329.4 (1.5%)')
  })

  it('layout: two columns (Greeks, Standard Deviation) in one card; no placeholder for the Later columns', () => {
    const w = lower(withTotalPerUnit(s54))
    expect(t(w, 'lower-card').exists()).toBe(true)
    expect(all(w, 'lower-column').map((c) => c.attributes('data-column'))).toEqual(['greeks', 'sd'])
    expect(w.text()).not.toMatch(/coming soon|Strikewise|Target Day/i)
  })
})

describe('answer states', () => {
  it('TOTAL Greek cell with no per-unit text: a dash in Per unit, never a number or 0', () => {
    const w = lower(s54) // recorded TOTAL has per_unit_display null
    expect(all(w, 'lower-greek-value').map((v) => v.text())).toEqual(['—', '—', '—', '—', '—'])
  })

  it('TOTAL Greek cell null / absent: a dash in both modes', async () => {
    const stripped = { ...s54, table: { ...s54.table, rows: s54.table.rows.map((r) => (r.row_id === 'TOTAL' ? { ...r, cells: { ...r.cells, delta: { ...r.cells.delta, display: null }, vega: undefined } } : r)) } }
    const w = lower(stripped)
    await t(w, 'lower-greeks-mode-position').trigger('click')
    const v = all(w, 'lower-greek-value').map((x) => x.text())
    expect(v[0]).toBe('—')
    expect(v[4]).toBe('—')
    expect(v[1]).toBe(total(s54).theta.display)
  })

  it('no TOTAL row: the empty line, not zeros', () => {
    const noTotal = { ...s54.table, rows: s54.table.rows.filter((r) => r.row_id !== 'TOTAL') }
    const w = mount(LowerCard, { props: { table: noTotal, legs: s54.legs, sd: sdBlock } })
    expect(t(w, 'lower-greeks-empty').exists()).toBe(true)
    expect(all(w, 'lower-greek-value')).toHaveLength(0)
  })

  it('no standard_deviation block: the column says so, no rows', () => {
    const w = lower(s54, null)
    expect(t(w, 'lower-sd-empty').text()).toContain('Standard deviation')
    expect(all(w, 'lower-sd-row')).toHaveLength(0)
  })

  it('available false with a reason: the right column shows the server reason', () => {
    const w = lower(s54, { available: false, reason: 'No implied volatility for these legs', rows: [], bands: [] })
    expect(t(w, 'lower-sd-empty').text()).toContain('No implied volatility for these legs')
    expect(all(w, 'lower-sd-row')).toHaveLength(0)
  })

  it('calendar reply (ADR-143): prints the TOTAL Greeks the server sent, a dash where it sent none', () => {
    const cal = flagOff.calendar_estimated_now
    const w = mount(LowerCard, { props: { table: cal.table, legs: cal.legs, sd: cal.standard_deviation ?? null } })
    const t0 = cal.table.rows.find((r) => r.row_id === 'TOTAL')
    if (t0) {
      const want = IDS.map((id) => (String(t0.cells?.[id]?.per_unit_display ?? '').trim() || '—'))
      expect(all(w, 'lower-greek-value').map((x) => x.text())).toEqual(want)
    } else expect(t(w, 'lower-greeks-empty').exists()).toBe(true)
  })

  it('FROM_ENTRIES reply: every Greek the server left as a dash stays a dash', async () => {
    const fe = flagOff.s54_from_entries
    const w = mount(LowerCard, { props: { table: fe.table, legs: fe.legs, sd: null } })
    await t(w, 'lower-greeks-mode-position').trigger('click')
    expect(all(w, 'lower-greek-value').map((x) => x.text())).toEqual(['—', '—', '—', '—', '—'])
  })
})

describe('REQ-145 AC-5: the Decay head has an info mark from the catalogue', () => {
  it('the catalogue holds a decay entry worded from REQ-145, pinned pending owner read', () => {
    expect(FIGURES.decay.label).toBe('Decay')
    expect(FIGURES.decay.text).toContain('time value change, in rupees, between now and the next market open')
    expect(FIGURES.decay.text).toContain('everything else stays the same')
    expect(FIGURES.decay.source).toContain('REQ-145')
    expect(FIGURES.decay.reviewed).toBe('pending owner read')
  })

  it('the Greeks tab Decay head and the lower card Decay name each carry the mark; the other heads do not', async () => {
    const cc = mount(ChartCard, { props: { points: s54.payoff.points, spot: s54.spot_level, table: s54.table, legs: s54.legs } })
    await t(cc, 'tab-greeks').trigger('click')
    const heads = all(cc, 'greeks-head')
    expect(heads.map((h) => h.find('[data-figure="decay"]').exists())).toEqual([false, false, true, false, false, false])
    const w = lower(withTotalPerUnit(s54))
    expect(all(w, 'lower-greek-name').map((n) => n.find('[data-figure="decay"]').exists())).toEqual([false, false, true, false, false])
  })
})
