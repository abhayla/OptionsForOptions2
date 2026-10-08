// REQ-035 AC-5: Bid/Ask appear only in Advanced Details; AC-2: the screen never reorders the API's columns;
// ADR-008: no client-side maths on the outcome's values (a second layer; the first is that the page takes strings).
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { columnsToRender, isCurrentColumn, cellText, STICKY_COUNT } from '@/lib/strategyTable'

const col = (id, extra = {}) => ({ id, label: id, kind: 'money', is_scenario_level: false, markers: [], visible: true, ...extra })
// the API's locked order with bid and ask in it (as the Advanced table carries them)
const COLUMNS = [col('leg'), col('action'), col('instrument'), col('expiry'), col('strike'), col('bid'), col('ask'), col('ltp'), col('iv', { visible: false }), col('22500'), col('22533.25', { markers: ['CURRENT'] }), col('status')]
const ids = (cols) => cols.map((c) => c.id)

describe('AC-5: bid and ask only in Advanced', () => {
  it('hides bid and ask at Standard and Guided', () => {
    for (const ux of ['standard', 'guided']) {
      const shown = ids(columnsToRender(COLUMNS, ux))
      expect(shown).not.toContain('bid')
      expect(shown).not.toContain('ask')
    }
  })
  it('shows bid and ask at Advanced', () => {
    const shown = ids(columnsToRender(COLUMNS, 'advanced'))
    expect(shown).toContain('bid')
    expect(shown).toContain('ask')
  })
  it('an unknown UX level is treated as not Advanced', () => {
    expect(ids(columnsToRender(COLUMNS, 'whatever'))).not.toContain('bid')
  })
})

describe('AC-2: the API order is kept', () => {
  it('never reorders, at any level', () => {
    const order = ids(COLUMNS)
    for (const ux of ['guided', 'standard', 'advanced']) {
      const shown = ids(columnsToRender(COLUMNS, ux))
      expect(shown).toEqual(order.filter((id) => shown.includes(id)))
    }
  })
  it('drops what the API marks as not visible', () => {
    expect(ids(columnsToRender(COLUMNS, 'advanced'))).not.toContain('iv')
  })
})

describe('AC-3 helpers', () => {
  it('flags only the CURRENT column and keeps three sticky columns', () => {
    expect(COLUMNS.filter(isCurrentColumn).map((c) => c.id)).toEqual(['22533.25'])
    expect(STICKY_COUNT).toBe(3)
  })
  it('cellText returns the API display text and nothing computed', () => {
    const row = { cells: { ltp: { display: '39.15' } } }
    expect(cellText(row, col('ltp'))).toBe('39.15')
    expect(cellText(row, col('missing'))).toBe('')
  })
})

describe('ADR-008: no client maths on the outcome response (second layer)', () => {
  const SRC = path.resolve(__dirname, '../src')
  const ALLOWED = new Set([path.join('lib', 'chartGeometry.js')]) // pixel positions only, never displayed
  const walk = (dir) => fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? walk(path.join(dir, e.name)) : [path.join(dir, e.name)]))
  const files = walk(SRC).filter((f) => /\.(vue|js)$/.test(f) && !ALLOWED.has(path.relative(SRC, f)))
  const BANNED = [/parseFloat\s*\(/, /\bNumber\s*\(/, /parseInt\s*\(/, /\bMath\.(round|floor|ceil|max|min|abs)\s*\(/, /\.toFixed\s*\(/, /\.reduce\s*\(/]

  it('scans the screen files', () => {
    expect(files.some((f) => f.endsWith('StrategyBuilderPage.vue'))).toBe(true)
    expect(files.some((f) => f.endsWith('StrategyTable.vue'))).toBe(true)
  })
  it('has no number parsing or arithmetic helpers in any screen file', () => {
    const hits = []
    for (const f of files) {
      const text = fs.readFileSync(f, 'utf8')
      for (const re of BANNED) if (re.test(text.replace(/\/\*[\s\S]*?\*\/|<!--[\s\S]*?-->|\/\/.*$/gm, ''))) hits.push(`${path.relative(SRC, f)}: ${re}`)
    }
    // PayoffChart.vue draws coordinates with toFixed on pixel positions from chartGeometry; it is the one named exception
    expect(hits.filter((h) => !h.startsWith(path.join('components', 'strategy', 'PayoffChart.vue') + ': /\\.toFixed'))).toEqual([])
  })
  it('the only file allowed to parse a payoff string is chartGeometry.js', () => {
    expect([...ALLOWED]).toEqual([path.join('lib', 'chartGeometry.js')])
  })
})
