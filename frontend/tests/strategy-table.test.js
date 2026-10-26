// REQ-035 AC-5: Bid/Ask appear only in the Details block, for everyone (ADR-168); AC-2: the screen never reorders the API's columns;
// ADR-008: no client-side maths on the outcome's values (a second layer; the first is that the page takes strings).
// The fixture is a REAL outcome response (NIFTY 13-Oct iron condor on the recorded 2026-10-08 09:20 frames, requested
// from the replay API), not invented columns or ids.
import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import fs from 'node:fs'
import path from 'node:path'
import { legQuotes, isCurrentColumn, cellText, STICKY_COUNT } from '@/lib/strategyTable'
import real from './fixtures/outcome-condor.json'

// the removed level names, built here so a search for them over the app finds only real uses
const OLD_BLOCK = ['advanced', 'details'].join('_')
const LEVEL_KEY = ['ux', 'level'].join('_')
const LEVEL_ATTR = ['data', 'ux'].join('-')
const OLD_LEVEL = ['gui', 'ded'].join('')
const ids = (cols) => cols.map((c) => c.id)
const without = (r) => {
  const { leg_quotes: _drop, ...rest } = r
  return rest
}

describe('the real response used here', () => {
  it('is a level-free condor with bid and ask from the API', () => {
    expect(real).not.toHaveProperty(LEVEL_KEY)
    expect(real.leg_quotes).toHaveLength(4)
    expect(real.leg_quotes[0]).toMatchObject({ instrument_id: 'NSE_FO:44624', symbol: 'NIFTY26O1322800CE', bid: '39', ask: '39.1' })
  })
})

describe('AC-5: bid and ask only in the Details block', () => {
  it('shows the API block as given, with no level argument', () => {
    expect(legQuotes(real)).toEqual(real.leg_quotes)
  })
  it('shows nothing when the response carries no block', () => {
    expect(legQuotes(without(real))).toBeNull()
    expect(legQuotes(null)).toBeNull()
    expect(legQuotes({ ...without(real), [OLD_BLOCK]: real.leg_quotes })).toBeNull() // the old name is not read
    expect(legQuotes({ ...without(real), leg_quotes: 'x' })).toBeNull() // not a list: nothing invented
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
    // ADR-194: the P&L Table tab opens compact; the full table is one switch away, the same for every user
    await w.get('[data-testid="tab-pnl"]').trigger('click')
    expect(w.get('[data-testid="compact-view"]').element.style.display).toBe('')
    expect(w.get('[data-testid="full-view"]').element.style.display).toBe('none')
    await w.get('[data-testid="full-table-switch"]').setValue(true)
    expect(w.get('[data-testid="full-view"]').element.style.display).toBe('')
    expect(w.findAll('[data-testid="col-head"]').length).toBe(real.table.columns.length)
    expect(w.findAll('[data-testid="col-head"]').map((h) => h.attributes('data-col'))).toEqual(ids(real.table.columns))
    expect(w.get('[data-testid="full-view"]').find('[data-testid="advanced-details"]').exists()).toBe(true) // Bid/Ask under the full table
    expect(real.table.columns.map((c) => c.id)).toContain('iv')
    expect(w.find('[data-testid="advanced-details"]').exists()).toBe(true)
    expect(w.findAll('[data-testid="adv-bid"]').length).toBe(real.leg_quotes.length)
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
    const heading = w.find('[data-testid="advanced-details"] summary').text() // REQ-034 AC-7: the h2 became the summary
    expect(heading).toBe('Details: bid and ask per leg')
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

// AC-7 / AC-2 / AC-3: the table as drawn. The heading pair is what the API sends (backend tests assert the wording from
// scenario_caption_parts); the fixture predates the field, so the pair is added here, as the API now sends it.
import StrategyTable from '@/components/strategy/StrategyTable.vue'
const HEADING = ['NIFTY at expiry', 'You make/lose']
const withHeading = (t, pair = HEADING) => ({ ...t, scenario_heading: pair })
const drawn = (table) => mount(StrategyTable, { props: { table }, global: { plugins: [] } })

describe('REQ-035 AC-7, AC-2, AC-3: the rendered table', () => {
  it('AC-2: the header cells appear in exactly the API column order', () => {
    const w = drawn(withHeading(real.table))
    expect(w.findAll('[data-testid="col-head"]').map((h) => h.attributes('data-col'))).toEqual(ids(real.table.columns))
    w.unmount()
  })
  it('AC-2: swapping two columns in the API order changes the drawn order (the screen never reorders)', () => {
    const cols = [...real.table.columns]
    ;[cols[1], cols[2]] = [cols[2], cols[1]]
    const w = drawn(withHeading({ ...real.table, columns: cols }))
    expect(w.findAll('[data-testid="col-head"]').map((h) => h.attributes('data-col'))).toEqual(ids(cols))
    expect(ids(cols)).not.toEqual(ids(real.table.columns))
    w.unmount()
  })
  it('AC-3: exactly one header carries current-col and it is the current level', () => {
    const w = drawn(withHeading(real.table))
    const current = w.findAll('th.current-col')
    expect(current).toHaveLength(1)
    expect(current[0].attributes('data-col')).toBe(real.spot_level)
    w.unmount()
  })
  it('AC-3: the highlight moves when the current level changes', () => {
    const cols = real.table.columns.map((c) => ({ ...c, markers: (c.markers || []).filter((m) => m !== 'CURRENT') }))
    const i = cols.findIndex((c) => c.id === '22600')
    cols[i] = { ...cols[i], markers: ['CURRENT'] }
    const w = drawn(withHeading({ ...real.table, columns: cols }))
    const current = w.findAll('th.current-col')
    expect(current).toHaveLength(1)
    expect(current[0].attributes('data-col')).toBe('22600')
    w.unmount()
  })
  it('AC-7: the heading pair renders once, in one cell spanning every scenario column, above the column heads', () => {
    const w = drawn(withHeading(real.table))
    const caption = w.find('[data-testid="scenario-caption"]')
    expect(w.findAll('[data-testid="scenario-caption"]')).toHaveLength(1)
    expect(w.find('[data-testid="scenario-caption-left"]').text()).toBe('NIFTY at expiry')
    expect(w.find('[data-testid="scenario-caption-right"]').text()).toBe('You make/lose')
    expect(caption.attributes('colspan')).toBe(String(real.table.columns.filter((c) => c.is_scenario_level).length))
    const rows = w.findAll('thead tr')
    expect(rows[0].find('[data-testid="scenario-caption"]').exists()).toBe(true)
    expect(rows[1].findAll('[data-testid="col-head"]')).toHaveLength(real.table.columns.length)
    w.unmount()
  })
  it('AC-7: a SENSEX table shows the SENSEX heading the API sent, not a NIFTY one', () => {
    const w = drawn(withHeading({ ...real.table, underlying: 'SENSEX' }, ['SENSEX at expiry', 'You make/lose']))
    expect(w.find('[data-testid="scenario-caption-left"]').text()).toBe('SENSEX at expiry')
    expect(w.text()).not.toContain('NIFTY at expiry')
    w.unmount()
  })
  it('AC-7: a table with no heading from the API draws no caption (nothing invented)', () => {
    const w = drawn(real.table)
    expect(w.find('[data-testid="scenario-caption-row"]').exists()).toBe(false)
    expect(w.text()).not.toContain('You make/lose')
    w.unmount()
  })
  it('AC-7: not connected / not live draws no table and no heading', async () => {
    apiAnswer = { state: 'NOT_CONNECTED', underlying: 'NIFTY', reason: null, table: null }
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
    await router.push({ path: '/strategy/builder', query: { draft: JSON.stringify(DRAFT) } })
    await router.isReady()
    const w = mount(StrategyBuilderPage, { global: { plugins: [router] } })
    await flushPromises()
    expect(w.find('[data-testid="strategy-table"]').exists()).toBe(false)
    expect(w.find('[data-testid="scenario-caption"]').exists()).toBe(false)
    w.unmount()
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


describe('REQ-077 AC-9: with no live data the page shows At Expiry from the user\'s prices, labelled, with no live number', () => {
  const FROM_YOUR_PRICES = 'From your prices - no live data'
  const answer = () => ({
    ...real, state: 'FROM_ENTRIES', status_label: FROM_YOUR_PRICES, output_label: FROM_YOUR_PRICES,
    centre_label: 'There is no live index price, so the levels are centred on the middle of your strikes, 22,800.',
    spot_level: null, spot_at: null, leg_quotes: undefined,
    legs: real.legs.map((l) => ({ ...l, ltp: null, iv: null, health: null })),
    table: { ...real.table, spot_level: null, spot_at: null, output_label: FROM_YOUR_PRICES },
  })
  async function openFromEntries(body) {
    await openBuilder({})
    apiAnswer = body
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
    await router.push({ path: '/strategy/builder', query: { draft: JSON.stringify(DRAFT) } })
    await router.isReady()
    const w = mount(StrategyBuilderPage, { global: { plugins: [router] } })
    await flushPromises()
    return w
  }
  it('shows the label, the centre line and the numbers, and no live level, no Bid/Ask block, no priced-at time', async () => {
    const w = await openFromEntries(answer())
    expect(w.find('[data-testid="numbers"]').exists()).toBe(true)
    expect(w.find('[data-testid="output-label"]').text()).toBe(FROM_YOUR_PRICES)
    expect(w.find('[data-testid="centre-label"]').text()).toContain('22,800')
    expect(w.find('[data-testid="underlying-spot"]').text()).toBe('—') // W-193: the level card is gone; the spot is in the underlying bar
    expect(w.find('[data-testid="advanced-details"]').exists()).toBe(false)
    expect(w.find('[data-testid="footer-valuation"]').exists()).toBe(false)
    expect(w.find('[data-testid="state-not-connected"]').exists()).toBe(false)
    expect(w.text()).not.toContain('Draft — Live data not connected')
    w.unmount()
  })
  it('Estimated Now is shown unavailable with the server\'s reason', async () => {
    const body = answer()
    body.scenario = { ...real.scenario, view: 'estimated_now', available: false, totals: null,
      unavailable_reason: 'Estimated Now needs live prices, which are not available. At Expiry is shown from your prices.' }
    body.payoff = { view: 'estimated_now', points: [] }
    const w = await openFromEntries(body)
    expect(w.find('[data-testid="estimate-unavailable"]').text()).toContain('needs live prices')
    w.unmount()
  })
  it('a COMPUTED answer shows neither the centre line nor an unavailable note', async () => {
    const w = await openBuilder({})
    expect(w.find('[data-testid="centre-label"]').exists()).toBe(false)
    expect(w.find('[data-testid="estimate-unavailable"]').exists()).toBe(false)
    w.unmount()
  })
})
