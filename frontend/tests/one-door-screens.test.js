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
//   (4) one duplicate-leg question, one same-contract test (Phase 5, Lane B): the test ids dup-increase / dup-separate appear only in
//       components/strategy/DuplicateLegDialog.vue; the DEFINITION of sameContract (function, const or method) only in lib/legDoor.js.
//       Calls and imports of sameContract elsewhere are allowed: LegList.vue shows the D-60 duplicate warning by calling the door's
//       own export, which is reading the door, not a second copy of the test. A second definition is the drift this rule stops.
//
// Keys name functions, not sites: a second hit of the same text in an exempt function is not counted (F7).
// Exemptions are keyed by (file, enclosing function or const, matched text), never by line, each with a category and a reason.
// A stale exemption fails ("shrink only"). Limits (not claims): a URL held in a variable first, a client reached through an alias
// that is called with a computed path, and code built at run time are not seen. The scan reads text, it does not parse.
// Also seen since review round 1: not-live text between tags of a .vue <template> (rule 1), method shorthand as the enclosing
// function (`async leak() {` on one line), `fetch(` of the orders path with method POST (rule 2) and of the single book (rule 3),
// and `sameContract:` / `as sameContract` (rule 4). Not seen: a fetch whose options come from a variable or sit after a `)`,
// parameters of a method that span several lines (the enclosing name then falls back to the nearest function above), and
// a shorthand `{ sameContract }` re-export.
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, sep } from 'node:path'
import { describe, it, expect } from 'vitest'
import { PAUSED_TEXT, NOT_CONNECTED_TEXT, NOT_LIVE_EXIT, CHANGED_ELSEWHERE_EXIT } from '@/lib/priceState'

const SRC = join(process.cwd(), 'src')

// ---- the doors -------------------------------------------------------------------------------------------------------------
const PRICE_STATE_HOME = 'src/lib/priceState.js'
const TRACKING_HOME = { file: 'src/lib/tracking.js', fn: 'addToPaper' }
const BOOK_READ_HOME = 'src/lib/usePaperBookRead.js'
const DUP_DIALOG_HOME = 'src/components/strategy/DuplicateLegDialog.vue'
const LEG_DOOR_HOME = 'src/lib/legDoor.js'

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
// method shorthand in an object or class: `async leak() {`, `leak(x) {`, `static async leak(x) {`, `get x() {` (one line of parameters)
const METHOD = /^\s*(?:static\s+)?(?:async\s+)?(?:get\s+|set\s+)?\*?\s*([A-Za-z_$][\w$]*)\s*\([^()]*\)\s*\{/
const NOT_A_METHOD = new Set(['if', 'for', 'while', 'switch', 'catch', 'with', 'function', 'return'])
/** The nearest function declaration, arrow const or string const at or above the line; '<top>' when none. */
function enclosing(lines, line) {
  for (let i = line; i > 0; i--) {
    const m = FN_DECL.exec(lines[i]) || CONST_FN.exec(lines[i]) || CONST_LIT.exec(lines[i])
    if (m) return m[1]
    const meth = METHOD.exec(lines[i])
    if (meth && !NOT_A_METHOD.has(meth[1])) return meth[1]
  }
  return '<top>'
}

const POST_ORDERS = /\.post\(\s*(?:`[^`]*?\/paper\/strategies\/\$\{[^}]*\}\/orders\b[^`]*`|['"]\/paper\/strategies\/[^'"]*['"]\s*\+[^,)]*?\+\s*['"]\/orders\b)/g
const FETCH_POST_ORDERS = /\bfetch\(\s*`[^`]*?\/paper\/strategies\/\$\{[^}]*\}\/orders\b[^`]*`[^)]*?method\s*:\s*['"]POST['"]/gi
const FETCH_BOOK = /\bfetch\(\s*`[^`]*?\/paper\/strategies\/\$\{[^}]*\}`\s*[,)]/g
const GET_BOOK = /\.get\(\s*(`\/paper\/strategies\/\$\{[^}]*\}`|['"]\/paper\/strategies\/['"]\s*\+\s*[^,)]+)\s*[,)]/g
const DUP_ID = /\bdup-(?:increase|separate)\b/g
const SAME_CONTRACT_DEF = /(?:^|[{,])\s*sameContract\s*:|\b(?:function\s+sameContract\b|(?:const|let|var)\s+sameContract\b|sameContract\s*\([^)]*\)\s*\{|as\s+sameContract\b)/gm
const LITERAL = /'[^'\n]*'|"[^"\n]*"|`[^`]*`/g

/** Every hit of the four rules in one source: [{rule, fn, line, text}]. */
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
  const open = code.indexOf('<template'), close = code.lastIndexOf('</template>')
  if (open >= 0 && close > open) { // text between tags of a .vue template (comments are already blanked; {{ }} holds code, read as literals above)
    const region = code.slice(open, close)
    for (const m of region.matchAll(/>([^<>]+)</g)) {
      const body = m[1].replace(/\{\{[\s\S]*?\}\}/g, (x) => blank(x))
      if (NOT_LIVE_TEXTS.some((t) => body.includes(t)) || NOT_LIVE_WORDS.test(body)) {
        out.push({ rule: 1, line: lineAt(open + m.index + 1), fn: '<template>', text: m[1].trim() })
      }
    }
  }
  for (const m of code.matchAll(POST_ORDERS)) {
    const line = lineAt(m.index)
    out.push({ rule: 2, line, fn: enclosing(lines, line), text: m[0] })
  }
  for (const m of code.matchAll(FETCH_POST_ORDERS)) {
    const line = lineAt(m.index)
    out.push({ rule: 2, line, fn: enclosing(lines, line), text: m[0] })
  }
  for (const m of code.matchAll(FETCH_BOOK)) {
    const line = lineAt(m.index)
    out.push({ rule: 3, line, fn: enclosing(lines, line), text: m[0].replace(/^[^`]*`|`\s*[,)]$/g, '') })
  }
  for (const m of code.matchAll(GET_BOOK)) {
    const line = lineAt(m.index)
    out.push({ rule: 3, line, fn: enclosing(lines, line), text: m[1].replace(/^`|`$/g, '') })
  }
  for (const m of code.matchAll(DUP_ID)) {
    const line = lineAt(m.index)
    out.push({ rule: 4, line, fn: enclosing(lines, line), text: m[0], home: DUP_DIALOG_HOME, what: 'dup question id' })
  }
  for (const m of code.matchAll(SAME_CONTRACT_DEF)) {
    const line = lineAt(m.index)
    out.push({ rule: 4, line, fn: enclosing(lines, line), text: 'sameContract', home: LEG_DOOR_HOME, what: 'sameContract definition' })
  }
  return out
}

const OUTSIDE = {
  1: (file, line, fn) => `not-live string outside priceState: ${file}:${line} in ${fn}. Use the texts exported by lib/priceState.js, or add (file, fn, text) to EXEMPT with a category and reason.`,
  2: (file, line, fn) => `paper order POST outside addToPaper: ${file}:${line} in ${fn}. Use addToPaper in lib/tracking.js, or add (file, fn) to EXEMPT with a category and reason.`,
  3: (file, line, fn) => `paper book read outside usePaperBookRead: ${file}:${line} in ${fn}. Use lib/usePaperBookRead.js, or add (file, fn) to EXEMPT with a category and reason.`,
  4: (file, line, fn, h) => `${h.what} outside its door: ${file}:${line} in ${fn}. Use components/strategy/DuplicateLegDialog.vue for the dup-increase / dup-separate ids and lib/legDoor.js for sameContract, or add (file, fn, text) to EXEMPT with a category and reason.`,
}
const WHAT = { 1: 'holds the text', 2: 'posts the orders', 3: 'reads the book', 4: 'holds the leg-door text' }

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
      if (h.home ? file === h.home : allowedHome(h.rule, file, h.fn)) continue
      const idx = exempt.findIndex((e) => e.rule === h.rule && e.file === file && e.fn === h.fn && e.text === h.text)
      if (idx >= 0) { used.add(idx); continue }
      out.push(OUTSIDE[h.rule](file, h.line, h.fn, h))
    }
  }
  exempt.forEach((e, idx) => {
    if (!used.has(idx)) out.push(`stale exemption: ${e.file}::${e.fn} no longer ${WHAT[e.rule]} "${e.text}"; delete the entry`)
  })
  return out
}

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
  it('finds no not-live string, paper order POST, paper book read, duplicate-leg id or sameContract definition outside its door', () => {
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

// ---- mutation tests: in-memory samples, no disk writes -------------------------------------------------------------------------
const BAD_TEXT = "const MSG = 'Prices are not live; try again when they update'\n"
const BAD_POST = "async function sendIt(api, id) {\n  return api.post(`/paper/strategies/${id}/orders`, { orders: [] })\n}\n"
const BAD_GET = "async function loadIt(api, id) {\n  return (await api.get(`/paper/strategies/${id}`)).data\n}\n"

describe('G3 mutations: a sample outside the door is one problem, the same sample in its home is none', () => {
  it('rule 1: a not-live text in a screen is one problem; in priceState.js none', () => {
    const bad = problems({ 'src/components/Foo.vue': BAD_TEXT }, [])
    expect(bad).toHaveLength(1)
    expect(bad[0]).toContain('not-live string outside priceState: src/components/Foo.vue:1 in MSG')
    expect(problems({ 'src/lib/priceState.js': BAD_TEXT }, [])).toEqual([])
  })

  it('rule 1: each exported text and a retyped wording is caught', () => {
    for (const t of [...NOT_LIVE_TEXTS, 'Total: prices are not live']) {
      expect(problems({ 'src/pages/A.vue': `const x = "${t}"\n` }, [])).toHaveLength(1)
    }
  })

  it('rule 1: the same words in a comment are not a problem', () => {
    expect(problems({ 'src/pages/A.vue': "// prices are not live here\n/* Prices are not live; try again when they update */\nconst x = 1\n" }, [])).toEqual([])
  })

  it('rule 2: an orders POST outside addToPaper is one problem; inside addToPaper none; another function of tracking.js is one', () => {
    const bad = problems({ 'src/pages/Foo.vue': BAD_POST }, [])
    expect(bad).toHaveLength(1)
    expect(bad[0]).toContain('paper order POST outside addToPaper: src/pages/Foo.vue:2 in sendIt')
    const home = BAD_POST.replace('sendIt', 'addToPaper')
    expect(problems({ 'src/lib/tracking.js': home }, [])).toEqual([])
    expect(problems({ 'src/lib/tracking.js': BAD_POST }, [])).toHaveLength(1)
  })

  it('rule 2: a string-joined path is caught too, and a POST to another path is not', () => {
    expect(problems({ 'src/a.js': "api.post('/paper/strategies/' + id + '/orders', b)\n" }, [])).toHaveLength(1)
    expect(problems({ 'src/a.js': "api.post(`/paper/strategies/${id}/triggers`, b)\n" }, [])).toEqual([])
  })

  it('rule 3: a single-book read outside usePaperBookRead is one problem; in its home none', () => {
    const bad = problems({ 'src/pages/Foo.vue': BAD_GET }, [])
    expect(bad).toHaveLength(1)
    expect(bad[0]).toContain('paper book read outside usePaperBookRead: src/pages/Foo.vue:2 in loadIt')
    expect(problems({ 'src/lib/usePaperBookRead.js': BAD_GET }, [])).toEqual([])
  })

  it('rule 3: the list and the sub-resources are out of scope by pattern', () => {
    const ok = "api.get('/paper/strategies')\napi.get(`/paper/strategies/${id}/triggers`)\napi.get(`/paper/strategies/${id}/exit-risk`, {})\n"
    expect(problems({ 'src/a.js': ok }, [])).toEqual([])
  })

  it('an unreadable source fails closed', () => {
    expect(problems({ 'src/a.js': null }, [])).toHaveLength(1)
  })
})

describe('G3 mutations: exemptions', () => {
  const E = [{ rule: 3, file: 'src/lib/x.js', fn: 'readIt', text: '/paper/strategies/${id}', category: 'own_process', reason: 'a long enough reason to be read' }]
  const SITE = "export async function readIt(c, id) {\n  return (await c.get(`/paper/strategies/${id}`)).data\n}\n"

  it('an exempt site is clean; a different function in the same file is not', () => {
    expect(problems({ 'src/lib/x.js': SITE }, E)).toEqual([])
    expect(problems({ 'src/lib/x.js': SITE.replace('readIt', 'other') }, E)).toHaveLength(2) // the new site, and the entry now stale
  })

  it('a deleted exempt site is a stale exemption', () => {
    const out = problems({ 'src/lib/x.js': 'export const a = 1\n' }, E)
    expect(out).toEqual(['stale exemption: src/lib/x.js::readIt no longer reads the book "/paper/strategies/${id}"; delete the entry'])
  })

  it('a deleted exempt file is a stale exemption', () => {
    expect(problems({}, E)).toHaveLength(1)
  })

  it('an exemption with an unknown category or no reason is a problem', () => {
    expect(problems({ 'src/lib/x.js': SITE }, [{ ...E[0], category: 'whatever' }])).toHaveLength(1)
    expect(problems({ 'src/lib/x.js': SITE }, [{ ...E[0], reason: '' }])).toHaveLength(1)
  })

  it('the real exemptions each still exist on this head (a deleted one fails the real scan with "stale exemption")', () => {
    const files = realFiles()
    for (const e of EXEMPT) {
      const alone = problems({ [e.file]: files[e.file] ?? '' }, [e])
      expect(alone, `${e.file}::${e.fn}`).toEqual([])
    }
    const e = EXEMPT[0]
    expect(problems({ [e.file]: '' }, [e])[0]).toMatch(/^stale exemption: .*::NO_TOTAL no longer holds the text/)
  })
})

describe('G3 mutations: rule 4 (one duplicate-leg dialog, one sameContract)', () => {
  const BAD_ID = '<template>\n  <button data-testid="dup-increase">Increase</button>\n</template>\n'
  const BAD_DEF = 'export const sameContract = (a, b) => a.instrument_id === b.instrument_id\n'

  it('a dup-increase or dup-separate id outside the dialog is one problem; in the dialog none', () => {
    for (const id of ['dup-increase', 'dup-separate']) {
      const src = BAD_ID.replace('dup-increase', id)
      const bad = problems({ 'src/pages/StrategyBuilderPage.vue': src }, [])
      expect(bad).toHaveLength(1)
      expect(bad[0]).toContain('dup question id outside its door: src/pages/StrategyBuilderPage.vue:2')
      expect(problems({ [DUP_DIALOG_HOME]: src }, [])).toEqual([])
    }
  })

  it('a second definition of sameContract is one problem (function, const, method); in legDoor.js none', () => {
    const forms = [BAD_DEF, 'function sameContract(a, b) {\n  return a === b\n}\n', 'const o = {\n  sameContract(a, b) {\n    return a === b\n  },\n}\n']
    for (const src of forms) {
      const bad = problems({ 'src/components/strategy/LegList.vue': src }, [])
      expect(bad).toHaveLength(1)
      expect(bad[0]).toContain('sameContract definition outside its door: src/components/strategy/LegList.vue')
      expect(problems({ [LEG_DOOR_HOME]: src }, [])).toEqual([])
    }
  })

  it('calls, imports, other names and comments are not problems', () => {
    const ok = "import { sameContract } from '@/lib/legDoor'\nconst sameContractAs = (l, i) => legs.findIndex((o, k) => k !== i && sameContract(o, l))\n// const sameContract = 1; dup-increase\n"
    expect(problems({ 'src/components/strategy/LegList.vue': ok }, [])).toEqual([])
  })

  it('a stale rule 4 exemption is reported', () => {
    const E = [{ rule: 4, file: 'src/pages/A.vue', fn: 'a', text: 'dup-separate', category: 'own_process', reason: 'a long enough reason to be read' }]
    expect(problems({ 'src/pages/A.vue': 'const a = 1\n' }, E)).toEqual(['stale exemption: src/pages/A.vue::a no longer holds the leg-door text "dup-separate"; delete the entry'])
    expect(problems({ 'src/pages/A.vue': "const a = 'dup-separate'\n" }, E)).toEqual([])
  })

  it('the real homes hold what the rule guards (the scan is not vacuous)', () => {
    const files = realFiles()
    expect(files[DUP_DIALOG_HOME]).toMatch(/dup-increase/)
    expect(files[DUP_DIALOG_HOME]).toMatch(/dup-separate/)
    expect(files[LEG_DOOR_HOME]).toMatch(SAME_CONTRACT_DEF)
  })
})

describe('G3 mutations: review round 1 (template text, method shorthand, fetch, sameContract property and re-export)', () => {
  it('rule 1: a not-live text typed between tags of a .vue template is one problem; in priceState.js none; in a comment none', () => {
    const bad = problems({ 'src/pages/A.vue': '<template><p>Prices are not live</p></template>\n' }, [])
    expect(bad).toHaveLength(1)
    expect(bad[0]).toContain('not-live string outside priceState: src/pages/A.vue:1')
    expect(problems({ 'src/lib/priceState.js': '<template><p>Prices are not live</p></template>\n' }, [])).toEqual([])
    expect(problems({ 'src/pages/A.vue': '<template><!-- Prices are not live --><p>ok</p></template>\n' }, [])).toEqual([])
    expect(problems({ 'src/pages/A.vue': `<template>\n  <p>${PAUSED_TEXT}</p>\n</template>\n` }, [])).toHaveLength(1)
  })

  it('rule 1: a literal inside a mustache is one problem, not two', () => {
    expect(problems({ 'src/pages/A.vue': "<template><p>{{ 'Prices are not live' }}</p></template>\n" }, [])).toHaveLength(1)
  })

  it('rule 2: a POST in a method shorthand of tracking.js after addToPaper is not attributed to addToPaper', () => {
    const post = "api.post(`/paper/strategies/${id}/orders`, b)"
    const head = 'export async function addToPaper(api, id, b) {\n  return ' + post + '\n}\n'
    expect(problems({ 'src/lib/tracking.js': head }, [])).toEqual([])
    for (const m of ['async leak(api, id, b) {', 'leak(api, id, b) {', 'static async leak(api, id, b) {']) {
      const bad = problems({ 'src/lib/tracking.js': head + 'const o = {\n  ' + m + '\n    return ' + post + '\n  },\n}\n' }, [])
      expect(bad, m).toHaveLength(1)
      expect(bad[0]).toContain('in leak')
    }
  })

  it('rule 2: a fetch POST to the orders path is one problem; in addToPaper none; a fetch GET of it is not a POST', () => {
    const f = "export async function sendIt(id) {\n  return fetch(`/paper/strategies/${id}/orders`, { method: 'POST', body: '{}' })\n}\n"
    expect(problems({ 'src/pages/A.vue': f }, [])).toHaveLength(1)
    expect(problems({ 'src/lib/tracking.js': f.replace('sendIt', 'addToPaper') }, [])).toEqual([])
    expect(problems({ 'src/a.js': "fetch(`/paper/strategies/${id}/orders`)\n" }, [])).toEqual([])
  })

  it('rule 3: a fetch of the single book is one problem; the list and sub-resources are not', () => {
    expect(problems({ 'src/a.js': "const r = await fetch(`/paper/strategies/${id}`)\n" }, [])).toHaveLength(1)
    expect(problems({ 'src/lib/usePaperBookRead.js': "const r = await fetch(`/paper/strategies/${id}`)\n" }, [])).toEqual([])
    expect(problems({ 'src/a.js': "fetch('/paper/strategies')\nfetch(`/paper/strategies/${id}/triggers`)\n" }, [])).toEqual([])
  })

  it('rule 4: a property definition and a re-export of sameContract are one problem each; a ternary and a call are not', () => {
    for (const src of ['const o = { sameContract: (a, b) => a === b }\n', 'const o = {\n  sameContract: (a, b) => a === b,\n}\n',
      'function s(a, b) { return a === b }\nexport { s as sameContract }\n']) {
      const bad = problems({ 'src/components/strategy/LegList.vue': src }, [])
      expect(bad, src).toHaveLength(1)
      expect(problems({ [LEG_DOOR_HOME]: src }, [])).toEqual([])
    }
    expect(problems({ 'src/a.js': 'const f = ok ? sameContract : other\nconst g = sameContract(a, b)\n' }, [])).toEqual([])
  })
})

describe('G3: the Lane B emitter guard', () => {
  const HERE = join(process.cwd(), 'tests')
  const include = () => /include:\s*\[([^\]]*)\]/.exec(readFileSync(join(process.cwd(), 'vite.config.js'), 'utf8'))?.[1] ?? ''

  it('vitest collects tests/*.test.js (the include pattern of vite.config.js)', () => {
    expect(include()).toContain("'tests/**/*.{test,spec}.{js,ts}'")
    expect(readdirSync(HERE)).toContain('one-door-screens.test.js')
  })

  it('frontend/tests/leg-emitters-guard.test.js exists (it matches the include pattern)', () => {
    expect(readdirSync(HERE)).toContain('leg-emitters-guard.test.js')
  })
})

// Rule 5 (ADR-330 (10), Q2 Chunk B): the one Positions list shows real rows read-only and starts no order. PositionsPage.vue and
// PositionsTotals.vue contain no addToPaper, no `.post(` and no `/orders` (comments blanked; strings kept). The 'Real (Zerodha
// order)' literal part of this rule is the second half, further down.
//
// KNOWN BYPASSES of rule 5 (both halves; a text scan, not a parser; written down, deliberately NOT chased):
//   - only PositionsPage.vue and every file under src/components/positions/ are scanned for orders; a Positions feature built in
//     another directory is not seen;
//   - the order patterns are `addToPaper`, `.post(` and `/orders`: `api.put(`, `api['post'](`, `.post (` (space) and `api.request(`
//     are not seen;
//   - the word 'Real (Zerodha order)' is matched as one literal: a split string ('Real (Zerodha ' + 'order)'), a non-breaking space or
//     another spelling is not seen; the real exit-button check is by name (ExitButton, usePaperExit, PaperConfirmDialog, an exit test id).
const POSITIONS_DIR = join(process.cwd(), 'src/components/positions')
const ONE_LIST_FILES = ['src/pages/PositionsPage.vue', ...readdirSync(POSITIONS_DIR).filter((n) => /\.(vue|js|ts)$/.test(n)).map((n) => `src/components/positions/${n}`)]
const ONE_LIST_BANNED = [/addToPaper/, /\.post\(/, /\/orders/]
const oneListProblems = (sources) => Object.entries(sources).flatMap(([file, src]) =>
  ONE_LIST_BANNED.filter((re) => re.test(stripComments(src))).map((re) => `${file}: ${re}`))
describe('G3 rule 5: the one Positions list starts no order', () => {
  const real = Object.fromEntries(ONE_LIST_FILES.map((f) => [f, readFileSync(join(process.cwd(), f), 'utf8')]))
  it('PositionsPage.vue and PositionsTotals.vue contain no addToPaper, .post( or /orders', () => {
    expect(oneListProblems(real)).toEqual([])
  })
  it('mutation: a scratch copy with .post(, addToPaper or /orders is one problem each; a comment is none', () => {
    const base = real['src/pages/PositionsPage.vue']
    expect(oneListProblems({ a: base + "\napi.post('/x')" })).toHaveLength(1)
    expect(oneListProblems({ a: base + '\naddToPaper(api)' })).toHaveLength(1)
    expect(oneListProblems({ a: base + '\nconst u = `/paper/strategies/1/orders`' })).toHaveLength(1)
    expect(oneListProblems({ a: base + '\n// api.post(\n' })).toEqual([])
  })
})

// Rule 5, second half (ADR-330 (10), Chunk C): the exit-title word 'Real (Zerodha order)' is spelled in ONE place, lib/paperDrafts.js
// (positionKindWord). A second copy in any other src file is a second door. Comments are not counted. No real exit button exists
// on the Positions page (ADR-281): it imports no ExitButton, usePaperExit or PaperConfirmDialog.
const KIND_WORD_HOME = 'src/lib/paperDrafts.js'
const KIND_WORD = /Real \(Zerodha order\)/
const kindWordProblems = (sources) => Object.entries(sources)
  .filter(([file, src]) => file !== KIND_WORD_HOME && KIND_WORD.test(stripComments(src))).map(([file]) => `${file}: holds the real exit word`)
const REAL_EXIT_BANNED = [/\bExitButton\b/, /\busePaperExit\b/, /\bPaperConfirmDialog\b/, /data-testid="[^"]*exit[^"]*"/i]
describe('G3 rule 5 (exit title): one spelling of Real (Zerodha order); no real exit on Positions', () => {
  it('the literal appears only in lib/paperDrafts.js, and is there (not vacuous)', () => {
    const files = realFiles()
    expect(kindWordProblems(files)).toEqual([])
    expect(KIND_WORD.test(stripComments(files[KIND_WORD_HOME]))).toBe(true)
  })
  it('mutation: the literal in another src file is one problem; in a comment or in the home none', () => {
    const files = realFiles()
    const scratch = { ...files, 'src/pages/Scratch.vue': "const t = 'Exit Real (Zerodha order) positions'\n" }
    expect(kindWordProblems(scratch)).toEqual(['src/pages/Scratch.vue: holds the real exit word'])
    expect(kindWordProblems({ ...files, 'src/pages/Scratch.vue': '// Real (Zerodha order)\n' })).toEqual([])
    expect(kindWordProblems({ [KIND_WORD_HOME]: "const w = 'Real (Zerodha order)'" })).toEqual([])
  })
  it('the Positions page and its totals render no real exit button or exit dialog', () => {
    const files = realFiles()
    expect(ONE_LIST_FILES).toContain('src/components/positions/PositionsTotals.vue')
    for (const f of ONE_LIST_FILES) {
      const src = stripComments(files[f])
      expect(REAL_EXIT_BANNED.filter((re) => re.test(src)), f).toEqual([])
    }
  })
  it('mutation: an ExitButton in a scratch copy of the Positions page is caught', () => {
    const src = stripComments(realFiles()['src/pages/PositionsPage.vue'] + '\n<ExitButton />')
    expect(REAL_EXIT_BANNED.some((re) => re.test(src))).toBe(true)
  })
})
