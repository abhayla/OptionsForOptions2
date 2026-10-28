// GC-UI step 4 FE round a, group 1 (D-B29, D-B30, D-B39; REQ-146 AC-5 as amended by ADR-204; REQ-151): every instrument
// the P&L Table, the Greeks tab and the tracking panel name reads "<lots> x <D Mon> <strike> <type>", e.g.
// "1 x 3 Nov 22600 CE". Strategy 54 as the builder holds it: BUY 22600 CE / SELL 22800 CE, 3 Nov 2026, quantity 65,
// lot size 65. Rows are the real condor reply's cells with the two legs' contract cells set to strategy 54's text.
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import real from './fixtures/outcome-condor.json'

vi.mock('chart.js/auto', () => ({ default: class { constructor() {} destroy() {} } }))
import ChartCard from '@/components/strategy/ChartCard.vue'
import { instrumentText } from '@/lib/chartCard'

const set = (row, over) => ({ ...row, cells: Object.fromEntries(Object.entries(row.cells).map(([k, c]) => [k, over[k] ? { ...c, ...over[k] } : c])) })
const cell = (v, d = v) => ({ value: v, display: d })
const leg = (rowId, action, strike, strikeDisplay, quantity = '65', type = 'CE', expiry = '2026-11-03') => set(
  real.table.rows.find((r) => r.row_id === rowId),
  { leg: cell(rowId), action: cell(action), instrument: cell(type), expiry: cell(expiry), strike: cell(strike, strikeDisplay), quantity: cell(quantity) },
)
const S54_LEGS = [
  { action: 'BUY', instrument: 'CE', strike: '22600', expiry: '2026-11-03', lots: 1, lot_size: 65, quantity: 65 },
  { action: 'SELL', instrument: 'CE', strike: '22800', expiry: '2026-11-03', lots: 1, lot_size: 65, quantity: 65 },
]
const S54_TABLE = () => ({
  ...real.table,
  rows: [leg('1', 'BUY', '22600', '22,600'), leg('2', 'SELL', '22800', '22,800'), real.table.rows.find((r) => r.row_id === 'TOTAL')],
})
const card = (table, legs) => mount(ChartCard, { attachTo: document.body, props: { points: real.payoff.points, spot: real.spot_level, table, legs } })
const texts = (w, id) => w.findAll(`[data-testid="${id}"]`).map((n) => n.text())

describe('Core (D-B29, D-B30, D-B39): strategy 54 instruments read like Sensibull', () => {
  it('the P&L Table instrument cell reads "1 x 3 Nov 22600 CE" (not "65 2026-11-03 22,600 CE")', () => {
    const w = card(S54_TABLE(), S54_LEGS)
    const cells = w.findAll('[data-testid="compact-row"] [data-testid="instrument-text"]')
    expect(cells.map((n) => n.text())).toEqual(['1 x 3 Nov 22600 CE', '1 x 3 Nov 22800 CE'])
    const first = w.find('[data-testid="compact-row"][data-row="1"]').text()
    expect(first).not.toContain('2026-11-03')
    expect(first).not.toContain('22,600')
    w.unmount()
  })

  it('the Greeks tab instrument reads the same form (not "B 22,600 CE")', () => {
    const w = card(S54_TABLE(), S54_LEGS)
    const rows = w.findAll('[data-testid="greeks-row"]').slice(0, 2)
    expect(rows.map((r) => r.find('[data-testid="instrument-text"]').text())).toEqual(['1 x 3 Nov 22600 CE', '1 x 3 Nov 22800 CE'])
    expect(rows[0].text()).not.toContain('22,600')
    w.unmount()
  })
})

describe('answer states for the instrument text', () => {
  it('instrumentText: whole lots, FUT leg, no lot count, no strike, unreadable date', () => {
    expect(instrumentText({ quantity: '130', expiry: '2026-11-03', strike: '22,600', instrument: 'PE' }, 2)).toBe('2 x 3 Nov 22600 PE')
    expect(instrumentText({ quantity: '65', expiry: '2026-11-03', strike: '22600.00', instrument: 'CE' }, 1)).toBe('1 x 3 Nov 22600 CE')
    expect(instrumentText({ quantity: '65', expiry: '2026-11-03', strike: '22312.50', instrument: 'CE' }, 1)).toBe('1 x 3 Nov 22312.5 CE')
    expect(instrumentText({ quantity: '65', expiry: '2026-11-03', strike: '-', instrument: 'FUT' }, 1)).toBe('1 x 3 Nov FUT')
    expect(instrumentText({ quantity: '65', expiry: '2026-11-03', strike: '', instrument: 'CE' }, 1)).toBe('1 x 3 Nov - CE')
    // the reply gave no whole-lot count (a quantity that is not a whole number of lots, or an unmatched row): quantity form
    for (const none of [null, undefined, 1.5, 0]) {
      expect(instrumentText({ quantity: '100', expiry: '2026-11-03', strike: '22600', instrument: 'CE' }, none)).toBe('100 units 3 Nov 22600 CE')
    }
    // a date that is not a date comes back as the server sent it
    expect(instrumentText({ quantity: '65', expiry: 'soon', strike: '22600', instrument: 'CE' }, 1)).toBe('1 x soon 22600 CE')
  })

  it('without the reply legs the card prints the quantity form; a leg that does not match its row is not trusted', () => {
    const none = card(S54_TABLE(), undefined)
    expect(texts(none, 'instrument-text').slice(0, 2)).toEqual(['65 units 3 Nov 22600 CE', '65 units 3 Nov 22800 CE'])
    none.unmount()
    const swapped = card(S54_TABLE(), [S54_LEGS[0], S54_LEGS[0]]) // row 2 is a SELL 22800; leg 2 says BUY 22600
    expect(texts(swapped, 'instrument-text').slice(0, 2)).toEqual(['1 x 3 Nov 22600 CE', '65 units 3 Nov 22800 CE'])
    swapped.unmount()
    const moved = card(S54_TABLE(), [S54_LEGS[0], { ...S54_LEGS[1], quantity: 130, lots: 2 }]) // quantity text disagrees with the row
    expect(texts(moved, 'instrument-text')[1]).toBe('65 units 3 Nov 22800 CE')
    moved.unmount()
  })
})
