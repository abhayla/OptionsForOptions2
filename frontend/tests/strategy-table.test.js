// REQ-035 AC-5: Bid/Ask appear only in the Details block, for everyone (ADR-168); AC-2: the screen never reorders the API's columns;
// ADR-008: no client-side maths on the outcome's values (a second layer; the first is that the page takes strings).
// The fixture is a REAL outcome response (NIFTY 13-Oct iron condor on the recorded 2026-10-08 09:20 frames, requested
// from the replay API), not invented columns or ids.
import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import fs from 'node:fs'
import path from 'node:path'
import { advancedDetails, isCurrentColumn, cellText, STICKY_COUNT } from '@/lib/strategyTable'
import real from './fixtures/outcome-condor.json'

// the removed level names, built here so a search for them over the app finds only real uses
const LEVEL_KEY = ['ux', 'level'].join('_')
const LEVEL_ATTR = ['data', 'ux'].join('-')
const OLD_LEVEL = ['gui', 'ded'].join('')
const ids = (cols) => cols.map((c) => c.id)
const without = (r) => {
  const { advanced_details: _drop, ...rest } = r
  return rest
}

describe('the real response used here', () => {
  it('is a level-free condor with bid and ask from the API', () => {
    expect(real).not.toHaveProperty(LEVEL_KEY)
    expect(real.advanced_details).toHaveLength(4)
    expect(real.advanced_details[0]).toMatchObject({ instrument_id: 'NSE_FO:44624', symbol: 'NIFTY26O1322800CE', bid: '39', ask: '39.1' })
  })
})

describe('AC-5: bid and ask only in the Details block', () => {
  it('shows the API block as given, with no level argument', () => {
    expect(advancedDetails(real)).toEqual(real.advanced_details)
  })
  it('shows nothing when the response carries no block', () => {
    expect(advancedDetails(without(real))).toBeNull()
    expect(advancedDetails(null)).toBeNull()
  })
  it('bid and ask are never table columns (AC-2 locked order)', () => {
    expect(ids(real.table.columns)).not.toContain('bid')
    expect(ids(real.table.columns)).not.toContain('ask')
  })
})

let apiAnswer = null
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: () => Promise.reject(new Error('unmocked get')), post: () => Promise.resolve({ data: apiAnswer }) } }
})
vi.mock('chart.js/auto', () => ({ default: class { destroy() {} } }))
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'

const DRAFT = { underlying: 'NIFTY', legs: real.legs.map((l) => ({ instrument_id: l.instrument_id, action: l.action, lots: l.lots,
  planned_entry: l.planned_entry, captured_at: l.captured_at })) }
async function openBuilder(query) {
  apiAnswer = real
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await router.push({ path: '/strategy/builder', query: { draft: JSON.stringify(DRAFT), ...query } })
  await router.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [router] } })
  await flushPromises()
  return w
}

describe('ADR-168: one full builder screen, no level switch', () => {
  it('attack 1: the page shows every API column (Greeks and IV included) and the details block, and no level control', async () => {
    const w = await openBuilder({})
    expect(w.findAll('[data-testid="col-head"]').length).toBe(real.table.columns.length)
    expect(real.table.columns.map((c) => c.id)).toContain('iv')
    expect(w.find('[data-testid="advanced-details"]').exists()).toBe(true)
    expect(w.findAll('[data-testid="adv-bid"]').length).toBe(real.advanced_details.length)
    expect(w.find('[data-testid="strategy-header"]').find('button').exists()).toBe(false)
    expect(w.find('[data-testid^="ux-"]').exists()).toBe(false)
    expect(w.find('[data-testid="strategy-builder"]').attributes(LEVEL_ATTR)).toBeUndefined()
    w.unmount()
  })
  it('attack 2: an old link with a level query opens the same full screen', async () => {
    const plain = await openBuilder({})
    const old = await openBuilder({ ux: OLD_LEVEL })
    expect(old.findAll('[data-testid="col-head"]').length).toBe(plain.findAll('[data-testid="col-head"]').length)
    expect(old.find('[data-testid="advanced-details"]').exists()).toBe(true)
    plain.unmount()
    old.unmount()
  })
  it('attack 4: no Guided, Standard or Advanced level text in the header or the details heading', async () => {
    const w = await openBuilder({})
    const header = w.find('[data-testid="strategy-header"]').text()
    const heading = w.find('[data-testid="advanced-details"] h2').text()
    expect(heading).toBe('Details')
    for (const word of ['Guided', 'Standard', 'Advanced', 'Detail level']) {
      expect(header).not.toContain(word)
      expect(heading).not.toContain(word)
    }
    w.unmount()
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
