// REQ-035 AC-5: Bid/Ask appear only in Advanced Details; AC-2: the screen never reorders the API's columns;
// ADR-008: no client-side maths on the outcome's values (a second layer; the first is that the page takes strings).
// The fixture is a REAL outcome response (NIFTY 13-Oct iron condor on the recorded 2026-10-08 09:20 frames, requested
// at ux_level=advanced from the replay API), not invented columns or ids.
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { columnsToRender, advancedDetails, isCurrentColumn, cellText, STICKY_COUNT } from '@/lib/strategyTable'
import real from './fixtures/outcome-condor-advanced.json'

const ids = (cols) => cols.map((c) => c.id)
const without = (r) => {
  const { advanced_details: _drop, ...rest } = r
  return rest
}

describe('the real response used here', () => {
  it('is the advanced condor with bid and ask from the API', () => {
    expect(real.ux_level).toBe('advanced')
    expect(real.advanced_details).toHaveLength(4)
    expect(real.advanced_details[0]).toMatchObject({ instrument_id: 'NSE_FO:44624', symbol: 'NIFTY26O1322800CE', bid: '39', ask: '39.1' })
  })
})

describe('AC-5: bid and ask only in Advanced Details', () => {
  it('shows the API block at Advanced, as given', () => {
    expect(advancedDetails(real, 'advanced')).toEqual(real.advanced_details)
  })
  it('shows nothing at Standard and Guided even if a block were present', () => {
    for (const ux of ['standard', 'guided', '', undefined, 'whatever']) expect(advancedDetails(real, ux)).toBeNull()
  })
  it('shows nothing at Advanced when the response carries no block', () => {
    expect(advancedDetails(without(real), 'advanced')).toBeNull()
    expect(advancedDetails(null, 'advanced')).toBeNull()
  })
  it('bid and ask are never table columns, at any level (AC-2 locked order)', () => {
    expect(ids(columnsToRender(real.table.columns))).not.toContain('bid')
    expect(ids(real.table.columns)).not.toContain('ask')
  })
})

describe('AC-2: the API order is kept', () => {
  it('never reorders and drops only what the API marks as not visible', () => {
    const shown = ids(columnsToRender(real.table.columns))
    expect(shown).toEqual(ids(real.table.columns.filter((c) => c.visible)))
  })
})

describe('AC-3 helpers', () => {
  it('flags only the CURRENT column (the real spot level) and keeps three sticky columns', () => {
    expect(real.table.columns.filter(isCurrentColumn).map((c) => c.id)).toEqual([real.spot_level])
    expect(STICKY_COUNT).toBe(3)
  })
  it('cellText returns the API display text and nothing computed', () => {
    const row = real.table.rows[0]
    const col = real.table.columns.find((c) => c.id === 'ltp')
    expect(cellText(row, col)).toBe(row.cells.ltp.display)
    expect(cellText(row, { id: 'missing' })).toBe('')
  })
})

describe('W-075: the Charges and taxes row is drawn from the API like every other row', () => {
  it('cellText gives the API label and the API money display, and the browser adds nothing', () => {
    const row = {
      row_id: 'CHARGES',
      cells: {
        leg: { value: 'Charges and taxes (estimate)', display: 'Charges and taxes (estimate)' },
        '22533.25': { value: '-214.959564795', display: '-₹214.96' },
      },
    }
    expect(cellText(row, { id: 'leg' })).toBe('Charges and taxes (estimate)')
    expect(cellText(row, { id: '22533.25', is_scenario_level: true })).toBe('-₹214.96')
    expect(cellText(row, { id: 'iv' })).toBe('')
  })
})

describe('ADR-008: no client maths on the outcome response (second layer)', () => {
  const SRC = path.resolve(__dirname, '../src')
  // Named exceptions, each with its reason: PayoffChart hands numbers to chart.js to DRAW the line (its tooltip and labels
  // show the API strings); PnLCell parses the API value for a colour intensity only (its text is the API's display).
  const ALLOWED = new Set([path.join('components', 'strategy', 'PayoffChart.vue'), path.join('components', 'strategy', 'PnLCell.vue')])
  const walk = (dir) => fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? walk(path.join(dir, e.name)) : [path.join(dir, e.name)]))
  const files = walk(SRC).filter((f) => /\.(vue|js)$/.test(f) && !ALLOWED.has(path.relative(SRC, f)))
  const BANNED = [/parseFloat\s*\(/, /\bNumber\s*\(/, /parseInt\s*\(/, /\bMath\.(round|floor|ceil|max|min|abs)\s*\(/, /\.toFixed\s*\(/, /\.reduce\s*\(/]
  // lib/guided.js only SELECTS index levels and strikes from the catalogue (distance between levels, nearest strike); it
  // never touches an outcome/P&L number (its header says so). It may use Number, Math.abs/min/max and reduce; rounding and
  // number formatting stay banned there.
  const GUIDED_BANNED = [/parseFloat\s*\(/, /parseInt\s*\(/, /\bMath\.(round|floor|ceil)\s*\(/, /\.toFixed\s*\(/]

  it('scans the screen files', () => {
    expect(files.some((f) => f.endsWith('StrategyBuilderPage.vue'))).toBe(true)
    expect(files.some((f) => f.endsWith('StrategyTable.vue'))).toBe(true)
  })
  it('has no number parsing or arithmetic helpers in any screen file', () => {
    const hits = []
    for (const f of files) {
      const text = fs.readFileSync(f, 'utf8')
      for (const re of path.relative(SRC, f) === path.join('lib', 'guided.js') ? GUIDED_BANNED : BANNED) if (re.test(text.replace(/\/\*[\s\S]*?\*\/|<!--[\s\S]*?-->|\/\/.*$/gm, ''))) hits.push(`${path.relative(SRC, f)}: ${re}`)
    }
    // PayoffChart.vue draws coordinates with toFixed on pixel positions from chartGeometry; it is the one named exception
    expect(hits.filter((h) => !h.startsWith(path.join('components', 'strategy', 'PayoffChart.vue') + ': /\\.toFixed'))).toEqual([])
  })
  it('only the two named files may parse an API number, and they exist', () => {
    expect([...ALLOWED].sort()).toEqual([path.join('components', 'strategy', 'PayoffChart.vue'), path.join('components', 'strategy', 'PnLCell.vue')])
    for (const f of ALLOWED) expect(fs.existsSync(path.join(SRC, f))).toBe(true)
  })
})
