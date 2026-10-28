// GC-UI step 4 round b2 (docs/process/ui-match-differences-2026-10-28.md Area B): the Greeks tab in the spec's order with
// Decay (D-B34, REQ-145 AC-2), the Payoff Table view from the server's `payoff_table` (D-B24 / D-B25 / D-B26, REQ-137
// AC-1), the TOTAL row's net Entry / LTP (D-B28), the lower card with portfolio Greeks and the SD table (D-B43, D-B45,
// D-B46). Mounted on the RECORDED replies in tests/fixtures/outcome_both_curves/flag_off.json (repo root; funds null, no
// funds figure) - every expected string below is read from that file or quoted from it.
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import flagOff from '../../tests/fixtures/outcome_both_curves/flag_off.json'

vi.mock('chart.js/auto', () => ({ default: class { constructor() {} destroy() {} } }))
import ChartCard from '@/components/strategy/ChartCard.vue'

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
