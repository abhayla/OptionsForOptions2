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
    expect(w.find('[data-testid="strategy-header"]').exists()).toBe(false) // polish 1: the NIFTY pill is gone
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
    const header = w.find('[data-testid="strategy-builder"]').text()
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
  // F-15: the two ALLOWED files are scanned too. A use is allowed only by its exact (trimmed) line, with its reason; any other
  // line that hits BANNED fails, and a listed line that no longer exists fails (the list cannot go stale or be padded).
  const L = (line, reason) => ({ line, reason })
  const NAMED_USES = {
    [path.join('components', 'strategy', 'PayoffChart.vue')]: [
      L('const at = Math.max(0, Math.min(1, (y0 - area.top) / (area.bottom - area.top)))', 'pixel clamp in crossingGradient'),
      L('const lineData = (points) => points.map((p) => ({ x: Number(p.level), y: Number(p.pnl) }))', 'drawing coordinates handed to chart.js'),
      L('const x = chart.scales.x.getPixelForValue(Number(props.spot))', 'index level to a pixel'),
      L('const firstLevel = () => Number(props.points[0].level)', 'index level, not money'),
      L('const lastLevel = () => Number(props.points[props.points.length - 1].level)', 'index level, not money'),
      L('const lv = Number(p.level)', 'index level, not money'),
      L('const d = Math.abs(lv - value)', 'nearest index level, not money'),
      L('const spot = Number(props.spot)', 'pctFromSpot: index level'),
      L('const pct = ((Number(level) - spot) / spot) * 100', 'pctFromSpot: index level percent, not money'),
      L('const text = Math.abs(pct).toFixed(1)', 'pctFromSpot: index percent text, not money'),
      L('ctx.fillRect(x - w / 2, top, w, 16)', 'pixel rectangle of the hover label'),
      L('ctx.strokeRect(x - w / 2, top, w, 16)', 'pixel rectangle of the hover label'),
      L('return a.right > a.left ? firstLevel() + ((x - a.left) / (a.right - a.left)) * (lastLevel() - firstLevel()) : firstLevel()', 'pixel to index level, not money'),
      L('return span ? a.left + ((level - firstLevel()) / span) * (a.right - a.left) : a.left', 'index level to pixel'),
      L('x: pixelAt(Number(p.level)),', 'index level to a pixel'),
      L('return Math.max(h.area.left, Math.min(h.x - w / 2, h.area.right - w))', 'pixel clamp of the tooltip'),
      L('const startIndex = () => nearestIndex(props.spot ? Number(props.spot) : firstLevel())', 'index level, not money'),
      L("show(Math.max(0, Math.min(props.points.length - 1, from + (e.key === 'ArrowRight' ? 1 : -1))))", 'array index clamp'),
      // F-1 round 1: the wider operator pattern (- and +) and the bound/template expressions now reach these real drawing lines
      L(':style="{ left: `${hovered.x}px`, top: `${hovered.area.top}px`, height: `${hovered.area.bottom - hovered.area.top}px` }"', 'pixel height of the hover guide line'),
      L('<span data-testid="payoff-last">{{ points[points.length - 1]?.level }}</span>', 'array index of the last point, text shown as sent'),
      L('const w = ctx.measureText(text).width + 8', 'pixel width of the hover label'),
      L('ctx.fillText(text, x, top + 8)', 'pixel position of the hover label text'),
      L('const span = lastLevel() - firstLevel()', 'index level range, not money'),
      L('show(nearestIndex(levelAt(e.clientX - box().left)))', 'mouse pixel to canvas pixel'),
    ],
    [path.join('components', 'strategy', 'PnLCell.vue')]: [
      L('const v = Number(props.value)', 'colour intensity only; the text is the API display'),
      L('const i = Math.min(v / (Number(props.maxProfit) || 1), 1)', 'colour intensity only'),
      L('const i = Math.min(Math.abs(v) / (Math.abs(Number(props.maxLoss)) || 1), 1)', 'colour intensity only'),
    ],
  }
  // A small lexer, not a regex pair: comments are removed only OUTSIDE strings; a quote-delimited string is blanked, except the
  // value of a Vue directive attribute (:x="..", @x="..", v-x="..") and the ${...} parts of a template literal, which are
  // code and are scanned. Both outputs keep every newline, so line N of `masked` is line N of `plain` (comments removed,
  // strings intact: the text a NAMED_USES line is compared with). A construct it cannot close is reported in `errors`.
  const DIRECTIVE_ATTR = /(?:^|\s)(?::[\w.:-]+|@[\w.:-]+|v-[\w.:-]+)=$/
  const nl = (s) => s.replace(/[^\n]/g, '')
  function lex(text) {
    let plain = ''
    let masked = ''
    const errors = []
    let i = 0
    const skip = (open, close) => {
      const end = text.indexOf(close, i + open.length)
      const stop = end < 0 ? text.length : end + close.length
      plain += nl(text.slice(i, stop))
      masked += nl(text.slice(i, stop))
      i = stop
    }
    while (i < text.length) {
      const c = text[i]
      if (text.startsWith('/*', i)) { skip('/*', '*/'); continue }
      if (text.startsWith('<!--', i)) { skip('<!--', '-->'); continue }
      if (text.startsWith('//', i)) { const e = text.indexOf('\n', i); i = e < 0 ? text.length : e; continue }
      if (c === "'" || c === '"') {
        let j = i + 1
        while (j < text.length && text[j] !== c && text[j] !== '\n') j += text[j] === '\\' ? 2 : 1
        if (text[j] === c) {
          const seg = text.slice(i, j + 1)
          const before = plain.slice(-60)
          plain += seg
          if (DIRECTIVE_ATTR.test(before)) masked += ' (' + lex(seg.slice(1, -1)).masked + ') '
          else masked += "''"
          i = j + 1
          continue
        }
      }
      if (c === '`') {
        let j = i + 1
        let m = '``'
        while (j < text.length && text[j] !== '`') {
          if (text[j] === '\\') { j += 2; continue }
          if (text[j] === '$' && text[j + 1] === '{') {
            let depth = 1
            let k = j + 2
            while (k < text.length && depth) { depth += text[k] === '{' ? 1 : text[k] === '}' ? -1 : 0; k++ }
            if (depth) { errors.push('unclosed ${ in a template literal'); break }
            const sub = lex(text.slice(j + 2, k - 1))
            errors.push(...sub.errors)
            m += ' (' + sub.masked + ') '
            j = k
            continue
          }
          if (text[j] === '\n') m += '\n'
          j++
        }
        if (text[j] !== '`') { errors.push('unterminated template literal'); plain += text.slice(i); masked += m; i = text.length; continue }
        plain += text.slice(i, j + 1)
        masked += m
        i = j + 1
        continue
      }
      plain += c
      masked += c
      i++
    }
    return { plain, masked, errors }
  }
  // Operators on a value: binary and compound (* / % + - ** and their =), a continuation line that starts with one, and a
  // unary plus. Keywords that may precede a sign are replaced first; data-/aria-/v- attribute names are not subtraction.
  const OPERAND = '[-+]?\\s*[A-Za-z0-9_(.]'
  const MONEY_OPS = [
    new RegExp('[A-Za-z0-9_)\\]]\\s*(?:\\*\\*|[*/%+-])=?\\s*' + OPERAND),
    new RegExp('^\\s*(?:\\*\\*|[*/%+-])=?\\s*' + OPERAND),
    /(?:^|[=(,:?&|]\s*)\+\s*[A-Za-z_(]/,
  ]
  const MONEY_MATHS = [...BANNED, ...MONEY_OPS]
  const forTest = (line) => line.replace(/\b(?:return|typeof|case|in|of|else|yield|void|delete|new)\b/g, ';').replace(/(?<![\w.$)\]])(?:data|aria|v)-[\w-]+/g, '')
  // returns the violations of one allowed file's text: banned lines not in its list, and listed lines not found exactly once
  function scanAllowedFile(text, uses) {
    const listed = new Map(uses.map((u) => [u.line, 0]))
    const bad = []
    const { plain, masked, errors } = lex(text)
    for (const e of errors) bad.push(`unclassifiable: ${e}`)
    const plainLines = plain.split('\n')
    const maskedLines = masked.split('\n')
    plainLines.forEach((raw, n) => {
      const code = raw.trim()
      if (!code || !MONEY_MATHS.some((re) => re.test(forTest(maskedLines[n].trim())))) return
      if (listed.has(code)) listed.set(code, listed.get(code) + 1)
      else bad.push(`unlisted: ${code}`)
    })
    for (const [line, n] of listed) if (n !== 1) bad.push(`listed line found ${n} times: ${line}`)
    return bad
  }
  it('F-15: PayoffChart.vue and PnLCell.vue pass the scan with only their named uses', () => {
    for (const rel of ALLOWED) {
      expect(NAMED_USES[rel].every((u) => u.reason.length > 5)).toBe(true)
      expect(scanAllowedFile(fs.readFileSync(path.join(SRC, rel), 'utf8'), NAMED_USES[rel])).toEqual([])
    }
  })
  it('F-15 mutation: a new money expression in PayoffChart.vue fails the scan', () => {
    const rel = path.join('components', 'strategy', 'PayoffChart.vue')
    const text = fs.readFileSync(path.join(SRC, rel), 'utf8')
    for (const evil of ['const _x = Number(point.pnl) * 2', 'const _y = p.pnl.toFixed(2)', 'const _z = pnl / 2']) {
      expect(scanAllowedFile(text + '\n' + evil, NAMED_USES[rel]).length).toBeGreaterThan(0)
    }
  })
  it('F-15 mutation (round 1): a template binding, a template literal, a // after a string and a subtraction fail the scan', () => {
    const rel = path.join('components', 'strategy', 'PayoffChart.vue')
    const text = fs.readFileSync(path.join(SRC, rel), 'utf8')
    const evils = [
      '<span :title="Number(p.pnl) * 2" />',
      '<span :style="{ top: p.pnl - q.pnl }" />',
      'const w = `${Number(p.pnl) * 2}`',
      "const s = 'a//b'; const m = Number(p.pnl) * 2",
      'const d = p.pnl - q.pnl',
      'const e = p.pnl * -1',
      'x.pnl *= 2',
      'const f = +p.pnl + +q.pnl',
      'const g = p.pnl\n  * 2',
      'const h = `${p.pnl',
    ]
    for (const evil of evils) expect(scanAllowedFile(text + '\n' + evil, NAMED_USES[rel]).length, evil).toBeGreaterThan(0)
  })
  it('F-15 lexer: // inside a string does not hide the rest of the line; a real comment still does', () => {
    expect(scanAllowedFile("const s = 'a//b'; const m = Number(p.pnl) * 2", []).length).toBeGreaterThan(0)
    expect(scanAllowedFile('const k = 1 // Number(p.pnl) * 2', [])).toEqual([])
    expect(scanAllowedFile("const u = 'https://x.y/z'", [])).toEqual([])
    expect(scanAllowedFile('<div class="a-b c/d" data-testid="x-y">{{ t }}</div>', [])).toEqual([])
  })
  it('F-15 mutation: a marker comment does not exempt a line that is not listed', () => {
    const rel = path.join('components', 'strategy', 'PayoffChart.vue')
    const text = fs.readFileSync(path.join(SRC, rel), 'utf8')
    const bad = scanAllowedFile(text + '\nconst _m = Number(p.pnl) * 2 // adr008-allow: drawing', NAMED_USES[rel])
    expect(bad.some((b) => b.startsWith('unlisted:'))).toBe(true)
  })
  it('F-15 mutation: a listed use that is removed or duplicated fails', () => {
    const rel = path.join('components', 'strategy', 'PnLCell.vue')
    const text = fs.readFileSync(path.join(SRC, rel), 'utf8')
    expect(scanAllowedFile(text.replace('const v = Number(props.value)', ''), NAMED_USES[rel]).length).toBeGreaterThan(0)
    expect(scanAllowedFile(text + '\nconst v = Number(props.value)', NAMED_USES[rel]).length).toBeGreaterThan(0)
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
