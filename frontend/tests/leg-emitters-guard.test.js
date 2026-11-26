// Phase 5 guard (modular doors, 26 Nov 2026): ONE leg emitter. Every way of adding or moving a builder leg passes the one door
// (lib/legDoor.js admitLegs, reached through composables/useLegDoor.js: door.admit / door.admitMoved) before the leg list changes.
// Spec basis: ADR-319 (1) the one duplicate-leg door, ADR-328 (1) moves ask about the opposite side, ADR-329 the chain add goes through
// the door; plan docs/design/modular-doors-2026-11-25/PLAN-phases-3-8.md "Guard: frontend/tests/leg-emitters-guard.test.js".
//
// What counts as an emitter (a text scan of frontend/src, .vue .js .ts; comments are blanked, strings kept):
//   kind 'emit'   : `emit('update:legs'` - a component hands the page a new leg list.
//   kind 'assign' : `legs.value =` - the page's leg ref is assigned (a bare `legs`, not `x.legs` or `savedLegs`).
// Each hit is keyed by (file, enclosing function, kind), never by line. Every key must be on ALLOWED below with a reason; a hit not on
// it is a second emitter and fails; an entry with no hit is stale and fails ("shrink only"). An entry with `door` must also call the door
// inside that function (or, with `door: null`, be a named non-add path with its reason). Also: admitLegs is referenced only by the door
// files, each sanctioned caller really calls door.admit / door.admitMoved, and the scan finds a non-zero expected count (D1: zero hits
// proves only the pattern failed). Limits: text, not a parse; an emit through a renamed event or a ref reached by an alias is not seen.
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, sep } from 'node:path'
import { describe, it, expect } from 'vitest'

const SRC = join(process.cwd(), 'src')
const DOOR_FILES = ['src/lib/legDoor.js', 'src/composables/useLegDoor.js']
const PAGE = 'src/pages/StrategyBuilderPage.vue'
const PICKER = 'src/components/strategy/LegPicker.vue'
const READY = 'src/components/strategy/ReadyMadePanel.vue'

// Each: file, fn (enclosing function), kind, door (text that must appear in that function, or null), reason.
export const ALLOWED = [
  { file: PICKER, fn: 'save', kind: 'emit', door: 'admitHere(', reason: 'picker form Save / edit: admitHere -> door.admit before either emit (Increase and plain add)' },
  { file: PICKER, fn: 'remove', kind: 'emit', door: null, reason: 'removing a leg adds or moves nothing' },
  { file: PICKER, fn: 'resolveDuplicates', kind: 'emit', door: 'admitHere(', reason: 'picker Done / futures: admitHere -> door.admit, emits only the Increase result' },
  { file: PICKER, fn: 'addChosen', kind: 'emit', door: null, reason: 'only reached after resolveDuplicates (the door) has answered; asserted below' },
  { file: READY, fn: 'run', kind: 'emit', door: null, reason: 'ready-made replaces the whole list from the served shape (plan: keeps its flow)' },
  { file: PAGE, fn: 'nameLegsFrom', kind: 'assign', door: null, reason: 'names the same legs from the catalogue answer (same ids, contracts, actions, lots); adds and moves nothing' },
  { file: PAGE, fn: 'setLegs', kind: 'assign', door: null, reason: 'the page funnel: replaces the list for the non-add flows (remove, Undo, Exit, saved load, Compare, ready-made, plan) and the already-admitted picker and chain results' },
  { file: PAGE, fn: 'sendEdit', kind: 'assign', door: 'door.admitMoved(', reason: 'leg-edit reply: a move passes door.admitMoved before legs.value = landed; the read and include replies move no contract' },
]

// The sanctioned call sites of the door (each really calls it).
const DOOR_CALLERS = [
  { file: PAGE, text: 'door.admit(legs.value, incoming', what: 'the chain trip add (ADR-329)' },
  { file: PAGE, text: 'door.admitMoved(baseLegs, landed)', what: 'step, Shift, Width, Hedge moves (ADR-328 (1))' },
  { file: PICKER, text: 'door.admit(before, incoming', what: 'picker Done, futures, form Save, edit form' },
]
const DOOR_HOMES = [
  { file: DOOR_FILES[0], text: 'export async function admitLegs' },
  { file: DOOR_FILES[1], text: 'admitLegs(held, incoming' },
  { file: DOOR_FILES[1], text: 'async function admitMoved' },
]

const EMIT = /\bemit\(\s*['"]update:legs['"]/g
const ASSIGN = /(?<![\w.$])legs\.value\s*=(?!=)/g

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) walk(p, out)
    else if (/\.(vue|js|ts)$/.test(name)) out.push(p)
  }
  return out
}
const realFiles = () => Object.fromEntries(walk(SRC).map((p) => [`src/${relative(SRC, p).split(sep).join('/')}`, readFileSync(p, 'utf8')]))

const blank = (s) => (m) => m.replace(/[^\n]/g, ' ') + s
/** Comments blanked, line numbers kept; strings kept. */
export function strip(text, file) {
  let t = text.replace(/\/\*[\s\S]*?\*\//g, blank(''))
  if (file.endsWith('.vue')) t = t.replace(/<!--[\s\S]*?-->/g, blank(''))
  return t.split('\n').map((l) => l.replace(/(^|\s)\/\/.*$/, (m) => m.replace(/[^\s]/g, ' '))).join('\n')
}

const FN_START = [
  /^(\s*)(?:export\s+)?(?:async\s+)?function\s+(\w+)/,
  /^(\s*)(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*=>/,
]
/** Enclosing function of line `i`: the nearest line above that starts a function whose body still holds line i. */
function enclosing(lines, i) {
  for (let s = i; s >= 0; s--) {
    const m = FN_START.map((r) => r.exec(lines[s])).find(Boolean)
    if (!m) continue
    const indent = m[1].length
    let e = s
    if (!/=>\s*[^{\s]/.test(lines[s]) || /\{\s*$/.test(lines[s])) { // block body: ends at the first closing line at the same indent
      e = s + 1
      while (e < lines.length && !(lines[e].length - lines[e].trimStart().length <= indent && /^\s*\}/.test(lines[e]))) e++
    }
    if (i <= e) return { name: m[2], text: lines.slice(s, e + 1).join('\n') }
  }
  return null
}

/** Every emitter hit: { file, line, fn, kind, text (the enclosing function) }. */
export function scan(files) {
  const hits = []
  for (const [file, raw] of Object.entries(files)) {
    const lines = strip(raw, file).split('\n')
    lines.forEach((l, i) => {
      for (const [kind, re] of [['emit', EMIT], ['assign', ASSIGN]]) {
        re.lastIndex = 0
        if (!re.test(l)) continue
        const fn = enclosing(lines, i)
        hits.push({ file, line: i + 1, fn: fn?.name ?? '(top level)', kind, text: fn?.text ?? '' })
      }
    })
  }
  return hits
}

/** The problems of a file set: second emitters, stale allow-list entries, a caller that no longer calls the door, a stray admitLegs. */
export function problems(files, allowed = ALLOWED) {
  const out = []
  const hits = scan(files)
  const keyOf = (h) => `${h.file}::${h.fn}::${h.kind}`
  for (const h of hits) {
    const a = allowed.find((x) => keyOf(x) === keyOf(h))
    if (!a) out.push(`second leg emitter: ${h.file}:${h.line} (${h.fn}, ${h.kind}) adds or moves legs without the door; route it through door.admit / door.admitMoved`)
    else if (a.door && !h.text.includes(a.door)) out.push(`${h.file}:${h.line} (${h.fn}) is allowed only with ${a.door} in the function, and it is gone`)
  }
  for (const a of allowed) if (!hits.some((h) => keyOf(h) === keyOf(a))) out.push(`stale allow-list entry: ${keyOf(a)}`)
  for (const c of DOOR_CALLERS) if (!strip(files[c.file] ?? '', c.file).includes(c.text)) out.push(`${c.file} no longer calls the door for ${c.what} (${c.text})`)
  for (const c of DOOR_HOMES) if (!strip(files[c.file] ?? '', c.file).includes(c.text)) out.push(`door home ${c.file} lost ${c.text}`)
  for (const [file, raw] of Object.entries(files)) {
    if (!DOOR_FILES.includes(file) && /\badmitLegs\b/.test(strip(raw, file))) out.push(`${file} uses admitLegs directly: only legDoor.js and useLegDoor.js do; go through door.admit`)
  }
  return out
}

describe('the leg emitter guard (Phase 5, ADR-319 / ADR-328 / ADR-329)', () => {
  const files = realFiles()
  const hits = scan(files)

  it('the real source has no second leg emitter and no stale allow-list entry', () => {
    expect(problems(files)).toEqual([])
  })

  it('D1: the scan finds the expected emitters (a pattern that matches nothing proves nothing)', () => {
    expect(Object.keys(files).length).toBeGreaterThan(50)
    expect(hits.filter((h) => h.kind === 'emit').length).toBe(6) // ReadyMadePanel 1 + LegPicker 5 (save x2, remove, resolveDuplicates, addChosen)
    expect(hits.filter((h) => h.kind === 'assign').length).toBe(4)
    expect(new Set(hits.map((h) => `${h.file}::${h.fn}::${h.kind}`)).size).toBe(ALLOWED.length)
    expect(hits.every((h) => h.fn !== '(top level)')).toBe(true)
  })

  it('addChosen is reached only after resolveDuplicates (the door) answered', () => {
    const src = strip(files[PICKER], PICKER)
    expect(src).toMatch(/await resolveDuplicates\(/)
    expect(src).toMatch(/addChosen\(/)
  })

  it('a second emitter in a component is caught (mutations in memory)', () => {
    const picker = files[PICKER]
    const bad = picker + "\nfunction sneak(x) {\n  emit('update:legs', [...props.legs, x])\n}\n"
    expect(problems({ ...files, [PICKER]: bad })[0]).toMatch(/second leg emitter: .*LegPicker\.vue:\d+ \(sneak, emit\)/)
    const other = { ...files, 'src/components/strategy/Other.vue': "<script setup>\nconst go = () => emit('update:legs', [])\n</script>\n" }
    expect(problems(other)).toHaveLength(1)
    const assign = { ...files, 'src/pages/Other.vue': 'function f(n) {\n  legs.value = n\n}\n' }
    expect(problems(assign)[0]).toMatch(/Other\.vue:2 \(f, assign\)/)
  })

  it('a comment or a different ref is not an emitter; a stale entry, a dropped door call and a direct admitLegs fail', () => {
    const quiet = { ...files, 'src/x.js': "// emit('update:legs', a)\nconst savedLegs = {}\nsavedLegs.value = 1\nthis.legs.value = 2\nif (legs.value == 3) {}\n" }
    expect(problems(quiet)).toEqual([])
    expect(problems(files, [...ALLOWED, { file: PAGE, fn: 'gone', kind: 'emit', door: null, reason: 'x' }])).toEqual([`stale allow-list entry: ${PAGE}::gone::emit`])
    const noDoor = { ...files, [PAGE]: files[PAGE].replaceAll('door.admitMoved(', 'moveWithout(') }
    expect(problems(noDoor).some((p) => /allowed only with door\.admitMoved\(/.test(p))).toBe(true)
    expect(problems(noDoor).some((p) => /no longer calls the door/.test(p))).toBe(true)
    const direct = { ...files, 'src/lib/other.js': "import { admitLegs } from '@/lib/legDoor'\n" }
    expect(problems(direct)[0]).toMatch(/uses admitLegs directly/)
  })
})
