// N-07 guard (26 Nov 2026; class D-41 of tests/one-source-d41.test.js): a paper trade's per-leg price / P&L has ONE reader on the builder page,
// lib/usePaperBookRead (legPricesOf / paperPnlBlock / paperLegsOf). Spec basis: ADR-328 (3), ADR-212, ADR-008.
// What is scanned (text of frontend/src, .vue .js .ts, comments blanked):
//   1. REGISTRY: every file that mentions a leg price / P&L field of a server reply (TOKENS) must be on READERS with its source and reason;
//      an unlisted file is a possible third reader and fails; a listed file with no hit is stale and fails ("shrink only").
//   2. WIRING: every <ChartCard in src passes :paper-legs, and ChartCard.vue hands props.paperLegs to compactRows (the P&L Table).
// KNOWN BYPASSES (not seen): a price read through a renamed field or a computed key; a reply object passed whole to a child that reads it
// there; a new file that reads a leg price under a token not in TOKENS; Advanced Details (bid/ask only)
// and Greeks (not prices) read the reply; #744 moved the Full table, the LegList "now" price and the failed-read panel rows onto the book (WIRING below).
// The mutation check at the bottom runs the real ChartCard text with the fix removed and shows the wiring check goes red.
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, sep } from 'node:path'
import { describe, expect, it } from 'vitest'

const SRC = join(process.cwd(), 'src')
const TOKENS = /unrealized_pnl|ltp_text|total_text|current_price_display|ltp_display|compactRows|pnl_text|\.unbooked/

const BOOK = 'the page book read (usePaperBookRead)'
export const READERS = [
  { file: 'src/lib/usePaperBookRead.js', source: BOOK, why: 'the one reader itself' },
  { file: 'src/lib/chartCard.js', source: BOOK, why: 'compactRows takes paperLegs (paperLegsOf) and prints those texts for a paper leg' },
  { file: 'src/components/strategy/ChartCard.vue', source: BOOK, why: 'P&L Table: passes props.paperLegs to compactRows' },
  { file: 'src/components/strategy/PaperBookPanel.vue', source: BOOK, why: 'legs table (Net Positions): the book itself' },
  { file: 'src/lib/tracking.js', source: BOOK, why: 'sharedTotal / readTracking: the headline is the book; TrackingPanel overlays the book LegPrice by contract id' },
  { file: 'src/pages/StrategyBuilderPage.vue', source: BOOK, why: 'wires paperLegsOf / paperPnlBlock / paperLegListPrices into the panels; its reply ltp maps (ltpById, priceTextById) are only the non-paper fallback of legListPrices, livePriceById feeds the confirm dialog / draft bar (not a shown leg price)' },
  { file: 'src/lib/legEdit.js', source: BOOK, why: 'movedMarker prints the "now" price it is given; for a paper trade the page gives it the book LTP (paperLegListPrices)' },
  { file: 'src/components/strategy/LegList.vue', source: BOOK, why: 'LegList prints movedMarker with the page maps (the book LTP for a paper trade); #744' },
  { file: 'src/lib/paperDrafts.js', source: BOOK, why: 'exit / pending-order rows priced from the book positions' },
  { file: 'src/lib/paperList.js', source: 'GET /paper/strategies list', why: 'the My Strategies list, not the builder page' },
  { file: 'src/components/strategy/PaperStrategies.vue', source: 'GET /paper/strategies list', why: 'list page, not the builder page' },
  { file: 'src/pages/MyStrategiesPage.vue', source: 'GET /paper/strategies list', why: 'list page' },
  { file: 'src/components/live/LiveStrategyCard.vue', source: 'paper book of its own card', why: 'Live page card, not the builder page' },
  { file: 'src/pages/PositionsPage.vue', source: 'positions read', why: 'Positions page' },
  { file: 'src/components/strategy/AdjustSteps.vue', source: 'adjust plan reply', why: 'Adjust review, not a live leg price' },
  { file: 'src/lib/adjustDrawer.js', source: 'adjust plan reply', why: 'Adjust drawer' },
]

// REMAINING readers of the outcome reply on a paper trade, by file and the text of the line (shrink only: a changed line fails and must be re-read).
export const REMAINING = [
  { file: 'src/components/strategy/AdvancedDetails.vue', line: 23, text: 'adv-bid', why: 'bid / ask per leg from the reply leg_quotes (not an LTP or P&L); listed for completeness' },
]

// #744 WIRING of the three readers that used to read the reply (each: file, a pattern that must be present, the problem text if it is gone).
const WIRING = [
  { file: 'src/components/strategy/ChartCard.vue', re: /:book-cells="fullBookCells"/, out: 'ChartCard.vue does not pass :book-cells to the Full table (StrategyTable)' },
  { file: 'src/components/strategy/ChartCard.vue', re: /fullBookCells = computed\(\(\) => \(props\.paperLegs && compact\.value[\s\S]*?cellText\(r, c\)/, out: 'ChartCard.vue: the Full table cells are not the compact (book) rows' },
  { file: 'src/components/strategy/StrategyTable.vue', re: /:book-cells="bookCells\?\.\[row\.row_id\] \?\? null"/, out: 'StrategyTable.vue does not hand its book cells to StrategyLegRow' },
  { file: 'src/components/strategy/StrategyLegRow.vue', re: /bookCells\?\.\[c\.id\] \?\? cellText\(row, c\)/, out: 'StrategyLegRow.vue does not print the book cell before the reply cell' },
  { file: 'src/pages/StrategyBuilderPage.vue', re: /:ltp-by-id="legListPrices\.ltpById" :price-text-by-id="legListPrices\.priceTextById"/, out: 'the page does not give LegList the legListPrices maps' },
  { file: 'src/pages/StrategyBuilderPage.vue', re: /legListPrices = computed\(\(\) => \(paper\.value \? paperLegListPrices\(data\.value\?\.legs, paperLegsOf\(paper\.value\.net, paper\.value\.book, paperBookFailed\.value\)\)/, out: 'legListPrices is not the book read (paperLegListPrices of paperLegsOf) for a paper trade' },
  { file: 'src/lib/chartCard.js', re: /paperBookLeg\(l, replyLegs, paperLegs\)/, out: 'paperLegListPrices does not use the one join (paperBookLeg)' },
  { file: 'src/lib/chartCard.js', re: /own = paperBookLeg\(byLegNo\.get/, out: 'compactRows does not use the one join (paperBookLeg)' },
  { file: 'src/lib/usePaperBookRead.js', re: /legPricesOf\(book, failed\)/, out: 'paperPnlBlock does not hand `failed` to legPricesOf (the Paper P&L panel rows would keep old figures)' },
]

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) walk(p, out)
    else if (/\.(vue|js|ts)$/.test(name)) out.push(p)
  }
  return out
}
const blank = (m) => m.replace(/[^\n]/g, ' ')
export const strip = (text) => text.replace(/\/\*[\s\S]*?\*\//g, blank).replace(/<!--[\s\S]*?-->/g, blank).replace(/^\s*\/\/.*$/gm, blank)
const files = () => Object.fromEntries(walk(SRC).map((p) => [relative(process.cwd(), p).split(sep).join('/'), strip(readFileSync(p, 'utf8'))]))

/** Problems of a {path: text} map; empty = guard green. */
export function problems(map) {
  const out = []
  const listed = new Set(READERS.map((r) => r.file))
  const hit = Object.keys(map).filter((f) => TOKENS.test(map[f]))
  for (const f of hit) if (!listed.has(f)) out.push(`unlisted reader of leg price / P&L: ${f}`)
  for (const f of listed) if (!hit.includes(f)) out.push(`stale entry (no hit): ${f}`)
  for (const [f, text] of Object.entries(map)) {
    if (/<ChartCard\b/.test(text) && !/:paper-legs=/.test(text)) out.push(`ChartCard used without :paper-legs: ${f}`)
  }
  // wiring (round 2): the page hands the book join (never null / a literal) and compactRows really uses what it is given
  const page = map['src/pages/StrategyBuilderPage.vue'] ?? ''
  if (!/:paper-legs="paper \? paperLegsOf\(paper\.net, paper\.book, paperBookFailed\) : null"/.test(page)) out.push('the page does not pass :paper-legs from paperLegsOf(paper.net, paper.book, paperBookFailed)')
  const lib = map['src/lib/chartCard.js'] ?? ''
  if (!/paperLegs\?\.get\(/.test(lib) || !/if \(!paperLegs\) return rows/.test(lib)) out.push('compactRows does not read paperLegs')
  const card = map['src/components/strategy/ChartCard.vue'] ?? ''
  if (!/compactRows\(props\.table,\s*props\.legs,\s*props\.paperLegs\)/.test(card)) out.push('ChartCard.vue does not hand props.paperLegs to compactRows')
  for (const w of WIRING) if (!w.re.test(map[w.file] ?? '')) out.push(w.out)
  for (const r of REMAINING) {
    if (!(map[r.file] ?? '').includes(r.text)) out.push(`remaining reader changed or gone (update the registry): ${r.file}`)
  }
  return out
}

describe('N-07 guard: one reader of a paper leg price / P&L', () => {
  it('the scan finds the expected files (D1: zero hits proves only the pattern failed)', () => {
    expect(Object.keys(files()).length).toBeGreaterThan(100)
    expect(Object.keys(files()).filter((f) => TOKENS.test(files()[f])).length).toBeGreaterThanOrEqual(READERS.length)
  })
  it('the real source has no third reader and the P&L Table is wired to the book read', () => {
    expect(problems(files())).toEqual([])
  })
  it('MUTATION: the pre-fix ChartCard (paperLegs not handed to compactRows) turns the guard red', () => {
    const map = files()
    const prefix = map['src/components/strategy/ChartCard.vue'].replace('compactRows(props.table, props.legs, props.paperLegs)', 'compactRows(props.table, props.legs)')
    expect(prefix).not.toBe(map['src/components/strategy/ChartCard.vue'])
    expect(problems({ ...map, 'src/components/strategy/ChartCard.vue': prefix })).toEqual(['ChartCard.vue does not hand props.paperLegs to compactRows'])
  })
  it('MUTATION: compactRows ignoring paperLegs, and the page passing :paper-legs=null, are red', () => {
    const map = files()
    const lib = map['src/lib/chartCard.js'].replace('paperLegs?.get(', 'new Map().get(')
    expect(problems({ ...map, 'src/lib/chartCard.js': lib })).toEqual(['compactRows does not read paperLegs'])
    const page = map['src/pages/StrategyBuilderPage.vue'].replace(/:paper-legs="[^"]*"/, ':paper-legs="null"')
    expect(problems({ ...map, 'src/pages/StrategyBuilderPage.vue': page })).toEqual(['the page does not pass :paper-legs from paperLegsOf(paper.net, paper.book, paperBookFailed)'])
  })
  it('the REMAINING registry lines are where it says (file:line)', () => {
    for (const r of REMAINING) expect(readFileSync(join(process.cwd(), r.file), 'utf8').split('\n')[r.line - 1]).toContain(r.text)
  })
  it('#744 MUTATION: each of the three readers going back to the reply turns the guard red', () => {
    const map = files()
    const mutate = (file, from, to) => {
      expect(map[file]).toMatch(from)
      return problems({ ...map, [file]: map[file].replace(from, to) })
    }
    // Full table back to the reply cells, in the card, the table and the row
    expect(mutate('src/components/strategy/ChartCard.vue', ':book-cells="fullBookCells"', '')).toEqual(['ChartCard.vue does not pass :book-cells to the Full table (StrategyTable)'])
    expect(mutate('src/components/strategy/StrategyLegRow.vue', 'bookCells?.[c.id] ?? cellText(row, c)', 'cellText(row, c)')).toEqual(['StrategyLegRow.vue does not print the book cell before the reply cell'])
    expect(mutate('src/components/strategy/StrategyTable.vue', ':book-cells="bookCells?.[row.row_id] ?? null"', '')).toEqual(['StrategyTable.vue does not hand its book cells to StrategyLegRow'])
    // leg list "now" price back to the reply maps
    expect(mutate('src/pages/StrategyBuilderPage.vue', ':ltp-by-id="legListPrices.ltpById"', ':ltp-by-id="ltpById"')).toEqual(['the page does not give LegList the legListPrices maps'])
    expect(mutate('src/pages/StrategyBuilderPage.vue', 'paperLegListPrices(data.value?.legs', 'paperLegListPrices(null')).toEqual(['legListPrices is not the book read (paperLegListPrices of paperLegsOf) for a paper trade'])
    // Paper P&L panel after a failed read back to the last figures
    expect(mutate('src/lib/usePaperBookRead.js', 'legPricesOf(book, failed)', 'legPricesOf(book)')).toEqual(['paperPnlBlock does not hand `failed` to legPricesOf (the Paper P&L panel rows would keep old figures)'])
    // a second join
    expect(mutate('src/lib/chartCard.js', 'own = paperBookLeg(byLegNo.get', 'own = paperLegs.get(byLegNo.get')).toEqual(['compactRows does not use the one join (paperBookLeg)'])
  })
  it('MUTATION: a page that mounts ChartCard without :paper-legs, and a new file reading ltp_text, are red', () => {
    const map = files()
    const page = map['src/pages/StrategyBuilderPage.vue'].replace(/:paper-legs="[^"]*"/, '')
    expect(problems({ ...map, 'src/pages/StrategyBuilderPage.vue': page })).toContain('ChartCard used without :paper-legs: src/pages/StrategyBuilderPage.vue')
    expect(problems({ ...map, 'src/components/strategy/NewLegView.vue': 'const x = leg.ltp_text' })).toEqual(['unlisted reader of leg price / P&L: src/components/strategy/NewLegView.vue'])
  })
})
