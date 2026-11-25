// Phase 8, guard G3 (modular doors, 25 Nov 2026): the browser screens go through ONE door each.
// Spec basis: none: the spec says nothing about repo guard tests (searched: guard, repo_scan, allow-list); kit C3 (a structural
// guarantee first, a detector second). Plan: docs/design/modular-doors-2026-11-25/PLAN-phases-3-8.md section 5.8, G3.
//
// Rules (a text scan of frontend/src, .vue .js .ts; comments are blanked, string literals are kept):
//   (1) the not-live strings (the texts exported by lib/priceState.js, and the same words typed again) appear as string literals
//       only in lib/priceState.js.
//   (2) a `.post(` to /paper/strategies/${...}/orders only in lib/tracking.js, function addToPaper.
//   (3) a `.get(` of the single book /paper/strategies/${id} only in lib/usePaperBookRead.js. The list read /paper/strategies and the
//       sub-resources (/triggers, /exit-risk, /armed-exits, /orders ...) are another reply and are out of scope by pattern.
//   (4) PLACEHOLDER, Phase 5 (Lane B): dup-increase / dup-separate only in DuplicateLegDialog.vue, sameContract only in lib/legDoor.js.
//       NOT implemented here; Lane B owns it (frontend/tests/leg-emitters-guard.test.js). Do not add it in this file.
//
// Exemptions are keyed by (file, enclosing function or const, matched text), never by line, each with a category and a reason.
// A stale exemption fails ("shrink only"). Limits (not claims): a URL held in a variable first, a client reached through an alias
// that is called with a computed path, and code built at run time are not seen. The scan reads text, it does not parse.
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, sep } from 'node:path'
import { describe, it, expect } from 'vitest'
import { PAUSED_TEXT, NOT_CONNECTED_TEXT, NOT_LIVE_EXIT, CHANGED_ELSEWHERE_EXIT } from '@/lib/priceState'

const SRC = join(process.cwd(), 'src')

// ---- the doors -------------------------------------------------------------------------------------------------------------
const PRICE_STATE_HOME = 'src/lib/priceState.js'
const TRACKING_HOME = { file: 'src/lib/tracking.js', fn: 'addToPaper' }
const BOOK_READ_HOME = 'src/lib/usePaperBookRead.js'

// The exported not-live texts, pinned here and checked against the real exports below (a new export fails the test that compares).
const NOT_LIVE_TEXTS = [PAUSED_TEXT, NOT_CONNECTED_TEXT, NOT_LIVE_EXIT, CHANGED_ELSEWHERE_EXIT]
// The same words typed again in another sentence (NO_TOTAL says "prices are not live" with other words around it).
const NOT_LIVE_WORDS = /prices (?:are )?not live|live prices are not connected|paper p&l paused|changed elsewhere\. reload/i

const CATEGORIES = ['own_process', 'display', 'real_path']

// Each: rule, file, fn (enclosing function or const), text (the matched text), category, reason.
export const EXEMPT = [
  {
    rule: 1, file: 'src/components/strategy/PaperStrategies.vue', fn: 'NO_TOTAL', text: 'No paper total yet: prices are not live',
    category: 'display', reason: 'same rule, other words: the compact card says there is no total yet (RESULTS Phase 2); not one of the exported paused texts',
  },
  {
    rule: 3, file: 'src/lib/paperDrafts.js', fn: 'readPaperBook', text: '/paper/strategies/${id}',
    category: 'own_process', reason: 'Drafts Mode entry read: its own 404 means "not a paper strategy, open the saved plan", which the shared reader does not model',
  },
  {
    rule: 3, file: 'src/components/live/LiveStrategyCard.vue', fn: 'rereadBook', text: '/paper/strategies/${props.strategy.id}',
    category: 'display', reason: 'D-06: the live card re-reads its own book every 5 s for its figures, with its own busy flag',
  },
]

// ---- the scan --------------------------------------------------------------------------------------------------------------
const blank = (m) => m.replace(/[^\n]/g, ' ')
/** The source with comments turned into spaces (newlines kept, so line numbers hold). Strings stay. */
function stripComments(src) {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, blank)
    .replace(/<!--[\s\S]*?-->/g, blank)
    .replace(/(^|[\s;,)}\]])\/\/[^\n]*/g, (m, pre) => pre + blank(m.slice(pre.length)))
}

const FN_DECL = /^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)/
const CONST_FN = /^\s*(?:export\s+)?(?:const|let)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>/
const CONST_LIT = /^\s*(?:export\s+)?const\s+([A-Za-z_$][\w$]*)\s*=\s*['"`]/
/** The nearest function declaration, arrow const or string const at or above the line; '<top>' when none. */
function enclosing(lines, line) {
  for (let i = line; i > 0; i--) {
    const m = FN_DECL.exec(lines[i]) || CONST_FN.exec(lines[i]) || CONST_LIT.exec(lines[i])
    if (m) return m[1]
  }
  return '<top>'
}

const POST_ORDERS = /\.post\(\s*(?:`[^`]*?\/paper\/strategies\/\$\{[^}]*\}\/orders\b[^`]*`|['"]\/paper\/strategies\/[^'"]*['"]\s*\+[^,)]*?\+\s*['"]\/orders\b)/g
const GET_BOOK = /\.get\(\s*(`\/paper\/strategies\/\$\{[^}]*\}`|['"]\/paper\/strategies\/['"]\s*\+\s*[^,)]+)\s*[,)]/g
const LITERAL = /'[^'\n]*'|"[^"\n]*"|`[^`]*`/g

/** Every hit of the three rules in one source: [{rule, fn, line, text}]. */
function hitsOf(src) {
  const code = stripComments(src)
  const lines = ['', ...code.split('\n')]
  const lineAt = (idx) => code.slice(0, idx).split('\n').length
  const out = []
  for (const m of code.matchAll(LITERAL)) {
    const body = m[0].slice(1, m[0].length - 1)
    if (NOT_LIVE_TEXTS.some((t) => body.includes(t)) || NOT_LIVE_WORDS.test(body)) {
      const line = lineAt(m.index)
      out.push({ rule: 1, line, fn: enclosing(lines, line), text: body })
    }
  }
  for (const m of code.matchAll(POST_ORDERS)) {
    const line = lineAt(m.index)
    out.push({ rule: 2, line, fn: enclosing(lines, line), text: m[0] })
  }
  for (const m of code.matchAll(GET_BOOK)) {
    const line = lineAt(m.index)
    out.push({ rule: 3, line, fn: enclosing(lines, line), text: m[1].replace(/^`|`$/g, '') })
  }
  return out
}

const OUTSIDE = {
  1: (file, line, fn) => `not-live string outside priceState: ${file}:${line} in ${fn}. Use the texts exported by lib/priceState.js, or add (file, fn, text) to EXEMPT with a category and reason.`,
  2: (file, line, fn) => `paper order POST outside addToPaper: ${file}:${line} in ${fn}. Use addToPaper in lib/tracking.js, or add (file, fn) to EXEMPT with a category and reason.`,
  3: (file, line, fn) => `paper book read outside usePaperBookRead: ${file}:${line} in ${fn}. Use lib/usePaperBookRead.js, or add (file, fn) to EXEMPT with a category and reason.`,
}
const WHAT = { 1: 'holds the text', 2: 'posts the orders', 3: 'reads the book' }

function allowedHome(rule, file, fn) {
  if (rule === 1) return file === PRICE_STATE_HOME
  if (rule === 2) return file === TRACKING_HOME.file && fn === TRACKING_HOME.fn
  return file === BOOK_READ_HOME
}

/** Pure: files is {repo-relative posix path: source}. Returns the list of problem sentences (empty = clean).
 *  `exempt` defaults to the real list; a test passes its own. */
export function problems(files, exempt = EXEMPT) {
  const out = []
  for (const e of exempt) {
    if (!CATEGORIES.includes(e.category) && !/^awaiting_phase_\d+$/.test(e.category)) out.push(`bad exemption category: ${e.file}::${e.fn} has "${e.category}"`)
    if (!e.reason || e.reason.length === 0) out.push(`bad exemption: ${e.file}::${e.fn} has no reason`)
  }
  const used = new Set()
  for (const [file, src] of Object.entries(files)) {
    if (typeof src !== 'string') { out.push(`unreadable source (fail closed): ${file}`); continue }
    for (const h of hitsOf(src)) {
      if (allowedHome(h.rule, file, h.fn)) continue
      const idx = exempt.findIndex((e) => e.rule === h.rule && e.file === file && e.fn === h.fn && e.text === h.text)
      if (idx >= 0) { used.add(idx); continue }
      out.push(OUTSIDE[h.rule](file, h.line, h.fn))
    }
  }
  exempt.forEach((e, idx) => {
    if (!used.has(idx)) out.push(`stale exemption: ${e.file}::${e.fn} no longer ${WHAT[e.rule]} "${e.text}"; delete the entry`)
  })
  return out
}

// ---- Rule (4): PLACEHOLDER (Phase 5, Lane B) --------------------------------------------------------------------------------
// dup-increase / dup-separate only in components/DuplicateLegDialog.vue; sameContract only in lib/legDoor.js. Not built here.

// ---- the real scan -----------------------------------------------------------------------------------------------------------
function walk(dir, acc = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) walk(p, acc)
    else if (/\.(vue|js|ts)$/.test(name)) acc.push(p)
  }
  return acc
}
const realFiles = () => {
  const files = {}
  for (const p of walk(SRC)) files[`src/${relative(SRC, p).split(sep).join('/')}`] = readFileSync(p, 'utf8')
  return files
}

describe('G3: one door per screen concern (real scan of src/)', () => {
  it('finds no not-live string, paper order POST or paper book read outside its door', () => {
    const files = realFiles()
    expect(Object.keys(files).length).toBeGreaterThan(100) // the scan really saw src/
    expect(problems(files)).toEqual([])
  })

  it('the pinned not-live texts are the exports of lib/priceState.js, and its home is in the scan', () => {
    const src = readFileSync(join(SRC, 'lib/priceState.js'), 'utf8')
    const exported = [...src.matchAll(/^export const [A-Z_]+ = '([^']*)'/gm)].map((m) => m[1])
    expect(exported.sort()).toEqual([...NOT_LIVE_TEXTS].sort())
  })

  it('every exemption has a known category and a reason', () => {
    for (const e of EXEMPT) {
      expect(CATEGORIES).toContain(e.category)
      expect(e.reason.length).toBeGreaterThan(20)
    }
  })
})
