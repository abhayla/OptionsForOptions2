// Guard (ADR-330 (3b), item P1): ONE info pop-up module. `showToast(` and `useToast` appear only in src/lib/infoPopup.js (the
// caller API) and src/composables/useToast.js (the list) and ToastHost.vue (the renderer). No other component renders its own
// pop-up LIST with role="alert" (an element carrying role="alert" and v-for on one line); a single role="alert" error line
// (a refusal under a form) is not a pop-up list and is not flagged.
// Bypasses (written here on purpose): a bad call split over two lines (`show` + `Toast(`) or built by string concatenation is not
// seen; a pop-up list whose v-for sits on another line than role="alert" is not seen. The mutation samples below prove the scan
// itself works on the shapes it claims to catch.
import { describe, it, expect } from 'vitest'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, sep } from 'node:path'

const SRC = join(__dirname, '..', 'src')
const toPosix = (p) => p.split(sep).join('/')

// the allowed homes of the toast list API, each with its reason
const TOAST_HOMES = {
  'lib/infoPopup.js': 'the one caller API: showInfo',
  'composables/useToast.js': 'the list itself',
  'components/layout/ToastHost.vue': 'renders the list',
}
// role="alert" + v-for exemptions: file -> reason. A stale entry (the file no longer has such a line) fails.
const ALERT_LIST_EXEMPT = {}

const TOAST_RE = /\bshowToast\(|\buseToast\b/
const ALERT_LIST_RE = /role="alert"[^\n]*v-for|v-for[^\n]*role="alert"/

/** Problems of one file's text: [{ file, rule }]. */
export function scanFile(rel, text) {
  const out = []
  if (!(rel in TOAST_HOMES) && TOAST_RE.test(text)) out.push({ file: rel, rule: 'toast API outside infoPopup.js / ToastHost.vue' })
  if (!(rel in ALERT_LIST_EXEMPT) && rel !== 'components/layout/ToastHost.vue' && ALERT_LIST_RE.test(text)) out.push({ file: rel, rule: 'own role="alert" pop-up list' })
  return out
}

function walk(dir) {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n)
    return statSync(p).isDirectory() ? walk(p) : /\.(vue|js)$/.test(n) ? [p] : []
  })
}
const files = walk(SRC).map((p) => ({ rel: toPosix(relative(SRC, p)), text: readFileSync(p, 'utf8') }))

describe('one pop-up module', () => {
  it('no file outside the allowed homes uses showToast( or useToast, and none renders its own role="alert" list', () => {
    const problems = files.flatMap((f) => scanFile(f.rel, f.text))
    expect(problems).toEqual([])
  })
  it('every allowed home exists and still uses the toast API (no stale home)', () => {
    for (const home of Object.keys(TOAST_HOMES)) {
      const f = files.find((x) => x.rel === home)
      expect(f, `${home} is missing`).toBeTruthy()
      expect(TOAST_RE.test(f.text) || /\btoasts\b/.test(f.text), `${home} no longer uses the toast list`).toBe(true)
    }
  })
  it('no stale role="alert" exemption', () => {
    for (const rel of Object.keys(ALERT_LIST_EXEMPT)) {
      const f = files.find((x) => x.rel === rel)
      expect(f && ALERT_LIST_RE.test(f.text), `${rel} no longer has such a list`).toBe(true)
    }
  })
  it('mutation: an in-memory bad file gives exactly one problem naming the file', () => {
    expect(scanFile('pages/Bad.vue', "const { showToast } = useToast()\nshowToast('x')")).toEqual([{ file: 'pages/Bad.vue', rule: 'toast API outside infoPopup.js / ToastHost.vue' }])
    expect(scanFile('pages/Bad2.vue', '<div v-for="t in list" :key="t" role="alert">{{ t }}</div>')).toEqual([{ file: 'pages/Bad2.vue', rule: 'own role="alert" pop-up list' }])
  })
  it('mutation: the allowed home gives none; a single role="alert" error line gives none', () => {
    expect(scanFile('lib/infoPopup.js', "useToast().showToast(text, 'info')")).toEqual([])
    expect(scanFile('pages/Ok.vue', '<p v-if="error" role="alert">{{ error }}</p>')).toEqual([])
  })
})
