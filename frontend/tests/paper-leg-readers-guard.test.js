// N-07 guard (26 Nov 2026; class D-41 of tests/one-source-d41.test.js): a paper trade's per-leg price / P&L has ONE reader on the builder page,
// lib/usePaperBookRead (legPricesOf / paperPnlBlock / paperLegsOf). Spec basis: ADR-328 (3), ADR-212, ADR-008.
// What is scanned (text of frontend/src, .vue .js .ts, comments blanked):
//   1. REGISTRY: every file that mentions a leg price / P&L field of a server reply (TOKENS) must be on READERS with its source and reason;
//      an unlisted file is a possible third reader and fails; a listed file with no hit is stale and fails ("shrink only").
//   2. WIRING: every <ChartCard in src passes :paper-legs, and ChartCard.vue hands props.paperLegs to compactRows (the P&L Table).
// KNOWN BYPASSES (not seen): a price read through a renamed field or a computed key; a reply object passed whole to a child that reads it
// there; a new file that reads a leg price under a token not in TOKENS; the Full table (StrategyTable), LegList "now" price, Advanced Details
// and Greeks still read the outcome reply on a paper trade (listed REMAINING below: each is registered with that reason, so a NEW one fails).
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
  { file: 'src/pages/StrategyBuilderPage.vue', source: BOOK, why: 'wires paperLegsOf / paperPnlBlock into the panels; its own ltp maps (ltpById, livePriceById, priceTextById) feed LegList/dialog = REMAINING outcome-reply readers' },
  { file: 'src/lib/legEdit.js', source: 'outcome reply', why: 'REMAINING: LegList "Price has moved ... now" text uses the reply ltp_display (deferred issue)' },
  { file: 'src/components/strategy/LegList.vue', source: 'outcome reply', why: 'REMAINING: same "now" price as legEdit.js' },
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
  { file: 'src/components/strategy/StrategyTable.vue', line: 54, text: '<StrategyLegRow v-for="row in table.rows"', why: 'Full table: every cell (LTP, entry, P&L) is the outcome reply row; deferred issue' },
  { file: 'src/components/strategy/AdvancedDetails.vue', line: 23, text: 'adv-bid', why: 'bid / ask per leg from the reply leg_quotes (not an LTP or P&L); listed for completeness' },
  { file: 'src/components/strategy/LegList.vue', line: 43, text: 'priceTextById', why: 'leg list "Price has moved ... now" text from the reply ltp_display; deferred issue' },
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
  if (!/paperLegs\.get\(/.test(lib) || !/if \(!paperLegs\) return rows/.test(lib)) out.push('compactRows does not read paperLegs')
  const card = map['src/components/strategy/ChartCard.vue'] ?? ''
  if (!/compactRows\(props\.table,\s*props\.legs,\s*props\.paperLegs\)/.test(card)) out.push('ChartCard.vue does not hand props.paperLegs to compactRows')
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
    const lib = map['src/lib/chartCard.js'].replace('paperLegs.get(', 'new Map().get(')
    expect(problems({ ...map, 'src/lib/chartCard.js': lib })).toEqual(['compactRows does not read paperLegs'])
    const page = map['src/pages/StrategyBuilderPage.vue'].replace(/:paper-legs="[^"]*"/, ':paper-legs="null"')
    expect(problems({ ...map, 'src/pages/StrategyBuilderPage.vue': page })).toEqual(['the page does not pass :paper-legs from paperLegsOf(paper.net, paper.book, paperBookFailed)'])
  })
  it('the REMAINING registry lines are where it says (file:line)', () => {
    for (const r of REMAINING) expect(readFileSync(join(process.cwd(), r.file), 'utf8').split('\n')[r.line - 1]).toContain(r.text)
  })
  it('MUTATION: a page that mounts ChartCard without :paper-legs, and a new file reading ltp_text, are red', () => {
    const map = files()
    const page = map['src/pages/StrategyBuilderPage.vue'].replace(/:paper-legs="[^"]*"/, '')
    expect(problems({ ...map, 'src/pages/StrategyBuilderPage.vue': page })).toContain('ChartCard used without :paper-legs: src/pages/StrategyBuilderPage.vue')
    expect(problems({ ...map, 'src/components/strategy/NewLegView.vue': 'const x = leg.ltp_text' })).toEqual(['unlisted reader of leg price / P&L: src/components/strategy/NewLegView.vue'])
  })
})
