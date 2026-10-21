// W-121 fix round (REQ-073 AC-6, run-discipline C8): the structural guarantee that no screen offers Execute while the order
// path is off. ONE helper (lib/orderPath.js `useOrderPath`) decides; this scan fails when a .vue file under src renders a
// link or navigation to an order page (`/execute`, `execution/returned`) without going through it.
// Fails closed: an order-path mention that is not inside an element whose own opening tag carries `v-if` on the helper's
// ref (a router.push, a dynamic `:is`, a computed target) is a finding; a helper imported under an alias is a finding.
// Allow-list (named, not a forbidden list): the order screens themselves, reachable only through the guarded routes.
import { describe, it, expect } from 'vitest'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, resolve, sep } from 'node:path'

const SRC = resolve(__dirname, '../src')
// the order screens: a page may only be reached through routes.js (guarded below); the components only through the pages
const ORDER_SCREENS = new Set(['pages/ExecuteStrategyPage.vue', 'pages/ExecutionReturnedPage.vue'])
const ORDER_COMPONENT_DIR = 'components/execution/'
const ORDER_PATH_RE = /\/execute\b|execution\/returned/
const HELPER_IMPORT = /import\s*\{([^}]*)\}\s*from\s*'@\/lib\/orderPath'/
const HELPER_CALL = /const\s+orderPathOn\s*=\s*useOrderPath\(\)/

const posix = (p) => p.split(sep).join('/')
function walk(dir) {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n)
    return statSync(p).isDirectory() ? walk(p) : [p]
  })
}
const blank = (m) => m.replace(/[^\n]/g, ' ')
const noImports = (t) => t.replace(/^\s*import\s[^\n]*from\s*'[^']*'/gm, blank) // `@/lib/execute` is a module name, not a link
const stripComments = (t) => t.replace(/<!--[\s\S]*?-->/g, blank).replace(/\/\*[\s\S]*?\*\//g, blank).replace(/(^|[^:'"`])\/\/[^\n]*/g, (m, p) => p + blank(m.slice(p.length)))

/** Findings for one .vue source (relative path `rel`). Pure, so the mutation tests can feed it a scratch source. */
function findings(rel, source) {
  const name = posix(rel)
  if (ORDER_SCREENS.has(name) || name.startsWith(ORDER_COMPONENT_DIR)) return []
  const text = noImports(stripComments(source))
  const withImports = stripComments(source)
  const hits = [...text.matchAll(new RegExp(ORDER_PATH_RE, 'g'))]
  if (!hits.length) return []
  const out = []
  const imp = HELPER_IMPORT.exec(withImports)
  const names = imp ? imp[1].split(',').map((x) => x.trim()) : []
  if (!names.includes('useOrderPath') || names.some((n) => /\bas\b/.test(n))) out.push(`${name}: useOrderPath is not imported by its own name from '@/lib/orderPath'`)
  if (!HELPER_CALL.test(text)) out.push(`${name}: no 'const orderPathOn = useOrderPath()'`)
  for (const h of hits) {
    const open = text.lastIndexOf('<', h.index)
    const close = text.indexOf('>', h.index)
    const tag = open >= 0 && close > open && !text.slice(open + 1, close).includes('<') ? text.slice(open, close + 1) : null
    const ok = tag !== null && /^<(router-link|RouterLink|a)\b/.test(tag) && /\sv-if="[^"]*\borderPathOn\b[^"]*"/.test(tag)
    if (!ok) out.push(`${name}: an order path at offset ${h.index} is not inside a link element guarded by v-if="orderPathOn"`)
  }
  return out
}

describe('AC-6: no screen offers Execute except through useOrderPath', () => {
  const files = walk(SRC).filter((f) => f.endsWith('.vue')).map((f) => [relative(SRC, f), readFileSync(f, 'utf8')])

  it('scans every .vue file under src (not an empty scan)', () => {
    expect(files.length).toBeGreaterThan(20)
    expect(files.map(([r]) => posix(r))).toEqual(expect.arrayContaining([...ORDER_SCREENS, 'pages/MyStrategiesPage.vue', 'components/strategy/StrategyActions.vue']))
  })

  it('no .vue file renders an unguarded link to an order page', () => {
    expect(files.flatMap(([rel, src]) => findings(rel, src))).toEqual([])
  })

  it('exactly two screens mention an order page outside the order screens, and both are guarded', () => {
    const users = files
      .filter(([rel, src]) => !ORDER_SCREENS.has(posix(rel)) && !posix(rel).startsWith(ORDER_COMPONENT_DIR) && ORDER_PATH_RE.test(noImports(stripComments(src))))
      .map(([rel]) => posix(rel))
      .sort()
    expect(users).toEqual(['components/strategy/StrategyActions.vue', 'pages/MyStrategiesPage.vue'])
  })

  it('the order screens are reached only through routes.js, and both routes carry the guard', () => {
    const routes = readFileSync(join(SRC, 'router/routes.js'), 'utf8')
    expect(routes).toMatch(/import\s*\{\s*requireOrderPath\s*\}\s*from\s*'\.\.\/lib\/orderPath\.js'/)
    for (const page of ['ExecuteStrategyPage', 'ExecutionReturnedPage']) {
      const line = routes.split('\n').find((l) => l.includes(`${page}.vue`))
      expect(line, page).toMatch(/beforeEnter:\s*requireOrderPath/)
      const importers = walk(SRC)
        .filter((f) => /\.(vue|js)$/.test(f) && readFileSync(f, 'utf8').includes(`${page}.vue`))
        .map((f) => posix(relative(SRC, f)))
      expect(importers, page).toEqual(['router/routes.js'])
    }
  })

  it('mutation: a raw /execute router-link with no guard is a finding', () => {
    const scratch = '<template><router-link :to="`/strategy/${id}/execute`">Execute</router-link></template>'
    expect(findings('pages/Scratch.vue', scratch).length).toBeGreaterThan(0)
  })

  it('mutation: guarded by v-if but the helper aliased or not called is a finding; the right shape is clean', () => {
    const tpl = '<template><router-link v-if="orderPathOn" :to="\'/strategy/1/execute\'">x</router-link></template>'
    const head = (imp, call) => `<script setup>\n${imp}\n${call}\n</script>`
    const ok = ["import { useOrderPath } from '@/lib/orderPath'", 'const orderPathOn = useOrderPath()']
    expect(findings('pages/A.vue', head("import { useOrderPath as u } from '@/lib/orderPath'", ok[1]) + tpl).length).toBeGreaterThan(0)
    expect(findings('pages/B.vue', head(ok[0], '') + tpl).length).toBeGreaterThan(0)
    expect(findings('pages/C.vue', head(ok[0], ok[1]) + tpl)).toEqual([])
  })

  it('mutation: a router.push to an order page (not a guarded link element) fails closed', () => {
    const src = "<script setup>\nimport { useOrderPath } from '@/lib/orderPath'\nconst orderPathOn = useOrderPath()\nconst go = () => router.push('/strategy/1/execute')\n</script>"
    expect(findings('pages/D.vue', src).length).toBeGreaterThan(0)
  })
})
